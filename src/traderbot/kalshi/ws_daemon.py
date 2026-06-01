"""Persistent WebSocket daemon for Kalshi real-time market data.

Writes streaming data to ``~/.traderbot/ws_cache/`` so ephemeral cron
containers can read latest market state without making REST API calls.
Designed to run as a systemd user service on the host.

Cache directory layout::

    ~/.traderbot/ws_cache/
    ├── daemon.json              # status metadata (pid, uptime, channels)
    ├── markets.jsonl            # market_lifecycle_v2 events (append-only)
    ├── fills.jsonl              # fill events (append-only)
    └── tickers/
        ├── KXHIGHNY.jsonl       # per-series ticker updates
        ├── KXLOWNYC.jsonl
        └── ...
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

import websockets

from traderbot.auth import get_credential
from traderbot.kalshi.pinning import create_pinned_ssl_context
from traderbot.kalshi.signing import auth_headers
from traderbot.paths import get_data_dir

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ws-daemon")

CACHE_DIR = get_data_dir() / "ws_cache"
RECONNECT_DELAY = 5.0
MAX_RECONNECT_DELAY = 60.0
PING_INTERVAL = 15.0
CHANNELS: list[str] = [
    "market_lifecycle_v2",
    "ticker",
    "user_fills",
    "user_orders",
]


def _ensure_dirs() -> None:
    (CACHE_DIR / "tickers").mkdir(parents=True, exist_ok=True)


def _write_status(**kw: Any) -> None:
    payload = {"pid": os.getpid(), "uptime": time.time(), "channels": CHANNELS, **kw}
    (CACHE_DIR / "daemon.json").write_text(json.dumps(payload, indent=2))


def _append_jsonl(path: Path, data: Any) -> None:
    with open(path, "a") as f:
        f.write(json.dumps(data, default=str) + "\n")


def _on_market_lifecycle(msg: dict[str, Any]) -> None:
    _append_jsonl(CACHE_DIR / "markets.jsonl", msg)


def _on_ticker(msg: dict[str, Any]) -> None:
    series = msg.get("series_ticker", "unknown")
    _append_jsonl(CACHE_DIR / "tickers" / f"{series}.jsonl", msg)


def _on_fill(msg: dict[str, Any]) -> None:
    _append_jsonl(CACHE_DIR / "fills.jsonl", msg)


_DISPATCH: dict[str, Any] = {
    "market_lifecycle_v2": _on_market_lifecycle,
    "ticker": _on_ticker,
    "fill": _on_fill,
    "user_fills": _on_fill,
    "user_orders": _on_fill,
}


def _dispatch(msg: dict[str, Any]) -> None:
    channel = msg.get("channel", msg.get("type", ""))
    handler = _DISPATCH.get(channel)
    if handler:
        try:
            handler(msg)
        except Exception:
            logger.exception("Handler failed for channel=%s", channel)


async def _run(
    api_key: str,
    private_key: str,
    ws_url: str,
    channels: list[str],
    *,
    market_tickers: list[str] | None = None,
) -> None:
    delay = RECONNECT_DELAY
    while True:
        try:
            headers = auth_headers(api_key, private_key, "GET", "/trade-api/ws/v2")
            headers["Content-Type"] = "application/json"

            async with websockets.connect(
                ws_url,
                additional_headers=headers,
                ssl=create_pinned_ssl_context(),
                ping_interval=PING_INTERVAL,
            ) as ws:
                logger.info("Connected to %s", ws_url)
                delay = RECONNECT_DELAY
                _write_status(connected=True, ws_url=ws_url)

                sub: dict[str, Any] = {"type": "subscribe", "channels": channels}
                if market_tickers:
                    sub["market_tickers"] = market_tickers
                await ws.send(json.dumps(sub))
                ack = await ws.recv()
                logger.info("Subscription ack: %s", ack[:200])
                _write_status(connected=True, subscribed=channels)

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning("Unparseable message: %s", raw[:200])
                        continue
                    _dispatch(msg)
                    _write_status(connected=True, last_msg_at=time.time())

        except websockets.ConnectionClosed:
            logger.warning("Connection closed, reconnecting in %.0fs", delay)
        except OSError as exc:
            logger.error("Connection error: %s, retrying in %.0fs", exc, delay)
        except Exception:
            logger.exception("Unexpected error, reconnecting in %.0fs", delay)
            _write_status(connected=False, error=str(sys.exc_info()[1]))

        _write_status(connected=False)
        await asyncio.sleep(delay)
        delay = min(delay * 1.5, MAX_RECONNECT_DELAY)


def main() -> None:
    parser = argparse.ArgumentParser(description="TraderBot WebSocket daemon")
    parser.add_argument("--channels", nargs="+", default=CHANNELS)
    parser.add_argument("--tickers", nargs="*")
    args = parser.parse_args()

    _ensure_dirs()

    private_key_pem = get_credential("kalshi", "private_key_pem")
    if not private_key_pem:
        logger.error("Kalshi credentials not found.")
        sys.exit(1)

    api_key = get_credential("kalshi", "api_key")
    if not api_key:
        logger.error("Kalshi API key not found.")
        sys.exit(1)

    # Resolve PEM — handle KALSHI_PRIVATE_KEY_PATH fallback
    priv = private_key_pem.get_secret_value()
    pem_path = Path(priv)
    if pem_path.exists():
        priv = pem_path.read_text().strip()

    ws_url = "wss://api.elections.kalshi.com/trade-api/ws/v2"

    stop = asyncio.Event()

    def _handle_sigterm() -> None:
        logger.info("Received SIGTERM, shutting down...")
        _write_status(connected=False, shutdown="SIGTERM")
        stop.set()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.add_signal_handler(signal.SIGTERM, _handle_sigterm)
    loop.add_signal_handler(signal.SIGINT, _handle_sigterm)

    async def _amain() -> None:
        task = asyncio.create_task(
            _run(api_key.get_secret_value(), priv, ws_url, args.channels, market_tickers=args.tickers)
        )
        await asyncio.wait(
            [task, asyncio.create_task(stop.wait())],
            return_when=asyncio.FIRST_COMPLETED,
        )
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    try:
        loop.run_until_complete(_amain())
    except KeyboardInterrupt:
        _write_status(connected=False, shutdown="KeyboardInterrupt")


if __name__ == "__main__":
    main()