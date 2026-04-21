"""Historical data service — cutoffs, historical trades, settled markets."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from traderbot.kalshi._normalize import _normalize_market, _normalize_trade, _unix_to_datetime
from traderbot.kalshi.models import (
    CutoffTimestamps,
    Market,
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

    async def get_cutoffs(self, ticker: str) -> CutoffTimestamps:
        response = await self._client.get(f"/markets/{ticker}")
        response.raise_for_status()
        data = response.json()
        market_raw = data.get("market", data)

        def _parse_ts(key: str) -> datetime | None:
            val = market_raw.get(key)
            if val is None:
                return None
            return _unix_to_datetime(int(val))

        return CutoffTimestamps(
            market_settled_ts=_parse_ts("market_settled_ts"),
            trade_cutoff_ts=_parse_ts("trade_cutoff_ts"),
            order_cutoff_ts=_parse_ts("order_cutoff_ts"),
        )

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

        response = await self._client.get(f"/markets/{ticker}/trades", **params)
        response.raise_for_status()
        data = response.json()
        trades = [_normalize_trade(t) for t in data.get("trades", [])]
        return TradeListResponse(trades=trades, cursor=data.get("cursor"))

    async def get_settled_markets(
        self,
        cursor: str | None = None,
        limit: int = 100,
    ) -> MarketListResponse:
        params: dict[str, Any] = {"limit": limit, "state": "settled"}
        if cursor is not None:
            params["cursor"] = cursor

        response = await self._client.get("/markets", **params)
        response.raise_for_status()
        data = response.json()
        markets = [_normalize_market(m) for m in data.get("markets", [])]
        return MarketListResponse(markets=markets, cursor=data.get("cursor"))

    async def get_market_series(self, ticker: str) -> Market:
        response = await self._client.get(f"/markets/{ticker}")
        response.raise_for_status()
        data = response.json()
        market_raw = data.get("market", data)
        return _normalize_market(market_raw)
