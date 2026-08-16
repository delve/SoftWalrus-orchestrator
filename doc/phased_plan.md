The first-week plan

I want to lay out the shape of what we'll build so you can push back before I start writing code. Not code yet — just the plan.

Phase 1: Skeleton and Claude Agent SDK plumbing

Goal: a minimal working graph that can invoke one agent (developer) via the SDK, checkpoint state, and let you inspect it. Nothing about the pipeline logic yet.

pyproject.toml with dependencies (langgraph, claude-agent-sdk, pydantic, typer or argparse).
state.py: pydantic model for the graph state (fields: request, per-phase outputs, per-layer status, cost totals).
claude.py: thin async wrapper around the Claude Agent SDK. Takes agent name + prompt + optional tools list. Returns typed result with cost, session_id, output, error.
graph.py: a stub graph with one node (developer) and no conditional logic.
cli.py: run, status, resume subcommands. run invokes the stub. status reads the checkpoint. resume re-invokes with same thread_id.
Verify: agent-pipeline run --request "make a hello world" runs the developer once, exits, and status shows the state.

Phase 2: Add the pipeline shape

Goal: full graph with all six nodes, but no conditional skips yet — everything runs in sequence.

Add architect, designer, reviewer, qa node functions.
Add the develop→review→[converged? fix : next_layer] subgraph for a single layer.
Add per-layer looping (data → domain → ui).
Interrupt after each layer for human review.
Verify: end-to-end run against a trivial "add a hello endpoint" request, halting between layers.

Phase 3: Conditional skips for architect and designer

Goal: architect and designer can each decide their work isn't needed and route accordingly.

Structured output from architect and designer (skip decision + reasoning + output).
Conditional edges based on the decision.
Notification when a phase is skipped, with the agent's reasoning.
Verify: a small request ("fix this typo") should skip architect and designer entirely.

Phase 4: Circuit breakers and retries

Goal: the wait/retry behavior you already have, ported cleanly.

Token exhaustion detection and wait-until-reset (same logic as current, wrapped as a node retry policy).
Regression detection in review handoffs (2-strike rule).
Max rounds per layer.
Discord notifications at phase boundaries and halts.

Phase 5: Portability polish

--project-dir flag (defaults to cwd).
.orchestrator/ created in target project for state.db, transcripts, log.
Per-project config file (.orchestrator/config.toml) for tuning: max rounds, timeouts, whether QA runs, layer names.
README with install and setup.

Phase 6 (deferred): anything about parallel runs across projects, agent skill customization, cross-project reporting.
