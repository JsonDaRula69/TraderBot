"""Exchange service — check if the Kalshi exchange is open for trading."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from traderbot.kalshi.models import ExchangeStatus

if TYPE_CHECKING:
    from traderbot.kalshi.client import KalshiClient


class ExchangeService:
    """Fetches exchange status from the Kalshi API via a KalshiClient."""

    def __init__(self, client: KalshiClient) -> None:
        self._client = client

    async def get_status(self) -> ExchangeStatus:
        """Return current exchange status (open/closed/maintenance)."""
        response = await self._client.get("/exchange/status")
        response.raise_for_status()
        data = response.json()

        return ExchangeStatus(
            is_open=data.get("is_open", False),
            description=data.get("description", ""),
            active_markets=int(data.get("active_markets", 0)),
        )