"""Internal normalization helpers shared across kalshi modules.

Ported from ``.trash/src/traderbot/kalshi/_normalize.py`` (retired v1
client). The category map is adapted to the v2 ``MarketCategory`` enum,
which uses ``"financial"`` / ``"world"`` / ``"other"`` instead of the v1
``"financials"`` / ``"mentions"`` / ``"social"`` values.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from math import isfinite
from typing import Any, Final

from traderbot.kalshi.models import Market, MarketCategory, OrderBookLevel, Trade

logger = logging.getLogger(__name__)


def _to_cents(value: str | float) -> int:
    """Convert a value to integer cents.

    Handles fixed-point dollar strings like '0.55' → 55 and floats like 0.65 → 65.
    """
    if isinstance(value, str):
        return round(float(value) * 100)
    if isinstance(value, float):
        return round(value * 100)
    return int(value)


def _unix_to_datetime(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=UTC)


_CATEGORY_MAP: dict[str, MarketCategory] = {
    "economics": MarketCategory.ECONOMICS,
    "politics": MarketCategory.POLITICS,
    "weather": MarketCategory.WEATHER,
    "climate and weather": MarketCategory.WEATHER,
    "sports": MarketCategory.SPORTS,
    "crypto": MarketCategory.CRYPTO,
    "entertainment": MarketCategory.ENTERTAINMENT,
    "financials": MarketCategory.FINANCIAL,
    "financial": MarketCategory.FINANCIAL,
    "world": MarketCategory.WORLD,
    "other": MarketCategory.OTHER,
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
    elif isinstance(close_time_val, str):
        try:
            close_time_val = datetime.fromisoformat(close_time_val.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            close_time_val = _unix_to_datetime(0)
    else:
        close_time_val = _unix_to_datetime(0)

    category_str = raw.get("category")

    # V2 API uses `title` instead of `question`
    # Daily/resolution markets use `no_sub_title`/`yes_sub_title` instead
    question = raw.get("question") or raw.get("title", "")
    if not question:
        question = raw.get("no_sub_title") or raw.get("yes_sub_title", "")

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

    # V2 API uses "active"/"initialized" for open markets; map to "open" for Market model
    # V2 API uses "finalized" for settled markets; map to "settled"
    raw_status = raw.get("state", raw.get("status", "closed"))
    if raw_status in ("active", "initialized"):
        status_val = "open"
    elif raw_status == "finalized":
        status_val = "settled"
    else:
        status_val = raw_status

    logger.debug(
        "Normalized market: %s -> status=%s ticker=%s",
        raw.get("ticker"),
        status_val,
        raw.get("ticker"),
    )

    strike_type_raw = raw.get("strike_type")
    strike_type_val: str | None = None
    if isinstance(strike_type_raw, str):
        st_lower = strike_type_raw.lower()
        if st_lower in ("less", "greater", "between"):
            strike_type_val = st_lower
        elif "less" in st_lower or "below" in st_lower or "under" in st_lower:
            strike_type_val = "less"
        elif "greater" in st_lower or "above" in st_lower or "over" in st_lower:
            strike_type_val = "greater"

    return Market(
        ticker=raw["ticker"],
        question=question,
        outcome_prices=outcome_prices,
        volume=volume,
        open_interest=open_interest,
        close_time=close_time_val,
        status=status_val,
        event_ticker=raw["event_ticker"],
        series_ticker=raw.get("series_ticker"),
        category=category_str,
        market_category=_map_category(category_str),
        settlement_result=raw.get("settlement_result"),
        strike_type=strike_type_val,
    )


def _normalize_orderbook_level(raw: list[Any]) -> OrderBookLevel:
    return OrderBookLevel(price=_to_cents(raw[0]), size=int(float(raw[1])))


def _normalize_trade(raw: dict[str, Any]) -> Trade:
    ts_val = (
        raw.get("timestamp") if raw.get("timestamp") is not None else raw.get("created_time", 0)
    )
    if isinstance(ts_val, int):
        ts_val = _unix_to_datetime(ts_val)
    else:
        ts_val = _unix_to_datetime(0)

    price = _to_cents(raw.get("price_dollars") or raw.get("price_fp") or 0)

    quantity = int(raw.get("count_fp") or 0)

    return Trade(
        ticker=raw["ticker"],
        price=price,
        quantity=quantity,
        side=raw.get("side", "yes"),
        timestamp=ts_val,
    )


# Issue #251 slice 1: the WS ``ticker`` channel still sends the retired
# pre-v2 field names into ``daemon.apply_ws_message``, so every frame parsed
# to zeros. Map the cached price fields to their v2/legacy source names here,
# next to the REST normalization that owns the same knowledge.
_WS_TICKER_FIELDS: Final[tuple[tuple[str, str, str], ...]] = (
    # (cache field, v2 name, legacy name)
    ("last_price", "last_price_dollars", "last_price"),
    ("bid", "yes_bid_dollars", "bid"),
    ("ask", "yes_ask_dollars", "ask"),
    ("volume", "volume_fp", "volume"),
    ("open_interest", "open_interest_fp", "open_interest"),
)

#: Cached fields that are *prices* in the v2 payload (fixed-point dollars).
_WS_TICKER_PRICE_FIELDS: Final[frozenset[str]] = frozenset({"last_price", "bid", "ask"})


def _dollars_to_cents(value: object) -> float | None:
    """Parse a v2 fixed-point dollar value (``"0.55"`` or 0.55) into cents.

    Mirrors :func:`_to_cents` but tolerates absent or non-numeric input by
    returning ``None``: a malformed WebSocket field must not throw away the
    whole ticker frame.
    """
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        cents = float(_to_cents(value))
    except (ValueError, OverflowError, TypeError):
        return None
    return cents if isfinite(cents) else None


def _fp_to_float(value: object) -> float | None:
    """Parse a count/cent field (``volume_fp``-style or legacy) into a float.

    Counts are used raw by the REST path (``int(float(...))``); missing or
    non-numeric input returns ``None`` instead of a coerced zero.
    """
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    parsed = float(value)
    return parsed if isfinite(parsed) else None


def normalize_ticker_event(raw: dict[str, Any]) -> dict[str, float | None]:
    """Extract the cached price fields from one WS ``ticker`` event.

    Kalshi's v2 ticker payload names prices as fixed-point dollar strings
    (``last_price_dollars``, ``yes_bid_dollars``, ``yes_ask_dollars``) and
    counts as ``*_fp`` fields (``volume_fp``, ``open_interest_fp``); the
    retired pre-v2 channel used cent-integer names (``last_price``, ``bid``,
    ``ask``, ``volume``, ``open_interest``). Both shapes are accepted with
    the v2 name taking precedence and the legacy name as fallback, mirroring
    the REST path in :func:`_normalize_market` and :func:`_normalize_trade`.

    Dollar prices are converted to cents (``"0.55"`` -> ``55.0``) — the scale
    the cache and the MCP surface already use (:func:`_to_cents`); counts are
    used raw. A missing or non-numeric field is returned as ``None`` so the
    caller leaves the cached value untouched instead of writing a zero.
    """
    fields: dict[str, float | None] = {}
    for field, v2_name, legacy_name in _WS_TICKER_FIELDS:
        parse = _dollars_to_cents if field in _WS_TICKER_PRICE_FIELDS else _fp_to_float
        v2_value = parse(raw.get(v2_name))
        fields[field] = v2_value if v2_value is not None else _fp_to_float(raw.get(legacy_name))
    return fields
