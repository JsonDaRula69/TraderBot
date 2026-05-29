"""Cron command group — register decision/heartbeat cron loops with OpenClaw."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import json as json_lib
import os
import shutil
import subprocess as _subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from traderbot.cli.helpers import _SUDO, _SCHTASKS, _SYSTEMCTL, err_console

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
            capture_output=True, text=True, timeout=10,
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
            capture_output=True, timeout=10,
        )
        _sp.run(
            ["openclaw", "config", "set", f"{prefix}.heartbeat.isolatedSession", "true", "--strict-json"],
            capture_output=True, timeout=10,
        )
        _sp.run(
            ["openclaw", "config", "set", f"{prefix}.heartbeat.lightContext", "true", "--strict-json"],
            capture_output=True, timeout=10,
        )
        return True
    except Exception:
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
        from traderbot.utils import get_own_venv_dir, get_repo_dir
        from importlib import resources
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
        subprocess.run([_SUDO, "cp", str(tmp_svc), f"/etc/systemd/system/traderbot-news-ingest@{user}.service"], check=True, capture_output=True)
        subprocess.run([_SUDO, "cp", str(tmp_tmr), f"/etc/systemd/system/traderbot-news-ingest@{user}.timer"], check=True, capture_output=True)
        subprocess.run([_SUDO, _SYSTEMCTL, "daemon-reload"], check=True, capture_output=True)
        subprocess.run([_SUDO, _SYSTEMCTL, "enable", f"traderbot-news-ingest@{user}.timer"], check=True, capture_output=True)
        subprocess.run([_SUDO, _SYSTEMCTL, "start", f"traderbot-news-ingest@{user}.timer"], check=True, capture_output=True)
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
        except Exception:
            pass
        return
    if sys.platform != "linux":
        return
    if not _systemd_available():
        return

    try:
        subprocess.run(
            [_SUDO, _SYSTEMCTL, "stop", f"traderbot-news-ingest@{agent_user}.timer"],
            capture_output=True, timeout=15,
        )
        subprocess.run(
            [_SUDO, _SYSTEMCTL, "disable", f"traderbot-news-ingest@{agent_user}.timer"],
            capture_output=True, timeout=15,
        )
        subprocess.run(
            [_SUDO, "rm", "-f", f"/etc/systemd/system/traderbot-news-ingest@{agent_user}.service"],
            check=True, capture_output=True,
        )
        subprocess.run(
            [_SUDO, "rm", "-f", f"/etc/systemd/system/traderbot-news-ingest@{agent_user}.timer"],
            check=True, capture_output=True,
        )
        subprocess.run([_SUDO, _SYSTEMCTL, "daemon-reload"], capture_output=True, timeout=15)
    except Exception:
        pass


_SYSADMIN_HEARTBEAT_CRON_JOBS: list[dict[str, str]] = [
    {
        "name": "circuit-breaker-check",
        "cron_expr": "*/30 * * * *",
        "message": "Run `traderbot halt --json`. Check fleet-wide circuit breaker across all agents. If HALT or FULL_STOP, surface CRITICAL alert to human. If level is degraded, investigate which agent is responsible.",
    },
    {
        "name": "experiment-check",
        "cron_expr": "*/30 * * * *",
        "message": "Read each agent's SESSION-STATE.md via sessions_history. Check Pending Actions for experiment proposals marked DESIGNED or PROPOSED. Acknowledge receipt, add to test-lab/backlog.md, update SESSION-STATE.md with status.",
    },
    {
        "name": "experiment-execution",
        "cron_expr": "*/30 * * * *",
        "message": "Check test-lab/backlog.md for QUEUED experiments. Move one to RUNNING. Execute backtest or compare. Validate against deployment bar. DEPLOY if pass, REJECT with reason. Archive result.",
    },
    {
        "name": "learning-review",
        "cron_expr": "0 * * * *",
        "message": "Cross-reference PENDING_REVIEW learnings across agents against experiment backlog. Identify any pattern the backlog doesn't cover. Surface duplicates or conflicts.",
    },
    {
        "name": "pipeline-health",
        "cron_expr": "0 */3 * * *",
        "message": "Check pipeline timers via `systemctl list-timers --all | grep traderbot`. Verify ChromaDB data_points collection count > 0 via `traderbot data-points weather --json --count`. Run backfill if stale. Surface inactive timers or empty collections to human.",
    },
    {
        "name": "performance-review",
        "cron_expr": "0 */6 * * *",
        "message": "Run `traderbot heartbeat --json`. Review fleet P&L, agent win rates, drawdown across all assigned profiles. Check if any agent exceeds risk thresholds. Surface anomalies to human. Do not trade — do not touch order book.",
    },
]

_AGENT_HEARTBEAT_CRON_JOBS: list[dict[str, str]] = [
    {
        "name": "circuit-breaker-check",
        "cron_expr": "*/30 * * * *",
        "message": "Run `traderbot halt --json`. If circuit breaker is SLOW or worse, surface alert to sysadmin. If HALT or FULL_STOP, surface CRITICAL alert and do not trade.",
    },
    {
        "name": "data-forecast-check",
        "cron_expr": "*/30 * * * *",
        "message": "Run `traderbot data forecasts --cities NYC,CHI,LA,PHX,SEA --json`. Verify NWS and ensemble data availability. If empty, check pipeline timers and fall back to `traderbot data-points weather --json`. Log status.",
    },
    {
        "name": "news-scan",
        "cron_expr": "*/30 * * * *",
        "message": "Run `traderbot news-context weather --json`. Check for NHC advisories, NWS warnings, emergency declarations. If any active, surface alert to sysadmin.",
    },
    {
        "name": "position-health",
        "cron_expr": "0 * * * *",
        "message": "Run `traderbot positions --json`. Check positions with settlement < 48h. Check drawdown > 5%. Surface any at-risk positions to sysadmin.",
    },
    {
        "name": "settlement-monitor",
        "cron_expr": "0 * * * *",
        "session": "isolated",
        "message": "Check for recently settled markets and update positions DB. Run `traderbot check-settlements --json`.",
    },
    {
        "name": "performance-review",
        "cron_expr": "0 */6 * * *",
        "message": "Run `traderbot heartbeat --json`. Check drawdown > 3%, win rate < 40% over 30+ trades. Surface any issues to sysadmin.",
    },
    {
        "name": "learning-promotion",
        "cron_expr": "0 */6 * * *",
        "message": "Read `.learnings/LEARNINGS.md`. Find entries with Recurrence-Count >= 3. Promote each to PENDING_REVIEW via `traderbot learnings --promote <key>` if not already. For each newly promoted, follow Experiment Design Flow in AGENTS.md.",
    },
    {
        "name": "pipeline-health",
        "cron_expr": "0 */6 * * *",
        "message": "Check pipeline timers via `systemctl list-timers --all | grep traderbot`. Verify data_points count > 0. Surface any inactive timers or stale data to sysadmin.",
    },
]


@cron_app.command("setup-heartbeat-tasks")
def cron_setup_heartbeat_tasks(
    agent_id: Annotated[
        str,
        typer.Option("--agent", help="OpenClaw agent ID to register heartbeat tasks for"),
    ],
    role: Annotated[
        str, typer.Option("--role", help="Agent role: 'sysadmin' for fleet oversight, 'agent' for category trading"),
    ] = "agent",
    skip_heartbeat_config: Annotated[
        bool,
        typer.Option("--skip-heartbeat-config", help="Skip writing heartbeat config to openclaw.json"),
    ] = False,
    replace: Annotated[
        bool, typer.Option("--replace", help="Remove existing heartbeat tasks first, then re-register"),
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Register each heartbeat task as an isolated cron job.

    Each task runs in its own isolated cron session — zero collision with
    trading or other tasks. Use --role sysadmin for fleet oversight agents
    (circuit breaker, experiment management, pipeline health only, no trading
    commands) or --role agent (default) for category trading agents (includes
    data forecasts, news, positions, learning promotion). Pass --replace to
    remove any existing heartbeat tasks before registering anew — this
    prevents duplicate cron entries from re-runs of this command.
    """
    console = Console()
    results: list[dict[str, str | bool]] = []

    if not shutil.which("openclaw"):
        console.print("[red]Error:[/red] openclaw CLI not found in PATH")
        raise typer.Exit(1)

    if replace:
        import subprocess
        all_jobs_for_agent = _SYSADMIN_HEARTBEAT_CRON_JOBS + _AGENT_HEARTBEAT_CRON_JOBS
        _seen: set[str] = set()
        for job in all_jobs_for_agent:
            job_name = f"{agent_id}-{job['name']}"
            if job_name in _seen:
                continue
            _seen.add(job_name)
            try:
                subprocess.run(["openclaw", "cron", "remove", job_name], capture_output=True, text=True, timeout=15)
            except Exception:
                pass

    jobs = _SYSADMIN_HEARTBEAT_CRON_JOBS if role == "sysadmin" else _AGENT_HEARTBEAT_CRON_JOBS
    for job in jobs:
        args = [
            "--name", f"{agent_id}-{job['name']}",
            "--cron", job["cron_expr"],
            "--session", "isolated",
            "--message", job["message"],
            "--agent", agent_id,
        ]
        exit_code, output = _run_openclaw_cron_add(args)
        success = exit_code == 0
        results.append({
            "name": job["name"],
            "registered": success,
            "output": output if not success else "",
        })

    if json_output:
        json_lib.dump(results, sys.stdout, indent=2)
        return

    console.print("[bold]Heartbeat Task Registration[/bold]")
    for r in results:
        status = "[green]✓[/green]" if r["registered"] else "[red]✗[/red]"
        console.print(f"  {status} {r['name']}")
    console.print("\nAll tasks run in isolated cron sessions. No collision with trading.")


@cron_app.command("remove-heartbeat-tasks")
def cron_remove_heartbeat_tasks(
    agent_id: Annotated[
        str,
        typer.Option("--agent", help="OpenClaw agent ID to remove heartbeat tasks for"),
    ],
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Remove all registered heartbeat cron tasks for an agent."""
    import subprocess

    console = Console()
    removed: list[str] = []

    all_jobs = _SYSADMIN_HEARTBEAT_CRON_JOBS + _AGENT_HEARTBEAT_CRON_JOBS
    seen: set[str] = set()
    for job in all_jobs:
        job_name = f"{agent_id}-{job['name']}"
        if job_name in seen:
            continue
        seen.add(job_name)
        try:
            result = subprocess.run(
                ["openclaw", "cron", "remove", job_name],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                removed.append(job["name"])
        except Exception:
            pass

    if json_output:
        json_lib.dump({"removed": removed}, sys.stdout, indent=2)
        return

    for name in removed:
        console.print(f"  [green]✓[/green] Removed {name}")
    if not removed:
        console.print("[yellow]No heartbeat tasks found to remove.[/yellow]")
def cron_setup(
    agent_id: Annotated[
        str,
        typer.Option("--agent", help="OpenClaw agent ID to register loops for"),
    ],
    channel: Annotated[
        str | None,
        typer.Option("--channel", help="Delivery channel for announce (e.g. telegram, slack, whatsapp)"),
    ] = None,
    to: Annotated[
        str | None,
        typer.Option("--to", help="Delivery target (chat ID for telegram, E.164 phone for whatsapp)"),
    ] = None,
    heartbeat_interval: Annotated[
        str,
        typer.Option("--heartbeat-every", help="Heartbeat interval (e.g. 30m, 1h, 6h)"),
    ] = "6h",
    news_ingest_interval: Annotated[
        int | None,
        typer.Option("--news-ingest-every", help="News ingestion interval in minutes. 0=disable, omit=skip"),
    ] = None,
    skip_heartbeat_config: Annotated[
        bool,
        typer.Option("--skip-heartbeat-config", help="Skip writing heartbeat config to openclaw.json"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be registered without executing"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Register decision, heartbeat, and news cron loops with OpenClaw for an agent."""
    from traderbot.cron_loops import DecisionLoopPayload, HeartbeatLoopPayload, NewsLoopPayload

    console = Console()

    if bool(channel) ^ bool(to):
        console.print("[red]Error:[/red] Both --channel and --to are required when either is provided.")
        raise typer.Exit(1)

    results: list[dict[str, str | bool]] = []

    if not dry_run:
        if not shutil.which("openclaw"):
            console.print("[red]Error:[/red] openclaw CLI not found in PATH")
            console.print("Install OpenClaw first: https://github.com/openclaw/openclaw")
            raise typer.Exit(1)

        # channel/to validated by XOR check above — either both provided or neither
        bool(channel and to)  # implicit announce when channel+to provided

    decision_payload = DecisionLoopPayload()
    heartbeat_payload = HeartbeatLoopPayload()
    news_payload = NewsLoopPayload(topic="impact", impact_score=0.7)

    cron_jobs = [
        {
            "name": "decision_loop",
            "cron_expr": "*/5 * * * *",
            "session": "isolated",
            "message": decision_payload.message,
        },
        {
            "name": "heartbeat_loop",
            "cron_expr": "0 */6 * * *",
            "session": "isolated",
            "message": heartbeat_payload.message,
        },
        {
            "name": "news_ingest",
            "cron_expr": "*/30 * * * *",
            "session": "isolated",
            "message": news_payload.message,
        },
    ]

    for job in cron_jobs:
        cmd_args = [agent_id, "--name", job["name"], "--schedule", job["cron_expr"], "--session", job["session"], "--message", job["message"]]
        if channel and to:
            cmd_args += ["--channel", channel, "--to", to]

        if dry_run:
            console.print(f"[dim][dry-run][/dim] openclaw cron add {' '.join(cmd_args)}")
            results.append({"name": job["name"], "registered": True, "dry_run": True})
        else:
            exit_code, output = _run_openclaw_cron_add(cmd_args)
            ok = exit_code == 0
            results.append({
                "name": job["name"],
                "registered": ok,
                "exit_code": exit_code,
                "output": output,
            })

    if not dry_run:
        if not skip_heartbeat_config:
            hb_ok = _write_heartbeat_config(agent_id, heartbeat_interval)
            results.append({"name": "heartbeat_config", "registered": hb_ok})

        if news_ingest_interval is not None and news_ingest_interval > 0:
            timer_result = _install_news_ingest_timer(agent_id, interval_minutes=news_ingest_interval, console=console)
            results.append(timer_result)

    if json_output:
        json_lib.dump(results, sys.stdout, default=str)
        return

    for r in results:
        name = r.get("name", "?")
        if r.get("dry_run"):
            console.print(f"[dim][dry-run][/dim] {name}")
        elif r.get("registered"):
            console.print(f"[green]✓[/green] {name}")
        else:
            console.print(f"[red]✗[/red] {name}: {r.get('output', r.get('error', 'unknown error'))}")

    console.print(f"\n[bold]✓[/bold] Cron setup complete for agent '{agent_id}'")
