"""Developer node — handles both initial develop pass and fix passes.

`is_fix_pass` is determined by the layer's current status. Both cases write
to the same `develop-{prefix}.json` file (the node overwrites its own
previous output; the reviewer's file is untouched).
"""

from __future__ import annotations

import copy
from pathlib import Path

from ..handoffs import develop_json_path
from ..state import PipelineState
from ._common import invoke_and_validate


async def developer_node(state: PipelineState, project_dir: Path) -> dict:
    layer_id = state.get("current_layer_id")
    layers = state.get("layers", {})

    if not layer_id or layer_id not in layers:
        # Should never happen if the router is behaving; surface as a halt.
        halt = f"developer called with unknown current_layer_id={layer_id!r}"
        return {
            "last_result": {
                "agent": "developer", "success": False,
                "error": halt, "output_summary": halt,
                "cost_usd": 0.0, "session_id": None,
            },
        }

    layer = layers[layer_id]
    prefix = layer["handoff_prefix"]
    is_fix_pass = layer.get("status") == "fixing"
    command_name = "fix" if is_fix_pass else "develop"

    outcome = await invoke_and_validate(
        project_dir=project_dir,
        node_kind="developer",
        layer_id=layer_id,
        round_number=layer.get("rounds", 0),
        agent_name="developer",
        command_name=command_name,
        command_arguments=[prefix],
        output_path=develop_json_path(project_dir, prefix),
    )

    new_layer = copy.deepcopy(layer)
    new_layer["cost_usd"] = new_layer.get("cost_usd", 0.0) + outcome.claude.total_cost_usd
    if not outcome.validated.ok:
        new_layer["status"] = "halted"

    new_layers = dict(layers)
    new_layers[layer_id] = new_layer

    prior_invocations = state.get("invocations", [])
    prior_cost = state.get("total_cost_usd", 0.0)

    return {
        "layers": new_layers,
        "last_result": outcome.node_result,
        "invocations": prior_invocations + [outcome.invocation_record],
        "total_cost_usd": prior_cost + outcome.claude.total_cost_usd,
    }
