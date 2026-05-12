"""Internal normalization helpers for Kalshi V2 API responses."""

from datetime import UTC, datetime
from typing import Any

from traderbot.kalshi.models import (
    Fill,
    Market,
    MarketCategory,
    OrderBookLevel,
    Position,
    Trade,
)


def _to_cents(value: str | int) -> int:
    """Convert a FixedPointDollars string to integer cents. E.g. '0.55' → 55."""
    if isinstance(value, str):
        return int(round(float(value) * 100))
    return int(value)


def _to_count(value: str | int | float) -> int:
    """Convert a FixedPointCount string to integer. E.g. '1516.00' → 1516.

    FixedPointCount represents decimal contract quantities, NOT dollar amounts.
    """
    if isinstance(value, str):
        return int(round(float(value)))
    return int(value)


def _parse_datetime(value: str | int | None) -> datetime | None:
    """Parse a V2 API datetime field (ISO 8601 string or Unix timestamp)."""
    if value is None:
        return None
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(value, int):
        return datetime.fromtimestamp(value, tz=UTC)
    return None


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
    close_time_val = _parse_datetime(raw.get("close_time"))
    category_str = raw.get("category")

    volume_val = _to_count(raw.get("volume_fp") or raw.get("volume") or 0)
    oi_val = _to_count(raw.get("open_interest_fp") or raw.get("open_interest") or 0)

    # V2 price fields: last_price_dollars, yes/no bid/ask dollars
    last_price = _to_cents(raw.get("last_price_dollars") or 0)
    yes_bid = _to_cents(raw.get("yes_bid_dollars") or 0)
    yes_ask = _to_cents(raw.get("yes_ask_dollars") or 0)
    no_bid = _to_cents(raw.get("no_bid_dollars") or 0)
    no_ask = _to_cents(raw.get("no_ask_dollars") or 0)

    return Market(
        ticker=raw["ticker"],
        question=raw.get("title") or raw.get("question") or "",
        volume=volume_val,
        open_interest=oi_val,
        close_time=close_time_val,
        status=raw.get("status", "open"),
        event_ticker=raw.get("event_ticker", ""),
        last_price_cents=last_price,
        yes_bid_cents=yes_bid,
        yes_ask_cents=yes_ask,
        no_bid_cents=no_bid,
        no_ask_cents=no_ask,
        category=category_str,
        market_category=_map_category(category_str),
        settlement_result=raw.get("settlement_result"),
    )


def _normalize_position(raw: dict[str, Any]) -> Position:
    quantity = _to_count(raw.get("quantity_fp") or raw.get("quantity") or 0)
    avg_price = _to_cents(raw.get("avg_price_fp") or raw.get("avg_price") or 0)

    settlement_result = raw.get("settlement_result")
    if isinstance(settlement_result, str):
        settlement_result = settlement_result.lower() in ("yes", "true", "1")

    return Position(
        ticker=raw.get("ticker", ""),
        quantity=quantity,
        avg_price=avg_price,
        settlement_result=settlement_result,
    )


def _normalize_fill(raw: dict[str, Any]) -> Fill:
    price_raw = raw.get("yes_price_dollars") or raw.get("no_price_dollars") or 0
    price = _to_cents(price_raw)
    quantity = _to_count(raw.get("count_fp") or raw.get("count") or 0)
    ts = _parse_datetime(raw.get("created_time")) or _parse_datetime(raw.get("timestamp")) or datetime.fromtimestamp(0, tz=UTC)
    side = raw.get("side") or raw.get("outcome_side") or "yes"

    return Fill(
        order_id=str(raw.get("order_id", "")),
        ticker=raw.get("ticker", ""),
        side=side,
        price=price,
        quantity=quantity,
        timestamp=ts,
    )


def _normalize_orderbook_level(raw: list[Any]) -> OrderBookLevel:
    return OrderBookLevel(price=_to_cents(raw[0]), size=_to_count(raw[1]))


def _normalize_trade(raw: dict[str, Any]) -> Trade:
    ts = _parse_datetime(raw.get("timestamp") or raw.get("created_time")) or datetime.fromtimestamp(0, tz=UTC)

    price_raw = raw.get("price_fp") or raw.get("price_dollars") or 0
    if not price_raw:
        price_raw = raw.get("yes_price_dollars") or 0
    price = _to_cents(price_raw)

    quantity = _to_count(raw.get("count_fp") or raw.get("count") or 0)
    side = raw.get("taker_side") or raw.get("side") or raw.get("taker_outcome_side") or "yes"

    return Trade(
        ticker=raw["ticker"],
        price=price,
        quantity=quantity,
        side=side,
        timestamp=ts,
    )

