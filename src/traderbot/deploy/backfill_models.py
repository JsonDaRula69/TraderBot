from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict


class StrictResultModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True, extra="forbid", frozen=True)


class TableCounts(StrictResultModel):
    seen: int = 0
    inserted: int = 0
    duplicate: int = 0


class CollectorCounts(StrictResultModel):
    weather_forecasts: TableCounts = TableCounts()
    nws_forecasts: TableCounts = TableCounts()
    weather_observations: TableCounts = TableCounts()


class KalshiCounts(StrictResultModel):
    markets: TableCounts = TableCounts()
    candlesticks: TableCounts = TableCounts()
    forecast_history: TableCounts = TableCounts()


class ApiCounts(StrictResultModel):
    pages: int = 0
    markets: int = 0
    candlesticks: int = 0
    forecasts: int = 0


class BackfillFailure(StrictResultModel):
    code: str
    item: str | None = None
    detail: str


class BackfillResult(StrictResultModel):
    status: Literal["complete", "partial", "failure", "invalid_input"]
    collector: CollectorCounts = CollectorCounts()
    kalshi: KalshiCounts = KalshiCounts()
    api: ApiCounts = ApiCounts()
    warnings: tuple[str, ...] = ()
    failures: tuple[BackfillFailure, ...] = ()


__all__ = [
    "ApiCounts",
    "BackfillFailure",
    "BackfillResult",
    "CollectorCounts",
    "KalshiCounts",
    "TableCounts",
]
