from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field


class MarketCategory(StrEnum):
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
    yes = "yes"
    no = "no"


class OrderSideV2(StrEnum):
    bid = "bid"
    ask = "ask"


class OrderType(StrEnum):
    limit = "limit"
    market = "market"


class OrderStatus(StrEnum):
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
        return {
            "ticker": self.ticker,
            "side": self.side.value,
            "count": self.count,
            "price": self.price,
            "client_order_id": self.client_order_id or str(uuid4()),
            "time_in_force": self.time_in_force,
            "self_trade_prevention_type": self.self_trade_prevention_type,
        }


class OrderBookLevel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    price: Annotated[int, Field(ge=0, description="Price in cents")]
    size: Annotated[int, Field(ge=0)]


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
    model_config = ConfigDict(strict=True, extra="forbid")

    is_open: bool
    description: str = ""
    active_markets: Annotated[int, Field(ge=0)] = 0
