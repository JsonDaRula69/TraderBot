"""Tests for the market_prices MCP tool (DD-016, WS-cache reads only)."""

from __future__ import annotations

from pathlib import Path

import pytest

from traderbot.kalshi.ws_cache import MarketCache
from traderbot.mcp import tools
from traderbot.state import reset, set_market_cache

# Matches the hardcoded Phase 0 weather mapping in resolver.py.
_WEATHER_TOKEN = "weather-test-token"


@pytest.fixture(autouse=True)
def _clean_state() -> None:
    reset()
    set_market_cache(None)
    yield
    reset()
    set_market_cache(None)


@pytest.mark.asyncio
async def test_market_prices_returns_cached_ticker(tmp_path: Path) -> None:
    cache = MarketCache(db_path=tmp_path / "t.db")
    cache.update_ticker(
        "KXWETHRM0700M",
        last_price=55.0,
        bid=54.0,
        ask=56.0,
        volume=1200.0,
        open_interest=300.0,
    )
    set_market_cache(cache)

    result = await tools.traderbot__market_prices(token=_WEATHER_TOKEN, ticker="KXWETHRM0700M")

    assert result["status"] == "ok"
    assert result["ticker"] == "KXWETHRM0700M"
    assert result["current_price"] == 55.0
    assert result["bid"] == 54.0
    assert result["ask"] == 56.0
    assert result["spread"] == 2.0
    assert result["volume"] == 1200.0
    assert result["mode"] == "paper"


@pytest.mark.asyncio
async def test_market_prices_uncached_ticker_returns_error(tmp_path: Path) -> None:
    cache = MarketCache(db_path=tmp_path / "t.db")
    set_market_cache(cache)

    result = await tools.traderbot__market_prices(token=_WEATHER_TOKEN, ticker="KXNOPE")

    assert result["status"] == "error"
    assert "no data available" in str(result["error"])


@pytest.mark.asyncio
async def test_market_prices_no_daemon_returns_error() -> None:
    result = await tools.traderbot__market_prices(token=_WEATHER_TOKEN, ticker="KXWETHRM0700M")

    assert result["status"] == "error"
    assert "daemon not running" in str(result["error"])


@pytest.mark.asyncio
async def test_market_prices_invalid_token_rejected(tmp_path: Path) -> None:
    cache = MarketCache(db_path=tmp_path / "t.db")
    set_market_cache(cache)

    result = await tools.traderbot__market_prices(token="bogus-token", ticker="KXWETHRM0700M")

    assert "Invalid or expired profile token" in str(result["error"])


@pytest.mark.asyncio
async def test_market_prices_missing_ticker_rejected(tmp_path: Path) -> None:
    cache = MarketCache(db_path=tmp_path / "t.db")
    set_market_cache(cache)

    result = await tools.traderbot__market_prices(token=_WEATHER_TOKEN)

    assert "Invalid input" in str(result["error"])
