"""Market data service — list markets, get detail, orderbook, recent trades."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from traderbot.kalshi._normalize import (
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
        status: str | None = None,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
        min_close_ts: int | None = None,
        max_close_ts: int | None = None,
    ) -> MarketListResponse:
        """List markets with server-side filters.

        NOTE: The V2 /markets endpoint does NOT support category filtering.
        The `category` param was removed because the API silently ignores it.
        Use list_markets_by_category() for category-scoped market discovery.
        """
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        if status is not None:
            params["status"] = status
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
        return MarketListResponse(markets=markets, cursor=data.get("cursor"))

    async def list_markets_by_category(
        self,
        category: str,
        max_series: int = 10,
        max_events_per_series: int = 5,
    ) -> MarketListResponse:
        """List open markets for a given category via /series then /events.

        The V2 /events endpoint doesn't reliably filter by event state or
        market status, so we fetch events with nested markets and filter
        client-side for active/open markets only. This guarantees only
        tradeable markets in the requested category are returned.
        """
        from traderbot.kalshi._normalize import _map_category
        from traderbot.kalshi.models import CATEGORY_API_NAMES

        api_category = CATEGORY_API_NAMES.get(category.lower().replace(" ", "_"), category)
        target_category = api_category.lower()

        # Step 1: Fetch series for the category
        series_params: dict[str, Any] = {
            "limit": 100,
            "category": api_category,
        }
        series_response = await self._client.get("/series", **series_params)
        series_response.raise_for_status()
        series_data = series_response.json()
        raw_series_list = series_data.get("series", [])

        if not raw_series_list:
            return MarketListResponse(markets=[])

        # Step 2: Fetch events with markets for each series (parallel)
        series_tickers = [s.get("ticker") for s in raw_series_list if s.get("ticker")]
        series_tickers = series_tickers[:max_series]

        async def _fetch_series_events(series_ticker: str) -> list[dict]:
            params = {
                "limit": max_events_per_series,
                "with_nested_markets": "true",
                "series_ticker": series_ticker,
            }
            resp = await self._client.get("/events", **params)
            resp.raise_for_status()
            return resp.json().get("events", [])

        import asyncio

        tasks = [_fetch_series_events(t) for t in series_tickers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Step 3: Collect open/active markets from events, filtering client-side
        all_markets: list[Market] = []
        seen_tickers: set[str] = set()

        for result in results:
            if isinstance(result, Exception):
                continue
            for raw_event in result:
                event_category = raw_event.get("category")
                if event_category and event_category.lower() != target_category:
                    continue
                event_market_category = (
                    _map_category(event_category) if event_category else None
                )
                raw_markets = raw_event.get("markets") or []
                for raw_market in raw_markets:
                    market_status = raw_market.get("status", "").lower()
                    if market_status not in ("active", "open"):
                        continue
                    market = _normalize_market(raw_market)
                    if market.ticker not in seen_tickers:
                        seen_tickers.add(market.ticker)
                        market.category = event_category
                        market.market_category = event_market_category
                        all_markets.append(market)

        return MarketListResponse(markets=all_markets)

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

        # V2 orderbook uses orderbook_fp wrapper with yes_dollars/no_dollars keys.
        ob = data.get("orderbook_fp", data)
        yes_raw = ob.get("yes_dollars", ob.get("yes_bids", ob.get("yes", [])))
        no_raw = ob.get("no_dollars", ob.get("no_bids", ob.get("no", [])))

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
