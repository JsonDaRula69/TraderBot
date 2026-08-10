"""In-memory market data cache with SQLite persistence (DD-016, DD-037).

The WebSocket stream is the sole source of real-time Kalshi data. Messages from
the ``ticker``, ``orderbook_delta``, ``market_lifecycle_v2``, ``fill``,
``user_orders``, and ``market_positions`` channels update this cache in memory
immediately, and a write-behind timer persists the latest state to SQLite on a
schedule (default 5s). On cold start the cache loads the last persisted state
from SQLite *before* the WebSocket connects (stale-then-fresh pattern), so the
MCP layer and CLI never wait on the WS for recent data.

The retired v1 cache (``main/.trash/src/traderbot/kalshi/ws_cache.py``) wrote a
JSON file (``event_category_cache.json``) and read it on every access. This v2
module replaces that with a single ``MarketCache`` class backed by SQLite:

* ``market_data`` table — one row per market ticker: last price, bid, ask,
  volume, open interest, and the source timestamp.
* ``orderbook`` table — one row per market ticker: the aggregated orderbook
  levels (JSON) and the timestamp.

Everything is keyed by the Kalshi market ticker string (e.g.
``KXINXU-26AUG04H1600-T7599.9999``).

The cache is deliberately not thread-safe (constraint #248: provider state is
not thread-safe). All access happens on the asyncio event loop; the daemon and
the MCP handler share a single instance.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Final

from traderbot.db.pool import ConnectionPoolTimeoutError, SQLiteConnectionPool
from traderbot.paths import get_db_path

logger = logging.getLogger(__name__)

# Recursive JSON value types — matches the kalshi package.
type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]

#: Default write-behind persistence interval in seconds.
_DEFAULT_PERSIST_INTERVAL_S: Final = 5.0

#: The ``market_data`` table schema (created on first use).
_MARKET_DATA_SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS market_data (
    ticker TEXT PRIMARY KEY,
    last_price REAL,
    bid REAL,
    ask REAL,
    volume REAL,
    open_interest REAL,
    updated_at REAL NOT NULL
)
"""

#: The ``orderbook`` table schema (created on first use).
_ORDERBOOK_SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS orderbook (
    ticker TEXT PRIMARY KEY,
    bids_json TEXT NOT NULL,
    asks_json TEXT NOT NULL,
    updated_at REAL NOT NULL
)
"""


def _as_float(value: JsonValue | None) -> float:
    """Coerce a JSON value to float, returning 0.0 for non-numeric values."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def _encode(value: object) -> str:
    return json.dumps(value)


_EMPTY_TICKER: Final = {
    "last_price": 0.0,
    "bid": 0.0,
    "ask": 0.0,
    "volume": 0.0,
    "open_interest": 0.0,
    "updated_at": 0.0,
}


def _decode(raw: str | None) -> JsonValue:
    """JSON-decode a stored string; returns None for empty/invalid input."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


class MarketCache:
    """In-memory market data cache with write-behind SQLite persistence.

    Args:
        pool: Shared SQLite connection pool. A private compatibility pool is
            created when omitted.
        db_path: SQLite database file. Defaults to ``~/.traderbot/traderbot.db``.
        persist_interval_s: Write-behind interval. ``0`` disables automatic
            persistence (call :meth:`persist_to_db` manually).
    """

    def __init__(
        self,
        pool: SQLiteConnectionPool | None = None,
        db_path: Path | None = None,
        *,
        persist_interval_s: float = _DEFAULT_PERSIST_INTERVAL_S,
    ) -> None:
        self._pool: SQLiteConnectionPool = pool if pool is not None else SQLiteConnectionPool()
        self._db_path: Path = db_path or get_db_path()
        self._persist_interval_s: float = persist_interval_s

        # In-memory state. All dicts are keyed by market ticker.
        #: ticker -> {last_price, bid, ask, volume, open_interest, updated_at}
        self._tickers: dict[str, dict[str, JsonValue]] = {}
        #: ticker -> {bids: [...], asks: [...], updated_at}
        self._orderbooks: dict[str, dict[str, JsonValue]] = {}
        #: ticker -> lifecycle event (category, status, etc.)
        self._lifecycle: dict[str, dict[str, JsonValue]] = {}
        #: recent fills (most recent first), bounded to ``_FILLS_LIMIT``
        self._fills: list[dict[str, JsonValue]] = []
        #: recent order status updates, bounded to ``_ORDERS_LIMIT``
        self._orders: list[dict[str, JsonValue]] = []
        #: ticker -> position
        self._positions: dict[str, dict[str, JsonValue]] = {}

        # Write-behind bookkeeping.
        self._dirty: bool = False
        self._persist_task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event = asyncio.Event()
        self._last_persist: float = 0.0
        self._persist_errors: int = 0

    # -- lifecycle -----------------------------------------------------------

    def load_from_db(self) -> None:
        """Load the last persisted state into memory (stale-then-fresh)."""
        if not self._db_path.exists():
            return
        with self._pool.connection(self._db_path, readonly=True) as conn:
            rows = conn.execute(
                "SELECT ticker, last_price, bid, ask, volume, open_interest, "
                "updated_at FROM market_data"
            ).fetchall()
            for ticker, last_price, bid, ask, volume, oi, updated_at in rows:
                self._tickers[ticker] = {
                    "last_price": float(last_price) if last_price is not None else 0.0,
                    "bid": float(bid) if bid is not None else 0.0,
                    "ask": float(ask) if ask is not None else 0.0,
                    "volume": float(volume) if volume is not None else 0.0,
                    "open_interest": float(oi) if oi is not None else 0.0,
                    "updated_at": float(updated_at),
                }

            ob_rows = conn.execute(
                "SELECT ticker, bids_json, asks_json, updated_at FROM orderbook"
            ).fetchall()
            for ticker, bids_json, asks_json, updated_at in ob_rows:
                self._orderbooks[ticker] = {
                    "bids": _decode(bids_json) or [],
                    "asks": _decode(asks_json) or [],
                    "updated_at": float(updated_at),
                }
        if self._tickers or self._orderbooks:
            logger.info(
                "MarketCache loaded %d tickers, %d orderbooks from %s",
                len(self._tickers),
                len(self._orderbooks),
                self._db_path,
            )

    def persist_to_db(self) -> None:
        """Write the current in-memory state to SQLite (synchronous).

        Individual failures are logged and do not clear the dirty flag, so a
        later persist retries. The in-memory cache keeps serving regardless.
        """
        if not self._tickers and not self._orderbooks:
            self._dirty = False
            return
        try:
            with self._pool.connection(self._db_path) as conn:
                _ = conn.execute(_MARKET_DATA_SCHEMA)
                _ = conn.execute(_ORDERBOOK_SCHEMA)
                for ticker, t in self._tickers.items():
                    conn.execute(
                        "INSERT OR REPLACE INTO market_data "
                        "(ticker, last_price, bid, ask, volume, open_interest, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            ticker,
                            t.get("last_price", 0.0),
                            t.get("bid", 0.0),
                            t.get("ask", 0.0),
                            t.get("volume", 0.0),
                            t.get("open_interest", 0.0),
                            t.get("updated_at", 0.0),
                        ),
                    )
                for ticker, ob in self._orderbooks.items():
                    conn.execute(
                        "INSERT OR REPLACE INTO orderbook "
                        "(ticker, bids_json, asks_json, updated_at) VALUES (?, ?, ?, ?)",
                        (
                            ticker,
                            _encode(ob.get("bids") or []),
                            _encode(ob.get("asks") or []),
                            ob.get("updated_at", 0.0),
                        ),
                    )
        except (sqlite3.Error, ConnectionPoolTimeoutError) as exc:
            self._persist_errors += 1
            logger.error("MarketCache persist failed: %s", exc)
        else:
            self._dirty = False
            self._last_persist = time.time()

    # -- write-behind timer --------------------------------------------------

    async def start_persist_task(self) -> None:
        """Start the write-behind persistence task (idempotent)."""
        if self._persist_task is not None and not self._persist_task.done():
            return
        if self._persist_interval_s <= 0:
            return
        self._stop_event.clear()
        self._persist_task = asyncio.create_task(self._persist_loop(), name="market-cache-persist")

    async def stop_persist_task(self) -> None:
        """Stop the write-behind persistence task."""
        self._stop_event.set()
        if self._persist_task is not None:
            self._persist_task.cancel()
            try:
                await self._persist_task
            except (asyncio.CancelledError, Exception):
                pass
            self._persist_task = None
        # Final flush of anything still dirty.
        self.persist_to_db()

    async def _persist_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._persist_interval_s)
            except TimeoutError:
                pass
            if self._stop_event.is_set():
                break
            if self._dirty:
                self.persist_to_db()

    # -- in-memory updates (called from the WS message loop) ------------------

    def update_ticker(
        self,
        ticker: str,
        *,
        last_price: float | None = None,
        bid: float | None = None,
        ask: float | None = None,
        volume: float | None = None,
        open_interest: float | None = None,
        updated_at: float | None = None,
    ) -> None:
        """Update the cached ticker price for a market."""
        existing = self._tickers.setdefault(ticker, dict(_EMPTY_TICKER))
        if last_price is not None:
            existing["last_price"] = last_price
        if bid is not None:
            existing["bid"] = bid
        if ask is not None:
            existing["ask"] = ask
        if volume is not None:
            existing["volume"] = volume
        if open_interest is not None:
            existing["open_interest"] = open_interest
        existing["updated_at"] = updated_at if updated_at is not None else time.time()
        self._dirty = True

    def update_orderbook(
        self,
        ticker: str,
        *,
        bids: list[JsonValue] | None = None,
        asks: list[JsonValue] | None = None,
    ) -> None:
        """Replace the cached orderbook for a market (full snapshot semantics)."""
        existing = self._orderbooks.setdefault(ticker, {"bids": [], "asks": [], "updated_at": 0.0})
        if bids is not None:
            existing["bids"] = bids
        if asks is not None:
            existing["asks"] = asks
        existing["updated_at"] = time.time()
        self._dirty = True

    def update_lifecycle(self, ticker: str, event: dict[str, JsonValue]) -> None:
        """Record the latest market lifecycle event (category, status, etc.)."""
        self._lifecycle[ticker] = dict(event)
        category = event.get("category")
        if isinstance(category, str):
            self._tickers.setdefault(ticker, dict(_EMPTY_TICKER))
        self._dirty = True

    def record_fill(self, fill: dict[str, JsonValue]) -> None:
        """Record a fill notification (most recent first, bounded)."""
        self._fills.insert(0, dict(fill))
        self._fills = self._fills[:_FILLS_LIMIT]
        self._dirty = True

    def record_order(self, order: dict[str, JsonValue]) -> None:
        """Record an order status update (most recent first, bounded)."""
        self._orders.insert(0, dict(order))
        self._orders = self._orders[:_ORDERS_LIMIT]
        self._dirty = True

    def update_position(self, ticker: str, position: dict[str, JsonValue]) -> None:
        """Record the current position for a market."""
        self._positions[ticker] = dict(position)
        self._dirty = True

    # -- reads (MCP layer, CLI, tests) ----------------------------------------

    def get_ticker(self, ticker: str) -> JsonObject | None:
        """Return the cached ticker price for a market, or None if unknown."""
        t = self._tickers.get(ticker)
        if t is None:
            return None
        return {
            "ticker": ticker,
            "last_price": t.get("last_price", 0.0),
            "bid": t.get("bid", 0.0),
            "ask": t.get("ask", 0.0),
            "volume": t.get("volume", 0.0),
            "open_interest": t.get("open_interest", 0.0),
            "updated_at": t.get("updated_at", 0.0),
        }

    def get_tickers(self) -> dict[str, JsonObject]:
        """Return all cached ticker prices keyed by market ticker."""
        result: dict[str, JsonObject] = {}
        for ticker in self._tickers:
            entry = self.get_ticker(ticker)
            if entry is not None:
                result[ticker] = entry
        return result

    def get_orderbook(self, ticker: str) -> JsonObject | None:
        """Return the cached orderbook (bids/asks) for a market, or None."""
        ob = self._orderbooks.get(ticker)
        if ob is None:
            return None
        bids_raw = ob.get("bids")
        asks_raw = ob.get("asks")
        return {
            "ticker": ticker,
            "bids": list(bids_raw) if isinstance(bids_raw, list) else [],
            "asks": list(asks_raw) if isinstance(asks_raw, list) else [],
            "updated_at": _as_float(ob.get("updated_at")),
        }

    def get_lifecycle(self, ticker: str) -> JsonObject | None:
        """Return the latest lifecycle event for a market, or None."""
        ev = self._lifecycle.get(ticker)
        if ev is None:
            return None
        result: JsonObject = {"ticker": ticker}
        for key, value in ev.items():
            result[key] = value
        return result

    def get_open_markets(self, limit: int = 100) -> list[JsonObject]:
        """Return the most recently updated tickers as a list (for MCP tools).

        ``open`` here means "seen in the live stream" — the cache only holds
        markets with live WS data, which is what the MCP layer needs.
        """

        def _updated(kv: tuple[str, dict[str, JsonValue]]) -> float:
            return _as_float(kv[1].get("updated_at"))

        ordered = sorted(self._tickers.items(), key=_updated, reverse=True)
        result: list[JsonObject] = []
        for ticker, _ in ordered[:limit]:
            entry = self.get_ticker(ticker)
            if entry is not None:
                result.append(entry)
        return result

    def get_fills(self, limit: int = 50) -> list[JsonObject]:
        """Return recent fills (most recent first)."""
        return [dict(f) for f in self._fills[:limit]]

    def get_orders(self, limit: int = 50) -> list[JsonObject]:
        """Return recent order status updates (most recent first)."""
        return [dict(o) for o in self._orders[:limit]]

    def get_positions(self) -> dict[str, JsonObject]:
        """Return current positions keyed by ticker."""
        return {t: dict(p) for t, p in self._positions.items()}

    def get_event_category(self, ticker: str) -> str | None:
        """Return the cached category for a market ticker, or None."""
        ev = self._lifecycle.get(ticker)
        if ev is not None:
            category = ev.get("category")
            if isinstance(category, str):
                return category
        t = self._tickers.get(ticker)
        if t is not None:
            cat = t.get("category_name")
            if isinstance(cat, str):
                return cat
        return None

    def get_stats(self) -> JsonObject:
        """Return cache stats (counts + age)."""
        now = time.time()
        oldest_ts = min(
            (_as_float(t.get("updated_at")) for t in self._tickers.values()), default=0.0
        )
        return {
            "tickers": len(self._tickers),
            "orderbooks": len(self._orderbooks),
            "lifecycle_events": len(self._lifecycle),
            "fills": len(self._fills),
            "orders": len(self._orders),
            "positions": len(self._positions),
            "age_seconds": int(now - oldest_ts) if oldest_ts else -1,
            "dirty": self._dirty,
            "persist_errors": self._persist_errors,
        }


#: Bounded lists for fills/orders (memory guard).
_FILLS_LIMIT: Final = 500
_ORDERS_LIMIT: Final = 500

__all__ = ["MarketCache"]
