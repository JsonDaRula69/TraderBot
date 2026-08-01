from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from traderbot.paths import get_data_dir

console = Console()
CACHE_PATH = get_data_dir() / "event_category_cache.json"
DAEMON_STATUS_PATH = get_data_dir() / "ws_daemon.json"

ws_app = typer.Typer(help="Manage the Kalshi WebSocket event cache daemon")


def _get_status() -> dict | None:
    if not DAEMON_STATUS_PATH.exists():
        return None
    return json.loads(DAEMON_STATUS_PATH.read_text())


@ws_app.command()
def start() -> None:
    status = _get_status()
    if status and status.get("connected"):
        console.print("[yellow]Daemon is already running[/yellow]")
        return
    daemon_path = Path(sys.modules["traderbot"].__file__).parent / "kalshi" / "ws_daemon.py"
    venv_python = Path.home() / "traderbot" / ".venv" / "bin" / "python3"
    python = str(venv_python) if venv_python.exists() else "python3"
    proc = subprocess.Popen(
        [python, str(daemon_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    console.print(f"[green]WS daemon started (PID {proc.pid})[/green]")


@ws_app.command()
def stop() -> None:
    status = _get_status()
    if not status:
        console.print("[yellow]No daemon status file found[/yellow]")
        return
    pid = status.get("pid")
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(10):
                time.sleep(0.5)
                if not DAEMON_STATUS_PATH.exists():
                    break
            console.print(f"[green]Daemon (PID {pid}) stopped[/green]")
        except ProcessLookupError:
            console.print("[yellow]Process not found[/yellow]")
    if DAEMON_STATUS_PATH.exists():
        DAEMON_STATUS_PATH.unlink()


@ws_app.command()
def status() -> None:
    s = _get_status()
    if not s:
        console.print("[yellow]Daemon is not running[/yellow]")
        return
    t = Table(title="WS Daemon Status")
    t.add_column("Field", style="bold")
    t.add_column("Value")
    t.add_row(
        "Status", "[green]CONNECTED[/green]" if s.get("connected") else "[red]DISCONNECTED[/red]"
    )
    t.add_row("PID", str(s.get("pid")))
    uptime_secs = time.time() - s.get("uptime", time.time())
    t.add_row(
        "Uptime", f"{uptime_secs:.0f}s" if uptime_secs < 3600 else "%.1fh" % (uptime_secs / 3600)
    )
    t.add_row("Cache events", str(s.get("cache_size", 0)))
    last_msg = s.get("last_msg_at")
    if last_msg:
        age = time.time() - last_msg
        t.add_row("Last msg", f"{age:.0f}s ago" if age < 3600 else "%.1fh ago" % (age / 3600))
    console.print(t)


def _is_pid_alive(pid: int) -> bool:
    """Check whether *pid* refers to a running process."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # process exists but we lack permission to signal it


@ws_app.command()
def health() -> None:
    """Check WS daemon health — verify PID liveness and status consistency.

    Exit codes: 0 = healthy, 1 = stale/disconnected, 2 = error.
    """
    status_data = _get_status()
    if status_data is None:
        console.print("[red]UNHEALTHY[/red] — no status file found; daemon is not running")
        raise typer.Exit(code=1)

    pid = status_data.get("pid")
    connected = status_data.get("connected", False)

    if pid is None:
        console.print("[red]UNHEALTHY[/red] — status file missing PID")
        raise typer.Exit(code=1)

    alive = _is_pid_alive(pid)

    if not alive:
        # Stale PID — daemon died without cleaning up the status file
        stale_status = {**status_data, "connected": False}
        DAEMON_STATUS_PATH.write_text(json.dumps(stale_status, indent=2))
        console.print(
            f"[red]UNHEALTHY[/red] — PID {pid} is stale (process not found), "
            f"status file [yellow]corrected to DISCONNECTED[/yellow]"
        )
        raise typer.Exit(code=1)

    if not connected:
        console.print(
            f"[yellow]DEGRADED[/yellow] — PID {pid} alive but daemon reports DISCONNECTED"
        )
        raise typer.Exit(code=1)

    console.print(f"[green]HEALTHY[/green] — PID {pid} alive and CONNECTED")
    raise typer.Exit(code=0)


@ws_app.command()
def cache() -> None:
    if not CACHE_PATH.exists():
        console.print("[yellow]No event category cache[/yellow]")
        return
    data = json.loads(CACHE_PATH.read_text())
    entries = data.get("map", {})
    t = Table(title="Event Category Cache")
    t.add_column("Source", style="bold")
    t.add_column("Count")
    t.add_row("Events", str(len(entries)))
    cat_counts: dict[str, int] = {}
    for v in entries.values():
        cat_counts[v] = cat_counts.get(v, 0) + 1
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1])[:10]:
        t.add_row(cat, str(count))
    console.print(t)
