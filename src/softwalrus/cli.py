"""Command-line interface for SoftWalrus.

Subcommands (Phase 1):
    run       — start a new pipeline run for a request
    resume    — resume the current pipeline from the last checkpoint
    status    — print the current state without advancing the graph

Everything is async under the hood. Typer's sync commands wrap `asyncio.run`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import typer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from rich.console import Console
from rich.pretty import pprint

from .graph import build_graph
from .paths import ensure_state_dir, state_db_path

app = typer.Typer(add_completion=False, help="SoftWalrus pipeline orchestrator")
console = Console()

# One thread per project; each project has its own state.db anyway. If we
# ever want parallel runs within a single project we can accept a --thread flag.
THREAD_ID = "main"


def _resolve_project_dir(project_dir: Optional[Path]) -> Path:
    resolved = (project_dir or Path.cwd()).resolve()
    if not resolved.exists():
        raise typer.BadParameter(f"project dir does not exist: {resolved}")
    return resolved


def _thread_config() -> dict:
    return {"configurable": {"thread_id": THREAD_ID}}


async def _run_new(project_dir: Path, request: str) -> None:
    ensure_state_dir(project_dir)
    db_path = state_db_path(project_dir)

    builder = build_graph(project_dir)
    async with AsyncSqliteSaver.from_conn_string(str(db_path)) as saver:
        graph = builder.compile(checkpointer=saver)
        initial_state = {"request": request, "total_cost_usd": 0.0}
        final = await graph.ainvoke(initial_state, config=_thread_config())
        console.print("[bold green]Run complete.[/bold green]")
        console.print("Final state:")
        pprint(final, console=console)


async def _resume(project_dir: Path) -> None:
    ensure_state_dir(project_dir)
    db_path = state_db_path(project_dir)
    if not db_path.exists():
        console.print("[bold red]No state.db found — nothing to resume.[/bold red]")
        raise typer.Exit(code=1)

    builder = build_graph(project_dir)
    async with AsyncSqliteSaver.from_conn_string(str(db_path)) as saver:
        graph = builder.compile(checkpointer=saver)
        # Passing None as input tells LangGraph to continue from the checkpoint.
        final = await graph.ainvoke(None, config=_thread_config())
        console.print("[bold green]Resume complete.[/bold green]")
        console.print("Final state:")
        pprint(final, console=console)


async def _status(project_dir: Path) -> None:
    db_path = state_db_path(project_dir)
    if not db_path.exists():
        console.print("[bold yellow]No state.db found for this project.[/bold yellow]")
        raise typer.Exit(code=0)

    builder = build_graph(project_dir)
    async with AsyncSqliteSaver.from_conn_string(str(db_path)) as saver:
        graph = builder.compile(checkpointer=saver)
        snapshot = await graph.aget_state(config=_thread_config())
        if snapshot is None or snapshot.values == {}:
            console.print("[bold yellow]No state recorded on this thread.[/bold yellow]")
            return
        console.print("[bold]Next node(s):[/bold]", snapshot.next or "(pipeline finished)")
        console.print("[bold]State values:[/bold]")
        pprint(snapshot.values, console=console)
        if snapshot.tasks:
            console.print("[bold]Pending tasks:[/bold]")
            pprint(list(snapshot.tasks), console=console)


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
    asyncio.run(_run_new(pd, request))


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
    asyncio.run(_resume(pd))


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
