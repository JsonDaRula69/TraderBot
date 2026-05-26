"""Sandbox command group — agent filesystem isolation."""
from __future__ import annotations

import json as json_lib
import sys
from typing import Annotated

import typer
from rich.console import Console

from traderbot.cli.helpers import err_console

sandbox_app = typer.Typer(
    name="sandbox",
    help="Agent filesystem sandbox: isolate workspace, lock src/ read-only.",
    rich_markup_mode="rich",
)


@sandbox_app.command("enter")
def sandbox_enter() -> None:
    """Enter the sandbox: lock src/ read-only, create isolated workspace."""
    from traderbot.sandbox import FilesystemSandbox

    sandbox = FilesystemSandbox()
    if sandbox.status.value == "active":
        Console().print("[yellow]Sandbox is already active.[/yellow]")
        return

    try:
        sandbox.enter()
        Console().print(f"[green]Sandbox active[/green] (workspace: {sandbox.workspace_dir})")
        if sandbox.is_available():
            Console().print("[dim]macOS sandbox-exec enforcement enabled[/dim]")
        else:
            Console().print("[dim]Fallback: POSIX chmod enforcement[/dim]")
    except Exception as e:
        err_console.print(f"[red]Failed to enter sandbox:[/red] {e}")
        raise typer.Exit(code=1)


@sandbox_app.command("exit")
def sandbox_exit(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Exit the sandbox: restore permissions, workspace retained."""
    from traderbot.sandbox import FilesystemSandbox

    sandbox = FilesystemSandbox()
    sandbox.exit_sandbox()

    if json_output:
        json_lib.dump({"status": "sandbox_exited", "workspace": str(sandbox.workspace_dir)}, sys.stdout)
    else:
        Console().print("[green]Sandbox exited. Workspace retained at[/green]")
        Console().print(f"[dim]{sandbox.workspace_dir}[/dim]")


@sandbox_app.command("status")
def sandbox_status(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Show sandbox status: active/inactive, enforcement mode, workspace path."""
    from traderbot.sandbox import FilesystemSandbox, get_active_sandbox

    sandbox = get_active_sandbox() or FilesystemSandbox()
    source_readonly = sandbox.verify() if sandbox.status.value == "active" else False

    if json_output:
        json_lib.dump({
            "status": str(sandbox.status),
            "workspace": str(sandbox.workspace_dir),
            "src_root": str(sandbox.src_root),
            "source_readonly": source_readonly,
            "os_sandbox_available": sandbox.is_available(),
        }, sys.stdout)
        return

    console = Console()
    status_color = "green" if sandbox.status.value == "active" else "yellow"
    console.print(f"Status:       [{status_color}]{sandbox.status}[/{status_color}]")
    console.print(f"Workspace:    {sandbox.workspace_dir}")
    console.print(f"Source root:  {sandbox.src_root}")
    console.print(f"Source RO:    {'[green]Yes[/green]' if source_readonly else '[red]No[/red]'}")
    console.print(f"macOS sandbox:[{'green]Available[/green]' if sandbox.is_available() else 'yellow]Fallback (no sandbox-exec)[/yellow]'}")
