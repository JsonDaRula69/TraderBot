"""SettlementVerifier — lazy reconciliation of settled markets."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from traderbot.logging_config import log_reconciliation_event, log_settlement_event

if TYPE_CHECKING:
    from pathlib import Path

    from traderbot.kalshi.cache import MarketDataCache
    from traderbot.kalshi.portfolio import PortfolioService
    from traderbot.kalshi.provider import MarketDataProvider, SettlementResult
    from traderbot.profiles.models import Profile
    from traderbot.simulation.paper_trader import PaperTrader

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
#  Auto-settlement: reconcile open paper positions
# ------------------------------------------------------------------

# Regex for Kalshi tickers: KXHIGHCHI-26JUN02-T72 or KXHIGHCHI-26JUN02-B72.5
_TICKER_RE = re.compile(
    r"^(KX\w+)-(\d{2})([A-Z]{3})(\d{2})-(T|B)(\d+(?:\.\d+)?)$",
    re.IGNORECASE,
)

_MONTH_ABBR: dict[str, int] = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


def _parse_kalshi_ticker(ticker: str) -> tuple[str, int, int, int, str, float] | None:
    """Parse a Kalshi ticker into (base_prefix, year, month, day, strike_type, strike_val).

    Returns None if the ticker doesn't match the expected Kalshi date-strike pattern.
    """
    m = _TICKER_RE.match(ticker)
    if not m:
        return None
    prefix = m.group(1).upper()
    yy = int(m.group(2))
    month_abbr = m.group(3).upper()
    dd = int(m.group(4))
    strike_type = m.group(5).upper()  # 'T' threshold, 'B' bucket
    strike_val = float(m.group(6))

    month = _MONTH_ABBR.get(month_abbr)
    if month is None:
        return None

    year = 2000 + yy
    return (prefix, year, month, dd, strike_type, strike_val)


async def _settle_weather_bets(
    conn: Any, bets: list[tuple[Any, tuple[str, int, int, int, str, float]]]
) -> int:
    """Settle weather bets using Open-Meteo archive API for actual temperatures.

    Works without Kalshi auth. Queries the archive API for the actual high
    temperature on the settlement date and compares against the strike.
    """
    import httpx

    from traderbot.data.weather.provider import _KALSHI_CITY_MAP
    from traderbot.db.positions import update_settlement

    settled = 0

    async with httpx.AsyncClient(timeout=20.0) as client:
        for pos, parsed in bets:
            prefix, year, month, day, _strike_type, strike_val = parsed

            city_info = _KALSHI_CITY_MAP.get(prefix)
            if city_info is None:
                logger.debug("Unknown city prefix %s for ticker %s", prefix, pos.ticker)
                continue

            _city_name, lat, lon, timezone = city_info
            date_str = f"{year:04d}-{month:02d}-{day:02d}"

            try:
                url = "https://archive-api.open-meteo.com/v1/archive"
                params = {
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "temperature_2m_max",
                    "start_date": date_str,
                    "end_date": date_str,
                    "temperature_unit": "fahrenheit",
                    "timezone": timezone,
                }
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                daily = data.get("daily", {})
                temps = daily.get("temperature_2m_max", [])
                if not temps:
                    logger.warning("No temperature data for %s on %s", pos.ticker, date_str)
                    continue
                actual_high = float(temps[0])
            except Exception:
                logger.warning(
                    "Failed to fetch weather data for %s on %s", pos.ticker, date_str, exc_info=True
                )
                continue

            # YES position wins if actual temp > strike threshold
            won = actual_high > strike_val

            pnl_cents = (
                (100 - pos.avg_price) * pos.quantity if won else (0 - pos.avg_price) * pos.quantity
            )
            update_settlement(conn, pos.ticker, won, pnl_cents)
            settled += 1
            logger.info(
                "Settled %s: actual=%.1f strike=%.1f won=%s pnl=%d",
                pos.ticker,
                actual_high,
                strike_val,
                won,
                pnl_cents,
            )

    return settled


async def _settle_kalshi_bets(
    conn: Any,
    bets: list[tuple[Any, tuple[str, int, int, int, str, float]]],
) -> int:
    """Settle non-weather Kalshi bets using the public Kalshi /markets/{ticker} endpoint.

    No auth required — the /markets/{ticker} endpoint is public.
    """
    import httpx

    from traderbot.db.positions import update_settlement

    settled = 0
    base_url = "https://external-api.kalshi.com/trade-api/v2"
    async with httpx.AsyncClient(timeout=15.0) as client:
        for pos, _parsed in bets:
            url = f"{base_url}/markets/{pos.ticker}"
            try:
                resp = await client.get(url)
            except Exception:
                logger.warning(
                    "Failed to fetch market %s from Kalshi API", pos.ticker, exc_info=True
                )
                continue

            if resp.status_code != 200:
                logger.warning("HTTP %d fetching market %s", resp.status_code, pos.ticker)
                continue

            data = resp.json()
            market = data.get("market", {})
            sr = market.get("settlement_result")
            if sr is None:
                logger.debug("Market %s not yet settled via Kalshi API", pos.ticker)
                continue

            outcome = 1 if sr else 0
            pnl_cents = (outcome * 100 - pos.avg_price) * pos.quantity
            update_settlement(conn, pos.ticker, sr, pnl_cents)
            settled += 1
            logger.info(
                "Settled %s via Kalshi: result=%s pnl=%d",
                pos.ticker,
                sr,
                pnl_cents,
            )

    return settled


def auto_settle_paper_positions(
    profile: Profile | None = None,
    db_path: Path | None = None,
) -> int:
    """Settle paper positions for markets that have already expired.

    Checks open positions against settlement data:
    - Weather tickers (KXHIGH*): uses Open-Meteo archive API to get actual
      temperatures — works without Kalshi auth.
    - Other Kalshi tickers: queries Kalshi API for settlement results
      (requires auth credentials).

    Returns the number of positions settled.
    """
    from datetime import UTC, datetime

    from traderbot.data.weather.provider import _KALSHI_CITY_MAP
    from traderbot.db import get_connection
    from traderbot.db.positions import init_table, list_open_positions
    from traderbot.paths import _resolve_db_path

    async def _run() -> int:
        resolved_path = _resolve_db_path(db_path)
        with get_connection(resolved_path) as conn:
            init_table(conn)
            open_positions = list_open_positions(conn)

            if not open_positions:
                logger.info("No open positions to settle")
                return 0

            weather_bets: list[tuple[Any, tuple[str, int, int, int, str, float]]] = []
            kalshi_bets: list[tuple[Any, tuple[str, int, int, int, str, float]]] = []

            now = datetime.now(UTC)
            for pos in open_positions:
                parsed = _parse_kalshi_ticker(pos.ticker)
                if parsed is None:
                    continue
                _prefix, year, month, day, _st, _sv = parsed
                settlement_date = datetime(year, month, day, tzinfo=UTC)
                if settlement_date >= now:
                    continue
                if parsed[0] in _KALSHI_CITY_MAP:
                    weather_bets.append((pos, parsed))
                else:
                    kalshi_bets.append((pos, parsed))

            total = 0
            if weather_bets:
                total += await _settle_weather_bets(conn, weather_bets)
            if kalshi_bets:
                total += await _settle_kalshi_bets(conn, kalshi_bets)

            logger.info("auto_settle_paper_positions: %d positions settled", total)
            return total

    return asyncio.run(_run())


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
        logger.info("SettlementVerifier initialized")

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
                logger.warning(
                    "Batch settlement fetch failed, falling back to individual calls", exc_info=True
                )
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
                logger.warning(
                    "Cache lookup failed for %s, falling back to provider", ticker, exc_info=True
                )

        try:
            result = await self._provider.get_settlement(ticker)
        except Exception:
            logger.warning(
                "Provider settlement check failed for %s, allowing order", ticker, exc_info=True
            )
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
            logger.warning(
                "Portfolio service get_positions failed during reconciliation", exc_info=True
            )
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
