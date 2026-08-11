"""Handoff file paths and parsing helpers.

Ported from the old orchestrator. The regex and convergence rules are
unchanged; only the filename convention is new (hyphens throughout, no
spaces).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


FINDING_RE = re.compile(r"ID:\s*([CWO]\d+)\s*State:\s*(\w+)", re.IGNORECASE)

TERMINAL_STATES = {"Resolved", "Deferred", "Ignored"}


@dataclass
class Finding:
    id: str
    state: str


def developer_notes_path(project_dir: Path, handoff_prefix: str) -> Path:
    return project_dir / "handoffs" / f"developer-notes-{handoff_prefix}.md"


def code_review_path(project_dir: Path, handoff_prefix: str) -> Path:
    return project_dir / "handoffs" / f"code-review-{handoff_prefix}.md"


def architecture_md_path(project_dir: Path) -> Path:
    return project_dir / "handoffs" / "architecture.md"


def architecture_json_path(project_dir: Path) -> Path:
    return project_dir / "handoffs" / "architecture.json"


def design_md_path(project_dir: Path) -> Path:
    return project_dir / "handoffs" / "design.md"


def qa_report_path(project_dir: Path) -> Path:
    return project_dir / "handoffs" / "qa-report.md"


def parse_findings(handoff_path: Path) -> list[Finding]:
    """Extract all findings from a code-review handoff file."""
    if not handoff_path.exists():
        return []
    text = handoff_path.read_text()
    findings: list[Finding] = []
    for match in FINDING_RE.finditer(text):
        findings.append(Finding(id=match.group(1).upper(), state=match.group(2).capitalize()))
    return findings


def is_converged(findings: list[Finding]) -> bool:
    """Convergence: at least one finding exists AND all are terminal."""
    if not findings:
        return False
    return all(f.state in TERMINAL_STATES for f in findings)


def detect_regression(
    findings: list[Finding],
    prior_history: dict[str, str],
    regression_counts: dict[str, int],
    threshold: int = 2,
) -> Optional[str]:
    """Detect Fixed -> Open transitions.

    Increments `regression_counts` in place. Returns the ID of a finding
    that has regressed `threshold` times or more (indicating a stall).
    Updates `prior_history` in place at the end so the next call has a
    fresh reference point.
    """
    tripped: Optional[str] = None
    for f in findings:
        prior = prior_history.get(f.id)
        if prior == "Fixed" and f.state == "Open":
            regression_counts[f.id] = regression_counts.get(f.id, 0) + 1
            if regression_counts[f.id] >= threshold and tripped is None:
                tripped = f.id
    for f in findings:
        prior_history[f.id] = f.state
    return tripped
