"""Read unified market data cache maintained by ws_daemon.

WS daemon writes to ``event_category_cache.json`` with:
- ``map``: ticker → category mapping (from market_lifecycle_v2)
- ``tickers``: yes_bid, no_bid, volume, open_interest (from ticker channel)
- ``orderbooks``: per-ticker orderbook depth (from orderbook_delta)
- ``fills``: recent fill notifications (from fill channel)
- ``orders``: order status updates (from user_orders channel)
- ``positions``: position changes (from market_positions channel)

CLI commands read from cache first, fall back to REST.
"""

from __future__ import annotations

import json
import time

from traderbot.paths import get_data_dir

CACHE_PATH = get_data_dir() / "event_category_cache.json"

_TICKER_CACHE_TTL = 30  # seconds — ticker data is real-time
_ORDERBOOK_CACHE_TTL = 10  # seconds — orderbook data updates frequently


def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def get_ticker_price(ticker: str) -> dict | None:
    """Return cached price data for a ticker, or None if stale/missing."""
    data = _load_cache()
    tickers = data.get("tickers", {})
    t = tickers.get(ticker)
    if t is None:
        return None
    updated = t.get("updated_at", 0)
    if time.time() - updated > _TICKER_CACHE_TTL:
        return None
    return t


def get_ticker_prices(tickers: list[str]) -> dict[str, dict]:
    """Return cached prices for multiple tickers. Missing/stale entries omitted."""
    result: dict[str, dict] = {}
    for t in tickers:
        v = get_ticker_price(t)
        if v:
            result[t] = v
    return result


def get_orderbook(ticker: str) -> list[dict] | None:
    """Return cached orderbook entries for a ticker, or None if stale/missing.

    Returns a list of price-level dicts with keys: price, yes_bid_size,
    no_bid_size, side (\"buy\" or \"sell\"), or whichever shape the
    orderbook_delta channel provides.
    """
    data = _load_cache()
    obs = data.get("orderbooks", {})
    ob = obs.get(ticker)
    if ob is None:
        return None
    updated = ob.get("updated_at", 0)
    if time.time() - updated > _ORDERBOOK_CACHE_TTL:
        return None
    return ob.get("entries", [])


def get_fills(limit: int = 50) -> list[dict]:
    """Return recent fills from WS cache (most recent first)."""
    data = _load_cache()
    fills = data.get("fills", [])
    return fills[:limit]


def get_orders(limit: int = 50) -> list[dict]:
    """Return recent order status updates from WS cache."""
    data = _load_cache()
    orders = data.get("orders", [])
    return orders[:limit]


def get_positions() -> dict[str, dict]:
    """Return current positions from WS cache, keyed by ticker."""
    data = _load_cache()
    return data.get("positions", {})


def get_event_category(ticker: str) -> str | None:
    """Return cached category for a market ticker, or None if unknown."""
    data = _load_cache()
    mapping = data.get("map", {})
    return mapping.get(ticker)


def get_cache_stats() -> dict:
    """Return stats about the current cache contents."""
    data = _load_cache()
    return {
        "events": len(data.get("map", {})),
        "tickers": len(data.get("tickers", {})),
        "orderbooks": len(data.get("orderbooks", {})),
        "fills": len(data.get("fills", [])),
        "orders": len(data.get("orders", [])),
        "positions": len(data.get("positions", {})),
        "age_seconds": int(time.time() - data.get("ts", 0)) if data.get("ts") else -1,
    }
