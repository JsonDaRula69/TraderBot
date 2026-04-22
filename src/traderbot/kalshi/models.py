"""Pydantic v2 data models for Kalshi API responses and internal domain objects."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class OrderBookLevel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    price: Annotated[int, Field(ge=0, description="Price in cents")]
    size: Annotated[int, Field(ge=0)]


class Market(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    ticker: str
    question: str
    outcome_prices: list[str]
    volume: Annotated[int, Field(ge=0)]
    open_interest: Annotated[int, Field(ge=0)]
    close_time: datetime
    state: Literal["open", "closed", "settled"]
    event_ticker: str
    category: str | None = None
    market_category: MarketCategory | None = None
    settlement_result: bool | None = None


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
    direction: Literal["yes", "no", "hold"]
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
    current_value: float
    limit_value: float
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

    @computed_field
    @property
    def price_dollars(self) -> float:
        return self.price_cents / 100.0


class MarketCategory(StrEnum):
    """Market categories for cross-module use (analysis, simulation, etc.).

    Lives in kalshi/models.py to avoid circular dependencies.
    The similar enum in simulation/adaptation.py is kept for backward compatibility
    but code should prefer this version for cross-module use.
    """

    ECONOMICS = "Economics"
    POLITICS = "Politics"
    WEATHER = "Weather"
    SPORTS = "Sports"
    CULTURE = "Culture"
    TECHNOLOGY = "Technology"
    SCIENCE = "Science"


class OrderSide(StrEnum):
    yes = "yes"
    no = "no"


class OrderType(StrEnum):
    limit = "limit"
    market = "market"


class OrderRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    ticker: str
    side: OrderSide
    order_type: OrderType
    quantity: Annotated[int, Field(ge=1)]
    price: Annotated[int, Field(ge=1, le=99, description="Price in cents")]


class OrderStatus(StrEnum):
    live = "live"
    matched = "matched"
    cancelled = "cancelled"
    expired = "expired"


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


class CancelResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    order_id: str
    status: OrderStatus
