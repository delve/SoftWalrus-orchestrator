"""Developer node.

Dispatches the develop or fix slash command with the layer's handoff_prefix
as $ARGUMENTS[0].
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path

from ..claude import run_agent
from ..commands import render_command
from ..handoffs import developer_notes_path
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
    is_fix_pass = layer.get("status") == "fixing"

    command_name = "fix" if is_fix_pass else "develop"
    prompt = render_command(project_dir, command_name, arguments=[layer["handoff_prefix"]])

    result = await run_agent(
        prompt=prompt,
        project_dir=project_dir,
        agent_name="developer",
    )

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
            node_result["output_summary"] = f"fix pass complete for {layer['name']}"
        else:
            notes = developer_notes_path(project_dir, layer["handoff_prefix"])
            if not notes.exists() or notes.stat().st_size == 0:
                node_result["success"] = False
                node_result["error"] = (
                    f"agent reported success but {notes.name} is missing or empty"
                )
                node_result["output_summary"] = "missing developer notes"
                new_layer["status"] = "halted"
            else:
                node_result["output_summary"] = f"develop pass complete for {layer['name']}"

    new_layers = dict(layers)
    new_layers[layer_id] = new_layer

    return {
        "layers": new_layers,
        "last_result": node_result,
        "total_cost_usd": state.get("total_cost_usd", 0.0) + result.total_cost_usd,
    }
