"""LangGraph state graph definition — Phase 2.

Shape (excluding interrupt points):

    START
      |
      architect
      |
      [architect_success?] -- no --> halt (END)
      |
      designer_gate
      |
      [designer_needed?] -- yes --> designer -- [success?] -- no --> halt
      |                   -- no  --> ------------> router
      |                                              |
      |                              +---------------+
      |                              |
      |                              v
      |                            router
      |                              |
      |         [current_layer_id?] -- None --> qa --> END
      |                              |
      |                              v
      |                            developer
      |                              |
      |         [layer status?] -- 'halted' --> halt
      |                          -- other  --> reviewer
      |                              |
      |     [reviewer set layer.status to?]
      |         'converged' or 'halted'  --> router
      |         'fixing'                  --> developer (fix pass)
      |         'halted' during reviewer  --> halt

Interrupts (pauses for human review) fire after:
  - architect  (review the layer plan)
  - reviewer   (once layer.status == 'converged', so you can review handoffs
                before router moves to next layer or QA)
"""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Literal

from langgraph.graph import END, START, StateGraph

from .nodes.architect import architect_node
from .nodes.designer import designer_node
from .nodes.developer import developer_node
from .nodes.qa import qa_node
from .nodes.reviewer import reviewer_node
from .nodes.router import router_node
from .state import PipelineState


# ---------- Conditional edge functions ----------

def _after_architect(state: PipelineState) -> Literal["designer_gate", "halt"]:
    result = state.get("architect_result", {})
    if not result.get("success"):
        return "halt"
    plan = state.get("plan", {})
    if not plan.get("layers"):
        # Empty plan is a legitimate outcome (docs-only change) -- go to QA.
        # We still route through the designer gate first in case the change
        # affects UX documentation.
        return "designer_gate"
    return "designer_gate"


def _designer_gate(state: PipelineState) -> Literal["designer", "router"]:
    plan = state.get("plan", {})
    if plan.get("designer_needed", False):
        return "designer"
    return "router"


def _after_designer(state: PipelineState) -> Literal["router", "halt"]:
    result = state.get("designer_result", {})
    if not result.get("success"):
        return "halt"
    return "router"


def _after_router(state: PipelineState) -> Literal["developer", "qa"]:
    if state.get("current_layer_id") is None:
        return "qa"
    return "developer"


def _after_developer(state: PipelineState) -> Literal["reviewer", "halt"]:
    lid = state.get("current_layer_id")
    if not lid:
        return "halt"
    layer = state.get("layers", {}).get(lid, {})
    if layer.get("status") == "halted":
        return "halt"
    return "reviewer"


def _after_reviewer(state: PipelineState) -> Literal["developer", "router", "halt"]:
    lid = state.get("current_layer_id")
    if not lid:
        return "halt"
    layer = state.get("layers", {}).get(lid, {})
    status = layer.get("status", "")
    if status == "fixing":
        return "developer"
    if status == "converged":
        return "router"
    # 'halted' or anything else -> halt
    return "halt"


# ---------- Graph builder ----------

def build_graph(project_dir: Path):
    """Return an uncompiled StateGraph.

    Node functions get `project_dir` bound via functools.partial.
    """
    builder = StateGraph(PipelineState)

    builder.add_node("architect", partial(architect_node, project_dir=project_dir))
    builder.add_node("designer", partial(designer_node, project_dir=project_dir))
    builder.add_node("router", partial(router_node, project_dir=project_dir))
    builder.add_node("developer", partial(developer_node, project_dir=project_dir))
    builder.add_node("reviewer", partial(reviewer_node, project_dir=project_dir))
    builder.add_node("qa", partial(qa_node, project_dir=project_dir))

    builder.add_edge(START, "architect")

    builder.add_conditional_edges(
        "architect",
        _after_architect,
        {"designer_gate": "designer_gate_noop", "halt": END},
    )

    # designer_gate is a lightweight no-op node so we can attach a
    # conditional edge that reads state after the architect commits.
    async def _designer_gate_noop(state: PipelineState) -> dict:
        return {}
    builder.add_node("designer_gate_noop", _designer_gate_noop)
    builder.add_conditional_edges(
        "designer_gate_noop",
        _designer_gate,
        {"designer": "designer", "router": "router"},
    )

    builder.add_conditional_edges(
        "designer",
        _after_designer,
        {"router": "router", "halt": END},
    )

    builder.add_conditional_edges(
        "router",
        _after_router,
        {"developer": "developer", "qa": "qa"},
    )

    builder.add_conditional_edges(
        "developer",
        _after_developer,
        {"reviewer": "reviewer", "halt": END},
    )

    builder.add_conditional_edges(
        "reviewer",
        _after_reviewer,
        {"developer": "developer", "router": "router", "halt": END},
    )

    builder.add_edge("qa", END)

    return builder


# Node names to interrupt after (for human review). Pass to compile().
INTERRUPT_AFTER = ["architect", "reviewer"]
