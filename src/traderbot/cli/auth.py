"""Auth command group — API credential management."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import json as json_lib
import os
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from traderbot.cli.helpers import report_cli_error

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
        report_cli_error(f"Unknown service: {service}")

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
        existing_lines = [
            l
            for l in existing.splitlines()
            if not any(l.startswith(ek.split("=")[0]) for ek in env_lines)
        ]
        new_content = "\n".join(existing_lines).rstrip() + "\n" + "\n".join(env_lines) + "\n"
        env_path.write_text(new_content)
        os.chmod(env_path, 0o600)
        console.print(f"[dim]Credentials updated in {env_path}[/dim]")


@auth_app.command("check")
def auth_check(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    validate: Annotated[
        bool, typer.Option("--validate", help="Validate credentials against Kalshi API")
    ] = False,
    validate_scopes: Annotated[
        bool,
        typer.Option(
            "--validate-scopes",
            help="Full scope validation: tests authenticated endpoints and reports scope coverage",
        ),
    ] = False,
) -> None:
    """Verify KALSHI_API_KEY is configured (keyring, .env, or environment).

    With --validate, tests credentials against the authenticated /portfolio/balance endpoint.
    With --validate-scopes, also probes /portfolio/settlements to verify scope coverage.
    """
    console = Console()
    from traderbot.auth import AuthManager

    mgr = AuthManager()
    result = mgr.get_credential("kalshi", "api_key")
    if result is not None:
        key = result.value.get_secret_value()
    else:
        key = None

    key_found = bool(key and key.strip())

    output: dict[str, object] = {
        "status": "ok" if key_found else "missing",
        "key_found": key_found,
    }

    if key_found and (validate or validate_scopes):
        try:
            import asyncio

            from traderbot.exceptions import AuthenticationError
            from traderbot.kalshi.client import KalshiClient

            async def _test_endpoints() -> dict[str, object]:
                client = KalshiClient()
                results: dict[str, object] = {}

                # Authenticated endpoint: portfolio balance
                try:
                    resp = await client.get("/portfolio/balance")
                    results["portfolio_balance"] = resp.status_code == 200
                    if resp.status_code == 401:
                        results["portfolio_balance_error"] = (
                            "INCORRECT_API_KEY_SIGNATURE: API key and PEM private key don't match. "
                            "Run `traderbot auth set-kalshi` to re-register your credentials."
                        )
                except AuthenticationError as exc:
                    results["portfolio_balance"] = False
                    results["portfolio_balance_error"] = (
                        f"INCORRECT_API_KEY_SIGNATURE: {exc}. "
                        "Run `traderbot auth set-kalshi` to re-register your credentials."
                    )
                except Exception as exc:
                    results["portfolio_balance"] = False
                    results["portfolio_balance_error"] = str(exc)

                if validate_scopes:
                    # Authenticated endpoint: portfolio settlements
                    try:
                        resp = await client.get("/portfolio/settlements")
                        results["portfolio_settlements"] = resp.status_code == 200
                        if resp.status_code == 401:
                            results["portfolio_settlements_error"] = (
                                "INCORRECT_API_KEY_SIGNATURE: API key and PEM private key don't match. "
                                "Run `traderbot auth set-kalshi` to re-register your credentials."
                            )
                    except AuthenticationError as exc:
                        results["portfolio_settlements"] = False
                        results["portfolio_settlements_error"] = (
                            f"INCORRECT_API_KEY_SIGNATURE: {exc}. "
                            "Run `traderbot auth set-kalshi` to re-register your credentials."
                        )
                    except Exception as exc:
                        results["portfolio_settlements"] = False
                        results["portfolio_settlements_error"] = str(exc)

                await client.close()
                return results

            endpoint_results = asyncio.run(_test_endpoints())
            output.update(endpoint_results)
        except (AuthenticationError, Exception) as exc:
            output["api_valid"] = False
            output["error"] = str(exc)

    if json_output:
        json_lib.dump(output, sys.stdout, default=str)
        return

    if key_found:
        console.print("[green]OK: KALSHI_API_KEY configured[/green]")
        if validate:
            if output.get("portfolio_balance"):
                console.print("[green]Authenticated: /portfolio/balance OK[/green]")
            else:
                console.print(
                    f"[red]Authenticated: /portfolio/balance failed — {output.get('portfolio_balance_error', 'unknown error')}[/red]"
                )
        if validate_scopes:
            if output.get("portfolio_balance"):
                console.print(
                    "[green]✅ Authenticated: /portfolio/balance OK (portfolio:read scope)[/green]"
                )
            else:
                console.print(
                    f"[red]❌ Authenticated: /portfolio/balance failed — {output.get('portfolio_balance_error', 'unknown error')}[/red]"
                )
            if output.get("portfolio_settlements"):
                console.print(
                    "[green]✅ Authenticated: /portfolio/settlements OK (portfolio:read scope)[/green]"
                )
            else:
                console.print(
                    f"[red]❌ Authenticated: /portfolio/settlements failed — {output.get('portfolio_settlements_error', 'unknown error')}[/red]"
                )
    else:
        console.print("[red]Missing: KALSHI_API_KEY not found in .env or environment[/red]")
        console.print("[dim]Add KALSHI_API_KEY to your .env file in the data directory.[/dim]")


@auth_app.command("setup-master-password")
def auth_setup_master_password() -> None:
    """Create a new master password for trade/simulate command gating."""
    from traderbot.master_password import is_setup, setup_master_password

    if is_setup():
        report_cli_error("Master password already configured. Use 'traderbot auth change-master-password' to change it.")

    password = typer.prompt("New master password", hide_input=True, confirmation_prompt=True)
    try:
        setup_master_password(password)
        Console().print(
            "[green]Master password created. Session authenticated for 30 minutes.[/green]"
        )
    except ValueError as e:
        report_cli_error(str(e))


@auth_app.command("change-master-password")
def auth_change_master_password() -> None:
    """Change an existing master password (requires current password)."""
    from traderbot.master_password import change_master_password, is_setup

    if not is_setup():
        report_cli_error("No master password configured. Run 'traderbot auth setup-master-password' first.")

    old_password = typer.prompt("Current master password", hide_input=True)
    new_password = typer.prompt("New master password", hide_input=True, confirmation_prompt=True)
    try:
        change_master_password(old_password, new_password)
        Console().print(
            "[green]Master password changed. Session authenticated for 30 minutes.[/green]"
        )
    except (ValueError, FileNotFoundError) as e:
        report_cli_error(str(e))


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
def auth_set_kalshi(
    api_key: Annotated[
        Optional[str], typer.Option("--api-key", help="API key (non-interactive)")
    ] = None,
    pem: Annotated[
        Optional[str], typer.Option("--pem", help="PEM key path (non-interactive)")
    ] = None,
) -> None:
    """Store Kalshi credentials in OS keyring (or .env fallback).

    Always prompts for both API key and PEM — ignores any existing values
    in .env so you can rotate credentials without manual cleanup.

    The PEM key is saved to a file (kalshi_key.pem) and referenced by path
    in .env. The PEM content is NOT stored inline in .env because python-dotenv
    does not support multi-line values — storing inline truncates to the first
    line, breaking every authenticated API call.

    Use --api-key and --pem together for non-interactive (cron) usage.
    The --pem flag takes a file path; the PEM content is read from that file.
    """
    from traderbot.auth import AuthManager
    from traderbot.paths import get_data_dir

    console = Console()
    env_path = get_data_dir() / ".env"
    pem_file = get_data_dir() / "kalshi_key.pem"

    if api_key is not None and pem is not None:
        # Non-interactive mode: both flags provided
        console.print(
            "[yellow]Warning: API key provided via CLI argument — may be visible in process listings and shell history.[/yellow]"
        )
        pem_path = Path(pem)
        if not pem_path.is_file():
            report_cli_error(f"PEM file not found: {pem}")
        private_key_pem = pem_path.read_text(encoding="utf-8").strip()
        if not private_key_pem or "PRIVATE KEY" not in private_key_pem:
            report_cli_error("PEM file does not contain a valid private key.")
    elif api_key is not None or pem is not None:
        report_cli_error("Both --api-key and --pem are required for non-interactive mode.")
    else:
        # Interactive mode: prompt for both
        api_key = typer.prompt("KALSHI_API_KEY")
        console.print("[dim]Paste the full multi-line PEM key (Ctrl+D when done):[/dim]")
        private_key_pem = sys.stdin.read().strip()
        if not private_key_pem:
            report_cli_error("No PEM key provided.")

    pem_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    pem_file.write_text(private_key_pem.strip() + "\n", encoding="utf-8")
    pem_file.chmod(0o600)
    # Write both KALSHI_API_KEY and KALSHI_PRIVATE_KEY_PATH to .env
    env_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    old_lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    new_lines = [
        l
        for l in old_lines
        if not l.startswith("KALSHI_API_KEY=")
        and not l.startswith("KALSHI_PRIVATE_KEY_PATH=")
        and not l.startswith("KALSHI_PRIVATE_KEY_PEM=")
    ]
    new_lines.append(f"KALSHI_API_KEY={api_key}")
    new_lines.append(f"KALSHI_PRIVATE_KEY_PATH={pem_file}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    console.print(f"[green]✓[/green] RSA key saved to {pem_file}")

    mgr = AuthManager()
    api_source = mgr.set_credential("kalshi", "api_key", api_key)
    console.print(f"[green]✓[/green] KALSHI_API_KEY stored in {api_source} (and .env)")
    console.print(
        "[yellow]KALSHI_PRIVATE_KEY stored in kalshi_key.pem (referenced by KALSHI_PRIVATE_KEY_PATH in .env).[/yellow]"
    )


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
            console.print(
                f"[dim]Skipped {result['skipped']} (already in keyring or not found).[/dim]"
            )
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
        console.print(
            f"[yellow]{service}.{key} not found in keyring or keyring unavailable.[/yellow]"
        )


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
        Console().print(
            "[green]Session token cleared. Authentication will be required for next trade/simulate.[/green]"
        )
