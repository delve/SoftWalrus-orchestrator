# SoftWalrus contract with target projects

This document defines what SoftWalrus expects from a target project and what
guarantees SoftWalrus makes in return. Target projects that satisfy this
contract can be orchestrated by SoftWalrus without further code changes on
either side.

## What SoftWalrus expects from a target project

### Directory layout

```
<target>/
  .claude/
    agents/
      architect.md
      designer.md
      developer.md
      code-reviewer.md
      qa.md
    commands/
      pipeline/
        architect.md
        design.md
        develop.md
        codereview.md
        fix.md
        test.md
  handoffs/          (target-owned; SoftWalrus writes nothing here)
  .orchestrator/     (SoftWalrus-owned; state.db, log.txt, transcripts/)
```

### Agent names

Loaded via `--agent` flag from `.claude/agents/`:

- `architect`
- `designer`
- `developer`
- `code-reviewer`
- `qa`

### Slash command bodies

Located at `.claude/commands/pipeline/*.md`.

- SoftWalrus reads these as raw prompt templates.
- YAML frontmatter is stripped.
- `$ARGUMENTS[0]` is substituted with a single string SoftWalrus supplies
  (currently used only for the layer's `handoff_prefix`).
- Content is otherwise passed to the agent verbatim.

## Node invocations

SoftWalrus dispatches nodes in this order:

1. **architect** — command `architect`, no arguments.
2. **designer** — command `design`, no arguments. Skipped if the
   architect's plan sets `designer_needed: false`.
3. For each layer in the architect's plan, in `depends_on` order:
    - **developer** (initial) — command `develop`, argument `[handoff_prefix]`.
    - **code-reviewer** — command `codereview`, argument `[handoff_prefix]`.
    - If the layer converges, move on. If not:
    - **developer** (fix) — command `fix`, argument `[handoff_prefix]`.
    - Loop reviewer → fix until convergence or a halt.
4. **qa** — command `test`, no arguments.

## JSON contract per node

Every node MUST write exactly one JSON file per invocation.

### Envelope shape (all nodes)

```json
{
  "status": "success" | "failed",
  "message": "agent-authored summary; may be missing/empty on failure",
  "error": "agent-authored failure detail; present only when status is failed",
  "artifacts": { <node-specific object> }
}
```

### Output filenames

| Node                       | File                                  |
|----------------------------|---------------------------------------|
| architect                  | `handoffs/architect.json`             |
| designer                   | `handoffs/design.json`                |
| developer (initial and fix)| `handoffs/develop-<prefix>.json`      |
| code-reviewer              | `handoffs/code-review-<prefix>.json`  |
| qa                         | `handoffs/qa.json`                    |

Each node overwrites its own file on every invocation. No node reads
another node's JSON. JSON files are strictly agent → orchestrator;
agent ↔ agent collaboration happens through markdown files SoftWalrus
does not touch.

## Artifacts SoftWalrus reads

### architect (required schema)

```json
{
  "request_summary": "string",
  "architecture_updated": bool,
  "architecture_change_summary": "string",
  "designer_needed": bool,
  "designer_rationale": "string",
  "layers": [
    {
      "id": "data" | "domain" | "ui",
      "name": "string",
      "scope": "string",
      "handoff_prefix": "NN-<id>",
      "depends_on": ["<earlier layer id>", ...]
    }
  ]
}
```

An empty `layers` array is valid — the pipeline skips directly to QA.

### code-reviewer (required schema)

```json
{
  "findings": {
    "totalCount": <non-negative int>,
    "open":       <non-negative int>,
    "closed":     <non-negative int>,
    "regressionCount": <non-negative int, optional>
  }
}
```

Constraint: `open + closed == totalCount`.

### designer, developer, qa

Artifacts are opaque to SoftWalrus. Contents are recommended to include a
short `summary` field for status display, but SoftWalrus validates only
the envelope.

## Validations SoftWalrus performs after every invocation

1. Expected JSON file exists.
2. File contents changed (SHA-256 differs from pre-invocation, or file
   was newly created). Identical hash before and after is treated as a
   silent failure.
3. Contents parse as valid JSON.
4. Envelope has `status`, `message`, `artifacts` fields.
5. `status == "success"`.
6. Node-specific schema (architect, code-reviewer) validates.

Any failure = node failed = pipeline halts.

## Halt policies imposed by SoftWalrus

- **Regression threshold**: if the reviewer reports `regressionCount >= 6`,
  the layer halts.
- **Round cap**: if a layer's review round count reaches 8, the layer halts.

## Halt message ownership

- Node reports `status: "failed"` → SoftWalrus surfaces the node's `error`
  field verbatim.
- Node output fails a SoftWalrus validation (missing file, hash unchanged,
  malformed JSON, schema violation) → SoftWalrus authors the halt message.
- Threshold or round-cap halt → SoftWalrus authors the halt message.

## Human review checkpoints

The pipeline pauses (does not halt) after:

- Architect completes successfully.
- Each layer's review loop converges (`open == 0`).

Human resumes with `softwalrus resume`. Editing markdown files between
pause and resume is expected; SoftWalrus does not track those edits.
