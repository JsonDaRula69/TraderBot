"""Integration tests for PaperTrader with live Kalshi data and settlement blocking."""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from traderbot.kalshi.client import KalshiClient, KalshiConfig
from traderbot.kalshi.markets import MarketService
from traderbot.kalshi.provider import (
    MarketSnapshot,
    MockDataProvider,
    OrderBookLevelSnapshot,
    OrderBookSnapshot,
    ProdDataProvider,
    SettlementResult,
)
from traderbot.simulation.paper_trader import PaperFill, PaperTrader
from traderbot.simulation.settlement import SettlementVerifier

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_submit_paper_order(live_provider: ProdDataProvider) -> None:
    config = KalshiConfig(
        api_key=SecretStr(os.environ["KALSHI_API_KEY"]),
        private_key_pem=SecretStr(os.environ["KALSHI_PRIVATE_KEY_PEM"]),
    )
    client = KalshiClient(config=config)
    try:
        market_svc = MarketService(client)
        markets_resp = await market_svc.list_markets(limit=5, status="open")
        markets = markets_resp.markets
        if not markets:
            pytest.skip("No open markets available on Kalshi")

        ticker = markets[0].ticker

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        trader = PaperTrader(
            provider=live_provider,
            db_conn=conn,
            initial_cash_cents=1_000_00,
        )

        fill = await trader.submit_order(
            ticker=ticker,
            side="yes",
            quantity=1,
            price_cents=50,
            edge_estimate=0.10,
        )

        if fill is None:
            pytest.skip("Paper order rejected by risk gate — try another market")

        assert isinstance(fill, PaperFill)
        assert fill.ticker == ticker
        assert fill.side == "yes"
        assert fill.quantity >= 1

        portfolio = trader.get_portfolio()
        assert portfolio.cash_cents < 1_000_00

        positions = trader.get_positions()
        assert ticker in [p.ticker for p in positions]
        pos = next(p for p in positions if p.ticker == ticker)
        assert pos.side == "yes"
        assert pos.quantity >= 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_submit_order_settled_market_blocked() -> None:
    now = datetime.now(UTC)
    settled_ticker = "SETTLED-MKT-001"

    provider = MockDataProvider(
        markets={
            settled_ticker: MarketSnapshot(
                ticker=settled_ticker,
                status="settled",
                open_interest_cents=10_000_00,
                close_time=now,
                settlement_result=True,
            )
        },
        orderbooks={
            settled_ticker: OrderBookSnapshot(
                yes_bids=(OrderBookLevelSnapshot(price_cents=50, size=100),),
                no_bids=(OrderBookLevelSnapshot(price_cents=50, size=100),),
                timestamp=now,
            )
        },
        settlements={
            settled_ticker: SettlementResult(
                ticker=settled_ticker,
                outcome=True,
                settled_at=now,
            )
        },
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    trader = PaperTrader(
        provider=provider,
        db_conn=conn,
        initial_cash_cents=1_000_00,
    )

    verifier = SettlementVerifier(
        provider=provider,
        paper_trader=trader,
    )
    trader._settlement = verifier

    result = await trader.submit_order(
        ticker=settled_ticker,
        side="yes",
        quantity=1,
        price_cents=50,
        edge_estimate=0.10,
    )

    assert result is None
