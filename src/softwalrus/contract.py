"""SoftWalrus <-> target project JSON contract.

Every node in the graph produces exactly one JSON file per invocation.
This module owns the shape of that contract:

    {
      "status": "success" | "failed",
      "message": "agent-generated summary",
      "error": "populated only when status != success",
      "artifacts": { <node-specific object> }
    }

Node-specific validation lives here too (architect layer plan, reviewer
finding counts). Nothing else in SoftWalrus should parse or reason about
these files -- callers use validate() and inspect the returned ValidatedOutput.

Halt message ownership rule (see design notes): failures the *node* reports
carry the node's own `error` string. Failures SoftWalrus imposes (envelope
malformed, hash unchanged, threshold breached) carry a SoftWalrus-authored
message. validate() returns the node's error verbatim; SoftWalrus-authored
halts are constructed by callers.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


VALID_LAYER_IDS = {"data", "domain", "ui"}


@dataclass
class ValidatedOutput:
    """Result of running validate() against a node's JSON output file.

    ok=True means: file exists, is valid JSON, envelope shape is correct,
    node reported status=success, and any node-specific schema checks
    passed. Only in this state may downstream code trust `artifacts`.

    ok=False sets `halt_message` to a SoftWalrus-authored string OR to
    the node's own `error` field, per the halt ownership rule. Callers
    surface halt_message verbatim; they do not paraphrase.
    """
    ok: bool
    halt_message: Optional[str] = None
    envelope: dict = field(default_factory=dict)  # full parsed JSON on success
    artifacts: dict = field(default_factory=dict)  # convenience alias for envelope["artifacts"]


# ---------- Hash helpers ----------

def file_sha256(path: Path) -> Optional[str]:
    """Return hex SHA-256 of the file, or None if the file does not exist."""
    if not path.exists():
        return None
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def freshness_ok(before: Optional[str], after: Optional[str]) -> bool:
    """True if the file changed (or was created) between before and after.

    - before=None, after=<hash>: file was created. OK.
    - before=<h1>, after=<h2>, h1 != h2: file was updated. OK.
    - before=<h>, after=<same h>: file unchanged. NOT OK (silent failure).
    - after=None: file missing after invocation. NOT OK.
    """
    if after is None:
        return False
    if before is None:
        return True
    return before != after


# ---------- Envelope validation ----------

_ENVELOPE_REQUIRED = {"status", "message", "artifacts"}


def _validate_envelope(raw: Any) -> tuple[bool, Optional[str]]:
    """Return (ok, softwalrus_error). softwalrus_error is None on success."""
    if not isinstance(raw, dict):
        return False, "envelope must be a JSON object"
    missing = _ENVELOPE_REQUIRED - set(raw.keys())
    if missing:
        return False, f"envelope missing required field(s): {sorted(missing)}"
    status = raw.get("status")
    if status not in ("success", "failed"):
        return False, f"envelope 'status' must be 'success' or 'failed', got {status!r}"
    if not isinstance(raw.get("artifacts"), dict):
        return False, "envelope 'artifacts' must be a JSON object"
    if status == "failed":
        # error should be populated; message optional
        if "error" not in raw:
            return False, "envelope 'status' is 'failed' but 'error' field missing"
    return True, None


# ---------- Node-specific schema checks ----------

def _validate_architect_artifacts(artifacts: dict) -> tuple[bool, Optional[str]]:
    """Layer plan schema. Mirrors the old validator on architect.md."""
    required = ["request_summary", "architecture_updated",
                "architecture_change_summary", "designer_needed",
                "designer_rationale", "layers"]
    for key in required:
        if key not in artifacts:
            return False, f"artifacts missing required field: {key}"
    if not isinstance(artifacts["layers"], list):
        return False, "artifacts.layers must be an array"

    seen_ids: set[str] = set()
    for i, layer in enumerate(artifacts["layers"]):
        for key in ("id", "name", "scope", "handoff_prefix", "depends_on"):
            if key not in layer:
                return False, f"artifacts.layers[{i}] missing field: {key}"
        if layer["id"] not in VALID_LAYER_IDS:
            return False, (
                f"artifacts.layers[{i}].id {layer['id']!r} not in "
                f"{sorted(VALID_LAYER_IDS)}"
            )
        if layer["id"] in seen_ids:
            return False, f"artifacts.layers: id {layer['id']!r} appears more than once"
        seen_ids.add(layer["id"])
        if not isinstance(layer["depends_on"], list):
            return False, f"artifacts.layers[{i}].depends_on must be a list"
        for dep in layer["depends_on"]:
            if dep not in seen_ids:
                return False, (
                    f"artifacts.layers[{i}].depends_on references {dep!r} "
                    "which is not declared earlier in the plan"
                )
    return True, None


def _validate_reviewer_artifacts(artifacts: dict) -> tuple[bool, Optional[str]]:
    """Findings schema. totalCount, open, closed required; regressionCount optional."""
    findings = artifacts.get("findings")
    if not isinstance(findings, dict):
        return False, "artifacts.findings must be an object"

    for key in ("totalCount", "open", "closed"):
        if key not in findings:
            return False, f"artifacts.findings missing required field: {key}"
        val = findings[key]
        # bool is a subclass of int in Python; exclude it
        if not isinstance(val, int) or isinstance(val, bool) or val < 0:
            return False, f"artifacts.findings.{key} must be a non-negative integer"

    if findings["open"] + findings["closed"] != findings["totalCount"]:
        return False, (
            f"artifacts.findings: open ({findings['open']}) + "
            f"closed ({findings['closed']}) != totalCount ({findings['totalCount']})"
        )

    if "regressionCount" in findings:
        rc = findings["regressionCount"]
        if not isinstance(rc, int) or isinstance(rc, bool) or rc < 0:
            return False, "artifacts.findings.regressionCount must be a non-negative integer"

    return True, None


# Registry of node-specific validators. Nodes not listed here get envelope-only validation.
_ARTIFACT_VALIDATORS = {
    "architect": _validate_architect_artifacts,
    "reviewer": _validate_reviewer_artifacts,
}


# ---------- Public API ----------

def validate(
    path: Path,
    node_kind: str,
    hash_before: Optional[str],
) -> ValidatedOutput:
    """Validate a node's JSON output file end-to-end.

    Called AFTER the node has run. `hash_before` is the SHA-256 SoftWalrus
    recorded prior to invocation (or None if the file did not exist).

    Order of checks:
      1. File exists after invocation.
      2. Hash advanced (or file newly created).
      3. File contents parse as JSON.
      4. Envelope shape is valid.
      5. If envelope.status == 'failed', return with the node's error verbatim.
      6. Node-specific artifact schema (architect, reviewer).
      7. All good -> return artifacts.

    Any check failure returns ok=False with an appropriate halt_message.
    """
    if not path.exists():
        return ValidatedOutput(
            ok=False,
            halt_message=f"Output file `{path.name}` missing after invocation",
        )

    hash_after = file_sha256(path)
    if not freshness_ok(hash_before, hash_after):
        return ValidatedOutput(
            ok=False,
            halt_message=f"Output file `{path.name}` unchanged after invocation (silent failure)",
        )

    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        return ValidatedOutput(
            ok=False,
            halt_message=f"Output file `{path.name}` failed JSON parse: {e}",
        )

    envelope_ok, envelope_err = _validate_envelope(raw)
    if not envelope_ok:
        return ValidatedOutput(
            ok=False,
            halt_message=f"Output file `{path.name}` failed envelope validation: {envelope_err}",
        )

    if raw["status"] == "failed":
        # Node reported failure. Surface the node's own error message.
        node_error = raw.get("error") or "(no error text supplied)"
        return ValidatedOutput(
            ok=False,
            halt_message=node_error,
            envelope=raw,
            artifacts=raw.get("artifacts", {}),
        )

    validator = _ARTIFACT_VALIDATORS.get(node_kind)
    if validator is not None:
        artifacts_ok, artifacts_err = validator(raw["artifacts"])
        if not artifacts_ok:
            return ValidatedOutput(
                ok=False,
                halt_message=f"Output file `{path.name}` failed artifact validation: {artifacts_err}",
            )

    return ValidatedOutput(
        ok=True,
        envelope=raw,
        artifacts=raw.get("artifacts", {}),
    )
