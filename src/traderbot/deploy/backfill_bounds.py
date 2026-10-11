"""Filter historical records to validated backfill windows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from traderbot.kalshi.rest_models import (
    ForecastHistoryResponse,
    HistoricalCandlestickResponse,
    LiveCandlestickResponse,
)

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _within(timestamp: int, start: datetime, end: datetime) -> bool:
    instant = _EPOCH + timedelta(seconds=timestamp)
    return start <= instant < end


def filter_live_candles(
    response: LiveCandlestickResponse, start: datetime, end: datetime
) -> tuple[LiveCandlestickResponse, int]:
    bounded = tuple(
        candle for candle in response.candlesticks if _within(candle.end_period_ts, start, end)
    )
    return (
        response.model_copy(update={"candlesticks": list(bounded)}),
        len(response.candlesticks) - len(bounded),
    )


def filter_historical_candles(
    response: HistoricalCandlestickResponse, start: datetime, end: datetime
) -> tuple[HistoricalCandlestickResponse, int]:
    bounded = tuple(
        candle for candle in response.candlesticks if _within(candle.end_period_ts, start, end)
    )
    return (
        response.model_copy(update={"candlesticks": list(bounded)}),
        len(response.candlesticks) - len(bounded),
    )


def filter_forecasts(
    response: ForecastHistoryResponse, start: datetime, end: datetime
) -> tuple[ForecastHistoryResponse, int]:
    bounded = tuple(
        point for point in response.forecast_history if _within(point.end_period_ts, start, end)
    )
    return (
        response.model_copy(update={"forecast_history": list(bounded)}),
        len(response.forecast_history) - len(bounded),
    )
