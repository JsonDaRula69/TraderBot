from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from traderbot.kalshi.provider import MockDataProvider
from traderbot.simulation.paper_trader import PaperFill, PaperPosition, PaperTrader

TIMESTAMP = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


class TestPaperPositionModel:
    def test_default_status_is_open(self) -> None:
        pos = PaperPosition(ticker="TEST", side="yes", avg_price_cents=50, quantity=10)
        assert pos.status == "open"

    def test_status_can_be_set(self) -> None:
        pos = PaperPosition(ticker="TEST", side="yes", avg_price_cents=50, quantity=10, status="settled")
        assert pos.status == "settled"


class TestPaperTraderPositionManagement:
    def _make_trader(self) -> tuple[PaperTrader, sqlite3.Connection]:
        provider = MockDataProvider()
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        trader = PaperTrader(provider=provider, db_conn=conn, initial_cash_cents=10_000_00)
        return trader, conn

    def test_open_position_creates_row(self) -> None:
        trader, conn = self._make_trader()
        fill = PaperFill(ticker="A", side="yes", price_cents=50, quantity=10, slippage_cents=0, timestamp=TIMESTAMP)
        trader.record_fill(fill)
        positions = trader.get_positions()
        assert len(positions) == 1
        assert positions[0].ticker == "A"
        assert positions[0].side == "yes"
        assert positions[0].avg_price_cents == 50
        assert positions[0].quantity == 10
        assert positions[0].status == "open"
        conn.close()

    def test_add_to_existing_position_updates_avg_price(self) -> None:
        trader, conn = self._make_trader()
        trader.record_fill(PaperFill(ticker="A", side="yes", price_cents=50, quantity=10, slippage_cents=0, timestamp=TIMESTAMP))
        trader.record_fill(PaperFill(ticker="A", side="yes", price_cents=70, quantity=10, slippage_cents=0, timestamp=TIMESTAMP))
        pos = trader.get_positions()[0]
        assert pos.quantity == 20
        assert pos.avg_price_cents == (50 * 10 + 70 * 10) // 20
        conn.close()

    def test_close_position_removes_row(self) -> None:
        trader, conn = self._make_trader()
        trader.record_fill(PaperFill(ticker="A", side="yes", price_cents=50, quantity=10, slippage_cents=0, timestamp=TIMESTAMP))
        close_fill = PaperFill(ticker="A", side="no", price_cents=60, quantity=-10, slippage_cents=0, timestamp=TIMESTAMP)
        trader.record_fill(close_fill)
        assert len(trader.get_positions()) == 0
        conn.close()

    def test_mark_settled_updates_status_and_zeroes_quantity(self) -> None:
        trader, conn = self._make_trader()
        trader.record_fill(PaperFill(ticker="A", side="yes", price_cents=50, quantity=10, slippage_cents=0, timestamp=TIMESTAMP))
        trader.mark_settled("A", outcome=True)
        pos = trader.get_positions()[0]
        assert pos.status == "settled"
        assert pos.quantity == 0
        conn.close()

    def test_close_position_sets_status(self) -> None:
        trader, conn = self._make_trader()
        trader.record_fill(PaperFill(ticker="B", side="yes", price_cents=40, quantity=5, slippage_cents=0, timestamp=TIMESTAMP))
        trader.close_position("B")
        pos = trader.get_positions()[0]
        assert pos.status == "closed"
        conn.close()

    def test_mark_settled_nonexistent_ticker_does_nothing(self) -> None:
        trader, conn = self._make_trader()
        trader.mark_settled("NONEXISTENT", outcome=True)
        assert len(trader.get_positions()) == 0
        conn.close()

    def test_close_position_nonexistent_ticker_does_nothing(self) -> None:
        trader, conn = self._make_trader()
        trader.close_position("NONEXISTENT")
        assert len(trader.get_positions()) == 0
        conn.close()


class TestDbOperations:
    def test_idempotent_migration(self) -> None:
        from traderbot.simulation.paper_trader import _init_paper_positions_table

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _init_paper_positions_table(conn)
        _init_paper_positions_table(conn)
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_positions'").fetchall()
        assert len(rows) == 1
        conn.close()

    def test_status_column_exists_after_migration(self) -> None:
        from traderbot.simulation.paper_trader import _migrate_add_status_column

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE IF NOT EXISTS paper_positions (
                ticker TEXT UNIQUE NOT NULL,
                side TEXT NOT NULL,
                avg_price_cents INTEGER NOT NULL DEFAULT 0,
                quantity INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )"""
        )
        conn.commit()
        _migrate_add_status_column(conn)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(paper_positions)").fetchall()}
        assert "status" in columns
        conn.close()
