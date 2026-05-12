"""Portfolio service — balance, positions, fills, and settlements."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from traderbot.kalshi._normalize import _to_cents, _to_count, _normalize_fill, _normalize_position
from traderbot.kalshi.models import Fill, Position, Settlement

if TYPE_CHECKING:
    from traderbot.kalshi.client import KalshiClient

logger = logging.getLogger(__name__)


class PortfolioService:
    """Reads portfolio data from the Kalshi API via a KalshiClient."""

    def __init__(self, client: KalshiClient) -> None:
        self._client = client

    async def get_balance(self) -> dict:
        """Return the current account balance."""
        response = await self._client.get("/portfolio/balance")
        response.raise_for_status()
        return response.json()

    async def get_positions(
        self,
        ticker: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> list[Position]:
        """Return open positions, optionally filtered by ticker."""
        params: dict[str, Any] = {"limit": limit}
        if ticker is not None:
            params["ticker"] = ticker
        if cursor is not None:
            params["cursor"] = cursor

        response = await self._client.get("/portfolio/positions", **params)
        response.raise_for_status()
        data = response.json()
        return [_normalize_position(p) for p in data.get("positions", [])]

    async def get_fills(
        self,
        ticker: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> list[Fill]:
        """Return fill history, optionally filtered by ticker."""
        params: dict[str, Any] = {"limit": limit}
        if ticker is not None:
            params["ticker"] = ticker
        if cursor is not None:
            params["cursor"] = cursor

        response = await self._client.get("/portfolio/fills", **params)
        response.raise_for_status()
        data = response.json()
        return [_normalize_fill(f) for f in data.get("fills", [])]

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

                price_cents = _to_cents(raw.get("price_fp") or 0)

                settlement_price_cents = _to_cents(raw.get("settlement_price_fp") or 0)

                pnl_cents = _to_cents(raw.get("pnl_fp") or 0)

                quantity = _to_count(raw.get("count_fp") or 0)

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
                logger.warning("Skipping malformed settlement record: %s", raw.get("ticker", "unknown"))
                continue
        return settlements
