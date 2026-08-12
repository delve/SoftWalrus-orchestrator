"""Reviewer node.

Runs the code-reviewer sub-agent for the current layer, then reads the
review handoff to detect convergence and regressions. Updates the
layer status based on what it finds.

Fresh session per round (session reuse was removed in the old orchestrator
after we discovered per-round cost was compounding).
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path

from ..claude import run_agent
from ..handoffs import (
    code_review_path,
    detect_regression,
    is_converged,
    parse_findings,
)
from ..state import NodeResult, PipelineState

logger = logging.getLogger(__name__)

# Hard cap to prevent runaway review loops. Overridable later via config.
MAX_REVIEW_ROUNDS = 8


async def reviewer_node(state: PipelineState, project_dir: Path) -> dict:
    layer_id = state.get("current_layer_id")
    layers = state.get("layers", {})
    if not layer_id or layer_id not in layers:
        return {
            "last_result": NodeResult(
                agent="code-reviewer", success=False,
                error=f"current_layer_id {layer_id!r} not found in state.layers",
                output_summary="misrouted reviewer call", cost_usd=0.0, session_id=None,
            ),
        }
    layer = layers[layer_id]
    prefix = layer["handoff_prefix"]
    prior_rounds = layer.get("rounds", 0)

    # Prevent runaway
    if prior_rounds >= MAX_REVIEW_ROUNDS:
        new_layer = copy.deepcopy(layer)
        new_layer["status"] = "halted"
        new_layers = dict(layers)
        new_layers[layer_id] = new_layer
        return {
            "layers": new_layers,
            "last_result": NodeResult(
                agent="code-reviewer", success=False,
                error=f"max review rounds ({MAX_REVIEW_ROUNDS}) reached",
                output_summary="halted: max rounds", cost_usd=0.0, session_id=None,
            ),
        }

    prompt = (
        f"Session handoff file: `./handoffs/code-review-{prefix}.md`\n\n"
        f"Review the most recent developer session for the {layer['name']}, "
        f"then report findings in the handoff file above. Use that exact "
        f"filename; do not invent a different one.\n\n"
        f"Developer session notes are at "
        f"`./handoffs/developer-notes-{prefix}.md`. Read those before "
        f"beginning the review.\n\n"
        f"When a finding is resolved, update the issue state in the handoff. "
        f"If there is a regression, update the existing issue state to `Open` "
        f"and add a regression note in the summary rather than adding a new "
        f"issue. Treat the handoff file as a running document for multiple "
        f"passes, appending new findings and updating previous findings as "
        f"necessary."
    )

    result = await run_agent(
        prompt=prompt,
        project_dir=project_dir,
        agent_name="code-reviewer",
    )

    new_layer = copy.deepcopy(layer)
    new_layer["cost_usd"] = new_layer.get("cost_usd", 0.0) + result.total_cost_usd
    new_layer["rounds"] = prior_rounds + 1

    node_result: NodeResult = {
        "agent": "code-reviewer",
        "session_id": result.session_id,
        "cost_usd": result.total_cost_usd,
        "success": result.success,
        "error": result.raw_error,
        "output_summary": "",
    }

    if not result.success:
        node_result["output_summary"] = f"agent failed: subtype={result.subtype}"
        new_layer["status"] = "halted"
        new_layers = dict(layers)
        new_layers[layer_id] = new_layer
        return {
            "layers": new_layers,
            "last_result": node_result,
            "total_cost_usd": state.get("total_cost_usd", 0.0) + result.total_cost_usd,
        }

    review_path = code_review_path(project_dir, prefix)
    if not review_path.exists():
        node_result["success"] = False
        node_result["error"] = f"agent reported success but {review_path.name} is missing"
        node_result["output_summary"] = "missing review handoff"
        new_layer["status"] = "halted"
    else:
        findings = parse_findings(review_path)
        if not findings:
            node_result["success"] = False
            node_result["error"] = "review handoff contains no parseable findings"
            node_result["output_summary"] = "no findings parsed"
            new_layer["status"] = "halted"
        else:
            open_count = sum(1 for f in findings if f.state == "Open")
            fixed_count = sum(1 for f in findings if f.state == "Fixed")
            terminal_count = len(findings) - open_count - fixed_count

            if is_converged(findings):
                new_layer["status"] = "converged"
                node_result["output_summary"] = (
                    f"round {new_layer['rounds']}: converged "
                    f"({len(findings)} findings terminal)"
                )
            else:
                # Detect stall via regression tracking
                regression_counts = dict(new_layer.get("regression_counts", {}))
                history = dict(new_layer.get("finding_state_history", {}))
                stalled_id = detect_regression(findings, history, regression_counts)
                new_layer["regression_counts"] = regression_counts
                new_layer["finding_state_history"] = history
                if stalled_id:
                    new_layer["status"] = "halted"
                    node_result["success"] = False
                    node_result["error"] = (
                        f"finding {stalled_id} regressed multiple times; stall detected"
                    )
                    node_result["output_summary"] = (
                        f"round {new_layer['rounds']}: STALLED on {stalled_id}"
                    )
                else:
                    # Not converged, not stalled -> fix pass next
                    new_layer["status"] = "fixing"
                    node_result["output_summary"] = (
                        f"round {new_layer['rounds']}: {open_count} Open, "
                        f"{fixed_count} Fixed, {terminal_count} terminal"
                    )

    new_layers = dict(layers)
    new_layers[layer_id] = new_layer

    return {
        "layers": new_layers,
        "last_result": node_result,
        "total_cost_usd": state.get("total_cost_usd", 0.0) + result.total_cost_usd,
    }
