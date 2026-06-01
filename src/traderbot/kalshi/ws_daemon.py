"""Persistent WebSocket daemon that maintains the event category cache.

Connects to Kalshi WebSocket, subscribes to ``market_lifecycle_v2``,
and writes new events directly into ``~/.traderbot/event_category_cache.json``
so ``list_markets_by_category()`` always sees current data without REST polling.
Also seeds the cache from REST on startup if it's empty or stale.
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

CACHE_PATH = get_data_dir() / "event_category_cache.json"
WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
RECONNECT_DELAY = 5.0
MAX_RECONNECT_DELAY = 60.0
PING_INTERVAL = 15.0
DAEMON_STATUS_PATH = get_data_dir() / "ws_daemon.json"


def _write_status(**kw: object) -> None:
    payload = {"pid": os.getpid(), "uptime": time.time(), **kw}
    DAEMON_STATUS_PATH.write_text(json.dumps(payload, indent=2))


def _load_cache() -> dict[str, str]:
    if CACHE_PATH.exists():
        try:
            data = json.loads(CACHE_PATH.read_text())
            return data.get("map", {})
        except (json.JSONDecodeError, KeyError):
            pass
    return {}


def _save_cache(entries: dict[str, str]) -> None:
    payload = {"ts": time.time(), "map": entries}
    CACHE_PATH.write_text(json.dumps(payload, indent=2))


async def _seed_from_rest() -> dict[str, str]:
    logger.info("Seeding event cache from REST...")
    from traderbot.kalshi.client import KalshiClient
    client = KalshiClient()
    all_events: dict[str, str] = {}
    cursor: str | None = None
    for _ in range(20):
        try:
            params: dict[str, object] = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
            resp = await client.get("/events", **params)
            if resp.status_code == 429:
                logger.warning("REST seed rate limited at cursor=%s — collected %d so far", cursor, len(all_events))
                break
            if resp.status_code != 200:
                logger.warning("REST seed failed at cursor=%s: %d", cursor, resp.status_code)
                break
            data = resp.json()
            raw = data.get("events", data.get("event", []))
            if isinstance(raw, list):
                for ev in raw:
                    ticker = ev.get("ticker") or ev.get("event_ticker", "")
                    category = ev.get("category", "")
                    if ticker and category:
                        all_events[ticker] = category
            cursor = data.get("cursor")
            if not cursor:
                break
        except Exception as exc:
            logger.warning("REST seed failed at cursor=%s: %s — collected %d so far", cursor, exc, len(all_events))
            break
    await client.close()
    logger.info("Seeded %d events from REST", len(all_events))
    return all_events


async def _run(api_key: str, private_key: str, ws_url: str) -> None:
    delay = RECONNECT_DELAY

    current_map = _load_cache()
    logger.info("Loaded %d events from existing cache", len(current_map))
    if not current_map:
        current_map = await _seed_from_rest()
        _save_cache(current_map)
    _write_status(connected=False, cache_size=len(current_map))

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
                _write_status(connected=True)

                sub = {"id": 1, "cmd": "subscribe", "params": {"channels": ["market_lifecycle_v2"]}}
                await ws.send(json.dumps(sub))
                ack = await ws.recv()
                logger.info("Subscription ack: %s", ack[:200])

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    channel = msg.get("channel", msg.get("type", ""))
                    if channel != "market_lifecycle_v2":
                        continue

                    evt = msg.get("event", msg)
                    ticker = evt.get("ticker", "")
                    category = evt.get("category", "")
                    lifecycle = evt.get("lifecycle", evt.get("status", ""))

                    if ticker and category:
                        current_map[ticker] = category
                        _save_cache(current_map)
                        logger.debug("Cache updated: %s → %s (%s)", ticker, category, lifecycle)

                    _write_status(connected=True, last_msg_at=time.time(), cache_size=len(current_map))

        except websockets.ConnectionClosed:
            logger.warning("Connection closed, reconnecting in %.0fs", delay)
        except OSError as exc:
            logger.error("Connection error: %s, retrying in %.0fs", exc, delay)
        except Exception:
            logger.exception("Unexpected error, reconnecting in %.0fs", delay)

        _write_status(connected=False)
        await asyncio.sleep(delay)
        delay = min(delay * 1.5, MAX_RECONNECT_DELAY)


def main() -> None:
    parser = argparse.ArgumentParser(description="TraderBot WebSocket event cache daemon")
    parser.parse_args()

    private_key_pem = get_credential("kalshi", "private_key_pem")
    if not private_key_pem:
        logger.error("Kalshi credentials not found.")
        sys.exit(1)
    api_key = get_credential("kalshi", "api_key")
    if not api_key:
        logger.error("Kalshi API key not found.")
        sys.exit(1)

    priv = private_key_pem.get_secret_value()
    pem_path = Path(priv)
    if pem_path.exists():
        priv = pem_path.read_text().strip()

    stop = asyncio.Event()

    def _handle_sigterm() -> None:
        logger.info("SIGTERM received, shutting down...")
        stop.set()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.add_signal_handler(signal.SIGTERM, _handle_sigterm)
    loop.add_signal_handler(signal.SIGINT, _handle_sigterm)

    async def _amain() -> None:
        task = asyncio.create_task(_run(api_key.get_secret_value(), priv, WS_URL))
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
        pass


if __name__ == "__main__":
    main()