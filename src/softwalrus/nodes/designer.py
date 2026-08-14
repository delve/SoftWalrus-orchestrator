"""Designer node — thin wrapper over the design slash command."""

from __future__ import annotations

import logging
from pathlib import Path

from ..claude import run_agent
from ..commands import render_command
from ..handoffs import design_md_path
from ..state import NodeResult, PipelineState

logger = logging.getLogger(__name__)


async def designer_node(state: PipelineState, project_dir: Path) -> dict:
    request = state.get("request", "")
    plan = state.get("plan", {})
    scope_hint = plan.get("designer_rationale", "")

    template = render_command(project_dir, "design", arguments=[])
    prompt = (
        f"{template}\n\n"
        f"User request for this run: {request}\n"
        f"Architect's rationale for involving you: {scope_hint}"
    )

    result = await run_agent(
        prompt=prompt,
        project_dir=project_dir,
        agent_name="designer",
    )

    total_cost_delta = result.total_cost_usd
    node_result: NodeResult = {
        "agent": "designer",
        "session_id": result.session_id,
        "cost_usd": result.total_cost_usd,
        "success": result.success,
        "error": result.raw_error,
        "output_summary": "",
    }

    if not result.success:
        node_result["output_summary"] = f"agent failed: subtype={result.subtype}"
    else:
        design_path = design_md_path(project_dir)
        if not design_path.exists() or design_path.stat().st_size == 0:
            node_result["success"] = False
            node_result["error"] = f"agent reported success but {design_path.name} is missing or empty"
            node_result["output_summary"] = "missing design.md"
        else:
            node_result["output_summary"] = "design.md written"

    return {
        "designer_result": node_result,
        "total_cost_usd": state.get("total_cost_usd", 0.0) + total_cost_delta,
    }
