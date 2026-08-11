"""Graph state model.

The state is intentionally simple in Phase 1 — just enough to drive the
developer node end-to-end and prove checkpointing works. Later phases add
per-layer status, review rounds, regression counts, etc.
"""

from __future__ import annotations

from typing import Optional
from typing_extensions import TypedDict


class NodeResult(TypedDict, total=False):
    """Result payload from a single node invocation."""
    agent: str                  # which sub-agent was used
    session_id: Optional[str]   # SDK session id, useful for debug
    cost_usd: float             # cost of this invocation
    success: bool
    error: Optional[str]        # failure detail if not success
    output_summary: str         # short human-readable status


class PipelineState(TypedDict, total=False):
    """LangGraph state for the whole pipeline.

    Phase 1 keeps this minimal: the user request plus the last node's result.
    """
    # User input
    request: str

    # Rolling totals
    total_cost_usd: float

    # Last node's outcome (Phase 2 will introduce per-phase fields)
    last_result: NodeResult
