from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from traderbot.kalshi.models import CutoffTimestamps
from traderbot.kalshi.rest_models import MarketListResponse

type QueryParamValue = str | int | float | bool | None
type QueryParams = dict[str, QueryParamValue] | list[tuple[str, QueryParamValue]]


class HistoricalMarketParameterError(ValueError):
    def __init__(self, parameter: str, reason: str) -> None:
        self.parameter: str = parameter
        self.reason: str = reason
        super().__init__(f"invalid {parameter}: {reason}")


def _cursor(value: QueryParamValue) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise HistoricalMarketParameterError("cursor", "must be a string")
    if not value or not value.strip() or value != value.strip() or not value.isprintable():
        raise HistoricalMarketParameterError("cursor", "must be a printable nonempty string")
    return value


def _ticker(value: str | None, parameter: str) -> str | None:
    if value is None:
        return None
    ticker_text = value.replace("-", "").replace("_", "").replace(".", "")
    if not value or value != value.strip() or not ticker_text.isalnum():
        raise HistoricalMarketParameterError(parameter, "must use Kalshi ticker characters")
    return value


def _tickers(value: str | None) -> str | None:
    if value is None:
        return None
    parts = value.split(",")
    if not parts or any(_ticker(part, "tickers") is None for part in parts):
        raise HistoricalMarketParameterError("tickers", "must contain comma-separated tickers")
    return value


class KalshiArchiveMethods(ABC):
    @abstractmethod
    async def get(
        self,
        path: str,
        timeout: float = 30.0,
        *,
        query_params: QueryParams | None = None,
        **params: QueryParamValue,
    ) -> httpx.Response: ...

    async def get_historical_cutoff(self) -> CutoffTimestamps:
        response = await self.get("/historical/cutoff")
        return CutoffTimestamps.model_validate_json(response.content)

    async def get_historical_markets(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        tickers: str | None = None,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
        mve_filter: str | None = None,
    ) -> MarketListResponse:
        if limit is not None and (type(limit) is not int or not 0 <= limit <= 1000):
            raise HistoricalMarketParameterError("limit", "must be an integer between 0 and 1000")
        if mve_filter not in (None, "exclude"):
            raise HistoricalMarketParameterError("mve_filter", "must be exclude")
        selectors = (
            _tickers(tickers),
            _ticker(event_ticker, "event_ticker"),
            _ticker(series_ticker, "series_ticker"),
            mve_filter,
        )
        if sum(value is not None for value in selectors) > 1:
            raise HistoricalMarketParameterError("selectors", "filters are mutually exclusive")
        values: tuple[tuple[str, QueryParamValue], ...] = (
            ("limit", limit),
            ("cursor", _cursor(cursor)),
            ("tickers", selectors[0]),
            ("event_ticker", selectors[1]),
            ("series_ticker", selectors[2]),
            ("mve_filter", selectors[3]),
        )
        query: dict[str, QueryParamValue] = {
            name: value for name, value in values if value is not None
        }
        response = await self.get("/historical/markets", query_params=query)
        return MarketListResponse.model_validate_json(response.content)


__all__ = ["HistoricalMarketParameterError", "KalshiArchiveMethods"]
