"""Market data provider protocol and implementations for Kalshi data access."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from traderbot.kalshi.client import AuthenticationError
from traderbot.kalshi.markets import MarketService
from traderbot.logging_config import log_cache_event, log_market_event

if TYPE_CHECKING:
    from traderbot.kalshi.client import KalshiClient
    from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)

# Semaphore limits concurrent API calls in batch methods.
_BATCH_CONCURRENCY = 5
# Delay between batch chunks to respect rate limits.
_CHUNK_DELAY_SECONDS = 0.2


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


# --- Cache protocol (T8 provides the implementation) ---


@runtime_checkable
class MarketDataCache(Protocol):
    """Protocol for market data caching — T8 implements this."""

    def get_market(self, ticker: str) -> MarketSnapshot | None: ...
    def set_market(self, ticker: str, snapshot: MarketSnapshot) -> None: ...
    def get_orderbook(self, ticker: str) -> OrderBookSnapshot | None: ...
    def set_orderbook(self, ticker: str, snapshot: OrderBookSnapshot) -> None: ...


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


# --- Prod provider ---


class ProdDataProvider:
    """Production market data provider backed by the live Kalshi API.

    Read-only: fetches market snapshots, orderbooks, and settlement data.
    All monetary values are normalized to integer cents.
    """

    def __init__(
        self,
        client: KalshiClient,
        cache: MarketDataCache | None = None,
        profile: TradingProfile | None = None,
    ) -> None:
        self._client = client
        self._cache = cache
        self._profile = profile

    async def get_market(self, ticker: str) -> MarketSnapshot:
        if self._cache is not None:
            cached = self._cache.get_market(ticker)
            if cached is not None:
                log_cache_event(logger, "market", ticker, hit=True)
                return cached
            log_cache_event(logger, "market", ticker, hit=False)

        try:
            svc = MarketService(self._client)
            market = await svc.get_market(ticker)
        except AuthenticationError as exc:
            raise ProdAPIError(f"Kalshi API authentication failed: {exc}") from exc

        snapshot = MarketSnapshot(
            ticker=market.ticker,
            status=market.status,
            open_interest_cents=market.open_interest,
            close_time=market.close_time,
            settlement_result=market.settlement_result,
        )
        log_market_event(logger, "fetch_market", ticker, open_interest=market.open_interest)

        if self._cache is not None:
            self._cache.set_market(ticker, snapshot)

        return snapshot

    async def get_orderbook(self, ticker: str) -> OrderBookSnapshot:
        if self._cache is not None:
            cached = self._cache.get_orderbook(ticker)
            if cached is not None:
                log_cache_event(logger, "orderbook", ticker, hit=True)
                return cached
            log_cache_event(logger, "orderbook", ticker, hit=False)

        try:
            svc = MarketService(self._client)
            ob = await svc.get_orderbook(ticker)
        except AuthenticationError as exc:
            raise ProdAPIError(f"Kalshi API authentication failed: {exc}") from exc

        yes_bids = tuple(
            OrderBookLevelSnapshot(price_cents=lvl.price, size=lvl.size)
            for lvl in ob.yes_bids
        )
        no_bids = tuple(
            OrderBookLevelSnapshot(price_cents=lvl.price, size=lvl.size)
            for lvl in ob.no_bids
        )

        snapshot = OrderBookSnapshot(
            yes_bids=yes_bids,
            no_bids=no_bids,
            timestamp=datetime.now(UTC),
        )
        log_market_event(logger, "fetch_orderbook", ticker, levels=len(yes_bids) + len(no_bids))

        if self._cache is not None:
            self._cache.set_orderbook(ticker, snapshot)

        return snapshot

    async def get_settlement(self, ticker: str) -> SettlementResult | None:
        try:
            svc = MarketService(self._client)
            market = await svc.get_market(ticker)
        except AuthenticationError as exc:
            raise ProdAPIError(f"Kalshi API authentication failed: {exc}") from exc

        if market.status != "settled" or market.settlement_result is None:
            return None

        return SettlementResult(
            ticker=ticker,
            outcome=market.settlement_result,
            settled_at=market.close_time,
        )

    async def get_markets_batch(self, tickers: list[str]) -> dict[str, MarketSnapshot]:
        return await self._batch_fetch(tickers, self.get_market)

    async def get_orderbooks_batch(self, tickers: list[str]) -> dict[str, OrderBookSnapshot]:
        return await self._batch_fetch(tickers, self.get_orderbook)

    async def _batch_fetch(self, tickers: list[str], fetch_fn) -> dict:
        semaphore = asyncio.Semaphore(_BATCH_CONCURRENCY)
        results: dict[str, object] = {}

        async def _fetch_one(ticker: str) -> tuple[str, object]:
            async with semaphore:
                result = await fetch_fn(ticker)
                return ticker, result

        # Process in chunks to respect rate limits.
        for i in range(0, len(tickers), _BATCH_CONCURRENCY):
            chunk = tickers[i : i + _BATCH_CONCURRENCY]
            tasks = [_fetch_one(t) for t in chunk]
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)
            for outcome in outcomes:
                if isinstance(outcome, BaseException):
                    if isinstance(outcome, ProdAPIError):
                        raise outcome
                    raise ProdAPIError(f"Batch fetch failed: {outcome}") from outcome
                ticker, result = outcome
                results[ticker] = result
            if i + _BATCH_CONCURRENCY < len(tickers):
                await asyncio.sleep(_CHUNK_DELAY_SECONDS)

        return results
