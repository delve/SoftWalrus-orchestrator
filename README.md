# SoftWalrus

LangGraph-based orchestrator for pipeline agents (architect / designer / developer / reviewer / QA).

Standalone tool that operates on a target project directory. State lives in the target project under `.orchestrator/`.

## Status

**Phase 1** — skeleton and Claude Agent SDK plumbing. One node (developer). No conditional edges, no fix loop, no notifications yet. This phase proves the LangGraph + AsyncSqliteSaver + Claude Agent SDK stack works end-to-end.

## Install (development)

```bash
uv venv
uv pip install -e .
```

Or plain pip:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Prerequisites

1. Claude Code CLI installed and authenticated (`claude` runs interactively without prompting for auth). The Agent SDK talks to the same authenticated backend.
2. Target project has `.claude/agents/developer.md` defined.

## Usage

From within the target project directory:

```bash
softwalrus run --request "add a hello-world endpoint"
softwalrus status
softwalrus resume
```

Or from anywhere:

```bash
softwalrus run --request "..." --project-dir /path/to/target
softwalrus status --project-dir /path/to/target
```

## Layout inside target project

```
<target>/
  .claude/agents/*.md      (unchanged; SoftWalrus reads them via SDK auto-detect)
  handoffs/*.md            (unchanged; developer/reviewer/etc read and write here)
  .orchestrator/
    state.db               (LangGraph checkpoint store; add to .gitignore)
    log.txt                (append-only run log)
    transcripts/           (per-invocation transcripts)
```

## Inspecting state

State is stored as LangGraph checkpoints in `.orchestrator/state.db` (SQLite). Raw values are pickled and not human-readable via `sqlite3 state.db`. Use `softwalrus status` — it reads the checkpoint via the LangGraph API and pretty-prints.

## Roadmap

- Phase 2: full graph shape (architect, designer, developer, reviewer, QA), layer loop, human-review interrupts.
- Phase 3: conditional skips for architect and designer.
- Phase 4: token-exhaustion wait/retry, regression detection, Discord notifications.
- Phase 5: per-project config, `--project-dir` polish, packaging.
