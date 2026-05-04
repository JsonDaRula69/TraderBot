"""Events service — list events and retrieve event detail."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from traderbot.kalshi.client import KalshiClient


class EventsService:
    """Fetches event data from the Kalshi API via a KalshiClient."""

    def __init__(self, client: KalshiClient) -> None:
        self._client = client

    async def get_events(
        self,
        cursor: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Return a paginated list of events."""
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor

        response = await self._client.get("/events", **params)
        response.raise_for_status()
        data = response.json()
        return data.get("events", [])

    async def get_event(self, event_ticker: str) -> dict:
        """Return detail for a single event by ticker."""
        response = await self._client.get(f"/events/{event_ticker}")
        response.raise_for_status()
        data = response.json()
        return data.get("event", data)