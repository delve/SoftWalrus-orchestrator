"""Architect node.

Reads the target project's `architect` slash command, invokes the agent,
validates the resulting architect.json against the SoftWalrus contract,
and initializes per-layer state from the parsed layer plan.
"""

from __future__ import annotations

from pathlib import Path

from ..handoffs import architect_json_path
from ..state import LayerPlan, LayerSpec, PipelineState
from ._common import invoke_and_validate


async def architect_node(state: PipelineState, project_dir: Path) -> dict:
    request = state.get("request", "")
    output_path = architect_json_path(project_dir)

    prompt_suffix = f"User request for this run: {request}" if request else ""

    outcome = await invoke_and_validate(
        project_dir=project_dir,
        node_kind="architect",
        layer_id=None,
        round_number=0,
        agent_name="architect",
        command_name="architect",
        command_arguments=[],
        output_path=output_path,
        prompt_suffix=prompt_suffix,
    )

    prior_invocations = state.get("invocations", [])
    prior_cost = state.get("total_cost_usd", 0.0)

    update: dict = {
        "architect_result": outcome.node_result,
        "invocations": prior_invocations + [outcome.invocation_record],
        "total_cost_usd": prior_cost + outcome.claude.total_cost_usd,
    }

    if not outcome.validated.ok:
        return update

    # Build LayerPlan and per-layer status from the validated artifacts
    artifacts = outcome.validated.artifacts
    layers_spec: list[LayerSpec] = [
        LayerSpec(
            id=layer["id"],
            name=layer["name"],
            scope=layer["scope"],
            handoff_prefix=layer["handoff_prefix"],
            depends_on=list(layer["depends_on"]),
        )
        for layer in artifacts["layers"]
    ]
    plan: LayerPlan = {
        "request_summary": str(artifacts["request_summary"]),
        "architecture_updated": bool(artifacts["architecture_updated"]),
        "architecture_change_summary": str(artifacts["architecture_change_summary"]),
        "designer_needed": bool(artifacts["designer_needed"]),
        "designer_rationale": str(artifacts["designer_rationale"]),
        "layers": layers_spec,
    }

    layers_status = {
        spec["id"]: {
            "id": spec["id"],
            "name": spec["name"],
            "handoff_prefix": spec["handoff_prefix"],
            "scope": spec["scope"],
            "status": "pending",
            "rounds": 0,
            "cost_usd": 0.0,
        }
        for spec in layers_spec
    }

    update["plan"] = plan
    update["layers"] = layers_status
    return update
