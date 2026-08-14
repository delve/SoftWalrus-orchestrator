"""QA node — dispatches the test slash command."""

from __future__ import annotations

import logging
from pathlib import Path

from ..claude import run_agent
from ..commands import render_command
from ..handoffs import qa_report_path
from ..state import NodeResult, PipelineState

logger = logging.getLogger(__name__)


async def qa_node(state: PipelineState, project_dir: Path) -> dict:
    prompt = render_command(project_dir, "test", arguments=[])

    result = await run_agent(
        prompt=prompt,
        project_dir=project_dir,
        agent_name="qa",
    )

    node_result: NodeResult = {
        "agent": "qa",
        "session_id": result.session_id,
        "cost_usd": result.total_cost_usd,
        "success": result.success,
        "error": result.raw_error,
        "output_summary": "",
    }

    if not result.success:
        node_result["output_summary"] = f"agent failed: subtype={result.subtype}"
    else:
        report = qa_report_path(project_dir)
        if not report.exists() or report.stat().st_size == 0:
            node_result["success"] = False
            node_result["error"] = f"agent reported success but {report.name} is missing or empty"
            node_result["output_summary"] = "missing qa-report.md"
        else:
            node_result["output_summary"] = "QA complete; report written"

    return {
        "qa_result": node_result,
        "total_cost_usd": state.get("total_cost_usd", 0.0) + result.total_cost_usd,
    }
