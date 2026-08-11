"""Architect node.

Invokes the architect sub-agent, then reads and validates the resulting
architecture.json. The architect must always emit this file (both
cold-start and incremental modes).

Failure modes handled:
- Agent invocation itself fails (SDK error, timeout, etc.).
- Agent succeeded but architecture.json is missing.
- architecture.json is present but not valid JSON.
- architecture.json is valid JSON but doesn't match the expected schema.

All of these produce a NodeResult with success=False and an error string.
Downstream routing checks for success before proceeding.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..claude import run_agent
from ..handoffs import architecture_json_path
from ..state import LayerPlan, LayerSpec, NodeResult, PipelineState

logger = logging.getLogger(__name__)


VALID_LAYER_IDS = {"data", "domain", "ui"}


def _validate_plan(raw: dict) -> tuple[bool, str, LayerPlan]:
    """Return (ok, error_message, plan). If ok is False, plan is a partial value.

    Kept intentionally strict: any deviation from the documented schema
    fails validation. Downstream code should not have to defend against
    weird shapes.
    """
    required_top = ["request_summary", "architecture_updated",
                    "architecture_change_summary", "designer_needed",
                    "designer_rationale", "layers"]
    for key in required_top:
        if key not in raw:
            return False, f"architecture.json missing required field: {key}", {}
    if not isinstance(raw["layers"], list):
        return False, "architecture.json 'layers' must be an array", {}

    layers: list[LayerSpec] = []
    seen_ids: set[str] = set()
    for i, layer in enumerate(raw["layers"]):
        for key in ("id", "name", "scope", "handoff_prefix", "depends_on"):
            if key not in layer:
                return False, f"layer[{i}] missing field: {key}", {}
        if layer["id"] not in VALID_LAYER_IDS:
            return False, (
                f"layer[{i}].id '{layer['id']}' is not one of "
                f"{sorted(VALID_LAYER_IDS)}"
            ), {}
        if layer["id"] in seen_ids:
            return False, f"layer id '{layer['id']}' appears more than once", {}
        seen_ids.add(layer["id"])
        if not isinstance(layer["depends_on"], list):
            return False, f"layer[{i}].depends_on must be a list", {}
        for dep in layer["depends_on"]:
            if dep not in seen_ids:
                return False, (
                    f"layer[{i}].depends_on references '{dep}' which is not "
                    "declared earlier in the plan"
                ), {}
        layers.append(LayerSpec(
            id=layer["id"],
            name=layer["name"],
            scope=layer["scope"],
            handoff_prefix=layer["handoff_prefix"],
            depends_on=list(layer["depends_on"]),
        ))

    plan: LayerPlan = {
        "request_summary": str(raw["request_summary"]),
        "architecture_updated": bool(raw["architecture_updated"]),
        "architecture_change_summary": str(raw["architecture_change_summary"]),
        "designer_needed": bool(raw["designer_needed"]),
        "designer_rationale": str(raw["designer_rationale"]),
        "layers": layers,
    }
    return True, "", plan


async def architect_node(state: PipelineState, project_dir: Path) -> dict:
    request = state.get("request", "")
    if not request:
        return {
            "architect_result": NodeResult(
                agent="architect", success=False,
                error="empty request", output_summary="no request in state",
                cost_usd=0.0, session_id=None,
            ),
        }

    prompt = (
        "Evaluate the following user request against the project. Follow "
        "your agent instructions to detect cold-start vs incremental mode, "
        "update architecture.md if warranted, and produce architecture.json "
        "with the layer plan.\n\n"
        f"Request: {request}"
    )

    result = await run_agent(
        prompt=prompt,
        project_dir=project_dir,
        agent_name="architect",
    )

    total_cost_delta = result.total_cost_usd
    node_result: NodeResult = {
        "agent": "architect",
        "session_id": result.session_id,
        "cost_usd": result.total_cost_usd,
        "success": result.success,
        "error": result.raw_error,
        "output_summary": "",
    }

    if not result.success:
        node_result["output_summary"] = f"agent failed: subtype={result.subtype}"
        return {
            "architect_result": node_result,
            "total_cost_usd": state.get("total_cost_usd", 0.0) + total_cost_delta,
        }

    # Read architecture.json
    plan_path = architecture_json_path(project_dir)
    if not plan_path.exists():
        node_result["success"] = False
        node_result["error"] = f"agent reported success but {plan_path.name} was not written"
        node_result["output_summary"] = "missing architecture.json"
        return {
            "architect_result": node_result,
            "total_cost_usd": state.get("total_cost_usd", 0.0) + total_cost_delta,
        }

    try:
        raw = json.loads(plan_path.read_text())
    except json.JSONDecodeError as e:
        node_result["success"] = False
        node_result["error"] = f"architecture.json is not valid JSON: {e}"
        node_result["output_summary"] = "invalid architecture.json"
        return {
            "architect_result": node_result,
            "total_cost_usd": state.get("total_cost_usd", 0.0) + total_cost_delta,
        }

    ok, err, plan = _validate_plan(raw)
    if not ok:
        node_result["success"] = False
        node_result["error"] = f"architecture.json schema violation: {err}"
        node_result["output_summary"] = "invalid layer plan"
        return {
            "architect_result": node_result,
            "total_cost_usd": state.get("total_cost_usd", 0.0) + total_cost_delta,
        }

    # Initialize per-layer state from the plan
    layers_status = {
        spec["id"]: {
            "id": spec["id"],
            "name": spec["name"],
            "handoff_prefix": spec["handoff_prefix"],
            "scope": spec["scope"],
            "status": "pending",
            "rounds": 0,
            "regression_counts": {},
            "finding_state_history": {},
            "cost_usd": 0.0,
        }
        for spec in plan["layers"]
    }

    node_result["output_summary"] = (
        f"plan: {len(plan['layers'])} layer(s), "
        f"designer_needed={plan['designer_needed']}, "
        f"architecture_updated={plan['architecture_updated']}"
    )

    return {
        "architect_result": node_result,
        "plan": plan,
        "layers": layers_status,
        "total_cost_usd": state.get("total_cost_usd", 0.0) + total_cost_delta,
    }
