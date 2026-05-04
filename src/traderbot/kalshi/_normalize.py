"""Internal normalization helpers shared across kalshi modules."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from traderbot.kalshi.models import Market, OrderBookLevel, Trade


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
    ts_val = raw.get("timestamp") if raw.get("timestamp") is not None else raw.get("created_time", 0)
    if isinstance(ts_val, int):
        ts_val = _unix_to_datetime(ts_val)

    return Trade(
        ticker=raw["ticker"],
        price=_to_cents(raw.get("yes_price", raw.get("price", 0))),
        quantity=int(raw.get("count", raw.get("quantity", 0))),
        side=raw.get("side", "yes"),
        timestamp=ts_val,
    )
