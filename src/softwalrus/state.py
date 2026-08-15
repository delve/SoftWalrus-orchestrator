"""Graph state model.

The state tracks the layer plan produced by the architect and per-layer
status as the pipeline progresses. Per-invocation `artifacts` blobs are
appended to a running list keyed by node kind + layer id + round.
"""

from __future__ import annotations

from typing import Optional
from typing_extensions import TypedDict


class LayerSpec(TypedDict):
    """One layer as declared in the architect's plan."""
    id: str
    name: str
    scope: str
    handoff_prefix: str
    depends_on: list[str]


class LayerPlan(TypedDict, total=False):
    """Full architect output -- the parsed architecture.json artifacts."""
    request_summary: str
    architecture_updated: bool
    architecture_change_summary: str
    designer_needed: bool
    designer_rationale: str
    layers: list[LayerSpec]


class NodeResult(TypedDict, total=False):
    """Short breadcrumb for `softwalrus status`. Full detail is in
    persisted_artifacts and in the on-disk JSON files."""
    agent: str
    session_id: Optional[str]
    cost_usd: float
    success: bool
    error: Optional[str]         # halt message SoftWalrus surfaced (node error or SoftWalrus-authored)
    output_summary: str          # human-readable summary lifted from artifacts / envelope message


class LayerStatus(TypedDict, total=False):
    """Per-layer running status."""
    id: str
    name: str
    handoff_prefix: str
    scope: str
    status: str                  # 'pending', 'developing', 'reviewing', 'fixing', 'converged', 'halted', 'skipped'
    rounds: int
    cost_usd: float


class InvocationRecord(TypedDict):
    """Persisted record of one node invocation. Written to state on every call."""
    node: str                    # 'architect', 'designer', 'developer', 'reviewer', 'qa'
    layer_id: Optional[str]      # None for architect/designer/qa
    round: int                   # 0 for non-loop nodes; 1..N for review rounds; matched fix passes share the round number
    ok: bool
    artifacts: dict              # full artifacts blob from the node's JSON envelope (empty on failure)
    envelope_message: str        # envelope.message from the node
    halt_message: Optional[str]  # populated when ok=False


class PipelineState(TypedDict, total=False):
    """LangGraph state for the whole pipeline."""

    # User input
    request: str

    # Architect output (parsed from architect.json artifacts)
    plan: LayerPlan

    # Per-layer status keyed by layer id
    layers: dict[str, LayerStatus]

    # Which layer is currently being processed (for status display)
    current_layer_id: Optional[str]

    # Rolling totals
    total_cost_usd: float

    # History of every node invocation this run. Appended to by nodes.
    invocations: list[InvocationRecord]

    # Phase-level breadcrumbs (last invocation of each phase)
    architect_result: NodeResult
    designer_result: NodeResult
    qa_result: NodeResult
    last_result: NodeResult
