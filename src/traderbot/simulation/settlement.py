"""SettlementVerifier — lazy reconciliation of settled markets."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from traderbot.logging_config import log_reconciliation_event, log_settlement_event

if TYPE_CHECKING:
    from traderbot.kalshi.cache import MarketDataCache
    from traderbot.kalshi.portfolio import PortfolioService
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
        portfolio_service: PortfolioService | None = None,
    ) -> None:
        self._provider = provider
        self._paper_trader = paper_trader
        self._cache = cache
        self._portfolio_service = portfolio_service

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

    async def reconcile_positions(self) -> None:
        """Compare paper positions vs real positions and warn on drift.

        This is a read-only check — no positions are modified.
        """
        paper_positions = [p for p in self._paper_trader.get_positions() if p.status == "open"]

        if self._portfolio_service is None:
            logger.info("Skipping reconciliation — no portfolio service configured")
            return

        try:
            real_positions = await self._portfolio_service.get_positions()
        except Exception:
            logger.warning("Portfolio service get_positions failed during reconciliation", exc_info=True)
            return

        real_by_ticker: dict[str, Any] = {rp.ticker: rp for rp in real_positions}

        checked = 0
        drifts = 0

        for pp in paper_positions:
            rp = real_by_ticker.get(pp.ticker)
            checked += 1

            if rp is None:
                drifts += 1
                log_reconciliation_event(
                    logger,
                    pp.ticker,
                    drift_cents=pp.avg_price_cents * pp.quantity,
                    paper_side=pp.side,
                    paper_qty=pp.quantity,
                    real_side="not_found",
                    real_qty=0,
                )
                logger.warning(
                    "Position drift: paper=%s side=%s qty=%s, real=not found",
                    pp.ticker,
                    pp.side,
                    pp.quantity,
                )
                continue

            # Map real position fields (side may not exist on Position model)
            rp_side = getattr(rp, "side", "unknown")
            rp_qty = getattr(rp, "quantity", 0)

            if pp.side != rp_side or pp.quantity != rp_qty:
                drifts += 1
                drift_cents = abs(pp.avg_price_cents * pp.quantity - rp.avg_price * rp_qty)
                log_reconciliation_event(
                    logger,
                    pp.ticker,
                    drift_cents=drift_cents,
                    paper_side=pp.side,
                    paper_qty=pp.quantity,
                    real_side=rp_side,
                    real_qty=rp_qty,
                )
                logger.warning(
                    "Position drift: paper=%s side=%s qty=%s, real=side=%s qty=%s",
                    pp.ticker,
                    pp.side,
                    pp.quantity,
                    rp_side,
                    rp_qty,
                )
            else:
                logger.debug("Position OK: %s", pp.ticker)

        logger.info("Reconciliation: %d checked, %d drifts", checked, drifts)

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
