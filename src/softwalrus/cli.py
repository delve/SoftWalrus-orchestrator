"""Command-line interface for SoftWalrus.

Subcommands:
    run       — start a new pipeline run for a request
    resume    — resume the current pipeline from the last checkpoint
    status    — print the current state without advancing the graph

Interrupts pause the graph after the architect and after each reviewer
pass that reaches convergence. `resume` picks up from the interrupt.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

import typer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from rich.console import Console
from rich.pretty import pprint

from .graph import INTERRUPT_AFTER, build_graph
from .paths import ensure_state_dir, state_db_path

app = typer.Typer(add_completion=False, help="SoftWalrus pipeline orchestrator")
console = Console()

THREAD_ID = "main"


def _resolve_project_dir(project_dir: Optional[Path]) -> Path:
    resolved = (project_dir or Path.cwd()).resolve()
    if not resolved.exists():
        raise typer.BadParameter(f"project dir does not exist: {resolved}")
    return resolved


def _thread_config() -> dict:
    return {"configurable": {"thread_id": THREAD_ID}}


def _render_pause(snapshot: Any) -> None:
    console.print()
    console.print("[bold cyan]Pipeline paused for review.[/bold cyan]")
    if snapshot.next:
        console.print(f"Next node(s): [bold]{', '.join(snapshot.next)}[/bold]")
    console.print("Current state summary:")
    values = snapshot.values or {}
    if "plan" in values:
        plan = values["plan"]
        console.print(
            f"  request: [italic]{plan.get('request_summary', '(none)')}[/italic]"
        )
        console.print(f"  architecture_updated: {plan.get('architecture_updated')}")
        console.print(f"  designer_needed: {plan.get('designer_needed')}")
        console.print(f"  layers: {[l['id'] for l in plan.get('layers', [])]}")
    if "layers" in values:
        console.print("  layer status:")
        for lid, layer in values["layers"].items():
            console.print(
                f"    - {lid}: {layer.get('status')} "
                f"(rounds={layer.get('rounds', 0)}, ${layer.get('cost_usd', 0):.2f})"
            )
    console.print(f"  total_cost_usd: ${values.get('total_cost_usd', 0):.2f}")
    console.print()
    console.print("Edit handoff files now if needed, then run "
                  "[bold]softwalrus resume[/bold] to continue.")


def _render_final(final_state: dict) -> None:
    console.print()
    console.print("[bold green]Pipeline complete.[/bold green]")
    console.print("Final state:")
    pprint(final_state, console=console)


async def _invoke(project_dir: Path, initial: Optional[dict]) -> None:
    ensure_state_dir(project_dir)
    db_path = state_db_path(project_dir)
    builder = build_graph(project_dir)
    async with AsyncSqliteSaver.from_conn_string(str(db_path)) as saver:
        graph = builder.compile(
            checkpointer=saver,
            interrupt_after=INTERRUPT_AFTER,
        )
        final = await graph.ainvoke(initial, config=_thread_config())
        # After ainvoke returns, check whether we paused at an interrupt
        # or completed. get_state tells us next-nodes; if present, we paused.
        snapshot = await graph.aget_state(config=_thread_config())
        if snapshot and snapshot.next:
            _render_pause(snapshot)
        else:
            _render_final(final)


async def _status(project_dir: Path) -> None:
    db_path = state_db_path(project_dir)
    if not db_path.exists():
        console.print("[bold yellow]No state.db found for this project.[/bold yellow]")
        return
    builder = build_graph(project_dir)
    async with AsyncSqliteSaver.from_conn_string(str(db_path)) as saver:
        graph = builder.compile(checkpointer=saver, interrupt_after=INTERRUPT_AFTER)
        snapshot = await graph.aget_state(config=_thread_config())
        if snapshot is None or not snapshot.values:
            console.print("[bold yellow]No state recorded on this thread.[/bold yellow]")
            return
        console.print("[bold]Next node(s):[/bold]", snapshot.next or "(pipeline finished)")
        console.print("[bold]State values:[/bold]")
        pprint(snapshot.values, console=console)


@app.command()
def run(
    request: str = typer.Option(..., "--request", "-r", help="User-level request text"),
    project_dir: Optional[Path] = typer.Option(
        None, "--project-dir", "-p",
        help="Target project directory (defaults to cwd)",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Start a new pipeline run."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    pd = _resolve_project_dir(project_dir)
    asyncio.run(_invoke(pd, {"request": request, "total_cost_usd": 0.0, "layers": {}}))


@app.command()
def resume(
    project_dir: Optional[Path] = typer.Option(
        None, "--project-dir", "-p",
        help="Target project directory (defaults to cwd)",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Resume the current pipeline from its last checkpoint."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    pd = _resolve_project_dir(project_dir)
    asyncio.run(_invoke(pd, None))


@app.command()
def status(
    project_dir: Optional[Path] = typer.Option(
        None, "--project-dir", "-p",
        help="Target project directory (defaults to cwd)",
    ),
) -> None:
    """Print the current pipeline state without running anything."""
    pd = _resolve_project_dir(project_dir)
    asyncio.run(_status(pd))


if __name__ == "__main__":
    app()
