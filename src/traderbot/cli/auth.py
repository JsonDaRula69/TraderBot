"""Auth command group — API credential management."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import json as json_lib
import os
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from traderbot.cli.helpers import _mask_token, _write_token_to_env, err_console

auth_app = typer.Typer(
    name="auth",
    help="Manage API credentials via environment variables.",
    rich_markup_mode="rich",
)


@auth_app.command("list-keys")
def auth_list_keys() -> None:
    """List configured services and keys (never values)."""
    from traderbot.auth import AuthManager

    console = Console()
    mgr = AuthManager()
    services = mgr.list_services()

    if not services:
        console.print("No credentials configured.")
        return

    table = Table(title="Configured Credentials")
    table.add_column("Service", style="cyan")
    table.add_column("Keys")
    for s in services:
        table.add_row(s.name, ", ".join(s.keys))
    console.print(table)


@auth_app.command("rotate")
def auth_rotate(
    service: Annotated[str, typer.Argument(help="Service name to rotate")],
) -> None:
    """Rotate a credential (prompt for new values and update .env)."""
    from traderbot.auth import _ALL_SERVICES
    from traderbot.paths import get_data_dir

    console = Console()

    keys = _ALL_SERVICES.get(service)
    if keys is None:
        console.print(f"[red]Unknown service:[/red] {service}")
        raise typer.Exit(code=1)

    env_lines: list[str] = []
    for key in keys:
        new_val = typer.prompt(f"Enter new value for {service}.{key}", hide_input=True)
        env_key = f"{service.upper()}_{key.upper()}"
        env_lines.append(f"{env_key}={new_val}")
        console.print(f"[green]Updated[/green] {service}.{key}")

    if env_lines:
        env_path = get_data_dir() / ".env"
        env_path.parent.mkdir(parents=True, exist_ok=True)
        existing = env_path.read_text() if env_path.exists() else ""
        existing_lines = [l for l in existing.splitlines() if not any(l.startswith(ek.split("=")[0]) for ek in env_lines)]
        new_content = "\n".join(existing_lines).rstrip() + "\n" + "\n".join(env_lines) + "\n"
        env_path.write_text(new_content)
        os.chmod(env_path, 0o600)
        console.print(f"[dim]Credentials updated in {env_path}[/dim]")


@auth_app.command("check")
def auth_check(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Verify KALSHI_API_KEY is configured (keyring, .env, or environment)."""
    console = Console()
    from traderbot.auth import AuthManager
    mgr = AuthManager()
    result = mgr.get_credential("kalshi", "api_key")
    if result is not None:
        key = result.value.get_secret_value()
    else:
        key = None

    if key and key.strip():
        ok = True
        if json_output:
            print(json_lib.dumps({"status": "ok", "key_found": True}))
        else:
            console.print("[green]OK: KALSHI_API_KEY configured[/green]")
    else:
        ok = False
        if json_output:
            print(json_lib.dumps({"status": "missing", "key_found": False}))
        else:
            console.print("[red]Missing: KALSHI_API_KEY not found in .env or environment[/red]")

    if not ok and not json_output:
        console.print(
            "[dim]Add KALSHI_API_KEY to your .env file in the data directory.[/dim]"
        )


@auth_app.command("setup-master-password")
def auth_setup_master_password() -> None:
    """Create a new master password for trade/simulate command gating."""
    from traderbot.master_password import is_setup, setup_master_password

    if is_setup():
        err_console.print("[red]Master password already configured.[/red]")
        err_console.print("Use [bold]traderbot auth change-master-password[/bold] to change it.")
        raise typer.Exit(code=1)

    password = typer.prompt("New master password", hide_input=True, confirmation_prompt=True)
    try:
        setup_master_password(password)
        Console().print("[green]Master password created. Session authenticated for 30 minutes.[/green]")
    except ValueError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@auth_app.command("change-master-password")
def auth_change_master_password() -> None:
    """Change an existing master password (requires current password)."""
    from traderbot.master_password import change_master_password, is_setup

    if not is_setup():
        err_console.print("[red]No master password configured.[/red]")
        err_console.print("Run [bold]traderbot auth setup-master-password[/bold] first.")
        raise typer.Exit(code=1)

    old_password = typer.prompt("Current master password", hide_input=True)
    new_password = typer.prompt("New master password", hide_input=True, confirmation_prompt=True)
    try:
        change_master_password(old_password, new_password)
        Console().print("[green]Master password changed. Session authenticated for 30 minutes.[/green]")
    except (ValueError, FileNotFoundError) as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@auth_app.command("check-master-password")
def auth_check_master_password(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Check whether master password is configured and session is active.

    If configured but not active, attempts auto-authentication so that
    paper-mode trading agents can trade without manual password entry.
    """
    from traderbot.master_password import _try_auto_authenticate, is_setup, session_active

    configured = is_setup()
    if configured and not session_active():
        _try_auto_authenticate()
    active = session_active() if configured else False

    if json_output:
        json_lib.dump({"configured": configured, "session_active": active}, sys.stdout)
        return

    console = Console()
    if configured:
        console.print("[green]Master password: configured[/green]")
        if active:
            console.print("[green]Session: authenticated[/green]")
        else:
            console.print("[yellow]Session: not authenticated[/yellow]")
    else:
        console.print("[red]Master password: not configured[/red]")


@auth_app.command("set-kalshi")
def auth_set_kalshi() -> None:
    """Store Kalshi credentials in OS keyring (or .env fallback).

    If credentials already exist in .env, reads from there.
    Only prompts if missing.
    """
    from pathlib import Path
    from traderbot.auth import AuthManager

    console = Console()
    env_path = Path.home() / ".traderbot" / ".env"

    # Try to read existing .env credentials first
    api_key = None
    private_key_pem = None
    if env_path.exists():
        env_content = env_path.read_text(encoding="utf-8")
        for line in env_content.splitlines():
            if line.startswith("KALSHI_API_KEY="):
                api_key = line.split("=", 1)[1].strip().strip("'\"")
            elif line.startswith("KALSHI_PRIVATE_KEY_PATH="):
                pem_path = line.split("=", 1)[1].strip().strip("'\"")
                pem_file = Path(pem_path)
                if pem_file.exists():
                    private_key_pem = pem_file.read_text(encoding="utf-8")

    # Prompt only if still missing
    if not api_key:
        api_key = typer.prompt("KALSHI_API_KEY", hide_input=True)
    if not private_key_pem:
        private_key_pem = typer.prompt("KALSHI_PRIVATE_KEY_PEM", hide_input=True)

    mgr = AuthManager()
    api_source = mgr.set_credential("kalshi", "api_key", api_key)
    pem_source = mgr.set_credential("kalshi", "private_key_pem", private_key_pem)

    console.print(f"[green]✓[/green] KALSHI_API_KEY stored in {api_source}")
    console.print(f"[green]✓[/green] KALSHI_PRIVATE_KEY_PEM stored in {pem_source}")
    if api_source == ".env" or pem_source == ".env":
        console.print("[yellow]Keyring unavailable; credentials stored in .env file.[/yellow]")


@auth_app.command("migrate")
def auth_migrate(
    service: Annotated[
        str | None,
        typer.Option("--service", "-s", help="Service to migrate (default: all)"),
    ] = None,
) -> None:
    """Migrate credentials from .env to OS keyring."""
    from traderbot.auth import AuthManager

    console = Console()
    mgr = AuthManager()
    result = mgr.migrate_to_keyring(service)

    if result["migrated"] == 0 and result["skipped"] == 0:
        console.print("[yellow]Keyring unavailable; migration skipped.[/yellow]")
    elif result["migrated"] > 0:
        console.print(f"[green]Migrated {result['migrated']} credential(s) to keyring.[/green]")
        if result["skipped"] > 0:
            console.print(f"[dim]Skipped {result['skipped']} (already in keyring or not found).[/dim]")
    else:
        console.print("[dim]No new credentials to migrate.[/dim]")


@auth_app.command("delete-key")
def auth_delete_key(
    service: Annotated[str, typer.Argument(help="Service name")],
    key: Annotated[str, typer.Argument(help="Key name (e.g., api_key)")],
) -> None:
    """Delete a credential from OS keyring."""
    from traderbot.auth import AuthManager

    console = Console()
    mgr = AuthManager()
    if mgr.delete_credential(service, key):
        console.print(f"[green]Deleted {service}.{key} from keyring.[/green]")
    else:
        console.print(f"[yellow]{service}.{key} not found in keyring or keyring unavailable.[/yellow]")


@auth_app.command("clear-session")
def auth_clear_session(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Clear the current authenticated session token."""
    from traderbot.master_password import clear_session

    clear_session()
    if json_output:
        json_lib.dump({"status": "session_cleared"}, sys.stdout)
    else:
        Console().print("[green]Session token cleared. Authentication will be required for next trade/simulate.[/green]")
