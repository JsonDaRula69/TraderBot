"""SettlementVerifier — lazy reconciliation of settled markets."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from traderbot.logging_config import log_settlement_event

if TYPE_CHECKING:
    from traderbot.kalshi.cache import MarketDataCache
    from traderbot.kalshi.provider import MarketDataProvider, SettlementResult
    from traderbot.simulation.paper_trader import PaperTrader

logger = logging.getLogger(__name__)

_SWEEP_WINDOW = timedelta(minutes=30)
_SEMAPHORE_LIMIT = 5


class SettlementVerifier:
    """Verify market settlements and reconcile paper-trader positions.

    Startup check reconciles all open positions.
    Periodic sweep only checks positions within 30min of close.
    Pre-order check blocks orders on already-settled markets.
    """

    def __init__(
        self,
        provider: MarketDataProvider,
        paper_trader: PaperTrader,
        cache: MarketDataCache | None = None,
    ) -> None:
        self._provider = provider
        self._paper_trader = paper_trader
        self._cache = cache

    async def check_settlements_on_startup(self) -> None:
        """Reconcile all open positions against settlement data at startup."""
        open_positions = [p for p in self._paper_trader.get_positions() if p.status == "open"]
        if not open_positions:
            logger.info("Startup settlement check: no open positions")
            return

        tickers = [p.ticker for p in open_positions]

        batch_fn = getattr(self._provider, "get_settlements_batch", None)
        if batch_fn is not None:
            try:
                results: dict[str, SettlementResult | None] = await batch_fn(tickers)  # type: ignore[operator]
            except Exception:
                logger.warning("Batch settlement fetch failed, falling back to individual calls", exc_info=True)
                results = await self._gather_settlements(tickers)
        else:
            results = await self._gather_settlements(tickers)

        settled_count = 0
        for ticker, result in results.items():
            if result is not None:
                self._paper_trader.mark_settled(ticker, result.outcome)
                log_settlement_event(logger, ticker, result.outcome, source="startup")
                settled_count += 1

        logger.info(
            "Startup settlement check: %d open positions, %d newly settled",
            len(tickers),
            settled_count,
        )

    async def check_settlements_periodic(self, now: datetime) -> None:
        """Check open positions within 30min of close_time for settlement."""
        open_positions = [p for p in self._paper_trader.get_positions() if p.status == "open"]
        if not open_positions:
            return

        cutoff = now + _SWEEP_WINDOW
        near_expiry: list[str] = []
        for pos in open_positions:
            try:
                market = await self._provider.get_market(pos.ticker)
            except Exception:
                logger.warning("Failed to fetch market %s during sweep", pos.ticker, exc_info=True)
                continue
            if market.close_time <= cutoff:
                near_expiry.append(pos.ticker)

        if not near_expiry:
            logger.info("Sweep: no near-expiry positions")
            return

        results = await self._gather_settlements(near_expiry)
        settled_count = 0
        for ticker, result in results.items():
            if result is not None:
                self._paper_trader.mark_settled(ticker, result.outcome)
                log_settlement_event(logger, ticker, result.outcome, source="periodic")
                settled_count += 1

        logger.info("Sweep: checked %d, settled %d", len(near_expiry), settled_count)

    async def check_settlement_before_order(self, ticker: str) -> bool:
        """Check if a market is already settled before placing an order.

        Returns True if the market is settled (order should be blocked).
        Returns False if the market is open (order allowed).
        """
        if self._cache is not None:
            try:
                cached = await self._cache.get_settlement(ticker)
                if cached is not None:
                    log_settlement_event(logger, ticker, cached.outcome, source="cache-pre-order")
                    self._paper_trader.mark_settled(ticker, cached.outcome)
                    logger.info("Order blocked: %s is settled", ticker)
                    return True
            except Exception:
                logger.warning("Cache lookup failed for %s, falling back to provider", ticker, exc_info=True)

        try:
            result = await self._provider.get_settlement(ticker)
        except Exception:
            logger.warning("Provider settlement check failed for %s, allowing order", ticker, exc_info=True)
            return False

        if result is not None:
            self._paper_trader.mark_settled(ticker, result.outcome)
            log_settlement_event(logger, ticker, result.outcome, source="provider-pre-order")
            logger.info("Order blocked: %s is settled", ticker)
            return True

        return False

    def reconcile_positions(self) -> None:
        """Reconcile paper positions against expected valuations.

        T15 implements full reconciliation logic.
        """
        raise NotImplementedError("reconcile_positions not yet implemented — see T15")

    async def _gather_settlements(self, tickers: list[str]) -> dict[str, SettlementResult | None]:
        """Fetch settlement data for multiple tickers with concurrency limit."""
        semaphore = asyncio.Semaphore(_SEMAPHORE_LIMIT)

        async def _fetch_one(ticker: str) -> tuple[str, SettlementResult | None]:
            async with semaphore:
                try:
                    return ticker, await self._provider.get_settlement(ticker)
                except Exception:
                    logger.warning("Settlement check failed for %s", ticker, exc_info=True)
                    return ticker, None

        results = await asyncio.gather(*[_fetch_one(t) for t in tickers])
        return dict(results)
