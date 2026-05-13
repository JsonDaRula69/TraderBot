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
    close_time_val = raw.get("close_time")
    if isinstance(close_time_val, int):
        close_time_val = _unix_to_datetime(close_time_val)

    category_str = raw.get("category")

    # V2 API uses `title` instead of `question`
    question = raw.get("question") or raw.get("title", "")

    # V2 API uses `_fp` suffix for fixed-point string fields
    volume = int(float(raw.get("volume_fp", raw.get("volume", 0))))
    open_interest = int(float(raw.get("open_interest_fp", raw.get("open_interest", 0))))

    # V2 API uses `yes_ask_dollars`/`no_ask_dollars` instead of `outcome_prices`
    outcome_prices = raw.get("outcome_prices")
    if outcome_prices is None:
        yes_ask = raw.get("yes_ask_dollars")
        no_ask = raw.get("no_ask_dollars")
        if yes_ask is not None and no_ask is not None:
            outcome_prices = [yes_ask, no_ask]
        else:
            outcome_prices = ["0.50", "0.50"]

    return Market(
        ticker=raw["ticker"],
        question=question,
        outcome_prices=outcome_prices,
        volume=volume,
        open_interest=open_interest,
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
