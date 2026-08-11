"""Developer node.

Phase 1: single call, no layer awareness, no fix-loop. Just proves the plumbing
end-to-end: state in, agent runs in project cwd, state out.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..claude import run_agent
from ..state import PipelineState, NodeResult

logger = logging.getLogger(__name__)


async def developer_node(state: PipelineState, project_dir: Path) -> dict:
    """Run the developer sub-agent against the user request.

    Returns a dict that LangGraph merges into the state.
    """
    request = state.get("request", "")
    if not request:
        return {
            "last_result": NodeResult(
                agent="developer",
                success=False,
                error="empty request",
                output_summary="no request in state",
                cost_usd=0.0,
                session_id=None,
            )
        }

    prompt = (
        f"Implement the following user request in this project. "
        f"Write session notes to ./handoffs/developer-notes.md.\n\n"
        f"Request: {request}"
    )

    result = await run_agent(
        prompt=prompt,
        project_dir=project_dir,
        agent_name="developer",
    )

    prior = state.get("total_cost_usd", 0.0)
    return {
        "total_cost_usd": prior + result.total_cost_usd,
        "last_result": NodeResult(
            agent="developer",
            session_id=result.session_id,
            cost_usd=result.total_cost_usd,
            success=result.success,
            error=result.raw_error,
            output_summary=(
                (result.result_text or "")[:200] if result.success
                else f"failed: subtype={result.subtype}"
            ),
        ),
    }
