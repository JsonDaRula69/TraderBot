from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

type FixedPointDollars = Annotated[
    str,
    StringConstraints(pattern=r"^(?:0|[1-9][0-9]*)\.[0-9]{1,6}$"),
]
type FixedPointCount = Annotated[
    str,
    StringConstraints(pattern=r"^(?:0|[1-9][0-9]*)\.[0-9]{2}$"),
]
type MarketStatus = Literal[
    "initialized",
    "inactive",
    "active",
    "closed",
    "determined",
    "disputed",
    "amended",
    "finalized",
]
type MarketQueryStatus = Literal["unopened", "open", "paused", "closed", "settled"]
type CandlePeriod = Literal[1, 60, 1440]
type ForecastPeriod = Literal[0, 1, 60, 1440]
type StrikeType = Literal[
    "greater",
    "greater_or_equal",
    "less",
    "less_or_equal",
    "between",
    "functional",
    "custom",
    "structured",
]
type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


class _ResponseModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True, extra="ignore", frozen=True)
    error: None = None


class BalanceResponse(_ResponseModel):
    balance: int
    balance_dollars: FixedPointDollars
    portfolio_value: int
    updated_ts: int = Field(ge=0)


class SettlementSource(_ResponseModel):
    name: str | None = None
    url: str | None = None


class Series(_ResponseModel):
    ticker: str
    frequency: str
    title: str
    category: str
    tags: list[str] | None
    settlement_sources: list[SettlementSource] | None
    contract_url: str
    contract_terms_url: str
    fee_type: Literal["quadratic", "quadratic_with_maker_fees", "flat"]
    fee_multiplier: float
    additional_prohibitions: list[str] | None
    volume_fp: FixedPointCount | None = None
    last_updated_ts: datetime | None = None


class SeriesListResponse(_ResponseModel):
    series: list[Series]

    @field_validator("series", mode="before")
    @classmethod
    def _normalize_observed_empty(cls, value: object) -> object:
        """Normalize production's observed empty-series encoding.

        Production returns HTTP 200 with ``{"series": null}`` for an empty or
        unmatched ``category`` query (observed on-target against
        ``external-api.kalshi.com``). The official Get Series List schema
        declares ``series`` a required array, so only the observed null value is
        normalized to an empty list; a missing key still fails validation.
        """
        return [] if value is None else value


class PriceRange(_ResponseModel):
    start: FixedPointDollars
    end: FixedPointDollars
    step: FixedPointDollars


class MveSelectedLeg(_ResponseModel):
    event_ticker: str | None = None
    market_ticker: str | None = None
    side: str | None = None
    yes_settlement_value_dollars: FixedPointDollars | None = None


class KalshiMarket(_ResponseModel):
    ticker: str
    event_ticker: str
    market_type: Literal["binary", "scalar"]
    title: str | None = None
    subtitle: str | None = None
    yes_sub_title: str
    no_sub_title: str
    created_time: datetime
    updated_time: datetime
    open_time: datetime
    close_time: datetime
    latest_expiration_time: datetime
    settlement_timer_seconds: Annotated[int, Field(ge=0)]
    status: MarketStatus
    notional_value_dollars: FixedPointDollars
    yes_bid_dollars: FixedPointDollars
    yes_ask_dollars: FixedPointDollars
    no_bid_dollars: FixedPointDollars
    no_ask_dollars: FixedPointDollars
    yes_bid_size_fp: FixedPointCount
    yes_ask_size_fp: FixedPointCount
    last_price_dollars: FixedPointDollars
    previous_yes_bid_dollars: FixedPointDollars
    previous_yes_ask_dollars: FixedPointDollars
    previous_price_dollars: FixedPointDollars
    volume_fp: FixedPointCount
    volume_24h_fp: FixedPointCount
    open_interest_fp: FixedPointCount
    result: Literal["yes", "no", "scalar", ""]
    can_close_early: bool
    expiration_value: str
    rules_primary: str
    rules_secondary: str
    price_level_structure: str
    price_ranges: list[PriceRange]
    settlement_value_dollars: FixedPointDollars | None = None
    settlement_ts: datetime | None = None
    occurrence_datetime: datetime | None = None
    expected_expiration_time: datetime | None = None
    expiration_time: datetime | None = None
    strike_type: StrikeType | None = None
    floor_strike: float | None = None
    cap_strike: float | None = None
    functional_strike: str | None = None
    custom_strike: dict[str, JsonValue] | None = None
    mve_collection_ticker: str | None = None
    mve_selected_legs: list[MveSelectedLeg] | None = None
    is_provisional: bool | None = None
    exchange_index: int | None = None
    response_price_units: str | None = None
    early_close_condition: str | None = None
    fee_waiver_expiration_time: datetime | None = None
    primary_participant_key: str | None = None
    liquidity_dollars: FixedPointDollars | None = None
    fractional_trading_enabled: bool | None = None


class MarketListResponse(_ResponseModel):
    markets: list[KalshiMarket]
    cursor: str


class LiveBidAskDistribution(_ResponseModel):
    open_dollars: FixedPointDollars
    low_dollars: FixedPointDollars
    high_dollars: FixedPointDollars
    close_dollars: FixedPointDollars


class LivePriceDistribution(_ResponseModel):
    open_dollars: FixedPointDollars | None = None
    low_dollars: FixedPointDollars | None = None
    high_dollars: FixedPointDollars | None = None
    close_dollars: FixedPointDollars | None = None
    mean_dollars: FixedPointDollars | None = None
    previous_dollars: FixedPointDollars | None = None
    min_dollars: FixedPointDollars | None = None
    max_dollars: FixedPointDollars | None = None


class LiveCandlestick(_ResponseModel):
    end_period_ts: Annotated[int, Field(ge=0)]
    yes_bid: LiveBidAskDistribution
    yes_ask: LiveBidAskDistribution
    price: LivePriceDistribution
    volume_fp: FixedPointCount
    open_interest_fp: FixedPointCount


class LiveCandlestickResponse(_ResponseModel):
    ticker: str
    candlesticks: list[LiveCandlestick]


class HistoricalBidAskDistribution(_ResponseModel):
    open: FixedPointDollars
    low: FixedPointDollars
    high: FixedPointDollars
    close: FixedPointDollars


class HistoricalPriceDistribution(_ResponseModel):
    open: FixedPointDollars | None
    low: FixedPointDollars | None
    high: FixedPointDollars | None
    close: FixedPointDollars | None
    mean: FixedPointDollars | None
    previous: FixedPointDollars | None


class HistoricalCandlestick(_ResponseModel):
    end_period_ts: Annotated[int, Field(ge=0)]
    yes_bid: HistoricalBidAskDistribution
    yes_ask: HistoricalBidAskDistribution
    price: HistoricalPriceDistribution
    volume: FixedPointCount
    open_interest: FixedPointCount


class HistoricalCandlestickResponse(_ResponseModel):
    ticker: str
    candlesticks: list[HistoricalCandlestick]


class PercentilePoint(_ResponseModel):
    percentile: Annotated[int, Field(ge=0, le=9999)]
    raw_numerical_forecast: Decimal
    numerical_forecast: Decimal
    formatted_forecast: str


class ForecastPercentilesPoint(_ResponseModel):
    event_ticker: str
    end_period_ts: Annotated[int, Field(ge=0)]
    period_interval: ForecastPeriod
    percentile_points: list[PercentilePoint]


class ForecastHistoryResponse(_ResponseModel):
    forecast_history: list[ForecastPercentilesPoint]
