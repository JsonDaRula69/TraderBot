"""Historical data service — historical trades and settled markets."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from traderbot.kalshi._normalize import _normalize_market, _normalize_trade
from traderbot.kalshi.models import (
    MarketListResponse,
    TradeListResponse,
)

if TYPE_CHECKING:
    from datetime import datetime

    from traderbot.kalshi.client import KalshiClient


class HistoryService:
    """Fetches historical data from the Kalshi API via a KalshiClient."""

    def __init__(self, client: KalshiClient) -> None:
        self._client = client

    async def get_historical_trades(
        self,
        ticker: str,
        after: datetime | None = None,
        before: datetime | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> TradeListResponse:
        params: dict[str, Any] = {"limit": limit}
        if after is not None:
            params["min_ts"] = int(after.timestamp())
        if before is not None:
            params["max_ts"] = int(before.timestamp())
        if cursor is not None:
            params["cursor"] = cursor

        response = await self._client.get("/markets/trades", ticker=ticker, **params)
        response.raise_for_status()
        data = response.json()
        trades = [_normalize_trade(t) for t in data.get("trades", [])]
        return TradeListResponse(trades=trades, cursor=data.get("cursor"))

    async def get_settled_markets(
        self,
        cursor: str | None = None,
        limit: int = 100,
    ) -> MarketListResponse:
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor

        response = await self._client.get("/markets", **params)
        response.raise_for_status()
        data = response.json()
        all_markets = [_normalize_market(m) for m in data.get("markets", [])]
        settled = [m for m in all_markets if m.status == "settled"]
        return MarketListResponse(markets=settled, cursor=data.get("cursor"))

    async def get_market_series(self, ticker: str) -> Market:
        response = await self._client.get(f"/markets/{ticker}")
        response.raise_for_status()
        data = response.json()
        market_raw = data.get("market", data)
        return _normalize_market(market_raw)