"""Filesystem layout for orchestrator state inside a target project."""

from __future__ import annotations

from pathlib import Path

STATE_DIR = ".orchestrator"
STATE_DB = "state.db"
LOG_FILE = "log.txt"
TRANSCRIPTS_DIR = "transcripts"


def state_dir(project_dir: Path) -> Path:
    return project_dir / STATE_DIR


def state_db_path(project_dir: Path) -> Path:
    return state_dir(project_dir) / STATE_DB


def log_path(project_dir: Path) -> Path:
    return state_dir(project_dir) / LOG_FILE


def transcripts_dir(project_dir: Path) -> Path:
    return state_dir(project_dir) / TRANSCRIPTS_DIR


def ensure_state_dir(project_dir: Path) -> None:
    state_dir(project_dir).mkdir(parents=True, exist_ok=True)
    transcripts_dir(project_dir).mkdir(parents=True, exist_ok=True)
