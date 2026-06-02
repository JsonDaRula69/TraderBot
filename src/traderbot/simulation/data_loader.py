"""DataLoader — fetches historical data from Kalshi API and caches to SQLite with TTL expiry."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from traderbot.kalshi.models import Market, Trade

if TYPE_CHECKING:
    import sqlite3

    from traderbot.kalshi.history import HistoryService

logger = logging.getLogger(__name__)

_MIN_VOLUME_THRESHOLD = 100
_MIN_TRADES_FOR_QUALITY = 1
_DEFAULT_MARKET_TTL_HOURS = 1
_DEFAULT_TRADE_TTL_MINUTES = 5


class QualityFlag(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    ticker: str
    flag_type: str
    message: str


class DataQualityReport(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    total_markets: int
    flags: list[QualityFlag] = Field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return len(self.flags) == 0


def init_cache_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS cached_markets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            market_json TEXT NOT NULL,
            fetched_date_start TEXT NOT NULL,
            fetched_date_end TEXT NOT NULL,
            cached_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS cached_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            trade_json TEXT NOT NULL,
            cached_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cached_markets_dates ON cached_markets(fetched_date_start, fetched_date_end)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cached_trades_ticker ON cached_trades(ticker)")
    conn.commit()


class DataLoader:
    def __init__(
        self,
        conn: sqlite3.Connection,
        history: HistoryService,
        market_ttl_hours: int = _DEFAULT_MARKET_TTL_HOURS,
        trade_ttl_minutes: int = _DEFAULT_TRADE_TTL_MINUTES,
    ) -> None:
        self._conn = conn
        self._history = history
        self._market_ttl = timedelta(hours=market_ttl_hours)
        self._trade_ttl = timedelta(minutes=trade_ttl_minutes)

    async def get_markets(self, start: date, end: date) -> list[Market]:
        cached = self._get_cached_markets(start, end)
        if cached is not None:
            logger.debug("Markets cache HIT: %s to %s (%d markets)", start, end, len(cached))
            return cached

        logger.info("Markets cache MISS: fetching from API %s to %s", start, end)
        markets = await self._fetch_all_markets()
        self._cache_markets(start, end, markets)
        return markets

    async def get_trades(self, ticker: str) -> list[Trade]:
        cached = self._get_cached_trades(ticker)
        if cached is not None:
            logger.debug("Trades cache HIT: %s (%d trades)", ticker, len(cached))
            return cached

        logger.info("Trades cache MISS: fetching %s from API", ticker)
        trades = await self._fetch_all_trades(ticker)
        self._cache_trades(ticker, trades)
        return trades

    async def get_outcomes(self, tickers: list[str]) -> dict[str, bool]:
        if not tickers:
            return {}
        results: dict[str, bool] = {}
        for ticker in tickers:
            market = await self._history.get_market_series(ticker)
            results[ticker] = (
                bool(market.settlement_result) if market.settlement_result is not None else False
            )
        return results

    def quality_report(
        self,
        markets: list[Market],
        trades_by_ticker: dict[str, list[Trade]] | None = None,
    ) -> DataQualityReport:
        flags: list[QualityFlag] = []
        trades_map = trades_by_ticker or {}

        for market in markets:
            if market.volume < _MIN_VOLUME_THRESHOLD:
                flags.append(
                    QualityFlag(
                        ticker=market.ticker,
                        flag_type="low_liquidity",
                        message=f"Market has volume {market.volume} below threshold {_MIN_VOLUME_THRESHOLD}",
                    )
                )

            ticker_trades = trades_map.get(market.ticker, [])
            if len(ticker_trades) < _MIN_TRADES_FOR_QUALITY:
                flags.append(
                    QualityFlag(
                        ticker=market.ticker,
                        flag_type="no_trades",
                        message=f"Market has {len(ticker_trades)} trades",
                    )
                )

            if (
                market.status == "settled"
                and len(ticker_trades) >= _MIN_TRADES_FOR_QUALITY
                and self._check_settlement_inconsistency(market, ticker_trades)
            ):
                flags.append(
                    QualityFlag(
                        ticker=market.ticker,
                        flag_type="settlement_inconsistency",
                        message="Trade prices inconsistent with settlement result",
                    )
                )

        return DataQualityReport(total_markets=len(markets), flags=flags)

    def _check_settlement_inconsistency(self, market: Market, trades: list[Trade]) -> bool:
        if market.settlement_result is None or not trades:
            return False
        avg_price = sum(t.price for t in trades) / len(trades)
        return (market.settlement_result is True and avg_price < 30) or (
            market.settlement_result is False and avg_price > 70
        )

    def _get_cached_markets(self, start: date, end: date) -> list[Market] | None:
        rows = self._conn.execute(
            "SELECT market_json, cached_at FROM cached_markets WHERE fetched_date_start = ? AND fetched_date_end = ?",
            (start.isoformat(), end.isoformat()),
        ).fetchall()

        if not rows:
            return None

        cached_at_str = rows[0]["cached_at"]
        cached_at = datetime.fromisoformat(cached_at_str)
        if datetime.now(UTC) - cached_at > self._market_ttl:
            return None

        markets: list[Market] = []
        for row in rows:
            markets.append(Market.model_validate_json(row["market_json"]))
        return markets

    def _cache_markets(self, start: date, end: date, markets: list[Market]) -> None:
        self._conn.execute(
            "DELETE FROM cached_markets WHERE fetched_date_start = ? AND fetched_date_end = ?",
            (start.isoformat(), end.isoformat()),
        )
        now = datetime.now(UTC).isoformat()
        for market in markets:
            self._conn.execute(
                """INSERT INTO cached_markets (ticker, market_json, fetched_date_start, fetched_date_end, cached_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (market.ticker, market.model_dump_json(), start.isoformat(), end.isoformat(), now),
            )
        self._conn.commit()

    def _get_cached_trades(self, ticker: str) -> list[Trade] | None:
        rows = self._conn.execute(
            "SELECT trade_json, cached_at FROM cached_trades WHERE ticker = ?",
            (ticker,),
        ).fetchall()

        if not rows:
            return None

        cached_at_str = rows[0]["cached_at"]
        cached_at = datetime.fromisoformat(cached_at_str)
        if datetime.now(UTC) - cached_at > self._trade_ttl:
            return None

        trades: list[Trade] = []
        for row in rows:
            trades.append(Trade.model_validate_json(row["trade_json"]))
        return trades

    def _cache_trades(self, ticker: str, trades: list[Trade]) -> None:
        self._conn.execute(
            "DELETE FROM cached_trades WHERE ticker = ?",
            (ticker,),
        )
        now = datetime.now(UTC).isoformat()
        for trade in trades:
            self._conn.execute(
                """INSERT INTO cached_trades (ticker, trade_json, cached_at)
                   VALUES (?, ?, ?)""",
                (trade.ticker, trade.model_dump_json(), now),
            )
        self._conn.commit()

    async def _fetch_all_markets(self) -> list[Market]:
        all_markets: list[Market] = []
        cursor: str | None = None
        while True:
            response = await self._history.get_settled_markets(cursor=cursor)
            all_markets.extend(response.markets)
            cursor = response.cursor
            if cursor is None:
                break
        return all_markets

    async def _fetch_all_trades(self, ticker: str) -> list[Trade]:
        all_trades: list[Trade] = []
        cursor: str | None = None
        while True:
            response = await self._history.get_historical_trades(ticker, cursor=cursor)
            all_trades.extend(response.trades)
            cursor = response.cursor
            if cursor is None:
                break
        return all_trades
