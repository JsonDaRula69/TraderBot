"""Interactive setup wizard — replaces installer's interactive_config_flow for pipx users."""

from __future__ import annotations

import dataclasses
import json as json_lib
import logging
import sys
from typing import Annotated

import typer
from rich.console import Console

from traderbot.cli.helpers import (
    _python_version_ok,
)

logger = logging.getLogger(__name__)

# Services from _ALL_SERVICES excluding kalshi (handled separately)
_OPTIONAL_SERVICES: dict[str, str] = {
    "newsapi": "NewsAPI.org (headlines, search)",
    "voyage": "Voyage AI (embeddings)",
    "twitter": "Twitter/X API",
    "reddit": "Reddit API",
    "coingecko": "CoinGecko (crypto prices)",
    "openweathermap": "OpenWeatherMap (weather data)",
    "fred": "FRED (economic data)",
}


@dataclasses.dataclass
class StepResult:
    """Result of a single setup step."""

    step: str
    status: str  # "ok", "skipped", "error", "warning"
    message: str
    details: dict | None = None


def _console_step(console: Console, number: int, title: str) -> None:
    console.print(f"\n[bold]Step {number}: {title}[/bold]")


def _step_python_version(dry_run: bool = False) -> StepResult:
    py_ok, version_str, _ = _python_version_ok()
    if py_ok:
        return StepResult(
            step="python_version",
            status="ok",
            message=f"Python {version_str} is compatible (3.12.x required)",
        )
    return StepResult(
        step="python_version",
        status="error",
        message=f"Python {version_str} detected — 3.12.x required for chromadb dependency.",
    )


def _step_data_dir(dry_run: bool = False) -> StepResult:
    from traderbot.paths import get_data_dir

    data_dir = get_data_dir()
    if dry_run:
        return StepResult(
            step="data_dir",
            status="ok",
            message=f"Would create data directory at {data_dir}",
            details={"path": str(data_dir), "exists": data_dir.exists()},
        )

    data_dir.mkdir(parents=True, exist_ok=True)
    data_dir.chmod(0o700)
    return StepResult(
        step="data_dir",
        status="ok",
        message=f"Data directory ready at {data_dir}",
        details={"path": str(data_dir), "exists": True},
    )


def _step_db_init(dry_run: bool = False) -> StepResult:
    from traderbot.db import DB_PATH, get_connection, init_schema

    db_path = DB_PATH
    if dry_run:
        return StepResult(
            step="db_init",
            status="ok",
            message=f"Would initialize database at {db_path}",
            details={"path": str(db_path)},
        )

    try:
        with get_connection(db_path) as conn:
            init_schema(conn)
        return StepResult(
            step="db_init",
            status="ok",
            message=f"Database initialized at {db_path}",
            details={"path": str(db_path)},
        )
    except Exception as exc:
        logger.exception("Database initialization failed")
        return StepResult(
            step="db_init",
            status="error",
            message=f"Database init failed: {exc}",
            details={"path": str(db_path)},
        )


def _step_kalshi_credentials(
    console: Console, non_interactive: bool = False, dry_run: bool = False
) -> StepResult:
    from traderbot.auth import AuthManager

    mgr = AuthManager()
    result = mgr.get_credential("kalshi", "api_key")
    if result is not None and result.value.get_secret_value():
        return StepResult(
            step="kalshi_credentials",
            status="ok",
            message="Kalshi credentials already configured (keyring/env)",
        )

    if dry_run or non_interactive:
        return StepResult(
            step="kalshi_credentials",
            status="warning",
            message="Kalshi credentials not configured — run 'traderbot auth set-kalshi' to add them",
        )

    console.print("  Kalshi credentials are required for trading.")
    console.print("  Sign up at https://kalshi.com and generate an API key + RSA key pair.")
    setup_now = typer.confirm("  Configure Kalshi now?", default=True)
    if not setup_now:
        return StepResult(
            step="kalshi_credentials",
            status="skipped",
            message="Skipped — run 'traderbot auth set-kalshi' later to configure",
        )

    api_key = typer.prompt("  KALSHI_API_KEY")
    if not api_key:
        return StepResult(
            step="kalshi_credentials",
            status="error",
            message="No API key provided",
        )

    console.print("  Paste the full multi-line PEM key (press Enter then Ctrl+D when done):")
    pem_input = sys.stdin.read().strip()
    if not pem_input:
        return StepResult(
            step="kalshi_credentials",
            status="error",
            message="No PEM key provided",
        )

    from traderbot.paths import get_data_dir

    env_path = get_data_dir() / ".env"
    pem_file = get_data_dir() / "kalshi_key.pem"
    pem_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    pem_file.write_text(pem_input.strip() + "\n", encoding="utf-8")
    pem_file.chmod(0o600)

    env_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    old_lines = (
        env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    )
    new_lines = [
        line
        for line in old_lines
        if not line.startswith("KALSHI_API_KEY=")
        and not line.startswith("KALSHI_PRIVATE_KEY_PATH=")
        and not line.startswith("KALSHI_PRIVATE_KEY_PEM=")
    ]
    new_lines.append(f"KALSHI_API_KEY={api_key}")
    new_lines.append(f"KALSHI_PRIVATE_KEY_PATH={pem_file}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    mgr.set_credential("kalshi", "api_key", api_key)
    return StepResult(
        step="kalshi_credentials",
        status="ok",
        message="Kalshi credentials saved (API key masked)",
    )


def _step_optional_services(
    console: Console, non_interactive: bool = False, dry_run: bool = False
) -> StepResult:
    from traderbot.auth import AuthManager

    mgr = AuthManager()
    configured: list[str] = []
    skipped: list[str] = []

    for service, description in _OPTIONAL_SERVICES.items():
        existing = mgr.get_credential(service, "api_key")
        if existing is not None and existing.value.get_secret_value():
            configured.append(service)
            continue

        if non_interactive or dry_run:
            skipped.append(service)
            continue

        configure = typer.confirm(f"  Configure {service} ({description})?", default=False)
        if not configure:
            skipped.append(service)
            continue

        if service == "coingecko":
            api_key = typer.prompt(f"    {service.upper()}_API_KEY", default="")
            if api_key:
                mgr.set_credential("coingecko", "api_key", api_key)
                tier = typer.prompt("    COINGECKO_TIER (demo/pro)", default="demo")
                mgr.set_credential("coingecko", "tier", tier)
                configured.append(service)
            else:
                skipped.append(service)
        else:
            api_key = typer.prompt(f"    {service.upper()}_API_KEY", default="", hide_input=True)
            if api_key:
                mgr.set_credential(service, "api_key", api_key)
                configured.append(service)
            else:
                skipped.append(service)

    details = {"configured": configured, "skipped": skipped}
    if not configured and not skipped:
        return StepResult(
            step="optional_services",
            status="ok",
            message="No additional services configured (all optional)",
            details=details,
        )
    msg_parts = []
    if configured:
        msg_parts.append(f"Configured: {', '.join(configured)}")
    if skipped:
        msg_parts.append(f"Skipped: {', '.join(skipped)}")
    return StepResult(
        step="optional_services",
        status="ok",
        message=" | ".join(msg_parts),
        details=details,
    )


def _step_master_password(
    console: Console, non_interactive: bool = False, dry_run: bool = False
) -> StepResult:
    from traderbot.master_password import is_setup, setup_master_password

    if is_setup():
        return StepResult(
            step="master_password",
            status="ok",
            message="Master password already configured",
        )

    if dry_run or non_interactive:
        return StepResult(
            step="master_password",
            status="warning",
            message="Master password not configured — run 'traderbot auth setup-master-password' to set one",
        )

    console.print("  A master password protects trade and simulate commands.")
    console.print("  OS keyring is recommended for credential storage.")
    setup_now = typer.confirm("  Set up master password now?", default=True)
    if not setup_now:
        return StepResult(
            step="master_password",
            status="skipped",
            message="Skipped — run 'traderbot auth setup-master-password' later",
        )

    try:
        password = typer.prompt(
            "  New master password (min 8 chars)", hide_input=True, confirmation_prompt=True
        )
        setup_master_password(password)
        return StepResult(
            step="master_password",
            status="ok",
            message="Master password created — session authenticated for 30 minutes",
        )
    except ValueError as exc:
        return StepResult(
            step="master_password",
            status="error",
            message=str(exc),
        )


def _step_profile_creation(
    console: Console, non_interactive: bool = False, dry_run: bool = False
) -> StepResult:
    from traderbot.profiles.registry import ProfileRegistry

    registry = ProfileRegistry()
    existing_profiles = registry.list_profiles()

    if existing_profiles:
        return StepResult(
            step="profile_creation",
            status="ok",
            message=f"Profiles already exist: {', '.join(existing_profiles)}",
            details={"profiles": existing_profiles},
        )

    if dry_run or non_interactive:
        return StepResult(
            step="profile_creation",
            status="warning",
            message="No profiles found — run 'traderbot profile create' to create one",
        )

    console.print("  No trading profiles found.")
    create_now = typer.confirm("  Create a default paper trading profile?", default=True)
    if not create_now:
        return StepResult(
            step="profile_creation",
            status="skipped",
            message="Skipped — run 'traderbot profile create' later",
        )

    try:
        from traderbot.kalshi.models import MarketCategory
        from traderbot.profiles.models import TradingProfile

        default_categories = [
            cat
            for cat in MarketCategory
            if cat.value
            not in ("elections", "social", "mentions", "entertainment", "companies")
        ]

        profile = TradingProfile(
            name="default",
            mode="paper",
            description="Default paper trading profile",
            enabled_categories=default_categories,
            risk_multiplier=1.0,
            max_position_per_market_pct=5.0,
            max_daily_loss_pct=5.0,
            max_drawdown_pct=20.0,
            max_open_positions=10,
            min_liquidity_threshold=100,
            min_edge_pct=2.0,
            initial_balance_cents=10000,
        )
        registry.create_profile(profile)
        return StepResult(
            step="profile_creation",
            status="ok",
            message=f"Created profile 'default' (paper mode, ${profile.initial_balance_cents / 100:.2f})",
            details={"profile": "default", "mode": "paper"},
        )
    except Exception as exc:
        logger.exception("Profile creation failed")
        return StepResult(
            step="profile_creation",
            status="error",
            message=f"Failed to create profile: {exc}",
        )


def _print_summary(
    console: Console, results: list[StepResult], json_output: bool = False
) -> None:
    if json_output:
        json_lib.dump(
            {
                "results": [
                    {
                        "step": r.step,
                        "status": r.status,
                        "message": r.message,
                        "details": r.details,
                    }
                    for r in results
                ]
            },
            sys.stdout,
            default=str,
        )
        return

    ok_count = sum(1 for r in results if r.status == "ok")
    warn_count = sum(1 for r in results if r.status in ("warning", "skipped"))
    err_count = sum(1 for r in results if r.status == "error")

    console.print("\n[bold]=== Setup Summary ===[/bold]\n")
    for r in results:
        icon = {"ok": "✓", "warning": "⚠", "skipped": "○", "error": "✗"}.get(r.status, "?")
        color = {"ok": "green", "warning": "yellow", "skipped": "dim", "error": "red"}.get(
            r.status, ""
        )
        console.print(f"  [{color}]{icon}[/{color}] {r.message}")

    console.print(
        f"\n[bold]{ok_count} ok, {warn_count} warnings/skipped, {err_count} errors[/bold]"
    )

    if err_count > 0:
        console.print(
            "\n[yellow]Some steps had errors. Review the output above for details.[/yellow]"
        )

    if ok_count >= 6:
        console.print("\n[bold green]Next steps:[/bold green]")
        console.print("  • [dim]traderbot heartbeat[/dim]    — run self-review cycle")
        console.print("  • [dim]traderbot data settle[/dim]  — check for settlements")
        console.print("  • [dim]traderbot scan[/dim]         — explore active markets")


def _run_setup_steps(
    console: Console,
    *,
    dry_run: bool = False,
    non_interactive: bool = False,
    no_creds: bool = False,
    json_output: bool = False,
) -> int:
    """Run all setup steps and return exit code (0 = all good, 1 = errors)."""
    results: list[StepResult] = []

    # Step 1: Python version
    if not json_output:
        _console_step(console, 1, "Python Version Check")
    r1 = _step_python_version(dry_run=dry_run)
    results.append(r1)
    if not json_output:
        icon = "✓" if r1.status == "ok" else "✗"
        color = "green" if r1.status == "ok" else "red"
        console.print(f"  [{color}]{icon}[/{color}] {r1.message}")

    if r1.status == "error":
        if json_output:
            json_lib.dump(
                {"error": r1.message, "results": [dataclasses.asdict(r1) for r in results]},
                sys.stdout,
                default=str,
            )
        else:
            console.print(
                "\n[red bold]Python 3.12.x is required. Please upgrade and re-run setup.[/red bold]"
            )
        return 1

    # Step 2: Data directory
    if not json_output:
        _console_step(console, 2, "Data Directory")
    r2 = _step_data_dir(dry_run=dry_run)
    results.append(r2)
    if not json_output:
        icon = "✓" if r2.status == "ok" else "✗"
        color = "green" if r2.status == "ok" else "red"
        console.print(f"  [{color}]{icon}[/{color}] {r2.message}")

    # Step 3: Database initialization
    if not json_output:
        _console_step(console, 3, "Database Initialization")
    r3 = _step_db_init(dry_run=dry_run)
    results.append(r3)
    if not json_output:
        icon = "✓" if r3.status == "ok" else "✗"
        color = "green" if r3.status == "ok" else "red"
        console.print(f"  [{color}]{icon}[/{color}] {r3.message}")

    # Step 4: Kalshi credentials
    if not json_output:
        _console_step(console, 4, "Kalshi Credentials")
    if no_creds:
        r4 = StepResult(
            step="kalshi_credentials",
            status="skipped",
            message="Skipped (--no-creds flag)",
        )
    else:
        r4 = _step_kalshi_credentials(
            console, non_interactive=non_interactive, dry_run=dry_run
        )
    results.append(r4)
    if not json_output:
        _render_step_result(console, r4)

    # Step 5: Optional service credentials
    if not json_output:
        _console_step(console, 5, "Optional Service Credentials")
    if no_creds:
        r5 = StepResult(
            step="optional_services",
            status="skipped",
            message="Skipped (--no-creds flag)",
        )
    else:
        r5 = _step_optional_services(
            console, non_interactive=non_interactive, dry_run=dry_run
        )
    results.append(r5)
    if not json_output:
        console.print(f"  [dim]○[/dim] {r5.message}")

    # Step 6: Master password
    if not json_output:
        _console_step(console, 6, "Master Password")
    r6 = _step_master_password(
        console, non_interactive=non_interactive, dry_run=dry_run
    )
    results.append(r6)
    if not json_output:
        _render_step_result(console, r6)

    # Step 7: Profile creation
    if not json_output:
        _console_step(console, 7, "Profile Creation")
    r7 = _step_profile_creation(
        console, non_interactive=non_interactive, dry_run=dry_run
    )
    results.append(r7)
    if not json_output:
        _render_step_result(console, r7)

    # Summary
    if not json_output:
        _console_step(console, 8, "Summary")
    _print_summary(console, results, json_output=json_output)

    err_count = sum(1 for r in results if r.status == "error")
    return 1 if err_count > 0 else 0


def _render_step_result(console: Console, r: StepResult) -> None:
    """Render a single step result with appropriate icon and color."""
    icon_map = {"ok": "✓", "warning": "⚠", "skipped": "○", "error": "✗"}
    color_map = {"ok": "green", "warning": "yellow", "skipped": "dim", "error": "red"}
    icon = icon_map.get(r.status, "?")
    color = color_map.get(r.status, "")
    console.print(f"  [{color}]{icon}[/{color}] {r.message}")


def register_commands(parent_app: typer.Typer) -> None:
    """Register setup command on the main Typer app."""

    @parent_app.command()
    def setup(
        json_output: Annotated[
            bool, typer.Option("--json", help="Output as JSON for machine consumption")
        ] = False,
        dry_run: Annotated[
            bool, typer.Option("--dry-run", help="Validate without writing any changes")
        ] = False,
        non_interactive: Annotated[
            bool,
            typer.Option(
                "--non-interactive",
                help="Skip all prompts — use env vars or defaults",
            ),
        ] = False,
        no_creds: Annotated[
            bool,
            typer.Option(
                "--no-creds",
                help="Skip credential configuration entirely (kalshi + optional)",
            ),
        ] = False,
    ) -> None:
        """Run interactive setup wizard to configure TraderBot.

        Covers all steps from the installer's interactive_config_flow:
        Python version check, data directory, database init,
        Kalshi credentials, optional service credentials,
        master password, and profile creation.

        Use --non-interactive to skip all prompts (uses env vars or defaults).
        Use --dry-run to validate without writing.
        Use --no-creds to skip all credential prompts.
        """
        console = Console()
        exit_code = _run_setup_steps(
            console,
            dry_run=dry_run,
            non_interactive=non_interactive,
            no_creds=no_creds,
            json_output=json_output,
        )
        if exit_code != 0:
            raise typer.Exit(code=exit_code)
