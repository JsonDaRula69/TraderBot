"""Always-on TraderBot daemon for WS, data workers, storage, and MCP (DD-016)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys
from collections.abc import Awaitable, Callable, Sequence
from contextlib import ExitStack
from pathlib import Path
from types import FrameType
from typing import Any, Final

import uvicorn

from traderbot.data.pipeline import DataCollectionService
from traderbot.data.providers.news import NewsProvider
from traderbot.data.providers.nws import NwsProvider
from traderbot.data.providers.open_meteo import OpenMeteoProvider
from traderbot.data.providers.settlement import SettlementMonitor
from traderbot.db.access import DatabaseAccess
from traderbot.db.chroma_store import ChromaStore
from traderbot.db.migrations import init_schema
from traderbot.db.pool import SQLiteConnectionPool
from traderbot.db.security import create_chroma_root
from traderbot.kalshi.client import Environment, KalshiClient
from traderbot.kalshi.websocket import KalshiWebSocketManager
from traderbot.kalshi.ws_cache import MarketCache
from traderbot.mcp.server import app
from traderbot.paths import get_data_dir, get_db_path
from traderbot.secrets.resolver import build_secrets_store, build_secrets_store_selection
from traderbot.secrets.rotation import start_scheduler, stop_scheduler
from traderbot.secrets.store import SecretsStore
from traderbot.state import (
    DATA_PIPELINE_RUNNING,
    DATA_PIPELINE_STOPPED,
    WEBSOCKET_CONNECTED,
    WEBSOCKET_DISCONNECTED,
    WEBSOCKET_FAIL_OPEN,
    set_data_pipeline,
    set_market_cache,
    set_storage_health,
    set_websocket,
)

logger = logging.getLogger(__name__)

DEFAULT_PORT: Final = 8765
_DEFAULT_HOST: Final = "127.0.0.1"
# A fetch/insert cycle that exceeds this counts as a stalled iteration.
_COMPONENT_TIMEOUT: Final = 60.0

# #219: when the credential pair is missing at build time the daemon re-probes the secrets
# store on this backoff (capped) for as long as it stays degraded. The idle watch cadence
# also covers a fail-open that starts later in the process's life.
_CREDENTIAL_PROBE_INTERVAL_SECONDS: Final = 5.0
_CREDENTIAL_PROBE_MAX_INTERVAL_SECONDS: Final = 60.0
_CREDENTIAL_WATCH_INTERVAL_SECONDS: Final = 30.0

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
    """Route one inbound WebSocket message into the in-memory market cache."""
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
    db_path: Path | None = None,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Construct the daemon-owned component graph."""
    database_path = db_path if db_path is not None else get_db_path()
    data_directory = data_root if data_root is not None else get_data_dir()
    chroma_root = data_directory / "chromadb"

    async def _mark_ws_connected() -> None:
        set_websocket(WEBSOCKET_CONNECTED)

    async def _mark_ws_fail_open() -> None:
        set_websocket(WEBSOCKET_FAIL_OPEN)

    with ExitStack() as startup:
        _ = startup.callback(set_storage_health, False, False, False)
        init_schema(database_path)
        set_storage_health(True, False, False)
        pool = SQLiteConnectionPool()
        _ = startup.callback(pool.shutdown)
        if not chroma_root.exists():
            create_chroma_root(chroma_root)
        chroma = ChromaStore(chroma_root)
        _ = startup.callback(chroma.close)
        set_storage_health(True, True, True)
        access = DatabaseAccess(pool, data_directory)

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
        cache = MarketCache(pool, database_path)
        cache.load_from_db()
        set_market_cache(cache)

        ws = KalshiWebSocketManager(
            api_key=api_key or "",
            private_key_pem=private_key_pem or "",
            environment=environment,
            on_message=_message_callback(cache),
            on_reconnect=_mark_ws_connected,
            on_fail_open=_mark_ws_fail_open,
        )

        data = DataCollectionService()
        settlement = SettlementMonitor(client, pool, database_path)
        data.register(settlement)
        data.register(OpenMeteoProvider(pool, database_path))
        data.register(NwsProvider(pool, database_path))
        data.register(NewsProvider())

        components = {
            "pool": pool,
            "chroma": chroma,
            "access": access,
            "cache": cache,
            "client": client,
            "ws": ws,
            "data": data,
            "settlement": settlement,
            "mcp_app": app.streamable_http_app(),
            "app": app,
            # #219: the supervisor's trigger. ``False`` means the pair was missing at build
            # time, so the WS manager and client were constructed fail-open.
            "credentials_present": bool(api_key and private_key_pem),
        }
        _ = startup.pop_all()
        return components


def _message_callback(cache: MarketCache) -> Callable[[dict[str, Any]], Awaitable[None]]:
    async def on_message(message: dict[str, Any]) -> None:
        try:
            await apply_ws_message(message, cache)
        except Exception:  # noqa: BLE001 — never let a bad message kill the stream
            logger.exception("failed to apply ws message")

    return on_message


class CredentialSupervisor:
    """Heal a fail-open credential start without a daemon restart (#219).

    :func:`build_components` resolves the Kalshi credential pair once. When the secrets store
    is not yet reachable - a boot-order race between the daemon and Infisical - the resolver
    falls back to the local store, the pair comes back empty, and the WebSocket manager and
    client are constructed fail-open. Nothing re-reads the store afterwards, so the stream
    never comes up: the fleet keeps serving stale cache until an operator restarts the daemon,
    which breaks the 24/7 autonomy rule.

    This supervisor watches for that degraded state - the pair missing at build time, or the
    stream failing open at any later point - re-resolves the canonical pair and hands it to
    ``on_recovered`` so the caller can rebuild and restart the credential-bound components in
    place. Probing backs off while degraded but never gives up: the store may be unreachable
    for an unbounded time, so the daemon must tolerate it and heal as soon as it returns.
    Credential material is never logged.
    """

    def __init__(
        self,
        *,
        is_degraded: Callable[[], bool],
        resolve: Callable[[], Awaitable[tuple[str | None, str | None]]],
        on_recovered: Callable[[str, str], Awaitable[None]],
        probe_interval: float = _CREDENTIAL_PROBE_INTERVAL_SECONDS,
        max_interval: float = _CREDENTIAL_PROBE_MAX_INTERVAL_SECONDS,
        watch_interval: float = _CREDENTIAL_WATCH_INTERVAL_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._is_degraded = is_degraded
        self._resolve = resolve
        self._on_recovered = on_recovered
        self._probe_interval = probe_interval
        self._max_interval = max_interval
        self._watch_interval = watch_interval
        self._sleep = sleep
        self._stop = asyncio.Event()
        self._interval = probe_interval
        self._probes = 0
        self._recoveries = 0

    @property
    def probes(self) -> int:
        """Credential probes attempted so far."""
        return self._probes

    @property
    def recoveries(self) -> int:
        """Successful rebuilds handed to ``on_recovered``."""
        return self._recoveries

    def stop(self) -> None:
        """Ask :meth:`run` to return at its next check."""
        self._stop.set()

    async def run(self) -> None:
        """Watch for the degraded state until stopped."""
        while not self._stop.is_set():
            if self._is_degraded():
                if await self._probe():
                    self._interval = self._probe_interval
                    await self._sleep(self._watch_interval)
                    continue
                await self._sleep(self._interval)
                self._interval = min(self._interval * 2, self._max_interval)
            else:
                self._interval = self._probe_interval
                await self._sleep(self._watch_interval)

    async def _probe(self) -> bool:
        """Re-resolve the pair and rebuild once; ``True`` when the rebuild succeeded."""
        self._probes += 1
        api_key, private_key_pem = await self._resolve()
        if not api_key or not private_key_pem:
            return False
        try:
            await self._on_recovered(api_key, private_key_pem)
        except Exception:  # noqa: BLE001 - a failed rebuild must not kill the watcher
            logger.exception("credential recovery failed; will keep retrying")
            return False
        self._recoveries += 1
        logger.info("kalshi credentials recovered; credential-bound components rebuilt")
        return True


async def run_daemon(
    *,
    port: int = DEFAULT_PORT,
    host: str = _DEFAULT_HOST,
    environment: Environment = "production",
) -> None:
    """Run the always-on daemon until SIGTERM/SIGINT, then shut down cleanly."""
    components = await build_components(environment=environment)
    cache: MarketCache = components["cache"]
    ws: KalshiWebSocketManager = components["ws"]
    data: DataCollectionService = components["data"]
    settlement: SettlementMonitor | None = components.get("settlement")
    credentials_present = {"value": bool(components.get("credentials_present", True))}

    def _credentials_degraded() -> bool:
        """True while the credential-bound components need (re)building."""
        if not credentials_present["value"]:
            return True
        current_ws: KalshiWebSocketManager = components["ws"]
        return bool(getattr(current_ws, "fail_open_fired", False))

    async def _resolve_kalshi_pair() -> tuple[str | None, str | None]:
        """Re-resolve the canonical pair off the event loop (the SDK login blocks)."""
        store, _backend = await asyncio.to_thread(build_secrets_store_selection)
        return store.get("kalshi", "api_key"), store.get("kalshi", "private_key_pem")

    async def _mark_ws_connected() -> None:
        set_websocket(WEBSOCKET_CONNECTED)

    async def _mark_ws_fail_open() -> None:
        set_websocket(WEBSOCKET_FAIL_OPEN)

    async def _on_credentials_recovered(api_key: str, private_key_pem: str) -> None:
        """Rebuild the credential-bound components in place and restart the stream."""
        previous_ws: KalshiWebSocketManager = components["ws"]
        rebuilt_client = KalshiClient(
            api_key=api_key,
            private_key_pem=private_key_pem,
            environment=environment,
        )
        rebuilt_ws = KalshiWebSocketManager(
            api_key=api_key,
            private_key_pem=private_key_pem,
            environment=environment,
            on_message=_message_callback(cache),
            on_reconnect=_mark_ws_connected,
            on_fail_open=_mark_ws_fail_open,
        )
        # Retire the fail-open manager first: left running, its own callback would keep
        # overwriting the websocket state with ``fail_open`` after the stream is healthy.
        if previous_ws is not rebuilt_ws:
            await previous_ws.stop()
        components["client"] = rebuilt_client
        components["ws"] = rebuilt_ws
        credentials_present["value"] = True
        if settlement is not None:
            settlement.set_client(rebuilt_client)
        await rebuilt_ws.start()

    # Shutdown bookkeeping.
    stop = asyncio.Event()

    def _request_stop(signum: int, _frame: FrameType | None) -> None:
        logger.info("received signal %s; shutting down", signum)
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _request_stop, sig, None)

    mcp_task: asyncio.Task[None] | None = None
    supervisor_task: asyncio.Task[None] | None = None
    try:
        await cache.start_persist_task()
        await start_scheduler()
        await ws.start()
        await data.start()
        set_data_pipeline(DATA_PIPELINE_RUNNING)

        # #219: heal a fail-open credential start (and any later fail-open) in place.
        supervisor = CredentialSupervisor(
            is_degraded=_credentials_degraded,
            resolve=_resolve_kalshi_pair,
            on_recovered=_on_credentials_recovered,
        )
        supervisor_task = asyncio.create_task(
            supervisor.run(), name="traderbot-credential-supervisor"
        )

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
        await stop.wait()
    finally:
        logger.info("stopping daemon components (reverse order)")
        if supervisor_task is not None:
            supervisor.stop()
            _ = supervisor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await supervisor_task
        if mcp_task is not None:
            _ = mcp_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await mcp_task
        await data.stop()
        await components["ws"].stop()
        await stop_scheduler()
        await cache.stop_persist_task()
        await components["client"].close()
        components["chroma"].close()
        components["pool"].shutdown()
        set_storage_health(False, False, False)
        set_websocket(WEBSOCKET_DISCONNECTED)
        set_data_pipeline(DATA_PIPELINE_STOPPED)
        logger.info("daemon stopped")


def main(argv: Sequence[str] | None = None) -> None:
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


__all__ = ["DEFAULT_PORT", "CredentialSupervisor", "run_daemon"]
