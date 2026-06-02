"""Read unified market data cache maintained by ws_daemon.

WS daemon writes to ``event_category_cache.json`` with:
- ``map``: ticker → category mapping (from market_lifecycle_v2)
- ``tickers``: yes_bid, no_bid, volume, open_interest (from ticker channel)

CLI commands read from cache first, fall back to REST.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from traderbot.paths import get_data_dir

CACHE_PATH = get_data_dir() / "event_category_cache.json"

_TICKER_CACHE_TTL = 30  # seconds — ticker data is real-time


def get_ticker_price(ticker: str) -> dict | None:
    """Return cached price data for a ticker, or None if stale/missing."""
    if not CACHE_PATH.exists():
        return None
    try:
        data = json.loads(CACHE_PATH.read_text())
        tickers = data.get("tickers", {})
        t = tickers.get(ticker)
        if t is None:
            return None
        # Check freshness
        updated = t.get("updated_at", 0)
        if time.time() - updated > _TICKER_CACHE_TTL:
            return None
        return t
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def get_ticker_prices(tickers: list[str]) -> dict[str, dict]:
    """Return cached prices for multiple tickers. Missing/stale entries omitted."""
    result: dict[str, dict] = {}
    for t in tickers:
        v = get_ticker_price(t)
        if v:
            result[t] = v
    return result


def get_cache_stats() -> dict:
    """Return stats about the current cache contents."""
    if not CACHE_PATH.exists():
        return {"events": 0, "tickers": 0, "age_seconds": -1}
    try:
        data = json.loads(CACHE_PATH.read_text())
        return {
            "events": len(data.get("map", {})),
            "tickers": len(data.get("tickers", {})),
            "age_seconds": int(time.time() - data.get("ts", 0)),
        }
    except (json.JSONDecodeError, OSError):
        return {"events": 0, "tickers": 0, "age_seconds": -1}
