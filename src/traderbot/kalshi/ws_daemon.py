"""Persistent WebSocket daemon that maintains comprehensive market data cache.

Connects to Kalshi WebSocket, subscribes to all 6 valid channels
(``ticker``, ``market_lifecycle_v2``, ``orderbook_delta``, ``fill``,
``user_orders``, ``market_positions``), and writes data into
``~/.traderbot/event_category_cache.json`` so that CLI commands always
see current data without REST polling.

Cache format::

    {
      "ts": <unix>,
      "map": { "<ticker>": "<category>", ... },
      "tickers": {
        "<ticker>": {
          "yes_bid": <int>,
          "no_bid": <int>,
          "volume": <int>,
          "open_interest": <int>,
          "updated_at": <unix>
        },
        ...
      },
      "orderbooks": {
        "<ticker>": {
          "yes_bids": [[<price>, <size>], ...],
          "no_bids": [[<price>, <size>], ...],
          "updated_at": <unix>
        },
        ...
      },
      "fills": [
        {
          "order_id": <str>,
          "ticker": <str>,
          "side": <str>,
          "shares": <int>,
          "price": <int>,
          "timestamp": <unix>
        },
        ...
      ],
      "orders": {
        "<order_id>": {
          "ticker": <str>,
          "status": <str>,
          "side": <str>,
          "remaining": <int>,
          "filled": <int>,
          "updated_at": <unix>
        },
        ...
      },
      "positions": {
        "<ticker>": {
          "side": <str>,
          "quantity": <int>,
          "entry_price": <int>,
          "current_price": <int>,
          "updated_at": <unix>
        },
        ...
      }
    }

Seeds the cache from REST on startup if empty or stale.
Re-subscribes orderbook_delta dynamically when new tickers arrive via
market_lifecycle_v2.
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
WS_URL = "wss://external-api-ws.kalshi.com/trade-api/ws/v2"
RECONNECT_DELAY = 5.0
MAX_RECONNECT_DELAY = 60.0
PING_INTERVAL = 15.0
DAEMON_STATUS_PATH = get_data_dir() / "ws_daemon.json"

VALID_CHANNELS: frozenset[str] = frozenset(
    {
        "ticker",
        "orderbook_delta",
        "market_lifecycle_v2",
        "fill",
        "user_orders",
        "market_positions",
    }
)

_MARKET_CHANNELS: frozenset[str] = frozenset({"ticker", "orderbook_delta"})
_PORTFOLIO_CHANNELS: frozenset[str] = frozenset({"fill", "user_orders", "market_positions"})

_MAX_FILL_HISTORY = 500


def _write_status(**kw: object) -> None:
    payload = {"pid": os.getpid(), "uptime": time.time(), **kw}
    DAEMON_STATUS_PATH.write_text(json.dumps(payload, indent=2))


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            data = json.loads(CACHE_PATH.read_text())
            return {
                "map": data.get("map", {}),
                "tickers": data.get("tickers", {}),
                "orderbooks": data.get("orderbooks", {}),
                "fills": data.get("fills", []),
                "orders": data.get("orders", {}),
                "positions": data.get("positions", {}),
            }
        except (json.JSONDecodeError, KeyError):
            pass
    return {"map": {}, "tickers": {}, "orderbooks": {}, "fills": [], "orders": {}, "positions": {}}


def _save_cache(data: dict) -> None:
    payload = {
        "ts": time.time(),
        "map": data.get("map", {}),
        "tickers": data.get("tickers", {}),
        "orderbooks": data.get("orderbooks", {}),
        "fills": data.get("fills", []),
        "orders": data.get("orders", {}),
        "positions": data.get("positions", {}),
    }
    CACHE_PATH.write_text(json.dumps(payload, indent=2))


async def _seed_from_rest() -> tuple[dict[str, str], list[str]]:
    """Seed event→category map and list of known market tickers from REST."""
    logger.info("Seeding event cache from REST...")
    from traderbot.kalshi.client import KalshiClient

    client = KalshiClient()
    all_events: dict[str, str] = {}
    all_markets: list[str] = []
    cursor: str | None = None
    for _ in range(20):
        try:
            params: dict[str, object] = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
            resp = await client.get("/events", **params)
            if resp.status_code == 429:
                logger.warning(
                    "REST seed rate limited at cursor=%s — collected %d so far",
                    cursor,
                    len(all_events),
                )
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
            logger.warning(
                "REST seed failed at cursor=%s: %s — collected %d so far",
                cursor,
                exc,
                len(all_events),
            )
            break

    # Also fetch market tickers for orderbook_delta subscription
    cursor = None
    for _ in range(20):
        try:
            params: dict[str, object] = {"limit": 200, "status": "open"}
            if cursor:
                params["cursor"] = cursor
            resp = await client.get("/markets", **params)
            if resp.status_code == 429:
                logger.warning("REST market seed rate limited — collected %d so far", len(all_markets))
                break
            if resp.status_code != 200:
                logger.warning("REST market seed failed: %d", resp.status_code)
                break
            data = resp.json()
            raw = data.get("markets", [])
            if isinstance(raw, list):
                for mkt in raw:
                    tkr = mkt.get("ticker", "")
                    if tkr:
                        all_markets.append(tkr)
            cursor = data.get("cursor")
            if not cursor:
                break
        except Exception as exc:
            logger.warning("REST market seed failed: %s — collected %d", exc, len(all_markets))
            break

    await client.close()
    logger.info("Seeded %d events and %d market tickers from REST", len(all_events), len(all_markets))
    return all_events, all_markets


async def _run(api_key: str, private_key: str, ws_url: str) -> None:
    delay = RECONNECT_DELAY

    cache = _load_cache()
    current_map: dict[str, str] = cache.get("map", {})
    current_tickers: dict = cache.get("tickers", {})
    current_orderbooks: dict = cache.get("orderbooks", {})
    current_fills: list = cache.get("fills", [])
    current_orders: dict = cache.get("orders", {})
    current_positions: dict = cache.get("positions", {})

    # Track which tickers we've subscribed orderbook_delta for
    ob_subscribed: set[str] = set()

    logger.info(
        "Loaded cache: %d events, %d tickers, %d orderbooks, %d fills, %d orders, %d positions",
        len(current_map),
        len(current_tickers),
        len(current_orderbooks),
        len(current_fills),
        len(current_orders),
        len(current_positions),
    )
    if not current_map:
        current_map, seed_tickers = await _seed_from_rest()
        # Record seed tickers for orderbook_delta subscription
        for t in seed_tickers:
            ob_subscribed.add(t)
        _save_cache({
            "map": current_map,
            "tickers": current_tickers,
            "orderbooks": current_orderbooks,
            "fills": current_fills,
            "orders": current_orders,
            "positions": current_positions,
        })
    else:
        # Pre-populate ob_subscribed from existing orderbook keys and known tickers
        ob_subscribed.update(current_orderbooks.keys())
        ob_subscribed.update(current_tickers.keys())

    _write_status(connected=False, cache_size=len(current_map))

    msg_id = 0

    async def _send_sub(ws: websockets.WebSocketClientProtocol, params: dict) -> None:
        nonlocal msg_id
        msg_id += 1
        msg = {"id": msg_id, "cmd": "subscribe", "params": params}
        await ws.send(json.dumps(msg))

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

                # 1) Portfolio-level channels — no market_ticker needed
                await _send_sub(ws, {"channels": ["fill", "user_orders", "market_positions"]})

                # 2) Global broadcast channels
                await _send_sub(ws, {"channels": ["market_lifecycle_v2"]})

                # 3) Ticker — subscribe globally (no per-market filter needed by API)
                await _send_sub(ws, {"channels": ["ticker"]})

                # 4) orderbook_delta — subscribe per-market using known tickers
                if ob_subscribed:
                    tickers_list = sorted(ob_subscribed)
                    # Kalshi may have limits per subscription; batch if needed
                    batch_size = 100
                    for i in range(0, len(tickers_list), batch_size):
                        batch = tickers_list[i : i + batch_size]
                        await _send_sub(ws, {"channels": ["orderbook_delta"], "market_tickers": batch})
                        logger.info("Subscribed orderbook_delta for %d tickers (batch %d)", len(batch), i // batch_size + 1)

                # Read acks for all subscriptions
                for _ in range(msg_id):
                    try:
                        ack = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        logger.info("Subscription ack: %s", str(ack)[:200])
                    except asyncio.TimeoutError:
                        logger.warning("Timeout waiting for subscription ack")
                        break

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    channel = msg.get("channel", msg.get("type", ""))
                    now = time.time()

                    # --- ticker channel ---
                    if channel == "ticker":
                        data = msg.get("msg", msg)
                        tkr = data.get("ticker", "")
                        if tkr:
                            current_tickers[tkr] = {
                                "yes_bid": data.get("yes_bid"),
                                "no_bid": data.get("no_bid"),
                                "volume": data.get("volume"),
                                "open_interest": data.get("open_interest"),
                                "updated_at": now,
                            }
                            _save_cache({
                                "map": current_map, "tickers": current_tickers,
                                "orderbooks": current_orderbooks, "fills": current_fills,
                                "orders": current_orders, "positions": current_positions,
                            })
                        _write_status(connected=True, last_msg_at=now, cache_size=len(current_map))
                        continue

                    # --- market_lifecycle_v2 channel ---
                    if channel == "market_lifecycle_v2":
                        evt = msg.get("event", msg)
                        ticker = evt.get("ticker", "")
                        category = evt.get("category", "")
                        lifecycle = evt.get("lifecycle", evt.get("status", ""))

                        if ticker and category:
                            current_map[ticker] = category
                            _save_cache({
                                "map": current_map, "tickers": current_tickers,
                                "orderbooks": current_orderbooks, "fills": current_fills,
                                "orders": current_orders, "positions": current_positions,
                            })
                            logger.debug("Cache updated: %s → %s (%s)", ticker, category, lifecycle)

                        # If this ticker has markets and we haven't subscribed
                        # orderbook_delta for it yet, do so now
                        if ticker and ticker not in ob_subscribed:
                            ob_subscribed.add(ticker)
                            try:
                                await _send_sub(ws, {
                                    "channels": ["orderbook_delta"],
                                    "market_tickers": [ticker],
                                })
                                logger.info("Dynamic orderbook_delta sub for new ticker: %s", ticker)
                            except Exception as exc:
                                logger.warning("Failed to sub orderbook_delta for %s: %s", ticker, exc)

                        _write_status(connected=True, last_msg_at=now, cache_size=len(current_map))
                        continue

                    # --- orderbook_delta channel ---
                    if channel == "orderbook_delta":
                        data = msg.get("msg", msg)
                        tkr = data.get("ticker", msg.get("market_ticker", ""))
                        if tkr:
                            ob = current_orderbooks.get(tkr, {})
                            # Apply deltas: yes_bids and no_bids are arrays of [price, size]
                            if "yes_bids" in data:
                                ob["yes_bids"] = data["yes_bids"]
                            if "no_bids" in data:
                                ob["no_bids"] = data["no_bids"]
                            # Handle snapshot-style full replacement
                            if "yes" in data:
                                ob["yes_bids"] = data["yes"]
                            if "no" in data:
                                ob["no_bids"] = data["no"]
                            ob["updated_at"] = now
                            current_orderbooks[tkr] = ob
                            _save_cache({
                                "map": current_map, "tickers": current_tickers,
                                "orderbooks": current_orderbooks, "fills": current_fills,
                                "orders": current_orders, "positions": current_positions,
                            })
                        _write_status(connected=True, last_msg_at=now, cache_size=len(current_map))
                        continue

                    # --- fill channel ---
                    if channel == "fill":
                        data = msg.get("msg", msg)
                        fill_entry = {
                            "order_id": str(data.get("order_id", "")),
                            "ticker": data.get("ticker", data.get("market_ticker", "")),
                            "side": data.get("side", ""),
                            "shares": data.get("shares", data.get("count", 0)),
                            "price": data.get("price", 0),
                            "timestamp": now,
                        }
                        current_fills.append(fill_entry)
                        # Trim to max history
                        if len(current_fills) > _MAX_FILL_HISTORY:
                            current_fills = current_fills[-_MAX_FILL_HISTORY:]
                        _save_cache({
                            "map": current_map, "tickers": current_tickers,
                            "orderbooks": current_orderbooks, "fills": current_fills,
                            "orders": current_orders, "positions": current_positions,
                        })
                        _write_status(connected=True, last_msg_at=now, cache_size=len(current_map))
                        continue

                    # --- user_orders channel ---
                    if channel == "user_orders":
                        data = msg.get("msg", msg)
                        # May be a single order or list of orders
                        orders_raw = data.get("orders", [data]) if isinstance(data, dict) else data
                        if not isinstance(orders_raw, list):
                            orders_raw = [orders_raw]
                        for order_data in orders_raw:
                            oid = str(order_data.get("order_id", ""))
                            if oid:
                                current_orders[oid] = {
                                    "ticker": order_data.get("ticker", order_data.get("market_ticker", "")),
                                    "status": order_data.get("status", ""),
                                    "side": order_data.get("side", ""),
                                    "remaining": order_data.get("remaining", order_data.get("unfilled", 0)),
                                    "filled": order_data.get("filled", 0),
                                    "updated_at": now,
                                }
                        _save_cache({
                            "map": current_map, "tickers": current_tickers,
                            "orderbooks": current_orderbooks, "fills": current_fills,
                            "orders": current_orders, "positions": current_positions,
                        })
                        _write_status(connected=True, last_msg_at=now, cache_size=len(current_map))
                        continue

                    # --- market_positions channel ---
                    if channel == "market_positions":
                        data = msg.get("msg", msg)
                        # May be a single position or list
                        positions_raw = data.get("positions", [data]) if isinstance(data, dict) else data
                        if not isinstance(positions_raw, list):
                            positions_raw = [positions_raw]
                        for pos_data in positions_raw:
                            tkr = pos_data.get("ticker", pos_data.get("market_ticker", ""))
                            if tkr:
                                current_positions[tkr] = {
                                    "side": pos_data.get("side", ""),
                                    "quantity": pos_data.get("quantity", pos_data.get("count", 0)),
                                    "entry_price": pos_data.get("entry_price", 0),
                                    "current_price": pos_data.get("current_price", 0),
                                    "updated_at": now,
                                }
                        _save_cache({
                            "map": current_map, "tickers": current_tickers,
                            "orderbooks": current_orderbooks, "fills": current_fills,
                            "orders": current_orders, "positions": current_positions,
                        })
                        _write_status(connected=True, last_msg_at=now, cache_size=len(current_map))
                        continue

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
    args = parser.parse_args()

    stop = asyncio.Event()

    def _handle_sigterm() -> None:
        logger.info("SIGTERM received, shutting down...")
        _write_status(connected=False, shutdown="SIGTERM")
        stop.set()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.add_signal_handler(signal.SIGTERM, _handle_sigterm)
    loop.add_signal_handler(signal.SIGINT, _handle_sigterm)

    async def _resolve_creds() -> tuple[str, str] | None:
        api_key_str = get_credential("kalshi", "api_key")
        if not api_key_str:
            logger.error("Kalshi API key not found — will retry on reconnect")
            return None
        api_key = api_key_str.get_secret_value()

        raw = get_credential("kalshi", "private_key_pem")
        priv: str | None = None

        if raw:
            val = raw.get_secret_value()
            if val.startswith("/") and "-----BEGIN" not in val:
                p = Path(val)
                if not p.exists():
                    p = get_data_dir() / p.name
                if p.exists():
                    priv = p.read_text().strip()
            elif "-----BEGIN" in val and "-----END" in val:
                priv = val.replace("\\n", "\n").strip()

        if not priv:
            key_path = get_credential("kalshi", "private_key_path")
            if key_path:
                kp = key_path.get_secret_value()
                kp_path = Path(kp)
                if not kp_path.exists():
                    kp_path = get_data_dir() / kp_path.name
                if kp_path.exists():
                    priv = kp_path.read_text().strip()

        if not priv:
            logger.error("Kalshi private key not found — will retry on reconnect")
            return None

        return (api_key, priv)

    creds = loop.run_until_complete(_resolve_creds())
    if not creds:
        loop.close()
        sys.exit(1)
    api_key_str, priv_str = creds

    async def _amain() -> None:
        task = asyncio.create_task(_run(api_key_str, priv_str, WS_URL))
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