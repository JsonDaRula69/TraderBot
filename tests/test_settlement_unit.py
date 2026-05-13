from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from traderbot.kalshi.provider import (
    MarketSnapshot,
    MockDataProvider,
    SettlementResult,
)
from traderbot.simulation.paper_trader import PaperFill, PaperTrader
from traderbot.simulation.settlement import SettlementVerifier

TIMESTAMP = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


def _make_trader_with_positions(
    provider: MockDataProvider,
    tickers: list[str],
) -> tuple[PaperTrader, sqlite3.Connection]:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    trader = PaperTrader(provider=provider, db_conn=conn, initial_cash_cents=10_000_00)
    for ticker in tickers:
        fill = PaperFill(
            ticker=ticker,
            side="yes",
            price_cents=50,
            quantity=10,
            slippage_cents=0,
            timestamp=TIMESTAMP,
        )
        trader.record_fill(fill)
    return trader, conn


class TestCheckSettlementsOnStartup:
    async def test_marks_settled_positions(self) -> None:
        settlement = SettlementResult(
            ticker="SETTLED-MKT",
            outcome=True,
            settled_at=datetime(2025, 1, 2, 0, 0, 0, tzinfo=UTC),
        )
        provider = MockDataProvider(settlements={"SETTLED-MKT": settlement})
        trader, conn = _make_trader_with_positions(provider, ["SETTLED-MKT"])
        verifier = SettlementVerifier(provider=provider, paper_trader=trader)
        await verifier.check_settlements_on_startup()
        positions = trader.get_positions()
        assert len(positions) == 1
        assert positions[0].status == "settled"
        conn.close()

    async def test_no_open_positions_is_noop(self) -> None:
        provider = MockDataProvider()
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        trader = PaperTrader(provider=provider, db_conn=conn, initial_cash_cents=10_000_00)
        verifier = SettlementVerifier(provider=provider, paper_trader=trader)
        await verifier.check_settlements_on_startup()
        assert len(trader.get_positions()) == 0
        conn.close()

    async def test_unsettled_markets_remain_open(self) -> None:
        provider = MockDataProvider()
        trader, conn = _make_trader_with_positions(provider, ["OPEN-MKT"])
        verifier = SettlementVerifier(provider=provider, paper_trader=trader)
        await verifier.check_settlements_on_startup()
        positions = trader.get_positions()
        assert len(positions) == 1
        assert positions[0].status == "open"
        conn.close()


class TestCheckSettlementBeforeOrder:
    async def test_blocks_settled_market(self) -> None:
        settlement = SettlementResult(
            ticker="SETTLED-MKT",
            outcome=True,
            settled_at=datetime(2025, 1, 2, 0, 0, 0, tzinfo=UTC),
        )
        provider = MockDataProvider(settlements={"SETTLED-MKT": settlement})
        trader, conn = _make_trader_with_positions(provider, ["SETTLED-MKT"])
        verifier = SettlementVerifier(provider=provider, paper_trader=trader)
        result = await verifier.check_settlement_before_order("SETTLED-MKT")
        assert result is True
        conn.close()

    async def test_permits_open_market(self) -> None:
        provider = MockDataProvider()
        trader, conn = _make_trader_with_positions(provider, ["OPEN-MKT"])
        verifier = SettlementVerifier(provider=provider, paper_trader=trader)
        result = await verifier.check_settlement_before_order("OPEN-MKT")
        assert result is False
        conn.close()

    async def test_api_error_allows_order(self) -> None:
        """If provider raises exception, settlement check should permit the order."""

        class FailingProvider(MockDataProvider):
            async def get_settlement(self, ticker: str) -> SettlementResult | None:
                raise RuntimeError("API error")

        provider = FailingProvider()
        trader, conn = _make_trader_with_positions(provider, ["MKT"])
        verifier = SettlementVerifier(provider=provider, paper_trader=trader)
        result = await verifier.check_settlement_before_order("MKT")
        assert result is False
        conn.close()


class TestCheckSettlementsPeriodic:
    async def test_near_expiry_settled_is_marked(self) -> None:
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        close_time = now + timedelta(minutes=15)
        market = MarketSnapshot(
            ticker="NEAR-EXPIRY",
            status="open",
            open_interest_cents=5_000_00,
            close_time=close_time,
        )
        settlement = SettlementResult(
            ticker="NEAR-EXPIRY",
            outcome=True,
            settled_at=now,
        )
        provider = MockDataProvider(
            markets={"NEAR-EXPIRY": market},
            settlements={"NEAR-EXPIRY": settlement},
        )
        trader, conn = _make_trader_with_positions(provider, ["NEAR-EXPIRY"])
        verifier = SettlementVerifier(provider=provider, paper_trader=trader)
        await verifier.check_settlements_periodic(now)
        pos = trader.get_positions()[0]
        assert pos.status == "settled"
        conn.close()

    async def test_far_from_expiry_not_checked(self) -> None:
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
        close_time = now + timedelta(days=30)
        market = MarketSnapshot(
            ticker="FAR-MKT",
            status="open",
            open_interest_cents=5_000_00,
            close_time=close_time,
        )
        provider = MockDataProvider(markets={"FAR-MKT": market})
        trader, conn = _make_trader_with_positions(provider, ["FAR-MKT"])
        verifier = SettlementVerifier(provider=provider, paper_trader=trader)
        await verifier.check_settlements_periodic(now)
        pos = trader.get_positions()[0]
        assert pos.status == "open"
        conn.close()
