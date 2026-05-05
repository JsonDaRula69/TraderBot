"""Internal normalization helpers shared across kalshi modules."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from traderbot.kalshi.models import Market, MarketCategory, OrderBookLevel, Trade


def _to_cents(value: str | int) -> int:
    return int(value)


def _unix_to_datetime(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=UTC)


_CATEGORY_MAP: dict[str, MarketCategory] = {
    "economics": MarketCategory.ECONOMICS,
    "politics": MarketCategory.POLITICS,
    "weather": MarketCategory.WEATHER,
    "sports": MarketCategory.SPORTS,
    "culture": MarketCategory.CULTURE,
    "technology": MarketCategory.TECHNOLOGY,
    "tech": MarketCategory.TECHNOLOGY,
    "science": MarketCategory.SCIENCE,
    "crypto": MarketCategory.CRYPTO,
}


def _map_category(raw: str | None) -> MarketCategory | None:
    """Map a raw Kalshi API category string to MarketCategory enum."""
    if raw is None:
        return None
    return _CATEGORY_MAP.get(raw.lower())


def _normalize_market(raw: dict[str, Any]) -> Market:
    close_time_val = raw.get("close_time")
    if isinstance(close_time_val, int):
        close_time_val = _unix_to_datetime(close_time_val)

    category_str = raw.get("category")

    return Market(
        ticker=raw["ticker"],
        question=raw["question"],
        outcome_prices=raw["outcome_prices"],
        volume=int(raw["volume"]),
        open_interest=int(raw["open_interest"]),
        close_time=close_time_val,
        status=raw.get("state", raw.get("status")),
        event_ticker=raw["event_ticker"],
        category=category_str,
        market_category=_map_category(category_str),
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
