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
        max_series: int = 50,
        max_events_per_series: int = 10,
    ) -> MarketListResponse:
        """List open markets for a given category via series→events→markets chain.

        The V2 /markets endpoint does not support category filtering. This method
        works around it by: (1) fetching series for the category via /series,
        (2) fetching open events for each series via /events,
        (3) fetching markets for each event via /markets.
        """
        from traderbot.kalshi.events import EventsService

        events_svc = EventsService(self._client)

        series_resp = await events_svc.list_series(limit=max_series, category=category)
        all_markets: list[Market] = []
        seen_tickers: set[str] = set()
        cursor = series_resp.cursor

        while True:
            for series in series_resp.series:
                events = await events_svc.get_events(
                    limit=max_events_per_series,
                    series_ticker=series.ticker,
                    state="open",
                )
                for event in events:
                    result = await self.list_markets(
                        event_ticker=event.event_ticker,
                        limit=100,
                    )
                    for m in result.markets:
                        if m.ticker not in seen_tickers:
                            seen_tickers.add(m.ticker)
                            m.category = event.category
                            m.market_category = event.market_category
                            all_markets.append(m)

            if not cursor:
                break
            series_resp = await events_svc.list_series(
                limit=max_series, category=category, cursor=cursor,
            )
            cursor = series_resp.cursor

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
