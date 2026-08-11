"""Graph state model.

Phase 2: request -> architect -> (optional designer) -> per-layer
develop/review loop -> qa. The state tracks a layer plan produced by the
architect and per-layer status as the pipeline progresses.

Design notes:
- All non-primitive fields are declared with total=False so partial
  updates from nodes merge cleanly without requiring every node to
  return the full state.
- `layers` is a dict keyed by layer id (from the architect's plan) so
  updates to a single layer's status don't require rewriting the whole
  list. LangGraph's default reducer replaces dict values wholesale;
  we handle merges explicitly in nodes.
- `NodeResult` retains the minimal breadcrumb shape from Phase 1. The
  transcript files hold the full detail; the state holds just enough
  to render `softwalrus status` usefully.
"""

from __future__ import annotations

from typing import Optional
from typing_extensions import TypedDict


# ---------- Sub-shapes ----------

class LayerSpec(TypedDict):
    """One layer as declared in the architect's plan."""
    id: str                     # "data", "domain", "ui"
    name: str                   # "data layer"
    scope: str                  # what the developer should build
    handoff_prefix: str         # e.g. "01-data" -- used for filenames
    depends_on: list[str]       # layer ids this layer depends on


class LayerPlan(TypedDict, total=False):
    """Full architect output -- the parsed architecture.json."""
    request_summary: str
    architecture_updated: bool
    architecture_change_summary: str
    designer_needed: bool
    designer_rationale: str
    layers: list[LayerSpec]


class NodeResult(TypedDict, total=False):
    """Result payload from a single node invocation."""
    agent: str
    session_id: Optional[str]
    cost_usd: float
    success: bool
    error: Optional[str]
    output_summary: str


class LayerStatus(TypedDict, total=False):
    """Per-layer running status."""
    id: str
    name: str
    handoff_prefix: str
    scope: str
    status: str                 # 'pending', 'developing', 'reviewing', 'fixing', 'converged', 'halted', 'skipped'
    rounds: int                 # completed review rounds
    regression_counts: dict[str, int]  # finding id -> Fixed->Open transition count
    finding_state_history: dict[str, str]  # finding id -> last seen state
    cost_usd: float


# ---------- Top-level state ----------

class PipelineState(TypedDict, total=False):
    """LangGraph state for the whole pipeline."""

    # User input
    request: str

    # Architect output (parsed from architecture.json)
    plan: LayerPlan

    # Per-layer status keyed by layer id
    layers: dict[str, LayerStatus]

    # Which layer is currently being processed (for status display)
    current_layer_id: Optional[str]

    # Rolling totals
    total_cost_usd: float

    # Phase results (one per phase; nodes overwrite as they run)
    architect_result: NodeResult
    designer_result: NodeResult
    qa_result: NodeResult

    # Last develop/review/fix result (per-layer detail is in `layers`)
    last_result: NodeResult
