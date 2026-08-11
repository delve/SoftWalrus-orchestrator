"""Developer node.

Handles both the initial develop pass for a layer and subsequent fix
passes for the same layer. The differentiator is layer.status:
- 'pending' or 'developing' -> initial develop pass
- 'fixing' -> fix pass against review findings

The layer being processed is read from state.current_layer_id and the
detail from state.layers[current_layer_id].
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path

from ..claude import run_agent
from ..handoffs import (
    code_review_path,
    developer_notes_path,
)
from ..state import NodeResult, PipelineState

logger = logging.getLogger(__name__)


async def developer_node(state: PipelineState, project_dir: Path) -> dict:
    layer_id = state.get("current_layer_id")
    layers = state.get("layers", {})
    if not layer_id or layer_id not in layers:
        return {
            "last_result": NodeResult(
                agent="developer", success=False,
                error=f"current_layer_id {layer_id!r} not found in state.layers",
                output_summary="misrouted developer call", cost_usd=0.0, session_id=None,
            ),
        }
    layer = layers[layer_id]
    prefix = layer["handoff_prefix"]
    is_fix_pass = layer.get("status") == "fixing"

    if is_fix_pass:
        prompt = (
            f"Read the review findings for the {layer['name']} at "
            f"./handoffs/code-review-{prefix}.md.\n\n"
            "Review open issues in the handoff file and adjust code in the "
            f"{layer['name']} to correct them, or document your reasons for "
            "not correcting the finding in the handoff file. Add unit tests "
            "to cover any additional code created by the changes.\n\n"
            "Treat the handoff file as a running document for multiple passes, "
            "updating open issues as necessary."
        )
    else:
        prompt = (
            f"Implement the {layer['name']} for the current work item.\n\n"
            f"Scope for this layer: {layer['scope']}\n\n"
            "Read the current architecture at ./handoffs/architecture.md and "
            "the architecture plan at ./handoffs/architecture.json to "
            "understand context. Write your session notes to "
            f"./handoffs/developer-notes-{prefix}.md"
        )

    result = await run_agent(
        prompt=prompt,
        project_dir=project_dir,
        agent_name="developer",
    )

    # Build updated layer status
    new_layer = copy.deepcopy(layer)
    new_layer["cost_usd"] = new_layer.get("cost_usd", 0.0) + result.total_cost_usd

    node_result: NodeResult = {
        "agent": "developer",
        "session_id": result.session_id,
        "cost_usd": result.total_cost_usd,
        "success": result.success,
        "error": result.raw_error,
        "output_summary": "",
    }

    if not result.success:
        node_result["output_summary"] = f"agent failed: subtype={result.subtype}"
        new_layer["status"] = "halted"
    else:
        if is_fix_pass:
            # Fix pass done; the review handoff should already exist. Nothing
            # to verify on disk beyond what the review node will check next.
            node_result["output_summary"] = f"fix pass complete for {layer['name']}"
            # status transitions to 'reviewing' happen when the review node runs
        else:
            # Initial develop pass; verify the notes file was written.
            notes = developer_notes_path(project_dir, prefix)
            if not notes.exists() or notes.stat().st_size == 0:
                node_result["success"] = False
                node_result["error"] = (
                    f"agent reported success but {notes.name} is missing or empty"
                )
                node_result["output_summary"] = "missing developer notes"
                new_layer["status"] = "halted"
            else:
                node_result["output_summary"] = f"develop pass complete for {layer['name']}"
                # status transitions to 'reviewing' happen when the review node runs

    new_layers = dict(layers)
    new_layers[layer_id] = new_layer

    return {
        "layers": new_layers,
        "last_result": node_result,
        "total_cost_usd": state.get("total_cost_usd", 0.0) + result.total_cost_usd,
    }
