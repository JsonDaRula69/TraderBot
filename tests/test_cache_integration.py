"""Live Kalshi cache integration tests.

Verifies MarketDataCache correctly stores, retrieves, and expires
real market data snapshots.
"""

from __future__ import annotations

import asyncio

import pytest

from traderbot.kalshi.client import KalshiClient
from traderbot.kalshi.provider import MarketSnapshot, ProdDataProvider

pytestmark = pytest.mark.integration


async def _fetch_open_market(client: KalshiClient, provider: ProdDataProvider) -> tuple[str, MarketSnapshot]:
    """Helper: find an open market and fetch its MarketSnapshot."""
    response = await client.get("/markets", limit=5, status="open")
    assert response.status_code == 200
    ticker = response.json()["markets"][0]["ticker"]
    snapshot = await provider.get_market(ticker)
    return ticker, snapshot


@pytest.mark.live
async def test_cache_store_and_retrieve(
    live_client: KalshiClient,
    live_provider: ProdDataProvider,
    live_cache,
) -> None:
    """Cache should store a real snapshot and return it on subsequent get."""
    from traderbot.kalshi.cache import MarketDataCache as _Cache

    cache = live_cache
    ticker, snapshot = await _fetch_open_market(live_client, live_provider)

    await cache.set_market(ticker, snapshot)

    cached = await cache.get_market(ticker)
    assert cached is not None, f"Cache miss for {ticker!r} after explicit set"
    assert cached.ticker == ticker, f"Cached ticker mismatch: {cached.ticker!r} != {ticker!r}"
    assert cached.open_interest_cents == snapshot.open_interest_cents, (
        f"Cached open_interest_cents mismatch: {cached.open_interest_cents} != {snapshot.open_interest_cents}"
    )


@pytest.mark.live
async def test_cache_ttl_expiry(
    live_client: KalshiClient,
    live_provider: ProdDataProvider,
    live_cache,
) -> None:
    """Cache entries should expire after TTL and return None."""
    from unittest.mock import patch

    ticker, snapshot = await _fetch_open_market(live_client, live_provider)

    with patch("traderbot.kalshi.cache.MARKET_TTL", 0.01):
        await live_cache.set_market(ticker, snapshot)

    await asyncio.sleep(0.05)

    cached = await live_cache.get_market(ticker)
    assert cached is None, f"Cache entry for {ticker!r} should have expired"