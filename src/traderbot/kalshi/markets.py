"""Market data service — list markets, get detail, orderbook, recent trades."""

from __future__ import annotations

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
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        if category is not None:
            params["category"] = category
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
