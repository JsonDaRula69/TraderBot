"""Events and series services — list events, retrieve event detail, list series by category."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from traderbot.kalshi._normalize import _map_category, _unix_to_datetime
from traderbot.kalshi.models import Event, Series, SeriesListResponse

if TYPE_CHECKING:
    from traderbot.kalshi.client import KalshiClient


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


def _normalize_series(raw: dict[str, Any]) -> Series:
    category = raw.get("category")
    market_category = _map_category(category)

    return Series(
        ticker=raw["ticker"],
        title=raw.get("title", ""),
        category=category,
        market_category=market_category,
        frequency=raw.get("frequency"),
        fee_type=raw.get("fee_type"),
    )


class EventsService:
    """Fetches event and series data from the Kalshi API via a KalshiClient."""

    def __init__(self, client: KalshiClient) -> None:
        self._client = client

    async def get_events(
        self,
        cursor: str | None = None,
        limit: int = 100,
        state: str | None = None,
        series_ticker: str | None = None,
        with_nested_markets: bool = False,
    ) -> list[Event]:
        """Return a paginated list of events as typed Event models."""
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        if state is not None:
            params["state"] = state
        if series_ticker is not None:
            params["series_ticker"] = series_ticker
        if with_nested_markets:
            params["with_nested_markets"] = "true"

        response = await self._client.get("/events", **params)
        response.raise_for_status()
        data = response.json()
        raw_events = data.get("events", [])
        return [_normalize_event(e) for e in raw_events]

    async def get_event(self, event_ticker: str) -> Event:
        """Return detail for a single event by ticker."""
        response = await self._client.get(f"/events/{event_ticker}")
        response.raise_for_status()
        data = response.json()
        raw = data.get("event", data)
        return _normalize_event(raw)

    async def list_series(
        self,
        cursor: str | None = None,
        limit: int = 200,
        category: str | None = None,
    ) -> SeriesListResponse:
        """List series, optionally filtered by category.

        The /series endpoint is the only V2 endpoint that supports category
        filtering natively. Use this to discover series tickers for a given
        category, then fetch events via series_ticker.
        """
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        if category is not None:
            params["category"] = category

        response = await self._client.get("/series", **params)
        response.raise_for_status()
        data = response.json()
        raw_series = data.get("series", [])
        return SeriesListResponse(
            series=[_normalize_series(s) for s in raw_series],
            cursor=data.get("cursor"),
        )
