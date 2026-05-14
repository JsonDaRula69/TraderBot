"""Market data service — list markets, get detail, orderbook, recent trades."""

from __future__ import annotations

import asyncio
import logging
import time
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

_EVENT_CACHE_TTL = 300  # seconds — reuse event map for 5 minutes
_event_category_cache: dict[str, str] = {}
_event_cache_ts: float = 0.0


def _clear_event_cache() -> None:
    """Clear the event category cache (for testing)."""
    global _event_category_cache, _event_cache_ts  # noqa: PLW0603
    _event_category_cache = {}
    _event_cache_ts = 0.0


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
        limit: int = 500,
    ) -> MarketListResponse:
        """Fetch markets by category using event-first discovery with caching.

        The Kalshi V2 ``/events?category=`` and ``/markets?category=``
        filters are both broken (return unfiltered results).  Some events
        (notably daily weather) don't appear in ``/events`` at all.

        Strategy (minimizes API calls):
        1. Build event_ticker → category map from /events (cached for 5 min)
        2. Filter events by requested category
        3. Fetch markets only for matched events (not all 4000+)
        4. For remaining markets with no event match, look up individually
        """
        logger = logging.getLogger(__name__)
        logger.info("Fetching markets for category %s", category)

        event_category_map = await self._get_event_category_map()
        target_cat = category.lower().replace("_", " ")
        matched_events = [
            (ticker, cat) for ticker, cat in event_category_map.items()
            if target_cat in cat.lower()
        ]
        logger.info("Found %d events matching '%s' out of %d total", len(matched_events), category, len(event_category_map))

        all_markets: list[Market] = []
        semaphore = asyncio.Semaphore(3)

        async def _fetch_markets_for_event(evt_ticker: str) -> list[Market]:
            async with semaphore:
                await asyncio.sleep(0.15)
                try:
                    result = await self.list_markets(event_ticker=evt_ticker, limit=200)
                    return result.markets
                except Exception:
                    logger.debug("Failed to fetch markets for event=%s", evt_ticker)
                    return []

        if matched_events:
            results = await asyncio.gather(*[_fetch_markets_for_event(t) for t, _ in matched_events])
            event_ticker_to_cat = dict(matched_events)
            for market_list in results:
                all_markets.extend(market_list)
            for m in all_markets:
                if m.event_ticker in event_ticker_to_cat:
                    raw_cat = event_ticker_to_cat[m.event_ticker]
                    m.category = raw_cat
                    m.market_category = _map_category(raw_cat)

        uncategorized = {m.event_ticker for m in all_markets if m.event_ticker and m.category is None and m.event_ticker not in event_category_map}
        if uncategorized:
            await self._resolve_event_categories(uncategorized, event_category_map)
            for m in all_markets:
                if m.category is None and m.event_ticker in event_category_map:
                    raw_cat = event_category_map[m.event_ticker]
                    m.category = raw_cat
                    m.market_category = _map_category(raw_cat)

        filtered = [
            m for m in all_markets
            if m.category and (m.category.lower() == target_cat or target_cat in m.category.lower())
        ]

        logger.info("Category '%s': %d matched markets", category, len(filtered))
        return MarketListResponse(markets=filtered[:limit], cursor=None)

    async def _get_event_category_map(self) -> dict[str, str]:
        """Return cached event category map, refreshing if stale."""
        global _event_category_cache, _event_cache_ts  # noqa: PLW0603
        now = time.monotonic()
        if _event_category_cache and (now - _event_cache_ts) < _EVENT_CACHE_TTL:
            return _event_category_cache
        fresh = await self._build_event_category_map()
        _event_category_cache = fresh
        _event_cache_ts = now
        return fresh

    async def _build_event_category_map(self) -> dict[str, str]:
        """Fetch all open events and return event_ticker → category mapping."""
        logger = logging.getLogger(__name__)
        event_map: dict[str, str] = {}
        cursor: str | None = None

        for _ in range(20):
            try:
                params: dict[str, Any] = {"limit": 200, "status": "open"}
                if cursor:
                    params["cursor"] = cursor
                resp = await self._client.get("/events", **params)
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                logger.warning("Failed to fetch events page (collected %d so far)", len(event_map))
                break

            for evt in data.get("events", []):
                ticker = evt.get("ticker") or evt.get("event_ticker")
                cat = evt.get("category", "")
                if ticker and cat:
                    event_map[ticker] = cat

            cursor = data.get("cursor")
            if not cursor or not data.get("events"):
                break

        logger.info("Built event category map with %d events", len(event_map))
        return event_map

    async def _resolve_event_categories(
        self,
        tickers: set[str],
        event_category_map: dict[str, str],
    ) -> None:
        """Look up uncached event categories via /events/{ticker} with batching."""
        if not tickers:
            return

        logger = logging.getLogger(__name__)
        semaphore = asyncio.Semaphore(3)

        async def _lookup(ticker: str) -> tuple[str, str | None]:
            async with semaphore:
                await asyncio.sleep(0.15)
                try:
                    resp = await self._client.get(f"/events/{ticker}")
                    if resp.status_code != 200:
                        return ticker, None
                    data = resp.json()
                    ev = data.get("event", data)
                    return ticker, ev.get("category")
                except Exception:
                    logger.debug("Failed to look up event %s", ticker)
                    return ticker, None

        results = await asyncio.gather(*[_lookup(t) for t in tickers])
        for ticker, cat in results:
            if cat:
                event_category_map[ticker] = cat
