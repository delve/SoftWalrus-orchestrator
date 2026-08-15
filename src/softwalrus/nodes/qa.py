"""QA node — final pass after all layers converge."""

from __future__ import annotations

from pathlib import Path

from ..handoffs import qa_json_path
from ..state import PipelineState
from ._common import invoke_and_validate


async def qa_node(state: PipelineState, project_dir: Path) -> dict:
    outcome = await invoke_and_validate(
        project_dir=project_dir,
        node_kind="qa",
        layer_id=None,
        round_number=0,
        agent_name="qa",
        command_name="test",
        command_arguments=[],
        output_path=qa_json_path(project_dir),
    )

    prior_invocations = state.get("invocations", [])
    prior_cost = state.get("total_cost_usd", 0.0)

    return {
        "qa_result": outcome.node_result,
        "invocations": prior_invocations + [outcome.invocation_record],
        "total_cost_usd": prior_cost + outcome.claude.total_cost_usd,
    }
