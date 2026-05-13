"""Market data provider protocol and implementations for Kalshi data access."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import datetime

logger = logging.getLogger(__name__)


# --- Snapshot types (frozen dataclasses, all monetary values in cents) ---


@dataclass(frozen=True)
class OrderBookLevelSnapshot:
    """A single price/size level in an order book."""

    price_cents: int
    size: int


@dataclass(frozen=True)
class MarketSnapshot:
    """Immutable snapshot of a market's current state."""

    ticker: str
    status: str
    open_interest_cents: int
    close_time: datetime
    settlement_result: bool | None = None


@dataclass(frozen=True)
class OrderBookSnapshot:
    """Immutable snapshot of an order book at a point in time."""

    yes_bids: tuple[OrderBookLevelSnapshot, ...] = ()
    no_bids: tuple[OrderBookLevelSnapshot, ...] = ()
    timestamp: datetime | None = None


@dataclass(frozen=True)
class SettlementResult:
    """Result of a market settlement."""

    ticker: str
    outcome: bool
    settled_at: datetime


# --- Exceptions ---


class ProdAPIError(Exception):
    """Error raised when production API calls fail."""


# --- Protocol ---


@runtime_checkable
class MarketDataProvider(Protocol):
    """Protocol for market data access — async methods return immutable snapshots."""

    async def get_market(self, ticker: str) -> MarketSnapshot: ...
    async def get_orderbook(self, ticker: str) -> OrderBookSnapshot: ...
    async def get_settlement(self, ticker: str) -> SettlementResult | None: ...


# --- Mock provider (pre-configured data, no network) ---


class MockDataProvider:
    """Provider backed by pre-configured dicts — used in tests and simulation."""

    def __init__(
        self,
        markets: dict[str, MarketSnapshot] | None = None,
        orderbooks: dict[str, OrderBookSnapshot] | None = None,
        settlements: dict[str, SettlementResult] | None = None,
    ) -> None:
        self._markets: dict[str, MarketSnapshot] = markets or {}
        self._orderbooks: dict[str, OrderBookSnapshot] = orderbooks or {}
        self._settlements: dict[str, SettlementResult] = settlements or {}

    async def get_market(self, ticker: str) -> MarketSnapshot:
        logger.info("Fetching market data for %s", ticker)
        if ticker not in self._markets:
            raise ValueError(f"Market {ticker} not found")
        logger.info("Returning mock data for %s", ticker)
        return self._markets[ticker]

    async def get_orderbook(self, ticker: str) -> OrderBookSnapshot:
        logger.info("Fetching orderbook data for %s", ticker)
        if ticker not in self._orderbooks:
            raise ValueError(f"OrderBook {ticker} not found")
        logger.info("Returning mock orderbook data for %s", ticker)
        return self._orderbooks[ticker]

    async def get_settlement(self, ticker: str) -> SettlementResult | None:
        logger.info("Fetching settlement data for %s", ticker)
        result = self._settlements.get(ticker)
        if result is None:
            logger.info("No settlement data for %s", ticker)
        else:
            logger.info("Returning mock settlement data for %s", ticker)
        return result


# --- Prod provider placeholder (T7 implements this) ---


class ProdDataProvider:
    """Placeholder — real implementation lives in T7."""

    async def get_market(self, ticker: str) -> MarketSnapshot:
        raise NotImplementedError("ProdDataProvider not yet implemented — see T7")

    async def get_orderbook(self, ticker: str) -> OrderBookSnapshot:
        raise NotImplementedError("ProdDataProvider not yet implemented — see T7")

    async def get_settlement(self, ticker: str) -> SettlementResult | None:
        raise NotImplementedError("ProdDataProvider not yet implemented — see T7")
