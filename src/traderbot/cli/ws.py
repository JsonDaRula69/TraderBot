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
err_console = Console(stderr=True)
CACHE_DIR = get_data_dir() / "ws_cache"
DAEMON_STATUS_PATH = CACHE_DIR / "daemon.json"


def get_status() -> dict | None:
    if not DAEMON_STATUS_PATH.exists():
        return None
    return json.loads(DAEMON_STATUS_PATH.read_text())


def register_commands(parent_app: typer.Typer) -> None:
    @parent_app.command()
    def start(
        channels: list[str] = typer.Option(
            ["market_lifecycle_v2", "ticker", "user_fills", "user_orders"],
            "--channel",
            help="WS channels to subscribe to",
        ),
        tickers: list[str] | None = typer.Option(
            None, "--ticker", help="Market/series tickers to track",
        ),
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
            full_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        console.print(f"[green]WS daemon started (PID {proc.pid})[/green]")

    @parent_app.command()
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

    @parent_app.command()
    def status() -> None:
        sys_status = get_status()
        if not sys_status:
            console.print("[yellow]Daemon is not running[/yellow]")
            return
        connected = sys_status.get("connected", False)
        pid = sys_status.get("pid")
        uptime = time.time() - sys_status.get("uptime", time.time())
        channels_list = sys_status.get("channels", [])
        last_msg = sys_status.get("last_msg_at")
        table = Table(title="WS Daemon Status")
        table.add_column("Field", style="bold")
        table.add_column("Value")
        table.add_row("Status", "[green]CONNECTED[/green]" if connected else "[red]DISCONNECTED[/red]")
        table.add_row("PID", str(pid))
        table.add_row("Uptime", f"{uptime:.0f}s" if uptime < 3600 else f"{uptime / 3600:.1f}h")
        table.add_row("Channels", ", ".join(channels_list))
        table.add_row("Subscribed", str(sys_status.get("subscribed", False)))
        if last_msg:
            age = time.time() - last_msg
            table.add_row("Last message", f"{age:.0f}s ago" if age < 3600 else f"{age / 3600:.1f}h ago")
        console.print(table)

    @parent_app.command()
    def cache() -> None:
        if not CACHE_DIR.exists():
            console.print("[yellow]No WS cache directory[/yellow]")
            return
        markets = CACHE_DIR / "markets.jsonl"
        fills = CACHE_DIR / "fills.jsonl"
        tickers_dir = CACHE_DIR / "tickers"
        table = Table(title="WS Cache Statistics")
        table.add_column("Source", style="bold")
        table.add_column("Entries")
        table.add_row("markets.jsonl", str(len(markets.read_text().splitlines())) if markets.exists() else "0")
        table.add_row("fills.jsonl", str(len(fills.read_text().splitlines())) if fills.exists() else "0")
        ticker_count = 0
        if tickers_dir.exists():
            ticker_count = sum(1 for f in tickers_dir.iterdir() if f.suffix == ".jsonl")
        table.add_row("Ticker files", str(ticker_count))
        console.print(table)