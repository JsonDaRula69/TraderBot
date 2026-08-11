from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from traderbot.db.pool import SQLiteConnectionPool
from traderbot.deploy.backfill_models import TableCounts
from traderbot.kalshi.rest_models import (
    ForecastHistoryResponse,
    HistoricalCandlestickResponse,
    KalshiMarket,
    LiveCandlestickResponse,
)

_MARKET_SQL: Final = """INSERT OR IGNORE INTO kalshi_markets
(ticker,event_ticker,series_ticker,category,status,result,title,subtitle,yes_sub_title,
no_sub_title,market_type,volume_fp,open_interest_fp,created_ts,updated_ts,open_ts,close_ts,
settled_ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
_CANDLE_SQL: Final = """INSERT OR IGNORE INTO kalshi_candlesticks
(ticker,period_interval,end_period_ts,source,yes_bid_open,yes_bid_low,yes_bid_high,
yes_bid_close,yes_ask_open,yes_ask_low,yes_ask_high,yes_ask_close,price_open,price_low,
price_high,price_close,price_mean,price_previous,price_min,price_max,volume_fp,open_interest_fp)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
_FORECAST_SQL: Final = """INSERT OR IGNORE INTO kalshi_forecast_history
(event_ticker,series_ticker,end_period_ts,period_interval,percentile,
raw_numerical_forecast,numerical_forecast,formatted_forecast) VALUES (?,?,?,?,?,?,?,?)"""


@dataclass(frozen=True, slots=True)
class StoredMarket:
    market: KalshiMarket
    series_ticker: str
    category: str


@dataclass(frozen=True, slots=True)
class LiveCandleBatch:
    ticker: str
    period_interval: int
    response: LiveCandlestickResponse


@dataclass(frozen=True, slots=True)
class HistoricalCandleBatch:
    ticker: str
    period_interval: int
    response: HistoricalCandlestickResponse


@dataclass(frozen=True, slots=True)
class ForecastBatch:
    series_ticker: str
    response: ForecastHistoryResponse


def _counts(seen: int, before: int, after: int) -> TableCounts:
    inserted = after - before
    return TableCounts(seen=seen, inserted=inserted, duplicate=seen - inserted)


def write_markets(
    pool: SQLiteConnectionPool, target: Path, markets: tuple[StoredMarket, ...]
) -> TableCounts:
    rows = tuple(
        (
            item.market.ticker,
            item.market.event_ticker,
            item.series_ticker,
            item.category,
            item.market.status,
            item.market.result,
            item.market.title,
            item.market.subtitle,
            item.market.yes_sub_title,
            item.market.no_sub_title,
            item.market.market_type,
            item.market.volume_fp,
            item.market.open_interest_fp,
            int(item.market.created_time.timestamp()),
            int(item.market.updated_time.timestamp()),
            int(item.market.open_time.timestamp()),
            int(item.market.close_time.timestamp()),
            None
            if item.market.settlement_ts is None
            else int(item.market.settlement_ts.timestamp()),
        )
        for item in markets
    )
    with pool.connection(target) as connection:
        before = connection.total_changes
        _ = connection.executemany(_MARKET_SQL, rows)
        return _counts(len(rows), before, connection.total_changes)


def write_live_candles(
    pool: SQLiteConnectionPool, target: Path, batch: LiveCandleBatch
) -> TableCounts:
    rows = tuple(
        (
            batch.ticker,
            batch.period_interval,
            candle.end_period_ts,
            "live",
            candle.yes_bid.open_dollars,
            candle.yes_bid.low_dollars,
            candle.yes_bid.high_dollars,
            candle.yes_bid.close_dollars,
            candle.yes_ask.open_dollars,
            candle.yes_ask.low_dollars,
            candle.yes_ask.high_dollars,
            candle.yes_ask.close_dollars,
            candle.price.open_dollars,
            candle.price.low_dollars,
            candle.price.high_dollars,
            candle.price.close_dollars,
            candle.price.mean_dollars,
            candle.price.previous_dollars,
            candle.price.min_dollars,
            candle.price.max_dollars,
            candle.volume_fp,
            candle.open_interest_fp,
        )
        for candle in batch.response.candlesticks
    )
    return _write_rows(pool, target, _CANDLE_SQL, rows)


def write_historical_candles(
    pool: SQLiteConnectionPool, target: Path, batch: HistoricalCandleBatch
) -> TableCounts:
    rows = tuple(
        (
            batch.ticker,
            batch.period_interval,
            candle.end_period_ts,
            "historical",
            candle.yes_bid.open,
            candle.yes_bid.low,
            candle.yes_bid.high,
            candle.yes_bid.close,
            candle.yes_ask.open,
            candle.yes_ask.low,
            candle.yes_ask.high,
            candle.yes_ask.close,
            candle.price.open,
            candle.price.low,
            candle.price.high,
            candle.price.close,
            candle.price.mean,
            candle.price.previous,
            None,
            None,
            candle.volume,
            candle.open_interest,
        )
        for candle in batch.response.candlesticks
    )
    return _write_rows(pool, target, _CANDLE_SQL, rows)


def write_forecasts(pool: SQLiteConnectionPool, target: Path, batch: ForecastBatch) -> TableCounts:
    rows = tuple(
        (
            point.event_ticker,
            batch.series_ticker,
            point.end_period_ts,
            point.period_interval,
            percentile.percentile,
            str(percentile.raw_numerical_forecast),
            str(percentile.numerical_forecast),
            percentile.formatted_forecast,
        )
        for point in batch.response.forecast_history
        for percentile in point.percentile_points
    )
    return _write_rows(pool, target, _FORECAST_SQL, rows)


def _write_rows(
    pool: SQLiteConnectionPool,
    target: Path,
    sql: str,
    rows: tuple[tuple[str | int | None, ...], ...],
) -> TableCounts:
    with pool.connection(target) as connection:
        before = connection.total_changes
        _ = connection.executemany(sql, rows)
        return _counts(len(rows), before, connection.total_changes)


__all__ = [
    "ForecastBatch",
    "HistoricalCandleBatch",
    "LiveCandleBatch",
    "StoredMarket",
    "write_forecasts",
    "write_historical_candles",
    "write_live_candles",
    "write_markets",
]
