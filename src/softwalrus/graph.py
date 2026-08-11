"""LangGraph state graph definition.

Phase 1: single-node graph (developer). We're proving that the LangGraph +
checkpointer + Claude SDK stack works end-to-end. Phase 2 will add the
remaining nodes and the layer loop.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from .nodes.developer import developer_node
from .state import PipelineState


def build_graph(project_dir: Path):
    """Return an uncompiled StateGraph.

    Compile in the caller so we can inject the checkpointer at that point.
    Node functions get `project_dir` bound via functools.partial.
    """
    builder = StateGraph(PipelineState)
    builder.add_node("developer", partial(developer_node, project_dir=project_dir))
    builder.add_edge(START, "developer")
    builder.add_edge("developer", END)
    return builder
