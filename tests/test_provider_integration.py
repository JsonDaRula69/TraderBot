"""Live Kalshi market data provider integration tests.

Verifies real API calls through ProdDataProvider return properly
structured snapshots with cents-normalized monetary values.
"""

from __future__ import annotations

import pytest

from traderbot.kalshi.client import KalshiClient
from traderbot.kalshi.provider import (
    MarketSnapshot,
    OrderBookLevelSnapshot,
    OrderBookSnapshot,
    ProdDataProvider,
)

pytestmark = pytest.mark.integration


async def _find_open_market(client: KalshiClient) -> str:
    """Fetch an open market ticker from the live API."""
    response = await client.get("/markets", limit=5, status="open")
    assert response.status_code == 200, f"Failed to list markets: {response.status_code}"
    markets = response.json().get("markets", [])
    assert len(markets) > 0, "No open markets found on Kalshi"
    return markets[0]["ticker"]


@pytest.mark.live
async def test_get_market_real(live_client: KalshiClient, live_provider: ProdDataProvider) -> None:
    """Fetching a real market should return a MarketSnapshot with valid data."""
    ticker = await _find_open_market(live_client)
    snapshot = await live_provider.get_market(ticker)

    assert isinstance(snapshot, MarketSnapshot), f"Expected MarketSnapshot, got {type(snapshot).__name__}"
    assert snapshot.ticker == ticker, f"Expected ticker {ticker!r}, got {snapshot.ticker!r}"
    assert snapshot.status in ("open", "active"), f"Unexpected market status: {snapshot.status}"
    assert snapshot.open_interest_cents >= 0, (
        f"open_interest_cents should be >= 0, got {snapshot.open_interest_cents}"
    )


@pytest.mark.live
async def test_get_orderbook_real(live_client: KalshiClient, live_provider: ProdDataProvider) -> None:
    """Fetching a real orderbook should return OrderBookSnapshot with level tuples."""
    ticker = await _find_open_market(live_client)
    ob = await live_provider.get_orderbook(ticker)

    assert isinstance(ob, OrderBookSnapshot), f"Expected OrderBookSnapshot, got {type(ob).__name__}"

    if ob.yes_bids:
        assert all(isinstance(b, OrderBookLevelSnapshot) for b in ob.yes_bids), (
            "yes_bids should contain OrderBookLevelSnapshot instances"
        )
        for bid in ob.yes_bids:
            assert isinstance(bid.price_cents, int) and bid.price_cents > 0, (
                f"yes bid price_cents should be positive int, got {bid.price_cents}"
            )
            assert isinstance(bid.size, int) and bid.size > 0, (
                f"yes bid size should be positive int, got {bid.size}"
            )

    if ob.no_bids:
        assert all(isinstance(b, OrderBookLevelSnapshot) for b in ob.no_bids), (
            "no_bids should contain OrderBookLevelSnapshot instances"
        )


@pytest.mark.live
async def test_get_settlement_unsettled(live_client: KalshiClient, live_provider: ProdDataProvider) -> None:
    """An open (unsettled) market should return None from get_settlement."""
    ticker = await _find_open_market(live_client)
    result = await live_provider.get_settlement(ticker)

    assert result is None, (
        f"Open market {ticker!r} should have no settlement, got {result}"
    )