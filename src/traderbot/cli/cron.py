"""Cron command group — register decision/heartbeat cron loops with OpenClaw."""
from __future__ import annotations

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
    """Write heartbeat config for an agent into ~/.openclaw/openclaw.json."""
    import json as _json

    config_path = Path.home() / ".openclaw" / "openclaw.json"
    config: dict = {}

    if config_path.exists():
        try:
            config = _json.loads(config_path.read_text())
        except (ValueError, OSError):
            config = {}

    agents = config.setdefault("agents", {})
    agent_list = agents.setdefault("list", [])

    for entry in agent_list:
        if entry.get("id") == agent_id:
            entry["heartbeat"] = {
                "every": heartbeat_interval,
                "lightContext": True,
                "isolatedSession": True,
            }
            break
    else:
        agent_list.append({
            "id": agent_id,
            "heartbeat": {
                "every": heartbeat_interval,
                "lightContext": True,
                "isolatedSession": True,
            },
        })

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_json.dumps(config, indent=2) + "\n")
    return True


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


@cron_app.command("setup")
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
