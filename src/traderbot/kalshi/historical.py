from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Final, override

import httpx

from traderbot.kalshi.archive import KalshiArchiveMethods
from traderbot.kalshi.order_models import MarketCategory
from traderbot.kalshi.rest_models import (
    BalanceResponse,
    CandlePeriod,
    ForecastHistoryResponse,
    ForecastPeriod,
    HistoricalCandlestickResponse,
    LiveCandlestickResponse,
    MarketListResponse,
    MarketQueryStatus,
    SeriesListResponse,
)

type QueryParamValue = str | int | float | bool | None
type QueryParams = dict[str, QueryParamValue] | list[tuple[str, QueryParamValue]]

_TICKER_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_MARKET_STATUSES: Final = frozenset({"unopened", "open", "paused", "closed", "settled"})
_CANDLE_PERIODS: Final = frozenset({1, 60, 1440})
_FORECAST_PERIODS: Final = frozenset({0, 1, 60, 1440})


class KalshiParameterError(ValueError):
    def __init__(self, parameter: str, reason: str) -> None:
        self.parameter: str = parameter
        self.reason: str = reason
        super().__init__(f"invalid {parameter}: {reason}")


def _ticker(value: str, parameter: str) -> str:
    if _TICKER_PATTERN.fullmatch(value) is None:
        raise KalshiParameterError(parameter, "must use Kalshi ticker characters")
    return value


def _bounds(start_ts: int, end_ts: int) -> None:
    if type(start_ts) is not int or type(end_ts) is not int or start_ts < 0 or end_ts < 0:
        raise KalshiParameterError("time bounds", "timestamps must be nonnegative")
    if start_ts > end_ts:
        raise KalshiParameterError("time bounds", "start_ts must not exceed end_ts")


def _period(value: int, allowed: frozenset[int], parameter: str) -> int:
    if type(value) is not int or value not in allowed:
        raise KalshiParameterError(parameter, f"must be one of {sorted(allowed)}")
    return value


def _optional_ticker(value: str | None, parameter: str) -> str | None:
    if value is None or value == "":
        return None
    return _ticker(value, parameter)


def _optional_cursor(value: QueryParamValue) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise KalshiParameterError("cursor", "must be a string")
    if not value or not value.strip():
        raise KalshiParameterError("cursor", "must contain non-whitespace characters")
    if value != value.strip():
        raise KalshiParameterError("cursor", "must not contain surrounding whitespace")
    if not value.isprintable():
        raise KalshiParameterError("cursor", "must not contain control characters")
    return value


def _timestamp(value: int | None, parameter: str) -> int | None:
    if value is not None and (type(value) is not int or value < 0):
        raise KalshiParameterError(parameter, "must be nonnegative")
    return value


def _ordered_optional_bounds(minimum: int | None, maximum: int | None, parameter: str) -> None:
    if minimum is not None and maximum is not None and minimum > maximum:
        raise KalshiParameterError(parameter, "minimum must not exceed maximum")


class KalshiHistoricalMethods(KalshiArchiveMethods, ABC):
    @override
    @abstractmethod
    async def get(
        self,
        path: str,
        timeout: float = 30.0,
        *,
        query_params: QueryParams | None = None,
        **params: QueryParamValue,
    ) -> httpx.Response: ...

    async def get_series(self, category: MarketCategory | str) -> SeriesListResponse:
        category_value = str(category).strip().lower()
        if not category_value:
            raise KalshiParameterError("category", "must not be empty")
        response = await self.get("/series", category=category_value)
        return SeriesListResponse.model_validate_json(response.content)

    async def get_balance(self, *, timeout: float = 3.0) -> BalanceResponse:
        response = await self.get("/portfolio/balance", timeout=timeout)
        return BalanceResponse.model_validate_json(response.content)

    async def get_markets(
        self,
        *,
        status: MarketQueryStatus | str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
        min_created_ts: int | None = None,
        max_created_ts: int | None = None,
        min_updated_ts: int | None = None,
        min_close_ts: int | None = None,
        max_close_ts: int | None = None,
        min_settled_ts: int | None = None,
        max_settled_ts: int | None = None,
    ) -> MarketListResponse:
        if status is not None and status not in _MARKET_STATUSES:
            raise KalshiParameterError("status", f"must be one of {sorted(_MARKET_STATUSES)}")
        if limit is not None and (type(limit) is not int or not 1 <= limit <= 1000):
            raise KalshiParameterError("limit", "must be an integer between 1 and 1000")
        _ordered_optional_bounds(min_created_ts, max_created_ts, "created timestamps")
        _ordered_optional_bounds(min_close_ts, max_close_ts, "close timestamps")
        _ordered_optional_bounds(min_settled_ts, max_settled_ts, "settled timestamps")
        has_created = min_created_ts is not None or max_created_ts is not None
        has_close = min_close_ts is not None or max_close_ts is not None
        has_settled = min_settled_ts is not None or max_settled_ts is not None
        if sum((has_created, has_close, has_settled, min_updated_ts is not None)) > 1:
            raise KalshiParameterError(
                "timestamp filters", "filter families are mutually exclusive"
            )
        if has_created and status not in (None, "unopened", "open"):
            raise KalshiParameterError("status", "is incompatible with created timestamps")
        if has_close and status not in (None, "closed"):
            raise KalshiParameterError("status", "is incompatible with close timestamps")
        if has_settled and status not in (None, "settled"):
            raise KalshiParameterError("status", "is incompatible with settled timestamps")
        if min_updated_ts is not None and any((status, event_ticker, series_ticker)):
            raise KalshiParameterError("min_updated_ts", "is incompatible with other filters")
        query: dict[str, QueryParamValue] = {}
        values: tuple[tuple[str, QueryParamValue], ...] = (
            ("status", status),
            ("limit", limit),
            ("cursor", _optional_cursor(cursor)),
            ("event_ticker", _optional_ticker(event_ticker, "event_ticker")),
            ("series_ticker", _optional_ticker(series_ticker, "series_ticker")),
            ("min_created_ts", _timestamp(min_created_ts, "min_created_ts")),
            ("max_created_ts", _timestamp(max_created_ts, "max_created_ts")),
            ("min_updated_ts", _timestamp(min_updated_ts, "min_updated_ts")),
            ("min_close_ts", _timestamp(min_close_ts, "min_close_ts")),
            ("max_close_ts", _timestamp(max_close_ts, "max_close_ts")),
            ("min_settled_ts", _timestamp(min_settled_ts, "min_settled_ts")),
            ("max_settled_ts", _timestamp(max_settled_ts, "max_settled_ts")),
        )
        query.update((name, value) for name, value in values if value is not None)
        response = await self.get("/markets", query_params=query)
        return MarketListResponse.model_validate_json(response.content)

    async def get_candlesticks(
        self,
        series_ticker: str,
        ticker: str,
        start_ts: int,
        end_ts: int,
        period_interval: CandlePeriod | int,
    ) -> LiveCandlestickResponse:
        series = _ticker(series_ticker, "series_ticker")
        market = _ticker(ticker, "ticker")
        _bounds(start_ts, end_ts)
        period = _period(period_interval, _CANDLE_PERIODS, "period_interval")
        response = await self.get(
            f"/series/{series}/markets/{market}/candlesticks",
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=period,
        )
        return LiveCandlestickResponse.model_validate_json(response.content)

    async def get_historical_candlesticks(
        self,
        ticker: str,
        start_ts: int,
        end_ts: int,
        period_interval: CandlePeriod | int,
    ) -> HistoricalCandlestickResponse:
        market = _ticker(ticker, "ticker")
        _bounds(start_ts, end_ts)
        period = _period(period_interval, _CANDLE_PERIODS, "period_interval")
        response = await self.get(
            f"/historical/markets/{market}/candlesticks",
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=period,
        )
        return HistoricalCandlestickResponse.model_validate_json(response.content)

    async def get_forecast_percentile_history(
        self,
        series_ticker: str,
        event_ticker: str,
        start_ts: int,
        end_ts: int,
        percentiles: Sequence[int],
        period_interval: ForecastPeriod | int,
    ) -> ForecastHistoryResponse:
        series = _ticker(series_ticker, "series_ticker")
        event = _ticker(event_ticker, "event_ticker")
        _bounds(start_ts, end_ts)
        percentile_values = tuple(percentiles)
        if not 1 <= len(percentile_values) <= 10:
            raise KalshiParameterError("percentiles", "must contain 1 to 10 values")
        if len(set(percentile_values)) != len(percentile_values):
            raise KalshiParameterError("percentiles", "values must be unique")
        if any(type(value) is not int or value < 0 or value > 9999 for value in percentile_values):
            raise KalshiParameterError("percentiles", "values must be between 0 and 9999")
        period = _period(period_interval, _FORECAST_PERIODS, "period_interval")
        query: list[tuple[str, QueryParamValue]] = [
            ("percentiles", value) for value in percentile_values
        ]
        query.extend((("start_ts", start_ts), ("end_ts", end_ts), ("period_interval", period)))
        response = await self.get(
            f"/series/{series}/events/{event}/forecast_percentile_history",
            query_params=query,
        )
        return ForecastHistoryResponse.model_validate_json(response.content)
