"""Cron command group — register decision/heartbeat cron loops with OpenClaw."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import json as json_lib
import os
import shutil
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from traderbot.cli.helpers import _SUDO, _SYSTEMCTL, report_cli_error

# Ensure openclaw CLI is on PATH (npm global bin not inherited by subprocesses)
_npm_global = str(Path(os.environ.get("HOME", "")) / ".npm-global" / "bin")
if _npm_global not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{_npm_global}:{os.environ.get('PATH', '')}"

cron_app = typer.Typer(name="cron", help="Register cron loops and heartbeat with OpenClaw.")


def _run_openclaw_cron_add(args: list[str]) -> tuple[int, str]:
    """Run `openclaw cron add` and return (exit_code, output)."""
    import subprocess

    try:
        result = subprocess.run(
            ["openclaw", "cron", "add", *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        return -1, "openclaw CLI not found"
    except subprocess.TimeoutExpired:
        return -2, "openclaw cron add timed out"


def _write_heartbeat_config(agent_id: str, heartbeat_interval: str) -> bool:
    """Configure heartbeat isolation for an agent via the openclaw CLI.

    Uses ``openclaw config set`` to write per-agent heartbeat settings
    (isolatedSession, lightContext) — avoids direct openclaw.json edits.

    Falls back silently if openclaw is not available.
    """
    import subprocess as _sp

    try:
        # Find the agent's index in agents.list
        list_result = _sp.run(
            ["openclaw", "config", "get", "agents.list", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if list_result.returncode != 0:
            return False

        agent_list = _json.loads(list_result.stdout)
        if not isinstance(agent_list, list):
            return False

        agent_idx = None
        for i, entry in enumerate(agent_list):
            if entry.get("id") == agent_id:
                agent_idx = i
                break

        if agent_idx is None:
            return False

        prefix = f"agents.list[{agent_idx}]"

        # Set heartbeat config keys via CLI
        _sp.run(
            ["openclaw", "config", "set", f"{prefix}.heartbeat.every", heartbeat_interval],
            capture_output=True,
            timeout=10,
        )
        _sp.run(
            [
                "openclaw",
                "config",
                "set",
                f"{prefix}.heartbeat.isolatedSession",
                "true",
                "--strict-json",
            ],
            capture_output=True,
            timeout=10,
        )
        _sp.run(
            [
                "openclaw",
                "config",
                "set",
                f"{prefix}.heartbeat.lightContext",
                "true",
                "--strict-json",
            ],
            capture_output=True,
            timeout=10,
        )
        return True
    except Exception:
        logger.debug("systemd service installation failed")
        return False


def _install_news_ingest_timer(
    agent_user: str,
    interval_minutes: int = 30,
    console: object | None = None,
) -> dict[str, str | bool]:
    """Install systemd timer for offline news ingestion.

    Returns dict with 'registered' key and optional 'error'.
    No-op on non-Linux or non-systemd systems.
    """
    import subprocess

    result: dict[str, str | bool] = {
        "name": "news_ingest_timer",
        "registered": False,
    }

    if sys.platform == "win32":
        return _install_news_ingest_timer_windows(agent_user, interval_minutes, console, result)
    if sys.platform != "linux":
        return result

    if not _systemd_available():
        return result

    try:
        from importlib import resources

        from traderbot.utils import get_own_venv_dir, get_repo_dir
    except ImportError:
        return result

    repo_dir = get_repo_dir()
    venv_dir = get_own_venv_dir()
    service_dir = repo_dir / "services"
    service_template = service_dir / "traderbot-news-ingest@.service"
    timer_template = service_dir / "traderbot-news-ingest@.timer"

    if not service_template.exists() or not timer_template.exists():
        result["error"] = "systemd templates not found"
        return result

    import getpass as _gp

    user = agent_user or _gp.getuser()
    home = Path.home()

    svc_content = service_template.read_text()
    svc_content = svc_content.replace("User=%i", f"User={user}")
    svc_content = svc_content.replace("/home/%i/", f"/home/{user}/")
    svc_content = svc_content.replace("%h/.traderbot/.env", f"{home}/.traderbot/.env")

    tmp_svc = Path(f"/tmp/traderbot-news-ingest@{user}.service")
    tmp_svc.write_text(svc_content)

    tmr_content = timer_template.read_text()
    tmr_content = tmr_content.replace("(%i)", f"({user})")
    tmr_content = tmr_content.replace("@<user>", f"@{user}")
    tmp_tmr = Path(f"/tmp/traderbot-news-ingest@{user}.timer")
    tmp_tmr.write_text(tmr_content)

    try:
        subprocess.run(
            [
                _SUDO,
                "cp",
                str(tmp_svc),
                f"/etc/systemd/system/traderbot-news-ingest@{user}.service",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [_SUDO, "cp", str(tmp_tmr), f"/etc/systemd/system/traderbot-news-ingest@{user}.timer"],
            check=True,
            capture_output=True,
        )
        subprocess.run([_SUDO, _SYSTEMCTL, "daemon-reload"], check=True, capture_output=True)
        subprocess.run(
            [_SUDO, _SYSTEMCTL, "enable", f"traderbot-news-ingest@{user}.timer"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [_SUDO, _SYSTEMCTL, "start", f"traderbot-news-ingest@{user}.timer"],
            check=True,
            capture_output=True,
        )
        result["registered"] = True
    except subprocess.CalledProcessError as exc:
        result["error"] = str(exc.stderr.decode() if exc.stderr else exc)
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        tmp_svc.unlink(missing_ok=True)
        tmp_tmr.unlink(missing_ok=True)

    return result


def _install_news_ingest_timer_windows(
    agent_user: str,
    interval_minutes: int,
    console: object | None,
    result: dict[str, str | bool],
) -> dict[str, str | bool]:
    import getpass as _gp

    from traderbot.windows_service import (
        install_news_ingest_task,
        schtasks_available,
    )

    if not schtasks_available():
        result["error"] = "schtasks.exe not available"
        return result

    user = agent_user or _gp.getuser()
    try:
        success = install_news_ingest_task(user=user, interval_minutes=interval_minutes)
        if success:
            result["registered"] = True
        else:
            result["error"] = "schtasks create returned non-zero"
    except Exception as exc:
        result["error"] = str(exc)

    return result


def _systemd_available() -> bool:
    """Check if systemd is available on this system."""
    import subprocess

    try:
        subprocess.run([_SYSTEMCTL, "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.debug("systemctl not available, skipping systemd timer setup")
        return False


def _remove_news_ingest_timer(
    agent_user: str,
    console: object | None = None,
) -> None:
    import subprocess

    if sys.platform == "win32":
        from traderbot.windows_service import uninstall_news_ingest_task

        try:
            uninstall_news_ingest_task(agent_user)
        except Exception as exc:
            logger.error("Failed to remove cron jobs for %s: %s", agent_user, exc)
            return
    if sys.platform != "linux":
        return
    if not _systemd_available():
        return

    try:
        subprocess.run(
            [_SUDO, _SYSTEMCTL, "stop", f"traderbot-news-ingest@{agent_user}.timer"],
            capture_output=True,
            timeout=15,
        )
        subprocess.run(
            [_SUDO, _SYSTEMCTL, "disable", f"traderbot-news-ingest@{agent_user}.timer"],
            capture_output=True,
            timeout=15,
        )
        subprocess.run(
            [_SUDO, "rm", "-f", f"/etc/systemd/system/traderbot-news-ingest@{agent_user}.service"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [_SUDO, "rm", "-f", f"/etc/systemd/system/traderbot-news-ingest@{agent_user}.timer"],
            check=True,
            capture_output=True,
        )
        subprocess.run([_SUDO, _SYSTEMCTL, "daemon-reload"], capture_output=True, timeout=15)
    except Exception:
        logger.debug("systemd disable/remove failed, skipping")


_SYSADMIN_CRON_JOBS: list[dict[str, str]] = [
    {
        "name": "learning-pipeline",
        "cron_expr": "0 */6 * * *",
        "message": "Read each agent's `.learnings/LEARNINGS.md`. Find entries with Recurrence-Count >= 3 that are not already PENDING_REVIEW. Promote each via `traderbot learnings --promote <key>`. Then check test-lab/backlog.md for QUEUED experiments — move one to RUNNING, execute backtest, validate against deployment bar (Sharpe >= 1.0, win rate improvement >= 5pp, sample size >= 30). If requires code change: file GitHub issue with full experiment design, test results, and expected benefit (labels: enhancement, experiment). If profile param only: DEPLOY via `traderbot profile update`, notify target agent via `sessions_send`. Archive result in results/. If any step fails, write to `.learnings/ERRORS.md` with full context. If FULL_STOP is active, check for recovery experiment results. If a treatment validated, deployment via profile update clears the blocker.",
    },
    {
        "name": "error-logger",
        "cron_expr": "*/15 * * * *",
        "message": "Read each category agent's `.learnings/ERRORS.md` and `.learnings/FEATURE_REQUESTS.md`. For each unresolved entry: investigate by reproducing the error or verifying the capability gap. Cross-reference against experiment backlog to avoid duplicates. If confirmed as a new bug or valid feature gap: use the github skill to file a GitHub issue in JsonDaRula69/TraderBot with investigation results, reproduction steps, and proposed fix. Labels: bug for ERRORS.md, enhancement for FEATURE_REQUESTS.md. Mark the entry as INVESTIGATED. Do NOT create issues for behavioral learnings (LEARNINGS.md entries) — those go through experiment pipeline.",
    },
    {
        "name": "health-check",
        "cron_expr": "0 * * * *",
        "message": "Run `traderbot auth check --json`. Verify all API credentials are resolvable. If Kalshi credentials missing or invalid, write to `.learnings/ERRORS.md` and surface CRITICAL alert to human. Also run `traderbot heartbeat --json` — review fleet P&L, agent win rates, drawdown. If anomalies found, write to `.learnings/ERRORS.md` with details.",
    },
    {
        "name": "gateway-health",
        "cron_expr": "0 */6 * * *",
        "message": "Check: (1) systemd timers via `systemctl list-timers --all | grep traderbot`, (2) ChromaDB data_points count via `traderbot data-points weather --json --count`, (3) WS daemon via `traderbot ws status`. Run backfill if stale. For each issue, write to `.learnings/ERRORS.md` (failures), `.learnings/FEATURE_REQUESTS.md` (missing capabilities), or `.learnings/LEARNINGS.md` (recurring patterns). If requires code change, file GitHub issue with reproduction steps.",
    },
]

_TRADER_CRON_JOBS: list[dict[str, str]] = [
    {
        "name": "circuit-breaker-check",
        "cron_expr": "*/30 * * * *",
        "message": "Run `traderbot halt --json` then `traderbot halt --recover --json`. If SLOW or worse after recovery, write to `.learnings/ERRORS.md` and surface alert to sysadmin. If HALT or FULL_STOP, surface CRITICAL alert and do not trade. If level transitioned, log severity for adaptation feedback. Breaker events are automatically fed as weighted negative evidence into the BayesianAdapter during heartbeat.",
    },
    {
        "name": "decision-loop",
        "cron_expr": "*/5 * * * *",
        "message": "Full trading decision cycle: 1) `traderbot scan --category weather --limit 50 --json` — if empty, retry once after 30s; if still empty log SYSTEM ERROR to `.learnings/ERRORS.md`. 2) Filter by horizon (0-7 day). 3) `traderbot data forecasts --cities NYC,CHI,LA,PHX,SEA --json`. 4) Model consensus check (spread < 2°F = high conviction, > 5°F = halve position). 5) Compute edge for top 5 contracts by volume near NWS forecast. 6) `traderbot data bias <CITY> --days 90 --json`. 7) `traderbot analyze <TICKER> --json` on top 3. 8) `traderbot news-context weather --json` for advisories. 9) If risk passes and edge >= threshold: trade. Position sizing = risk_multiplier * conviction * available_balance, capped at max-position-pct. 10) Log every decision in SESSION-STATE.md.",
    },
    {
        "name": "position-review",
        "cron_expr": "0 * * * *",
        "message": "Run `traderbot data settle --json` then `traderbot positions --json` — check positions with settlement < 48h, drawdown > 5%. Write any issues to `.learnings/ERRORS.md` and surface to sysadmin. Settlement results are automatically synced to decisions.actual_result before adaptation runs. Verify positions with settlement < 48h are correctly reconciled at the decision level.",
    },
    {
        "name": "forecast-check",
        "cron_expr": "15,45 * * * *",
        "message": "Run `traderbot data forecasts --cities NYC,CHI,LA,PHX,SEA --json`. Verify NWS and ensemble data availability. If empty, check pipeline timers and fall back to `traderbot data-points weather --json`. If fallback also fails, write to `.learnings/ERRORS.md`. Log status.",
    },
    {
        "name": "health-check",
        "cron_expr": "0 * * * *",
        "message": "Run `traderbot auth check --json` — verify Kalshi credentials resolvable, surface alert if missing. Run `traderbot heartbeat --json` — check drawdown > 3%, win rate < 40% over 30+ trades. Write anomalies to `.learnings/ERRORS.md` and surface to sysadmin.",
    },
]


# ── Helper: remove cron jobs by agent prefix ─────────────────────────────
def _remove_cron_jobs_by_name(agent_id: str, exact: bool = False) -> list[str]:
    """Remove all cron jobs whose name starts with ``<agent_id>-`` (or exact match)."""
    import json as _cjson
    import subprocess

    removed: list[str] = []
    try:
        result = subprocess.run(
            ["openclaw", "cron", "list", "--json"],
            env={**dict(subprocess.os.environ), "OPENCLAW_SKIP_UPDATE_CHECK": "1"},
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            logger.warning(
                "openclaw cron list returned %d: %s", result.returncode, result.stderr.strip()
            )
            return removed
        raw = result.stdout.strip()
        brace = raw.find("\n{")
        if brace >= 0:
            raw = raw[brace + 1 :]
        elif raw.startswith("{"):
            pass
        else:
            brace = raw.find("{")
            if brace >= 0:
                raw = raw[brace:]
        jobs = _cjson.loads(raw)
        if not isinstance(jobs, list):
            jobs = jobs.get("jobs", []) if isinstance(jobs, dict) else []
        prefix = f"{agent_id}-"
        for job in jobs:
            jname = job.get("name", "")
            jid = job.get("id", "")
            if jid:
                if exact:
                    if jname == agent_id:
                        subprocess.run(
                            ["openclaw", "cron", "remove", jid], capture_output=True, timeout=10
                        )
                        removed.append(jname)
                elif jname.startswith(prefix):
                    subprocess.run(
                        ["openclaw", "cron", "remove", jid], capture_output=True, timeout=10
                    )
                    removed.append(jname)
    except Exception:
        logger.debug("Cron job removal batch failed, skipping")
    return removed


@cron_app.command("setup")
def cron_setup(
    agent_id: Annotated[
        str,
        typer.Option("--agent", help="OpenClaw agent ID to register cron jobs for"),
    ],
    role: Annotated[
        str,
        typer.Option(
            "--role",
            help="Agent role: 'sysadmin' or 'trader'",
        ),
    ] = "trader",
    replace: Annotated[
        bool,
        typer.Option("--replace", help="Remove existing cron jobs first, then re-register"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Register cron jobs for an agent based on its role.

    Sysadmin role (main) gets: learning-pipeline, error-logger, health-check,
    gateway-health — no trading commands.

    Trader role (weather, crypto, etc.) gets: decision-loop, position-review,
    forecast-check, circuit-breaker-check, health-check.

    Pass --replace to remove any existing jobs before registering anew —
    this prevents duplicate entries from re-runs of this command.
    """
    console = Console()
    results: list[dict[str, str | bool]] = []

    if role not in ("sysadmin", "trader"):
        report_cli_error(f"Invalid role '{role}'. Must be 'sysadmin' or 'trader'.")

    if not shutil.which("openclaw"):
        report_cli_error("openclaw CLI not found in PATH")

    if replace:
        _remove_cron_jobs_by_name(agent_id)

    jobs = _SYSADMIN_CRON_JOBS if role == "sysadmin" else _TRADER_CRON_JOBS
    for job in jobs:
        job_name = f"{agent_id}-{job['name']}"
        # Remove any existing job with this name before re-adding (avoids duplicates)
        _remove_cron_jobs_by_name(job_name, exact=True)
        args = [
            "--name",
            job_name,
            "--cron",
            job["cron_expr"],
            "--session",
            "isolated",
            "--message",
            job["message"],
            "--agent",
            agent_id,
        ]
        exit_code, output = _run_openclaw_cron_add(args)
        success = exit_code == 0
        results.append(
            {
                "name": job["name"],
                "registered": success,
                "output": output if not success else "",
            }
        )

    if json_output:
        json_lib.dump(results, sys.stdout, indent=2)
        return

    console.print(f"[bold]Cron setup ({role})[/bold]")
    for r in results:
        status = "[green]✓[/green]" if r["registered"] else "[red]✗[/red]"
        console.print(f"  {status} {r['name']}")
    if not results:
        console.print("[yellow]No jobs registered.[/yellow]")
    else:
        console.print(f"\n[bold]✓[/bold] Cron setup complete for agent '{agent_id}'")
