"""In-memory TTL cache + SQLite settlement cache for market data."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from traderbot.logging_config import log_cache_event

if TYPE_CHECKING:
    from traderbot.kalshi.provider import (
        MarketSnapshot,
        OrderBookSnapshot,
        SettlementResult,
    )
    from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)

ORDERBOOK_TTL = 30.0
MARKET_TTL = 60.0


def _resolve_settlement_db_path(profile: TradingProfile | None) -> Path:
    """Resolve the settlement cache DB path, per-profile if available."""
    if profile is not None:
        return Path(profile.base_dir) / "settlement_cache.db"
    from traderbot.paths import get_data_dir

    return get_data_dir() / "settlement_cache.db"


class MarketDataCache:
    """TTL-gated in-memory cache for market snapshots and orderbooks, plus a permanent SQLite settlement store."""

    def __init__(self, profile: TradingProfile | None = None) -> None:
        self._profile = profile
        self._lock = asyncio.Lock()
        self._market_cache: dict[str, tuple[MarketSnapshot, float]] = {}
        self._orderbook_cache: dict[str, tuple[OrderBookSnapshot, float]] = {}
        self._settlement_db_path = _resolve_settlement_db_path(profile)
        self._settlement_db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_settlement_table()

    async def get_market(self, ticker: str) -> MarketSnapshot | None:
        """Return cached MarketSnapshot or None if expired/missing."""
        async with self._lock:
            entry = self._market_cache.get(ticker)
            if entry is None:
                log_cache_event(logger, "get_market", ticker, hit=False)
                return None
            snapshot, expiry = entry
            if time.monotonic() >= expiry:
                del self._market_cache[ticker]
                log_cache_event(logger, "get_market", ticker, hit=False, reason="expired")
                return None
            log_cache_event(logger, "get_market", ticker, hit=True)
            return snapshot

    async def set_market(self, ticker: str, snapshot: MarketSnapshot) -> None:
        """Store a MarketSnapshot with market metadata TTL."""
        async with self._lock:
            expiry = time.monotonic() + MARKET_TTL
            self._market_cache[ticker] = (snapshot, expiry)
            log_cache_event(logger, "set_market", ticker, hit=False, action="store")

    async def get_markets_batch(
        self, tickers: list[str]
    ) -> dict[str, MarketSnapshot]:
        """Return cached snapshots for *tickers* — missing entries excluded.

        Caller inspects returned keys and fetches missing tickers from provider.
        """
        async with self._lock:
            result: dict[str, MarketSnapshot] = {}
            now = time.monotonic()
            hits = 0
            misses = 0
            for ticker in tickers:
                entry = self._market_cache.get(ticker)
                if entry is None:
                    misses += 1
                    continue
                snapshot, expiry = entry
                if now >= expiry:
                    del self._market_cache[ticker]
                    misses += 1
                    continue
                result[ticker] = snapshot
                hits += 1
            log_cache_event(
                logger, "get_markets_batch", str(len(tickers)), hit=hits > 0,
                hits=hits, misses=misses,
            )
            return result

    async def get_orderbook(self, ticker: str) -> OrderBookSnapshot | None:
        """Return cached OrderBookSnapshot or None if expired/missing."""
        async with self._lock:
            entry = self._orderbook_cache.get(ticker)
            if entry is None:
                log_cache_event(logger, "get_orderbook", ticker, hit=False)
                return None
            snapshot, expiry = entry
            if time.monotonic() >= expiry:
                del self._orderbook_cache[ticker]
                log_cache_event(logger, "get_orderbook", ticker, hit=False, reason="expired")
                return None
            log_cache_event(logger, "get_orderbook", ticker, hit=True)
            return snapshot

    async def set_orderbook(self, ticker: str, snapshot: OrderBookSnapshot) -> None:
        """Store an OrderBookSnapshot with orderbook TTL."""
        async with self._lock:
            expiry = time.monotonic() + ORDERBOOK_TTL
            self._orderbook_cache[ticker] = (snapshot, expiry)
            log_cache_event(logger, "set_orderbook", ticker, hit=False, action="store")

    async def get_orderbooks_batch(
        self, tickers: list[str]
    ) -> dict[str, OrderBookSnapshot]:
        """Return cached orderbook snapshots for *tickers* — missing excluded."""
        async with self._lock:
            result: dict[str, OrderBookSnapshot] = {}
            now = time.monotonic()
            for ticker in tickers:
                entry = self._orderbook_cache.get(ticker)
                if entry is None:
                    continue
                snapshot, expiry = entry
                if now >= expiry:
                    del self._orderbook_cache[ticker]
                    continue
                result[ticker] = snapshot
            return result

    def _invalidate_under_lock(
        self, ticker: str, reason: str = "invalidate"
    ) -> None:
        """Remove market + orderbook entries (caller holds lock)."""
        removed_market = ticker in self._market_cache
        removed_ob = ticker in self._orderbook_cache
        self._market_cache.pop(ticker, None)
        self._orderbook_cache.pop(ticker, None)
        log_cache_event(
            logger, reason, ticker, hit=False,
            removed_market=removed_market, removed_orderbook=removed_ob,
        )

    async def invalidate(self, ticker: str) -> None:
        """Remove market and orderbook entries for *ticker*."""
        async with self._lock:
            self._invalidate_under_lock(ticker)

    async def invalidate_all(self) -> None:
        """Clear all in-memory caches."""
        async with self._lock:
            market_count = len(self._market_cache)
            ob_count = len(self._orderbook_cache)
            self._market_cache.clear()
            self._orderbook_cache.clear()
            log_cache_event(
                logger, "invalidate_all", "all", hit=False,
                cleared_markets=market_count, cleared_orderbooks=ob_count,
            )

    async def clear_expired(self) -> None:
        """Remove all expired entries from in-memory caches."""
        async with self._lock:
            now = time.monotonic()
            expired_markets = [
                t for t, (_, exp) in self._market_cache.items() if now >= exp
            ]
            expired_obs = [
                t for t, (_, exp) in self._orderbook_cache.items() if now >= exp
            ]
            for t in expired_markets:
                del self._market_cache[t]
            for t in expired_obs:
                del self._orderbook_cache[t]
            if expired_markets or expired_obs:
                log_cache_event(
                    logger, "clear_expired", str(len(expired_markets + expired_obs)),
                    hit=False,
                    expired_markets=len(expired_markets),
                    expired_orderbooks=len(expired_obs),
                )

    def _init_settlement_table(self) -> None:
        """Create the settlements table if it does not exist."""
        with sqlite3.connect(str(self._settlement_db_path)) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS settlements (
                    ticker TEXT PRIMARY KEY,
                    outcome INTEGER NOT NULL,
                    settled_at TEXT NOT NULL
                )"""
            )
            conn.commit()

    def get_settlement(self, ticker: str) -> SettlementResult | None:
        """Return the settlement result for *ticker* or None."""
        from traderbot.kalshi.provider import SettlementResult

        with sqlite3.connect(str(self._settlement_db_path)) as conn:
            row = conn.execute(
                "SELECT outcome, settled_at FROM settlements WHERE ticker = ?",
                (ticker,),
            ).fetchone()
        if row is None:
            log_cache_event(logger, "get_settlement", ticker, hit=False)
            return None
        outcome, settled_at_str = row
        log_cache_event(logger, "get_settlement", ticker, hit=True)
        return SettlementResult(
            ticker=ticker,
            outcome=bool(outcome),
            settled_at=datetime.fromisoformat(settled_at_str),
        )

    def set_settlement(
        self, ticker: str, outcome: bool, settled_at: datetime
    ) -> None:
        """Persist a settlement result."""
        with sqlite3.connect(str(self._settlement_db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settlements (ticker, outcome, settled_at) "
                "VALUES (?, ?, ?)",
                (ticker, int(outcome), settled_at.isoformat()),
            )
            conn.commit()
        log_cache_event(
            logger, "set_settlement", ticker, hit=False,
            outcome=outcome, settled_at=settled_at.isoformat(),
        )

    def get_settlements_batch(
        self, tickers: list[str]
    ) -> dict[str, SettlementResult]:
        """Return settlement results for *tickers* in a single query.

        Missing tickers are excluded from the result dict.
        """
        from traderbot.kalshi.provider import SettlementResult

        if not tickers:
            return {}

        placeholders = ",".join("?" for _ in tickers)
        with sqlite3.connect(str(self._settlement_db_path)) as conn:
            rows = conn.execute(
                f"SELECT ticker, outcome, settled_at FROM settlements "
                f"WHERE ticker IN ({placeholders})",
                tuple(tickers),
            ).fetchall()

        result: dict[str, SettlementResult] = {}
        for ticker, outcome, settled_at_str in rows:
            result[ticker] = SettlementResult(
                ticker=ticker,
                outcome=bool(outcome),
                settled_at=datetime.fromisoformat(settled_at_str),
            )
        log_cache_event(
            logger, "get_settlements_batch", str(len(tickers)),
            hit=len(rows) > 0,
            hits=len(rows), misses=len(tickers) - len(rows),
        )
        return result

    def set_settlements_batch(
        self, settlements: dict[str, tuple[bool, datetime]]
    ) -> None:
        """Persist multiple settlement results in a single transaction.

        Each value is ``(outcome: bool, settled_at: datetime)``.
        """
        if not settlements:
            return

        rows = [
            (ticker, int(outcome), settled_at.isoformat())
            for ticker, (outcome, settled_at) in settlements.items()
        ]
        with sqlite3.connect(str(self._settlement_db_path)) as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO settlements (ticker, outcome, settled_at) "
                "VALUES (?, ?, ?)",
                rows,
            )
            conn.commit()
        log_cache_event(
            logger, "set_settlements_batch", str(len(rows)),
            hit=False, count=len(rows),
        )
