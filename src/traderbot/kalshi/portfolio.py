"""Portfolio service — balance, positions, fills, and settlements."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from traderbot.kalshi._normalize import _to_cents
from traderbot.kalshi.models import Fill, Position, Settlement

if TYPE_CHECKING:
    from traderbot.kalshi.client import KalshiClient

logger = logging.getLogger(__name__)

BALANCE_CACHE_TTL: int = 3600  # 1 hour in seconds


class PortfolioService:
    """Reads portfolio data from the Kalshi API via a KalshiClient."""

    def __init__(self, client: KalshiClient) -> None:
        self._client = client
        self._balance_cache: dict[str, Any] | None = None
        self._balance_cache_ts: float = 0.0

    async def get_balance(self) -> dict:
        """Return the current account balance (no cache)."""
        logger.debug("Fetching account balance")
        response = await self._client.get("/portfolio/balance")
        response.raise_for_status()
        data = response.json()
        logger.info("Balance fetched: %s", data)
        return data

    async def get_cached_balance(self) -> dict | None:
        """Return account balance, cached with hourly TTL.

        Returns None if the API call fails (stale cache kept on error).
        """
        now = time.monotonic()
        if self._balance_cache is not None and (now - self._balance_cache_ts) < BALANCE_CACHE_TTL:
            logger.debug("Returning cached balance")
            return self._balance_cache
        try:
            data = await self.get_balance()
            self._balance_cache = data
            self._balance_cache_ts = now
            return data
        except Exception:
            logger.warning("Failed to fetch balance, returning stale cache")
            return self._balance_cache  # return stale cache on error

    async def get_positions(
        self,
        ticker: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> list[Position]:
        """Return open positions, optionally filtered by ticker. WS cache primary, REST fallback."""
        from traderbot.kalshi.ws_cache import get_positions as get_cached_positions

        cached = get_cached_positions()
        if cached:
            if ticker and ticker in cached:
                pos = cached[ticker]
                return [Position(**pos)]
            if not ticker:
                return [Position(**p) for p in cached.values()]

        params: dict[str, Any] = {"limit": limit}
        if ticker is not None:
            params["ticker"] = ticker
        if cursor is not None:
            params["cursor"] = cursor

        response = await self._client.get("/portfolio/positions", **params)
        response.raise_for_status()
        data = response.json()
        positions = [Position.model_validate(p) for p in data.get("positions", [])]
        logger.info("Fetched %d positions", len(positions))
        return positions

    async def get_fills(
        self,
        ticker: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> list[Fill]:
        """Return fill history, optionally filtered by ticker. WS cache primary, REST fallback."""
        from traderbot.kalshi.ws_cache import get_fills as get_cached_fills

        if not cursor and not ticker:
            cached = get_cached_fills(limit=limit)
            if cached:
                return [Fill(**f) for f in cached]

        params: dict[str, Any] = {"limit": limit}
        if ticker is not None:
            params["ticker"] = ticker
        if cursor is not None:
            params["cursor"] = cursor

        response = await self._client.get("/portfolio/fills", **params)
        response.raise_for_status()
        data = response.json()
        fills = [Fill.model_validate(f) for f in data.get("fills", [])]
        logger.info("Fetched %d fills", len(fills))
        return fills

    async def get_settlements(
        self,
        ticker: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> list[Settlement]:
        """Return settlement history as typed Settlement models, optionally filtered by ticker."""
        params: dict[str, Any] = {"limit": limit}
        if ticker is not None:
            params["ticker"] = ticker
        if cursor is not None:
            params["cursor"] = cursor

        response = await self._client.get("/portfolio/settlements", **params)
        response.raise_for_status()
        data = response.json()
        raw_settlements = data.get("settlements", [])
        settlements: list[Settlement] = []
        for raw in raw_settlements:
            try:
                settled_val = raw.get("settlement_time") or raw.get("settled_at")
                settled_at = (
                    datetime.fromtimestamp(int(settled_val), tz=UTC)
                    if isinstance(settled_val, int)
                    else None
                )

                price_cents = _to_cents(raw.get("price_dollars") or raw.get("price_fp") or 0)

                settlement_price_cents = _to_cents(
                    raw.get("settlement_price_dollars") or raw.get("settlement_price_fp") or 0
                )

                pnl_cents = _to_cents(raw.get("pnl_dollars") or raw.get("pnl_fp") or 0)

                quantity = int(raw.get("count_fp") or 0)

                settlements.append(
                    Settlement(
                        ticker=raw.get("ticker", ""),
                        side=raw.get("side", "yes"),
                        quantity=quantity,
                        price_cents=price_cents,
                        settlement_price_cents=settlement_price_cents,
                        pnl_cents=pnl_cents,
                        settled_at=settled_at,
                    )
                )
            except Exception:
                continue
        total_pnl = sum(s.pnl_cents for s in settlements)
        logger.info("Fetched %d settlements, total PnL=%d cents", len(settlements), total_pnl)
        return settlements
