"""Internal normalization helpers shared across kalshi modules."""

from datetime import UTC, datetime
from typing import Any

from traderbot.kalshi.models import Market, MarketCategory, OrderBookLevel, Trade


def _to_cents(value: str | int) -> int:
    """Convert a value to integer cents. Handles fixed-point dollar strings like '0.55' → 55."""
    if isinstance(value, str):
        return int(round(float(value) * 100))
    return int(value)


def _unix_to_datetime(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=UTC)


_CATEGORY_MAP: dict[str, MarketCategory] = {
    "economics": MarketCategory.ECONOMICS,
    "politics": MarketCategory.POLITICS,
    "weather": MarketCategory.WEATHER,
    "climate and weather": MarketCategory.WEATHER,
    "sports": MarketCategory.SPORTS,
    "science and technology": MarketCategory.SCIENCE_AND_TECHNOLOGY,
    "technology": MarketCategory.SCIENCE_AND_TECHNOLOGY,
    "science": MarketCategory.SCIENCE_AND_TECHNOLOGY,
    "crypto": MarketCategory.CRYPTO,
    "commodities": MarketCategory.COMMODITIES,
    "companies": MarketCategory.COMPANIES,
    "elections": MarketCategory.ELECTIONS,
    "entertainment": MarketCategory.ENTERTAINMENT,
    "financials": MarketCategory.FINANCIALS,
    "health": MarketCategory.HEALTH,
    "mentions": MarketCategory.MENTIONS,
    "social": MarketCategory.SOCIAL,
}


def _map_category(raw: str | None) -> MarketCategory | None:
    """Map a raw Kalshi API category string to MarketCategory enum."""
    if raw is None:
        return None
    return _CATEGORY_MAP.get(raw.lower())


def _normalize_market(raw: dict[str, Any]) -> Market:
    raw_close = raw.get("close_time")
    if isinstance(raw_close, int):
        close_time_val = _unix_to_datetime(raw_close)
    elif isinstance(raw_close, str):
        from datetime import datetime as dt
        close_time_val = dt.fromisoformat(raw_close.replace("Z", "+00:00"))
    else:
        close_time_val = None

    category_str = raw.get("category")

    return Market(
        ticker=raw["ticker"],
        question=raw.get("question", raw.get("title", "")),
        outcome_prices=raw.get("outcome_prices"),
        volume=int(raw["volume"]) if raw.get("volume") else 0,
        open_interest=int(raw["open_interest"]) if raw.get("open_interest") else 0,
        close_time=close_time_val,
        status=raw.get("state", raw.get("status", "open")),
        event_ticker=raw.get("event_ticker", ""),
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

    price = _to_cents(
        raw.get("price_dollars") or raw.get("price_fp") or 0
    )

    quantity = int(raw.get("count_fp") or 0)

    return Trade(
        ticker=raw["ticker"],
        price=price,
        quantity=quantity,
        side=raw.get("side", "yes"),
        timestamp=ts_val,
    )
