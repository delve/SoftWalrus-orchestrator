"""Shared machinery for node functions.

The pattern every node follows:
    1. Determine expected JSON output path.
    2. Hash it (or note absence) before invocation.
    3. Render prompt from the target project's slash command.
    4. Invoke the agent via the Claude SDK.
    5. Validate the output against SoftWalrus's contract.
    6. Build a NodeResult breadcrumb + an InvocationRecord + any layer/state
       updates the caller needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..claude import ClaudeRunResult, run_agent
from ..commands import render_command
from ..contract import ValidatedOutput, file_sha256, validate
from ..state import InvocationRecord, NodeResult


@dataclass
class InvocationOutcome:
    """Everything the caller needs after invoking one node."""
    claude: ClaudeRunResult
    validated: ValidatedOutput
    node_result: NodeResult
    invocation_record: InvocationRecord


async def invoke_and_validate(
    *,
    project_dir: Path,
    node_kind: str,
    layer_id: Optional[str],
    round_number: int,
    agent_name: str,
    command_name: str,
    command_arguments: list[str],
    output_path: Path,
    prompt_suffix: str = "",
) -> InvocationOutcome:
    """Do the full run+validate cycle for one node. Returns everything the
    caller needs to update state.

    Halt-message ownership rule:
      - Claude SDK failures (subtype != 'success'): SoftWalrus-authored.
      - Node output validation failures: SoftWalrus-authored (contract.validate builds these).
      - status: 'failed' inside the node's own envelope: node's `error` field verbatim.
    """
    hash_before = file_sha256(output_path)

    template = render_command(project_dir, command_name, arguments=command_arguments)
    prompt = template if not prompt_suffix else f"{template}\n\n{prompt_suffix}"

    claude = await run_agent(
        prompt=prompt,
        project_dir=project_dir,
        agent_name=agent_name,
    )

    # If Claude itself blew up, that's a SoftWalrus-authored halt.
    if not claude.success:
        halt_msg = (
            f"Agent invocation failed: subtype={claude.subtype}"
            + (f"; {claude.raw_error}" if claude.raw_error else "")
        )
        node_result: NodeResult = {
            "agent": agent_name,
            "session_id": claude.session_id,
            "cost_usd": claude.total_cost_usd,
            "success": False,
            "error": halt_msg,
            "output_summary": halt_msg,
        }
        return InvocationOutcome(
            claude=claude,
            validated=ValidatedOutput(ok=False, halt_message=halt_msg),
            node_result=node_result,
            invocation_record=InvocationRecord(
                node=node_kind,
                layer_id=layer_id,
                round=round_number,
                ok=False,
                artifacts={},
                envelope_message="",
                halt_message=halt_msg,
            ),
        )

    # Claude returned success. Now validate the on-disk contract.
    validated = validate(output_path, node_kind=node_kind, hash_before=hash_before)

    envelope_msg = validated.envelope.get("message", "") if validated.envelope else ""

    node_result = {
        "agent": agent_name,
        "session_id": claude.session_id,
        "cost_usd": claude.total_cost_usd,
        "success": validated.ok,
        "error": None if validated.ok else validated.halt_message,
        "output_summary": envelope_msg if validated.ok else (validated.halt_message or ""),
    }
    invocation_record: InvocationRecord = {
        "node": node_kind,
        "layer_id": layer_id,
        "round": round_number,
        "ok": validated.ok,
        "artifacts": validated.artifacts if validated.ok else {},
        "envelope_message": envelope_msg,
        "halt_message": None if validated.ok else validated.halt_message,
    }

    return InvocationOutcome(
        claude=claude,
        validated=validated,
        node_result=node_result,
        invocation_record=invocation_record,
    )
