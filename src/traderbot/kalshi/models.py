"""Kalshi market models — v2 minimal types for Phase 0, extended for Phase 2.

Phase 0 ships ``MarketCategory`` for profile construction (DD-011). Phase 2
adds the market/order/fill data models ported from the retired v1 client
(``.trash/src/traderbot/kalshi/models.py``), modernized for pydantic v2.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, ClassVar, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, computed_field, field_validator

from traderbot.kalshi.order_models import (
    CancelResponse as CancelResponse,
)
from traderbot.kalshi.order_models import (
    ExchangeStatus as ExchangeStatus,
)
from traderbot.kalshi.order_models import (
    Fill as Fill,
)
from traderbot.kalshi.order_models import (
    MarketCategory,
    Trade,
)
from traderbot.kalshi.order_models import (
    Order as Order,
)
from traderbot.kalshi.order_models import (
    OrderBook as OrderBook,
)
from traderbot.kalshi.order_models import (
    OrderBookLevel as OrderBookLevel,
)
from traderbot.kalshi.order_models import (
    OrderRequest as OrderRequest,
)
from traderbot.kalshi.order_models import (
    OrderResponse as OrderResponse,
)
from traderbot.kalshi.order_models import (
    OrderResult as OrderResult,
)
from traderbot.kalshi.order_models import (
    OrderSide as OrderSide,
)
from traderbot.kalshi.order_models import (
    OrderSideV2 as OrderSideV2,
)
from traderbot.kalshi.order_models import (
    OrderStatus as OrderStatus,
)
from traderbot.kalshi.order_models import (
    OrderType as OrderType,
)
from traderbot.kalshi.order_models import (
    PortfolioState as PortfolioState,
)
from traderbot.kalshi.order_models import (
    Position as Position,
)
from traderbot.kalshi.order_models import (
    RiskCheckResult as RiskCheckResult,
)
from traderbot.kalshi.order_models import (
    TradeRequest as TradeRequest,
)
from traderbot.kalshi.order_models import (
    TradingOrder as TradingOrder,
)


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
    def _normalize_category(cls, v: str | None) -> str | None:
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
    def _normalize_category(cls, v: str | None) -> str | None:
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


class CutoffDatetimeError(ValueError):
    pass


class CutoffTimestamps(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True, extra="forbid", frozen=True)

    market_settled_ts: datetime
    trades_created_ts: datetime
    orders_updated_ts: datetime
    market_positions_last_updated_ts: datetime | None = None

    @field_validator("*")
    @classmethod
    def _normalize_aware_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        try:
            offset = value.utcoffset()
        except (OverflowError, ValueError) as exc:
            raise CutoffDatetimeError("cutoff datetime must have an available UTC offset") from exc
        if offset is None:
            raise CutoffDatetimeError("cutoff datetime must be timezone-aware")
        try:
            return value.astimezone(UTC)
        except (OverflowError, ValueError) as exc:
            raise CutoffDatetimeError("cutoff datetime cannot be normalized to UTC") from exc


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
