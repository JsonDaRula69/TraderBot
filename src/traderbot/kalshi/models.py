"""Pydantic v2 data models for Kalshi API responses and internal domain objects."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, computed_field, field_validator


class MarketCategory(StrEnum):
    """Market categories for cross-module use (analysis, simulation, news, etc.).

    Single source of truth — all modules import from here.
    Values are lowercase to match Kalshi API convention.
    API variant mappings: "Climate and Weather" → WEATHER,
    "Science and Technology" → SCIENCE_AND_TECHNOLOGY,
    "technology" → SCIENCE_AND_TECHNOLOGY, "science" → SCIENCE_AND_TECHNOLOGY.
    """

    ECONOMICS = "economics"
    POLITICS = "politics"
    WEATHER = "weather"
    SPORTS = "sports"
    SCIENCE_AND_TECHNOLOGY = "science_and_technology"
    CRYPTO = "crypto"
    COMMODITIES = "commodities"
    COMPANIES = "companies"
    ELECTIONS = "elections"
    ENTERTAINMENT = "entertainment"
    FINANCIALS = "financials"
    HEALTH = "health"
    MENTIONS = "mentions"
    SOCIAL = "social"


class OrderSide(StrEnum):
    """Internal yes/no side representation."""

    yes = "yes"
    no = "no"


class OrderSideV2(StrEnum):
    """V2 API-facing side values. bid → OrderSide.yes, ask → OrderSide.no."""

    bid = "bid"
    ask = "ask"


class OrderType(StrEnum):
    """Order type: limit (default) or market."""

    limit = "limit"
    market = "market"


class OrderStatus(StrEnum):
    """Order status values.

    V2: 'filled' replaces the legacy 'matched' status.
    """

    live = "live"
    resting = "resting"
    matched = "matched"
    filled = "filled"
    cancelled = "cancelled"
    expired = "expired"


class OrderRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    ticker: str
    side: OrderSideV2
    count: str
    price: str
    client_order_id: str | None = None
    time_in_force: str = "good_till_canceled"
    self_trade_prevention_type: str = "taker_at_cross"

    def to_v2_body(self) -> dict[str, str]:
        """Serialize to V2 API request body."""
        body: dict[str, str] = {
            "ticker": self.ticker,
            "side": self.side.value,
            "count": self.count,
            "price": self.price,
            "client_order_id": self.client_order_id or str(uuid4()),
            "time_in_force": self.time_in_force,
            "self_trade_prevention_type": self.self_trade_prevention_type,
        }
        return body


class OrderBookLevel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    price: Annotated[int, Field(ge=0, description="Price in cents")]
    size: Annotated[int, Field(ge=0)]


class Market(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", populate_by_name=True)

    ticker: str
    question: str
    outcome_prices: list[str]
    volume: Annotated[int, Field(ge=0)]
    open_interest: Annotated[int, Field(ge=0)]
    close_time: datetime
    status: Literal["open", "closed", "settled"] = Field(
        validation_alias=AliasChoices("status", "state"),
    )
    event_ticker: str

    category: str | None = None
    market_category: MarketCategory | None = None
    settlement_result: bool | None = None

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, v: object) -> str | None:
        if not isinstance(v, str):
            return None
        return v


class OrderBook(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    yes_bids: list[OrderBookLevel]
    no_bids: list[OrderBookLevel]


class Trade(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    ticker: str
    price: Annotated[int, Field(ge=0, description="Price in cents")]
    quantity: Annotated[int, Field(ge=0)]
    side: Literal["yes", "no"]
    timestamp: datetime


class Order(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    id: str
    ticker: str
    side: Literal["yes", "no"]
    price: Annotated[int, Field(ge=0, description="Price in cents")]
    quantity: Annotated[int, Field(ge=0)]
    status: Literal["resting", "filled", "cancelled"]
    created_time: datetime


class Position(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    ticker: str
    quantity: Annotated[int, Field(ge=0)]
    avg_price: Annotated[int, Field(ge=0, description="Average price in cents")]
    settlement_result: bool | None = None


class Fill(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    order_id: str
    ticker: str
    side: Literal["yes", "no"]
    price: Annotated[int, Field(ge=0, description="Price in cents")]
    quantity: Annotated[int, Field(ge=0)]
    timestamp: datetime


class Decision(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    timestamp: datetime
    ticker: str
    direction: Literal["yes", "no", "neutral"]
    quantity: Annotated[int, Field(ge=0)]
    price: Annotated[int, Field(ge=0, description="Price in cents")]
    signal_strength: Annotated[float, Field(ge=0, le=1)]
    confidence: Annotated[float, Field(ge=0, le=1)]
    edge_estimate: float
    risk_checks: dict[str, bool]
    outcome: Literal["executed", "rejected", "held"]
    rejection_reason: str | None = None
    actual_result: bool | None = None


class CutoffTimestamps(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    market_settled_ts: datetime | None = None
    trade_cutoff_ts: datetime | None = None
    order_cutoff_ts: datetime | None = None


class Event(BaseModel):
    """Kalshi event — a group of related markets sharing a resolution condition."""

    model_config = ConfigDict(strict=True, extra="forbid", populate_by_name=True)

    event_ticker: str
    title: str
    description: str = ""
    category: str | None = None
    market_category: MarketCategory | None = None
    state: str = Field(validation_alias=AliasChoices("state", "status"))
    close_time: datetime | None = None
    markets_count: int = 0


class Settlement(BaseModel):
    """A settled position with P&L in cents."""

    model_config = ConfigDict(strict=True, extra="forbid")

    ticker: str
    side: Literal["yes", "no"]
    quantity: Annotated[int, Field(ge=0)]
    price_cents: Annotated[int, Field(ge=0, description="Entry price in cents")]
    settlement_price_cents: Annotated[int, Field(ge=0, description="Settlement price in cents")]
    pnl_cents: Annotated[int, Field(description="Profit/loss in cents")]
    settled_at: datetime | None = None


class MarketListResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    markets: list[Market]
    cursor: str | None = None


class TradeListResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    trades: list[Trade]
    cursor: str | None = None


class RiskCheckResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    passed: bool
    limit_name: str
    current_value: float | int
    limit_value: float | int
    rejection_reason: str | None = None


class PortfolioState(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    portfolio_value_cents: Annotated[int, Field(gt=0)]
    peak_value_cents: Annotated[int, Field(gt=0)]
    current_positions_value_cents: Annotated[int, Field(ge=0)]
    today_realized_loss_cents: Annotated[int, Field(ge=0)]
    today_unrealized_loss_cents: Annotated[int, Field(ge=0)]
    open_positions_count: Annotated[int, Field(ge=0)]

    @computed_field
    @property
    def portfolio_value_dollars(self) -> float:
        return self.portfolio_value_cents / 100.0


class TradeRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    ticker: str
    direction: Literal["yes", "no"]
    quantity: Annotated[int, Field(gt=0)]
    price_cents: Annotated[int, Field(gt=0, description="Limit price in cents")]
    estimated_prob: Annotated[float, Field(ge=0, le=1)]
    confidence: Annotated[float, Field(ge=0, le=1)]
    edge_estimate: float
    market_price_cents: Annotated[int, Field(gt=0, description="Current market price in cents")]
    market_open_interest: Annotated[int, Field(ge=0)]
    market_category: MarketCategory | None = None

    @computed_field
    @property
    def price_dollars(self) -> float:
        return self.price_cents / 100.0





class TradingOrder(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    order_id: str
    ticker: str
    side: OrderSide
    order_type: OrderType
    quantity: Annotated[int, Field(ge=0)]
    price: Annotated[int, Field(ge=1, le=99, description="Price in cents")]
    status: OrderStatus
    created_time: datetime
    filled_quantity: Annotated[int, Field(ge=0)] = 0


class OrderResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    order: TradingOrder


class OrderResult(BaseModel):
    """V2 CreateOrderV2Response shape."""

    model_config = ConfigDict(strict=True, extra="forbid")

    order_id: str
    client_order_id: str | None = None
    fill_count: str = "0"
    remaining_count: str = "0"
    average_fill_price: str | None = None
    ts_ms: int | None = None


class CancelResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    order_id: str
    status: OrderStatus | None = None
    reduced_by: str | None = None


class ExchangeStatus(BaseModel):
    """Current status of the Kalshi exchange."""

    model_config = ConfigDict(strict=True, extra="forbid")

    is_open: bool
    description: str = ""
    active_markets: Annotated[int, Field(ge=0)] = 0
