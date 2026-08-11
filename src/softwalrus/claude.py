"""Wrapper around the Claude Agent SDK.

Turns the streaming `query()` iterator into a single typed result: the final
ResultMessage plus a summary of assistant text and tool activity. Higher
layers (node functions, retry logic) don't touch the SDK's message stream
directly; they call `run_agent()` and get a ClaudeRunResult back.

This is where we'd add token-exhaustion detection, retry-with-wait, and
similar circuit-breaker behavior in Phase 4. For Phase 1 we surface the raw
outcome and let the caller decide.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

logger = logging.getLogger(__name__)


@dataclass
class ClaudeRunResult:
    """Aggregated outcome of a single query() invocation."""

    success: bool
    is_error: bool
    subtype: str                       # 'success', 'error_max_turns', 'error_max_budget_usd', 'error_during_execution', etc.
    session_id: Optional[str]
    total_cost_usd: float
    num_turns: int
    duration_ms: int
    result_text: Optional[str]         # the agent's final message text
    stop_reason: Optional[str]
    assistant_texts: list[str] = field(default_factory=list)  # streamed text blocks for transcript
    raw_error: Optional[str] = None    # populated on failure


async def run_agent(
    *,
    prompt: str,
    project_dir: Path,
    agent_name: Optional[str] = None,
    max_budget_usd: Optional[float] = None,
    max_turns: Optional[int] = None,
    permission_mode: str = "bypassPermissions",
) -> ClaudeRunResult:
    """Invoke the Claude Agent SDK and reduce the message stream to a result.

    Parameters
    ----------
    prompt:
        Task prompt. If `agent_name` is set, the phrase "Use the X agent to ..."
        can appear in the prompt but is no longer load-bearing — the SDK loads
        the sub-agent via ClaudeAgentOptions.
    project_dir:
        Working directory for the agent (contains .claude/agents/, handoffs/,
        source, etc.). Passed as `cwd` on ClaudeAgentOptions so filesystem
        agents at `.claude/agents/` auto-load.
    agent_name:
        Name of the sub-agent to use for this run. When provided, prepends a
        "Use the {name} agent" directive to the prompt so the top-level Claude
        dispatches via the Agent tool. (An alternative — programmatically
        defining agents via `agents=`  on options — is planned for Phase 2 if
        filesystem detection proves flaky.)
    max_budget_usd:
        Hard cost cap. When exceeded, the SDK terminates cleanly with
        subtype='error_max_budget_usd' — safer than trusting our own
        counter.
    max_turns:
        Cap on agentic turns.
    permission_mode:
        'bypassPermissions' matches the old --dangerously-skip-permissions.
        Fine for now; lock down in a later phase.
    """
    options_kwargs = {
        "cwd": str(project_dir),
        "permission_mode": permission_mode,
    }
    if max_budget_usd is not None:
        options_kwargs["max_budget_usd"] = max_budget_usd
    if max_turns is not None:
        options_kwargs["max_turns"] = max_turns
    options = ClaudeAgentOptions(**options_kwargs)

    effective_prompt = prompt
    if agent_name:
        effective_prompt = f"Use the {agent_name} agent to complete the following task.\n\n{prompt}"

    assistant_texts: list[str] = []
    final: Optional[ResultMessage] = None

    async for message in query(prompt=effective_prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    assistant_texts.append(block.text)
        elif isinstance(message, ResultMessage):
            final = message

    if final is None:
        # Shouldn't happen with a normal query() run, but guard against it
        return ClaudeRunResult(
            success=False,
            is_error=True,
            subtype="error_no_result_message",
            session_id=None,
            total_cost_usd=0.0,
            num_turns=0,
            duration_ms=0,
            result_text=None,
            stop_reason=None,
            assistant_texts=assistant_texts,
            raw_error="query() ended without emitting a ResultMessage",
        )

    success = (not final.is_error) and (final.subtype == "success")
    return ClaudeRunResult(
        success=success,
        is_error=final.is_error,
        subtype=final.subtype,
        session_id=final.session_id,
        total_cost_usd=final.total_cost_usd or 0.0,
        num_turns=final.num_turns,
        duration_ms=final.duration_ms,
        result_text=final.result,
        stop_reason=final.stop_reason,
        assistant_texts=assistant_texts,
        raw_error=None if success else (final.result or f"subtype={final.subtype}"),
    )
