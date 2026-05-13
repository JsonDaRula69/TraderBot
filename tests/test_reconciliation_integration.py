"""Integration tests for position reconciliation drift detection."""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from traderbot.kalshi.models import Position
from traderbot.kalshi.portfolio import PortfolioService
from traderbot.kalshi.provider import (
    MarketSnapshot,
    MockDataProvider,
    OrderBookLevelSnapshot,
    OrderBookSnapshot,
)
from traderbot.simulation.paper_trader import PaperTrader
from traderbot.simulation.settlement import SettlementVerifier

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_reconcile_detects_drift(caplog: pytest.LogCaptureFixture) -> None:
    now = datetime.now(UTC)
    ticker_a = "DRIFT-TEST-A"
    ticker_b = "DRIFT-TEST-B"

    provider = MockDataProvider(
        markets={
            ticker_a: MarketSnapshot(
                ticker=ticker_a,
                status="open",
                open_interest_cents=10_000_00,
                close_time=now,
            ),
            ticker_b: MarketSnapshot(
                ticker=ticker_b,
                status="open",
                open_interest_cents=5_000_00,
                close_time=now,
            ),
        },
        orderbooks={
            ticker_a: OrderBookSnapshot(
                yes_bids=(OrderBookLevelSnapshot(price_cents=55, size=200),),
                no_bids=(OrderBookLevelSnapshot(price_cents=45, size=200),),
                timestamp=now,
            ),
            ticker_b: OrderBookSnapshot(
                yes_bids=(OrderBookLevelSnapshot(price_cents=30, size=100),),
                no_bids=(OrderBookLevelSnapshot(price_cents=70, size=100),),
                timestamp=now,
            ),
        },
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    trader = PaperTrader(
        provider=provider,
        db_conn=conn,
        initial_cash_cents=10_000_00,
    )

    fill_a = await trader.submit_order(
        ticker=ticker_a, side="yes", quantity=5, price_cents=55, edge_estimate=0.10
    )
    fill_b = await trader.submit_order(
        ticker=ticker_b, side="yes", quantity=5, price_cents=30, edge_estimate=0.10
    )

    if fill_a is None or fill_b is None:
        pytest.skip("Risk gate rejected orders — cannot set up drift scenario")

    mock_portfolio = AsyncMock(spec=PortfolioService)
    mock_portfolio.get_positions.return_value = [
        Position(
            ticker=ticker_a,
            quantity=fill_a.quantity,
            avg_price=fill_a.price_cents,
        ),
    ]

    mock_client = AsyncMock()
    portfolio_service = PortfolioService(client=mock_client)
    portfolio_service.get_positions = mock_portfolio.get_positions

    verifier = SettlementVerifier(
        provider=provider,
        paper_trader=trader,
        portfolio_service=portfolio_service,
    )

    with caplog.at_level(logging.WARNING):
        await verifier.reconcile_positions()

    assert any("drift" in r.message.lower() for r in caplog.records)
