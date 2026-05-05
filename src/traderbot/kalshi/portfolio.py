"""Portfolio service — balance, positions, fills, and settlements."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from traderbot.kalshi.models import Fill, Position, Settlement

if TYPE_CHECKING:
    from traderbot.kalshi.client import KalshiClient


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
        return [Position.model_validate(p) for p in data.get("positions", [])]

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
        return [Fill.model_validate(f) for f in data.get("fills", [])]

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
                settlements.append(
                    Settlement(
                        ticker=raw.get("ticker", ""),
                        side=raw.get("side", "yes"),
                        quantity=int(raw.get("count", raw.get("quantity", 0))),
                        price_cents=int(raw.get("yes_price", raw.get("price", 0))),
                        settlement_price_cents=int(
                            raw.get("settlement_price", raw.get("price", 0))
                        ),
                        pnl_cents=int(raw.get("pnl", raw.get("realized_pnl", 0))),
                        settled_at=settled_at,
                    )
                )
            except Exception:
                continue
        return settlements
