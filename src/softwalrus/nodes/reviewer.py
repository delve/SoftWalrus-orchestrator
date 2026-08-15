"""Reviewer node.

Reads artifacts.findings from the reviewer's JSON to determine convergence
and to apply SoftWalrus-imposed halt policies:

  - Convergence: findings.open == 0 -> layer status becomes 'converged'.
  - Regression threshold: findings.regressionCount (if present) >= 6 -> halt
    with SoftWalrus-authored message.
  - Max rounds: rounds > MAX_REVIEW_ROUNDS -> halt with SoftWalrus-authored
    message.

Everything else in the reviewer's artifacts is opaque to SoftWalrus and
gets persisted verbatim as an InvocationRecord.
"""

from __future__ import annotations

import copy
from pathlib import Path

from ..handoffs import code_review_json_path
from ..state import PipelineState
from ._common import invoke_and_validate

MAX_REVIEW_ROUNDS = 8
REGRESSION_THRESHOLD = 6


async def reviewer_node(state: PipelineState, project_dir: Path) -> dict:
    layer_id = state.get("current_layer_id")
    layers = state.get("layers", {})

    if not layer_id or layer_id not in layers:
        halt = f"reviewer called with unknown current_layer_id={layer_id!r}"
        return {
            "last_result": {
                "agent": "code-reviewer", "success": False,
                "error": halt, "output_summary": halt,
                "cost_usd": 0.0, "session_id": None,
            },
        }

    layer = layers[layer_id]
    prefix = layer["handoff_prefix"]
    prior_rounds = layer.get("rounds", 0)

    # Max rounds check happens BEFORE invocation so we don't burn tokens on a
    # round we've decided to reject anyway.
    if prior_rounds >= MAX_REVIEW_ROUNDS:
        halt_msg = f"Max review rounds reached ({MAX_REVIEW_ROUNDS})"
        new_layer = copy.deepcopy(layer)
        new_layer["status"] = "halted"
        new_layers = dict(layers)
        new_layers[layer_id] = new_layer
        return {
            "layers": new_layers,
            "last_result": {
                "agent": "code-reviewer", "success": False,
                "error": halt_msg, "output_summary": halt_msg,
                "cost_usd": 0.0, "session_id": None,
            },
        }

    outcome = await invoke_and_validate(
        project_dir=project_dir,
        node_kind="reviewer",
        layer_id=layer_id,
        round_number=prior_rounds + 1,
        agent_name="code-reviewer",
        command_name="codereview",
        command_arguments=[prefix],
        output_path=code_review_json_path(project_dir, prefix),
    )

    new_layer = copy.deepcopy(layer)
    new_layer["cost_usd"] = new_layer.get("cost_usd", 0.0) + outcome.claude.total_cost_usd
    new_layer["rounds"] = prior_rounds + 1

    node_result = outcome.node_result
    invocation_record = outcome.invocation_record

    if not outcome.validated.ok:
        new_layer["status"] = "halted"
    else:
        findings = outcome.validated.artifacts.get("findings", {})
        open_count = findings.get("open", 0)
        regression_count = findings.get("regressionCount")  # may be missing

        # Convergence check
        if open_count == 0:
            new_layer["status"] = "converged"
        else:
            new_layer["status"] = "fixing"

        # SoftWalrus-imposed halt: regressionCount threshold.
        # This OVERRIDES the fixing status set above; a regression halt trumps
        # continuing the loop.
        if regression_count is not None and regression_count >= REGRESSION_THRESHOLD:
            halt_msg = (
                f"Regressions exceed threshold "
                f"({regression_count} >= {REGRESSION_THRESHOLD})"
            )
            new_layer["status"] = "halted"
            # Rewrite the node_result and invocation_record with the
            # SoftWalrus-authored halt so downstream error surfacing is correct.
            node_result = dict(node_result)
            node_result["success"] = False
            node_result["error"] = halt_msg
            node_result["output_summary"] = halt_msg
            invocation_record = dict(invocation_record)
            invocation_record["ok"] = False
            invocation_record["halt_message"] = halt_msg

    new_layers = dict(layers)
    new_layers[layer_id] = new_layer

    prior_invocations = state.get("invocations", [])
    prior_cost = state.get("total_cost_usd", 0.0)

    return {
        "layers": new_layers,
        "last_result": node_result,
        "invocations": prior_invocations + [invocation_record],
        "total_cost_usd": prior_cost + outcome.claude.total_cost_usd,
    }
