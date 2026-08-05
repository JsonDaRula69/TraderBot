"""Kalshi market models — v2 minimal types for Phase 0, extended for Phase 2.

Phase 0 ships ``MarketCategory`` for profile construction (DD-011). Phase 2
adds the market/order/fill data models ported from the retired v1 client
(``.trash/src/traderbot/kalshi/models.py``), modernized for pydantic v2.
"""

from __future__ import annotations

import logging
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, computed_field, field_validator

logger = logging.getLogger(__name__)


class MarketCategory(StrEnum):
    """Kalshi market categories.

    Used by TradingProfile.enabled_categories for per-agent
    category isolation (DD-011).
    """

    WEATHER = "weather"
    ECONOMICS = "economics"
    CRYPTO = "crypto"
    SPORTS = "sports"
    POLITICS = "politics"
    ENTERTAINMENT = "entertainment"
    FINANCIAL = "financial"
    WORLD = "world"
    OTHER = "other"


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
    series_ticker: str | None = None

    category: str | None = None
    market_category: MarketCategory | None = None
    settlement_result: bool | None = None
    strike_type: Literal["between", "less", "greater"] | None = None

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, v: object) -> str | None:
        if not isinstance(v, str):
            return None
        return v


class Ticker(BaseModel):
    """Kalshi series ("ticker") metadata — ``GET /series/{series_ticker}`` response.

    A series is the recurring template behind a family of events (e.g.
    "Daily Weather in NYC"); markets belong to events, events belong to
    series. Fixed-point count fields (``volume_fp``) and category mapping
    mirror the v2 API shape.
    """

    model_config = ConfigDict(strict=True, extra="forbid", populate_by_name=True)

    ticker: str
    title: str
    frequency: str = ""
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    volume_fp: str = "0.00"
    last_updated_ts: datetime | None = None

    market_category: MarketCategory | None = None

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, v: object) -> str | None:
        if not isinstance(v, str):
            return None
        return v

    @computed_field
    @property
    def volume(self) -> int:
        """Volume as integer contracts, parsed from the fixed-point string."""
        try:
            return int(float(self.volume_fp))
        except (ValueError, TypeError):
            return 0


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
    side: str = "yes"
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

    def model_post_init(self, __context: Any, /) -> None:
        logger.debug(
            "TradeRequest: ticker=%s dir=%s qty=%s price=%s",
            self.ticker,
            self.direction,
            self.quantity,
            self.price_cents,
        )


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
