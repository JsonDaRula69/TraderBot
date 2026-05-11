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
        """List open markets for a given category via /events with nested markets.

        The V2 /markets endpoint does not support category filtering, but /events
        accepts category and with_nested_markets params that return markets inline.
        This reduces 60+ sequential API calls to 1-2 paginated requests.
        """
        from traderbot.kalshi._normalize import _map_category
        from traderbot.kalshi.models import CATEGORY_API_NAMES

        api_category = CATEGORY_API_NAMES.get(category.lower().replace(" ", "_"), category)
        all_markets: list[Market] = []
        seen_tickers: set[str] = set()

        params: dict[str, Any] = {
            "limit": 200,
            "category": api_category,
            "state": "open",
            "with_nested_markets": "true",
        }
        cursor: str | None = None

        for _ in range(10):
            if cursor is not None:
                params["cursor"] = cursor
            response = await self._client.get("/events", **params)
            response.raise_for_status()
            data = response.json()
            raw_events = data.get("events", [])

            for raw_event in raw_events:
                event_category = raw_event.get("category")
                event_market_category = _map_category(event_category) if event_category else None
                raw_markets = raw_event.get("markets") or []
                for raw_market in raw_markets:
                    market = _normalize_market(raw_market)
                    if market.ticker not in seen_tickers:
                        seen_tickers.add(market.ticker)
                        market.category = event_category
                        market.market_category = event_market_category
                        all_markets.append(market)

            cursor = data.get("cursor")
            if not cursor:
                break

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

        yes_bids = [
            _normalize_orderbook_level(level) for level in data.get("yes_bids", data.get("yes", []))
        ]
        no_bids = [
            _normalize_orderbook_level(level) for level in data.get("no_bids", data.get("no", []))
        ]

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
