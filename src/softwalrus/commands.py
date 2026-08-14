"""Load and substitute slash command templates from the target project.

Each command lives at `.claude/commands/pipeline/<name>.md` and uses
`$ARGUMENTS[N]` placeholders. The orchestrator provides the values.
"""

from __future__ import annotations

import re
from pathlib import Path


ARGUMENTS_RE = re.compile(r"\$ARGUMENTS\[(\d+)\]")


class CommandNotFoundError(FileNotFoundError):
    pass


class ArgumentIndexError(IndexError):
    pass


def load_command(project_dir: Path, name: str) -> str:
    """Read the raw slash command body, stripping YAML frontmatter."""
    path = project_dir / ".claude" / "commands" / "pipeline" / f"{name}.md"
    if not path.exists():
        raise CommandNotFoundError(str(path))
    text = path.read_text()
    # Strip a leading YAML frontmatter block if present.
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            text = text[end + 5:]
    return text.lstrip("\n")


def substitute_arguments(template: str, arguments: list[str]) -> str:
    """Replace every $ARGUMENTS[N] with arguments[N]."""
    def _sub(match: re.Match) -> str:
        idx = int(match.group(1))
        if idx >= len(arguments):
            raise ArgumentIndexError(
                f"$ARGUMENTS[{idx}] referenced but only {len(arguments)} "
                f"argument(s) provided"
            )
        return arguments[idx]
    return ARGUMENTS_RE.sub(_sub, template)


def render_command(project_dir: Path, name: str, arguments: list[str]) -> str:
    """Load and substitute in one call."""
    return substitute_arguments(load_command(project_dir, name), arguments)
