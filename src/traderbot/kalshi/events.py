"""Events service — list events and retrieve event detail."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from traderbot.kalshi._normalize import _map_category, _unix_to_datetime
from traderbot.kalshi.models import Event

if TYPE_CHECKING:
    from traderbot.kalshi.client import KalshiClient

logger = logging.getLogger(__name__)


def _normalize_event(raw: dict[str, Any]) -> Event:
    close_time_val = raw.get("close_time")
    if isinstance(close_time_val, int):
        close_time_val = _unix_to_datetime(close_time_val)

    category = raw.get("category")
    market_category = _map_category(category)

    return Event(
        event_ticker=raw["ticker"],
        title=raw.get("title", ""),
        description=raw.get("description", ""),
        category=category,
        market_category=market_category,
        state=raw.get("state", raw.get("status", "")),
        close_time=close_time_val,
        markets_count=int(raw.get("markets_count", 0)),
    )


class EventsService:
    """Fetches event data from the Kalshi API via a KalshiClient."""

    def __init__(self, client: KalshiClient) -> None:
        self._client = client

    async def get_events(
        self,
        cursor: str | None = None,
        limit: int = 100,
        state: str | None = None,
    ) -> list[Event]:
        """Return a paginated list of events as typed Event models."""
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        if state is not None:
            params["state"] = state

        logger.debug("Fetching events: limit=%d state=%s", limit, state)
        response = await self._client.get("/events", **params)
        response.raise_for_status()
        data = response.json()
        raw_events = data.get("events", [])
        logger.info("Fetched %d events", len(raw_events))
        return [_normalize_event(e) for e in raw_events]

    async def get_event(self, event_ticker: str) -> Event:
        """Return detail for a single event by ticker."""
        logger.debug("Fetching event: ticker=%s", event_ticker)
        response = await self._client.get(f"/events/{event_ticker}")
        response.raise_for_status()
        data = response.json()
        raw = data.get("event", data)
        normalized = _normalize_event(raw)
        logger.info(
            "Fetched event: ticker=%s markets_count=%d", event_ticker, normalized.markets_count
        )
        return normalized
