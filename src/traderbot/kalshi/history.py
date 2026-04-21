"""Historical data service — cutoffs, historical trades, settled markets."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from traderbot.kalshi.models import (
    CutoffTimestamps,
    Market,
    MarketListResponse,
    Trade,
    TradeListResponse,
)

if TYPE_CHECKING:
    from traderbot.kalshi.client import KalshiClient


def _unix_to_datetime(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=UTC)


def _normalize_market(raw: dict[str, Any]) -> Market:
    close_time_val = raw.get("close_time")
    if isinstance(close_time_val, int):
        close_time_val = _unix_to_datetime(close_time_val)

    return Market(
        ticker=raw["ticker"],
        question=raw["question"],
        outcome_prices=raw["outcome_prices"],
        volume=int(raw["volume"]),
        open_interest=int(raw["open_interest"]),
        close_time=close_time_val,
        state=raw["state"],
        event_ticker=raw["event_ticker"],
        category=raw.get("category"),
        settlement_result=raw.get("settlement_result"),
    )


def _normalize_trade(raw: dict[str, Any]) -> Trade:
    ts_val = raw.get("timestamp") or raw.get("created_time", 0)
    if isinstance(ts_val, int):
        ts_val = _unix_to_datetime(ts_val)

    return Trade(
        ticker=raw["ticker"],
        price=int(raw.get("yes_price", raw.get("price", 0))),
        quantity=int(raw.get("count", raw.get("quantity", 0))),
        side=raw.get("side", "yes"),
        timestamp=ts_val,
    )


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
