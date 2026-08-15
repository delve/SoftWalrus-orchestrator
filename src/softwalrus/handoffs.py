"""Filesystem paths for target project handoff artifacts.

SoftWalrus reads only the JSON files below. Markdown files remain the
agents' collaboration surface and SoftWalrus never opens them.
"""

from __future__ import annotations

from pathlib import Path


HANDOFFS_DIR = "handoffs"


def architect_json_path(project_dir: Path) -> Path:
    return project_dir / HANDOFFS_DIR / "architect.json"


def design_json_path(project_dir: Path) -> Path:
    return project_dir / HANDOFFS_DIR / "design.json"


def develop_json_path(project_dir: Path, handoff_prefix: str) -> Path:
    return project_dir / HANDOFFS_DIR / f"develop-{handoff_prefix}.json"


def code_review_json_path(project_dir: Path, handoff_prefix: str) -> Path:
    return project_dir / HANDOFFS_DIR / f"code-review-{handoff_prefix}.json"


def qa_json_path(project_dir: Path) -> Path:
    return project_dir / HANDOFFS_DIR / "qa.json"
