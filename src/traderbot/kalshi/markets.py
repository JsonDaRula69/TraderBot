"""Market data service — list markets, get detail, orderbook, recent trades."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from traderbot.kalshi._normalize import (
    _map_category,
    _normalize_market,
    _normalize_orderbook_level,
    _normalize_trade,
)
from traderbot.kalshi.models import (
    Market,
    MarketListResponse,
    OrderBook,
    TradeListResponse,
)

if TYPE_CHECKING:
    from traderbot.kalshi.client import KalshiClient


class MarketService:
    """Fetches market data from the Kalshi API via a KalshiClient."""

    def __init__(self, client: KalshiClient) -> None:
        self._client = client

    async def list_markets(
        self,
        cursor: str | None = None,
        limit: int = 100,
        category: str | None = None,
        status: str | None = None,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
        min_close_ts: int | None = None,
        max_close_ts: int | None = None,
    ) -> MarketListResponse:
        params: dict[str, Any] = {"limit": limit, "status": status or "open"}
        if cursor is not None:
            params["cursor"] = cursor
        if category is not None:
            params["category"] = category
        if event_ticker is not None:
            params["event_ticker"] = event_ticker
        if series_ticker is not None:
            params["series_ticker"] = series_ticker
        if min_close_ts is not None:
            params["min_close_ts"] = min_close_ts
        if max_close_ts is not None:
            params["max_close_ts"] = max_close_ts

        response = await self._client.get("/markets", **params)
        response.raise_for_status()
        data = response.json()
        markets = [_normalize_market(m) for m in data.get("markets", [])]

        # V2 API returns category on events, not markets. Enrich from events.
        if markets:
            event_tickers = {m.event_ticker for m in markets if m.event_ticker}
            if event_tickers:
                event_categories = await self._fetch_event_categories(event_tickers)
                for m in markets:
                    if m.event_ticker in event_categories:
                        raw_cat = event_categories[m.event_ticker]
                        if m.category is None:
                            m.category = raw_cat
                        if m.market_category is None:
                            m.market_category = _map_category(raw_cat)

        return MarketListResponse(markets=markets, cursor=data.get("cursor"))

    async def get_market(self, ticker: str) -> Market:
        response = await self._client.get(f"/markets/{ticker}")
        response.raise_for_status()
        data = response.json()
        market_raw = data.get("market", data)
        return _normalize_market(market_raw)

    async def get_orderbook(self, ticker: str, depth: int = 10) -> OrderBook:
        response = await self._client.get(f"/markets/{ticker}/orderbook", depth=depth)
        response.raise_for_status()
        data = response.json()

        ob_data = data.get("orderbook_fp", data)

        yes_raw = ob_data.get("yes_bids", ob_data.get("yes_dollars", ob_data.get("yes", [])))
        no_raw = ob_data.get("no_bids", ob_data.get("no_dollars", ob_data.get("no", [])))

        yes_bids = [_normalize_orderbook_level(level) for level in yes_raw]
        no_bids = [_normalize_orderbook_level(level) for level in no_raw]

        return OrderBook(yes_bids=yes_bids, no_bids=no_bids)

    async def get_recent_trades(
        self,
        ticker: str,
        limit: int = 50,
        cursor: str | None = None,
    ) -> TradeListResponse:
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor

        response = await self._client.get("/markets/trades", ticker=ticker, **params)
        response.raise_for_status()
        data = response.json()
        trades = [_normalize_trade(t) for t in data.get("trades", [])]
        return TradeListResponse(trades=trades, cursor=data.get("cursor"))

    async def _fetch_event_categories(self, event_tickers: set[str]) -> dict[str, str]:
        categories: dict[str, str] = {}
        for ticker in event_tickers:
            try:
                resp = await self._client.get(f"/events/{ticker}")
                if resp.status_code == 200:
                    data = resp.json()
                    ev = data.get("event", data)
                    categories[ticker] = ev.get("category", "")
            except Exception:
                continue
        return categories

    async def list_all_markets(
        self,
        *,
        limit: int = 200,
        max_pages: int = 5,
        category: str | None = None,
        status: str | None = None,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
        min_close_ts: int | None = None,
        max_close_ts: int | None = None,
    ) -> MarketListResponse:
        """Fetch all markets by following cursor-based pagination.

        Calls ``list_markets()`` for each page and merges results.
        Stops when the cursor is exhausted, *max_pages* is reached,
        or enough markets have been collected to satisfy *limit*.

        Args:
            limit: Target number of markets to collect (default 200).
            max_pages: Safety ceiling — stop after this many pages (default 5).
            category: Filter by Kalshi category slug.
            status: Filter by market status (default ``"open"`` via list_markets).
            event_ticker: Filter by event ticker.
            series_ticker: Filter by series ticker.
            min_close_ts: Earliest close timestamp filter.
            max_close_ts: Latest close timestamp filter.

        Returns:
            ``MarketListResponse`` with all collected markets and ``cursor=None``.
            If a mid-page call fails, returns whatever was collected so far.
        """
        logger = logging.getLogger(__name__)
        all_markets: list[Market] = []
        cursor: str | None = None

        for page in range(max_pages):
            page_limit = min(200, limit - len(all_markets)) if limit else 200
            if page_limit <= 0:
                break
            try:
                result = await self.list_markets(
                    cursor=cursor,
                    limit=page_limit,
                    category=category,
                    status=status,
                    event_ticker=event_ticker,
                    series_ticker=series_ticker,
                    min_close_ts=min_close_ts,
                    max_close_ts=max_close_ts,
                )
            except Exception:
                logger.warning(
                    "list_all_markets: page %d failed (cursor=%s), returning %d markets collected so far",
                    page + 1,
                    cursor,
                    len(all_markets),
                )
                break

            all_markets.extend(result.markets)
            cursor = result.cursor

            if not cursor:
                break
            if limit and len(all_markets) >= limit:
                break

        if limit and len(all_markets) > limit:
            all_markets = all_markets[:limit]

        return MarketListResponse(markets=all_markets, cursor=None)

    async def list_markets_by_category(
        self,
        category: str,
        limit: int = 100,
    ) -> MarketListResponse:
        """Fetch markets by category via the events endpoint.

        The Kalshi V2 ``/events?category=`` and ``/markets?category=``
        filters are both broken (return unfiltered results).  This method
        works around it by:
        1. Fetching all open events via ``/events?status=open`` (paginated)
        2. Filtering client-side by matching ``category`` case-insensitively
        3. Fetching markets for matched events in parallel (asyncio.gather)
        4. Enriching category from the known event data directly
        """
        logger = logging.getLogger(__name__)

        all_events: list[dict] = []
        cursor: str | None = None
        for _ in range(10):
            try:
                params: dict[str, Any] = {"limit": 100, "status": "open"}
                if cursor:
                    params["cursor"] = cursor
                events_resp = await self._client.get("/events", **params)
                events_resp.raise_for_status()
                events_data = events_resp.json()
            except Exception:
                logger.warning("Failed to fetch events page for category=%s (collected %d so far)", category, len(all_events))
                break

            batch = events_data.get("events", [])
            all_events.extend(batch)
            cursor = events_data.get("cursor")
            if not cursor or not batch:
                break

        target_cat = category.lower().replace("_", " ")
        matched_events = [
            e for e in all_events
            if "event_ticker" in e and (e.get("category", "") == category or target_cat in e.get("category", "").lower())
        ]

        if not matched_events:
            return MarketListResponse(markets=[], cursor=None)

        # Build category lookup from event data we already have
        event_category_map: dict[str, str] = {
            e["event_ticker"]: e.get("category", "") for e in matched_events if e.get("category")
        }

        async def _fetch_event_markets(evt_ticker: str) -> list[Market]:
            try:
                result = await self.list_markets(event_ticker=evt_ticker, limit=200)
                return result.markets
            except Exception:
                logger.warning("Failed to fetch markets for event=%s, skipping", evt_ticker)
                return []

        batch_size = 3
        all_markets: list[Market] = []
        for i in range(0, len(matched_events), batch_size):
            batch = matched_events[i:i + batch_size]
            results = await asyncio.gather(
                *[_fetch_event_markets(e["event_ticker"]) for e in batch]
            )
            for market_list in results:
                all_markets.extend(market_list)
            if i + batch_size < len(matched_events):
                await asyncio.sleep(0.5)

        # Enrich category from event data we already fetched (no extra API calls)
        for m in all_markets:
            if m.event_ticker in event_category_map:
                raw_cat = event_category_map[m.event_ticker]
                if m.category is None:
                    m.category = raw_cat
                if m.market_category is None:
                    m.market_category = _map_category(raw_cat)

        markets = all_markets[:limit]
        return MarketListResponse(markets=markets, cursor=None)
