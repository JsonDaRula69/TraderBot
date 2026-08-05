"""Always-on TraderBot daemon (DD-016).

Single process that combines the Kalshi WebSocket stream, the scheduled data
pipeline, and the MCP server over ``streamable-http`` on loopback. Agents call
its MCP tools; the WebSocket is the sole source of real-time Kalshi data with
REST used only for startup seeding, recovery, and historical data (memory
#277). Graceful shutdown stops components in reverse order.

Entry point: ``traderbot-daemon`` console script → :func:`run_daemon`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Final

import uvicorn

from traderbot.data.pipeline import DataCollectionService
from traderbot.data.providers.news import NewsProvider
from traderbot.data.providers.nws import NwsProvider
from traderbot.data.providers.open_meteo import OpenMeteoProvider
from traderbot.data.providers.settlement import SettlementMonitor
from traderbot.kalshi.client import Environment, KalshiClient
from traderbot.kalshi.websocket import KalshiWebSocketManager
from traderbot.kalshi.ws_cache import MarketCache
from traderbot.mcp.server import app, start_scheduler, stop_scheduler
from traderbot.paths import get_db_path
from traderbot.secrets.resolver import build_secrets_store
from traderbot.secrets.store import SecretsStore
from traderbot.state import (
    DATA_PIPELINE_RUNNING,
    DATA_PIPELINE_STOPPED,
    WEBSOCKET_CONNECTED,
    WEBSOCKET_DISCONNECTED,
    WEBSOCKET_FAIL_OPEN,
    set_data_pipeline,
    set_market_cache,
    set_websocket,
)

logger = logging.getLogger(__name__)

DEFAULT_PORT: Final = 8765
_DEFAULT_HOST: Final = "127.0.0.1"
# A fetch/insert cycle that exceeds this counts as a stalled iteration.
_COMPONENT_TIMEOUT: Final = 60.0

# Map a WS message type to a MarketCache action. ``None`` means the message is
# returned as-is (public market messages carry a ``msg`` event payload).
_WS_CHANNEL_ACTIONS: Final = {
    "ticker": "ticker",
    "orderbook_delta": "orderbook",
    "market_lifecycle_v2": "lifecycle",
    "fill": "fill",
    "user_orders": "order",
    "market_positions": "position",
}


async def apply_ws_message(message: dict[str, Any], cache: MarketCache) -> None:
    """Route one inbound WebSocket message into the in-memory market cache.

    Args:
        message: A parsed JSON message from
            :meth:`traderbot.kalshi.websocket.KalshiWebSocket.receive`.
        cache: The :class:`MarketCache` to update in place.
    """
    msg_type = message.get("type") if isinstance(message.get("type"), str) else None
    if msg_type is None:
        return
    action = _WS_CHANNEL_ACTIONS.get(msg_type)
    if action is None:
        return
    # The channel's data lives under ``msg`` (server envelope).
    event = message.get("msg") if isinstance(message.get("msg"), dict) else {}
    if not isinstance(event, dict):
        return

    if action == "ticker":
        ticker = event.get("market_ticker") or event.get("ticker")
        if isinstance(ticker, str):
            cache.update_ticker(
                ticker,
                last_price=_to_float(event.get("last_price")),
                bid=_to_float(event.get("bid")),
                ask=_to_float(event.get("ask")),
                volume=_to_float(event.get("volume")),
                open_interest=_to_float(event.get("open_interest")),
            )
    elif action == "orderbook":
        # orderbook_delta carries either a full snapshot (``bids``/``asks``
        # with ``yes_price``-scaled levels) or a delta (``price_dollars``,
        # ``delta_fp``, ``side``). Full snapshots replace the cache; deltas
        # are recorded via the lifecycle path. For Phase 2 the snapshot path
        # is the one that drives ``market_prices``.
        ticker = event.get("market_ticker") or event.get("ticker")
        if isinstance(ticker, str) and "bids" in event:
            bids = event.get("bids") if isinstance(event.get("bids"), list) else []
            asks = event.get("asks") if isinstance(event.get("asks"), list) else []
            cache.update_orderbook(ticker, bids=bids, asks=asks)
    elif action == "lifecycle":
        ticker = event.get("market_ticker") or event.get("market_id")
        if isinstance(ticker, str):
            cache.update_lifecycle(ticker, {str(k): v for k, v in event.items()})
    elif action == "fill":
        cache.record_fill({str(k): v for k, v in event.items()})
    elif action == "order":
        cache.record_order({str(k): v for k, v in event.items()})
    elif action == "position":
        ticker = event.get("market_ticker") or event.get("ticker")
        if isinstance(ticker, str):
            cache.update_position(ticker, {str(k): v for k, v in event.items()})


def _to_float(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


async def build_components(
    secrets: SecretsStore | None = None,
    *,
    environment: Environment = "production",
    db_path: Any = None,
    port: int = DEFAULT_PORT,
    host: str = _DEFAULT_HOST,
) -> dict[str, Any]:
    """Construct the daemon's component graph.

    Returns a dict of components owned by the daemon lifecycle:
    ``cache``, ``client``, ``ws``, ``data``, ``mcp_app``, ``app``.
    """
    store = secrets if secrets is not None else build_secrets_store()
    api_key = store.get("kalshi", "api_key")
    private_key_pem = store.get("kalshi", "private_key_pem")
    if not api_key or not private_key_pem:
        logger.warning(
            "kalshi credentials missing; websocket/client will fail open "
            "(daemon still serves from SQLite cache)"
        )

    client = KalshiClient(
        api_key=api_key,
        private_key_pem=private_key_pem,
        environment=environment,
    )
    cache = MarketCache(db_path=db_path if db_path is not None else get_db_path())
    cache.load_from_db()
    set_market_cache(cache)

    async def _mark_ws_connected() -> None:
        set_websocket(WEBSOCKET_CONNECTED)

    async def _mark_ws_fail_open() -> None:
        set_websocket(WEBSOCKET_FAIL_OPEN)

    ws = KalshiWebSocketManager(
        api_key=api_key or "",
        private_key_pem=private_key_pem or "",
        environment=environment,
        on_message=_message_callback(cache),
        on_reconnect=_mark_ws_connected,
        on_fail_open=_mark_ws_fail_open,
    )

    data = DataCollectionService()
    data.register(SettlementMonitor(client=client))
    data.register(OpenMeteoProvider())
    data.register(NwsProvider())
    data.register(NewsProvider())

    mcp_app = app.streamable_http_app()
    return {
        "cache": cache,
        "client": client,
        "ws": ws,
        "data": data,
        "mcp_app": mcp_app,
        "app": app,
    }


def _message_callback(cache: MarketCache) -> Callable[[dict[str, Any]], Awaitable[None]]:
    async def on_message(message: dict[str, Any]) -> None:
        try:
            await apply_ws_message(message, cache)
        except Exception:  # noqa: BLE001 — never let a bad message kill the stream
            logger.exception("failed to apply ws message")

    return on_message


async def run_daemon(
    *,
    port: int = DEFAULT_PORT,
    host: str = _DEFAULT_HOST,
    environment: Environment = "production",
) -> None:
    """Run the always-on daemon until SIGTERM/SIGINT, then shut down cleanly."""
    components = await build_components(environment=environment, port=port, host=host)
    cache: MarketCache = components["cache"]
    ws: KalshiWebSocketManager = components["ws"]
    data: DataCollectionService = components["data"]

    # Shutdown bookkeeping.
    stop = asyncio.Event()

    def _request_stop(signum: int, _frame: object) -> None:
        logger.info("received signal %s; shutting down", signum)
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _request_stop, sig, None)

    # Component startup (cache already loaded).
    await cache.start_persist_task()
    await start_scheduler()
    await ws.start()
    await data.start()
    set_data_pipeline(DATA_PIPELINE_RUNNING)

    # Host the MCP app on loopback.
    config = uvicorn.Config(
        components["mcp_app"],
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    mcp_task = asyncio.create_task(server.serve(), name="traderbot-mcp-http")
    logger.info("daemon ready on http://%s:%s/mcp (pid=%s)", host, port, os.getpid())

    try:
        await stop.wait()
    finally:
        logger.info("stopping daemon components (reverse order)")
        mcp_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await mcp_task
        await data.stop()
        await ws.stop()
        await stop_scheduler()
        await cache.stop_persist_task()
        await components["client"].close()
        set_websocket(WEBSOCKET_DISCONNECTED)
        set_data_pipeline(DATA_PIPELINE_STOPPED)
        logger.info("daemon stopped")


def main(argv: Sequence[str] | None = None) -> None:
    """Entry point for the ``traderbot-daemon`` console script.

    ``argv`` is accepted so the ``traderbot daemon`` CLI subcommand can
    forward its parsed flags without leaking the ``daemon`` token into
    ``sys.argv`` (which would be rejected by this parser).
    """
    import argparse

    parser = argparse.ArgumentParser(description="Run the always-on TraderBot daemon")
    parser.add_argument("--host", default=_DEFAULT_HOST, help="bind host (loopback only)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="bind port")
    parser.add_argument(
        "--environment",
        default="production",
        choices=["production", "demo"],
        help="Kalshi environment",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        asyncio.run(run_daemon(port=args.port, host=args.host, environment=args.environment))
    except KeyboardInterrupt:
        logger.info("interrupted")


__all__ = ["DEFAULT_PORT", "run_daemon"]
