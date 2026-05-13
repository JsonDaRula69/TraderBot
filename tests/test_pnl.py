from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from traderbot.kalshi.provider import MockDataProvider
from traderbot.simulation.paper_trader import PaperFill, PaperTrader

TIMESTAMP = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


def _make_fill(
    ticker: str = "TEST",
    side: str = "yes",
    price_cents: int = 50,
    quantity: int = 10,
) -> PaperFill:
    return PaperFill(
        ticker=ticker,
        side=side,
        price_cents=price_cents,
        quantity=quantity,
        slippage_cents=0,
        timestamp=TIMESTAMP,
    )


class TestGetPnl:
    def test_zero_positions_returns_realized_pnl(self) -> None:
        provider = MockDataProvider()
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        trader = PaperTrader(provider=provider, db_conn=conn, initial_cash_cents=10_000_00)
        assert trader.get_pnl() == 0

    def test_single_yes_position_unrealized(self) -> None:
        provider = MockDataProvider()
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        trader = PaperTrader(provider=provider, db_conn=conn, initial_cash_cents=10_000_00)
        trader.record_fill(_make_fill(ticker="A", side="yes", price_cents=50, quantity=10))
        unrealized = trader.get_pnl(mark_prices={"A": 60})
        assert unrealized == (60 - 50) * 10

    def test_single_yes_position_unrealized_loss(self) -> None:
        provider = MockDataProvider()
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        trader = PaperTrader(provider=provider, db_conn=conn, initial_cash_cents=10_000_00)
        trader.record_fill(_make_fill(ticker="A", side="yes", price_cents=70, quantity=10))
        unrealized = trader.get_pnl(mark_prices={"A": 60})
        assert unrealized == (60 - 70) * 10

    def test_no_position_uses_reverse_pnl(self) -> None:
        provider = MockDataProvider()
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        trader = PaperTrader(provider=provider, db_conn=conn, initial_cash_cents=10_000_00)
        trader.record_fill(_make_fill(ticker="B", side="no", price_cents=40, quantity=10))
        unrealized = trader.get_pnl(mark_prices={"B": 30})
        assert unrealized == (40 - 30) * 10

    def test_multiple_positions_aggregate(self) -> None:
        provider = MockDataProvider()
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        trader = PaperTrader(provider=provider, db_conn=conn, initial_cash_cents=10_000_00)
        trader.record_fill(_make_fill(ticker="X", side="yes", price_cents=50, quantity=10))
        trader.record_fill(_make_fill(ticker="Y", side="yes", price_cents=30, quantity=20))
        pnl = trader.get_pnl(mark_prices={"X": 55, "Y": 35})
        assert pnl == (55 - 50) * 10 + (35 - 30) * 20

    def test_missing_mark_price_treated_as_zero_unrealized(self) -> None:
        provider = MockDataProvider()
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        trader = PaperTrader(provider=provider, db_conn=conn, initial_cash_cents=10_000_00)
        trader.record_fill(_make_fill(ticker="Z", side="yes", price_cents=50, quantity=10))
        pnl = trader.get_pnl(mark_prices={})
        assert pnl == 0

    def test_realized_pnl_from_close(self) -> None:
        provider = MockDataProvider()
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        trader = PaperTrader(provider=provider, db_conn=conn, initial_cash_cents=10_000_00)
        trader.record_fill(_make_fill(ticker="A", side="yes", price_cents=50, quantity=10))
        close_fill = PaperFill(
            ticker="A",
            side="no",
            price_cents=60,
            quantity=-10,
            slippage_cents=0,
            timestamp=TIMESTAMP,
        )
        trader.record_fill(close_fill)
        pnl = trader.get_pnl(mark_prices={})
        assert pnl == (60 - 50) * 10

    def test_no_mark_prices_returns_realized_only(self) -> None:
        provider = MockDataProvider()
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        trader = PaperTrader(provider=provider, db_conn=conn, initial_cash_cents=10_000_00)
        assert trader.get_pnl(mark_prices=None) == 0
