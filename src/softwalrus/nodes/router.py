"""Router node.

Doesn't invoke any agent. Its job is to advance state.current_layer_id
to the next layer that's ready to run (all its dependencies are
'converged' or 'skipped'), or to leave current_layer_id unset if all
layers are done.

The routing edges out of this node inspect state to decide whether to
send control to developer (start/continue a layer), qa (all done), or
END (halt state).
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..state import PipelineState

logger = logging.getLogger(__name__)


def _layer_ready(layer: dict, layers: dict[str, dict]) -> bool:
    """A layer is ready when all its dependencies are 'converged' or 'skipped'."""
    for dep_id in layer.get("depends_on", []) or []:
        dep = layers.get(dep_id)
        if dep is None:
            # unknown dependency - treat as blocking to be safe
            return False
        if dep.get("status") not in ("converged", "skipped"):
            return False
    return True


async def router_node(state: PipelineState, project_dir: Path) -> dict:
    """Update state to point at the next layer to process."""
    plan = state.get("plan", {})
    layers = state.get("layers", {})
    order = plan.get("layers", [])

    for spec in order:
        lid = spec["id"]
        layer = layers.get(lid, {})
        status = layer.get("status", "pending")

        if status in ("pending", "developing", "fixing"):
            if not _layer_ready(layer, layers):
                # Blocked by dependencies -- should not happen in the current
                # sequential design but the check makes the invariant explicit.
                continue
            return {"current_layer_id": lid}

    # No more layers to process
    return {"current_layer_id": None}
