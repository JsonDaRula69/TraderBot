from __future__ import annotations

import json
import logging
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

logger = logging.getLogger(__name__)
console = Console()
CACHE_DIR = get_data_dir() / "ws_cache"
DAEMON_STATUS_PATH = CACHE_DIR / "daemon.json"

ws_app = typer.Typer(help="Manage the persistent Kalshi WebSocket daemon")


def get_status() -> dict | None:
    if not DAEMON_STATUS_PATH.exists():
        return None
    return json.loads(DAEMON_STATUS_PATH.read_text())


@ws_app.command()
def start(
    channels: list[str] = typer.Option(
        ["market_lifecycle_v2", "ticker", "user_fills", "user_orders"],
        "--channel",
    ),
    tickers: list[str] | None = typer.Option(None, "--ticker"),
) -> None:
    status = get_status()
    if status and status.get("connected"):
        console.print("[yellow]Daemon is already running[/yellow]")
        console.print(json.dumps(status, indent=2))
        return
    daemon_path = Path(sys.modules["traderbot"].__file__).parent / "kalshi" / "ws_daemon.py"
    cmd = [str(daemon_path)]
    if channels:
        cmd += ["--channels"] + channels
    if tickers:
        cmd += ["--tickers"] + tickers
    venv_python = Path.home() / "traderbot" / ".venv" / "bin" / "python3"
    python = str(venv_python) if venv_python.exists() else "python3"
    full_cmd = [python] + cmd
    proc = subprocess.Popen(
        full_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, start_new_session=True,
    )
    console.print(f"[green]WS daemon started (PID {proc.pid})[/green]")


@ws_app.command()
def stop() -> None:
    status = get_status()
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
    s = get_status()
    if not s:
        console.print("[yellow]Daemon is not running[/yellow]")
        return
    t = Table(title="WS Daemon Status")
    t.add_column("Field", style="bold")
    t.add_column("Value")
    t.add_row("Status", "[green]CONNECTED[/green]" if s.get("connected") else "[red]DISCONNECTED[/red]")
    t.add_row("PID", str(s.get("pid")))
    uptime = time.time() - s.get("uptime", time.time())
    t.add_row("Uptime", "%.0fs" % uptime if uptime < 3600 else "%.1fh" % (uptime / 3600))
    t.add_row("Channels", ", ".join(s.get("channels", [])))
    t.add_row("Subscribed", str(s.get("subscribed", False)))
    last_msg = s.get("last_msg_at")
    if last_msg:
        age = time.time() - last_msg
        t.add_row("Last message", "%.0fs ago" % age if age < 3600 else "%.1fh ago" % (age / 3600))
    console.print(t)


@ws_app.command()
def cache() -> None:
    if not CACHE_DIR.exists():
        console.print("[yellow]No WS cache directory[/yellow]")
        return
    markets = CACHE_DIR / "markets.jsonl"
    fills = CACHE_DIR / "fills.jsonl"
    tickers_dir = CACHE_DIR / "tickers"
    t = Table(title="WS Cache Statistics")
    t.add_column("Source", style="bold")
    t.add_column("Entries")
    t.add_row("markets.jsonl", str(len(markets.read_text().splitlines())) if markets.exists() else "0")
    t.add_row("fills.jsonl", str(len(fills.read_text().splitlines())) if fills.exists() else "0")
    ticker_count = sum(1 for _ in tickers_dir.glob("*.jsonl")) if tickers_dir.exists() else 0
    t.add_row("Ticker files", str(ticker_count))
    console.print(t)