"""Designer node."""

from __future__ import annotations

from pathlib import Path

from ..handoffs import design_json_path
from ..state import PipelineState
from ._common import invoke_and_validate


async def designer_node(state: PipelineState, project_dir: Path) -> dict:
    request = state.get("request", "")
    plan = state.get("plan", {})
    scope_hint = plan.get("designer_rationale", "")

    prompt_suffix = (
        f"User request for this run: {request}\n"
        f"Architect's rationale for involving you: {scope_hint}"
    )

    outcome = await invoke_and_validate(
        project_dir=project_dir,
        node_kind="designer",
        layer_id=None,
        round_number=0,
        agent_name="designer",
        command_name="design",
        command_arguments=[],
        output_path=design_json_path(project_dir),
        prompt_suffix=prompt_suffix,
    )

    prior_invocations = state.get("invocations", [])
    prior_cost = state.get("total_cost_usd", 0.0)

    return {
        "designer_result": outcome.node_result,
        "invocations": prior_invocations + [outcome.invocation_record],
        "total_cost_usd": prior_cost + outcome.claude.total_cost_usd,
    }
