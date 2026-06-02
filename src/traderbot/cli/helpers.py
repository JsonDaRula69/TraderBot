"""Shared CLI utilities — app, console, and common helpers."""
from __future__ import annotations

import asyncio
import json as json_lib
import logging
import os
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile

from traderbot.profiles.registry import ProfileRegistry

logger = logging.getLogger(__name__)

_SUDO = shutil.which("sudo") or "/usr/bin/sudo"
_SYSTEMCTL = shutil.which("systemctl") or "/usr/bin/systemctl"
_LAUNCHCTL = shutil.which("launchctl") or "/bin/launchctl"
_SC = shutil.which("sc.exe") or shutil.which("sc")
_SCHTASKS = shutil.which("schtasks.exe") or shutil.which("schtasks")


def _mask_token(token: str) -> str:
    """Mask a token, showing only the last 4 characters."""
    return "****" + token[-4:] if len(token) > 4 else "****"


def _write_token_to_env(token: str, console: Console | None = None) -> None:
    """Write TRADERBOT_PROFILE_TOKEN to ~/.traderbot/.env so agent subprocesses
    that don't inherit systemd env vars can still resolve the profile."""
    from traderbot.paths import get_data_dir

    env_path = get_data_dir() / ".env"
    try:
        if env_path.exists():
            lines = env_path.read_text().splitlines()
            found = False
            new_lines = []
            for line in lines:
                if line.strip().startswith("TRADERBOT_PROFILE_TOKEN="):
                    new_lines.append(f"TRADERBOT_PROFILE_TOKEN={token}")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"TRADERBOT_PROFILE_TOKEN={token}")
            env_path.write_text("\n".join(new_lines) + "\n")
        else:
            env_path.parent.mkdir(parents=True, exist_ok=True)
            env_path.write_text(f"TRADERBOT_PROFILE_TOKEN={token}\n")
        env_path.chmod(0o600)
        if console:
            console.print("[green]✓[/green] Token written to .env")
    except Exception as e:
        logger.warning("Failed to write token to .env: %s", e)
        if console:
            console.print(f"[yellow]Warning:[/yellow] Failed to write token to .env: {e}")


app = typer.Typer(
    name="traderbot",
    help="Autonomous prediction market investment toolkit for Kalshi.",
    rich_markup_mode="rich",
)


def _version(value: bool) -> None:
    if value:
        from traderbot.updater import get_current_version

        print(f"traderbot v{get_current_version()}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: Annotated[
        bool,
        typer.Option(
            "--version", "-v", help="Show version and exit.", callback=_version, is_eager=True
        ),
    ] = False,
) -> None:
    """TraderBot — Autonomous prediction market agent."""


err_console = Console(stderr=True)


def _resolve_db_path(db_path: Path | None = None) -> Path:
    """Resolve database path: explicit override > profile-specific > global default."""
    from traderbot.db import DB_PATH
    from traderbot.profiles.isolation import get_profile_db_path

    if db_path is not None:
        return db_path

    from traderbot.profiles.runtime import get_current_profile
    profile = get_current_profile()
    if profile is not None:
        return get_profile_db_path(profile, "decisions.db")

    return DB_PATH


def _with_db(db_path, func):
    """Run func with a database connection, handling open/close."""
    from traderbot.db import get_connection, init_schema

    with get_connection(_resolve_db_path(db_path)) as conn:
        init_schema(conn)
        return func(conn)


def _get_strategy(name: str):
    from traderbot.simulation.strategies import get_strategy as _get_strat

    return _get_strat(name)


def _python_version_ok() -> tuple[bool, str, tuple[int, int]]:
    """Check if the running Python version is compatible (3.12.x only)."""
    major, minor = sys.version_info.major, sys.version_info.minor
    version_str = f"{major}.{minor}.{sys.version_info.micro}"
    return (major, minor) == (3, 12), version_str, (major, minor)


def _check_updates_on_startup() -> None:
    """Check for updates on startup if configured."""
    try:
        from traderbot.update_config import UpdateConfig
        from traderbot.updater import check_for_updates

        config = UpdateConfig.load()
        if not config.enabled or not config.check_on_startup:
            return

        result = check_for_updates()
        if result:
            Console().print(
                f"[dim]Update available: v{result['current']} → v{result['latest']}. "
                f"Run 'traderbot update' to update.[/dim]"
            )
    except Exception:
        pass


def _resolve_agent_path(agent_id: str) -> Path | None:
    """Resolve agent path from openclaw.json config, then fall back to filesystem heuristics.

    Source of truth is always openclaw.json ``agents.list``.  This handles every
    combination OpenClaw supports: explicit workspace, inherited default workspace,
    agentDir-only configs, and default-flagged agents.
    """
    import json as _json
    from pathlib import Path

    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if config_path.exists():
        try:
            config = _json.loads(config_path.read_text())
            section = config.get("agents", {})
            defaults_ws = section.get("defaults", {}).get("workspace", "")

            for entry in section.get("list", []):
                if not isinstance(entry, dict):
                    continue
                if entry.get("id") != agent_id:
                    continue

                ws = entry.get("workspace") or defaults_ws
                if ws:
                    p = Path(ws).expanduser()
                    if p.is_dir() and ((p / "IDENTITY.md").exists() or (p / "TOOLS.md").exists()):
                        return p

                ad = entry.get("agentDir", "")
                if ad:
                    p = Path(ad).expanduser()
                    if p.is_dir() and ((p / "IDENTITY.md").exists() or (p / "TOOLS.md").exists()):
                        return p

                if ws:
                    p = Path(ws).expanduser()
                    if p.is_dir():
                        return p

                break
        except (_json.JSONDecodeError, OSError):
            pass

    candidates = [
        Path.home() / ".openclaw" / f"workspace-{agent_id}",
        Path.home() / ".openclaw" / "workspace" / agent_id,
        Path.home() / ".openclaw" / "agents" / agent_id,
        Path.cwd() / ".openclaw" / "workspace" / agent_id,
        # Default agent "main" uses the root workspace directly
        Path.home() / ".openclaw" / "workspace",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir() and ((candidate / "IDENTITY.md").exists() or (candidate / "TOOLS.md").exists()):
            return candidate
    return None
