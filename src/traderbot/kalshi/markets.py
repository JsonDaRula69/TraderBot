"""Market data service — list markets, get detail, orderbook, recent trades."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from traderbot.kalshi.models import (
    Market,
    MarketListResponse,
    OrderBook,
    OrderBookLevel,
    Trade,
    TradeListResponse,
)

if TYPE_CHECKING:
    from traderbot.kalshi.client import KalshiClient


def _to_cents(value: str | int) -> int:
    return int(value)


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


def _normalize_orderbook_level(raw: list[Any]) -> OrderBookLevel:
    return OrderBookLevel(price=_to_cents(raw[0]), size=int(raw[1]))


def _normalize_trade(raw: dict[str, Any]) -> Trade:
    ts_val = raw.get("timestamp") or raw.get("created_time", 0)
    if isinstance(ts_val, int):
        ts_val = _unix_to_datetime(ts_val)

    return Trade(
        ticker=raw["ticker"],
        price=_to_cents(raw.get("yes_price", raw.get("price", 0))),
        quantity=int(raw.get("count", raw.get("quantity", 0))),
        side=raw.get("side", "yes"),
        timestamp=ts_val,
    )


class MarketService:
    """Fetches market data from the Kalshi API via a KalshiClient."""

    def __init__(self, client: KalshiClient) -> None:
        self._client = client

    async def list_markets(
        self,
        cursor: str | None = None,
        limit: int = 100,
        category: str | None = None,
        state: str | None = None,
    ) -> MarketListResponse:
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        if category is not None:
            params["category"] = category
        if state is not None:
            params["state"] = state

        response = await self._client.get("/markets", **params)
        response.raise_for_status()
        data = response.json()
        markets = [_normalize_market(m) for m in data.get("markets", [])]
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

        yes_bids = [_normalize_orderbook_level(level) for level in data.get("yes_bids", data.get("yes", []))]
        no_bids = [_normalize_orderbook_level(level) for level in data.get("no_bids", data.get("no", []))]

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

        response = await self._client.get(f"/markets/{ticker}/trades", **params)
        response.raise_for_status()
        data = response.json()
        trades = [_normalize_trade(t) for t in data.get("trades", [])]
        return TradeListResponse(trades=trades, cursor=data.get("cursor"))
