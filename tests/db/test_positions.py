from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from traderbot.db.positions import DbPosition, count_open, init_table, list_open_positions


class TestDbPositionModel:
    def test_positive_quantity(self) -> None:
        p = DbPosition(
            id=1,
            ticker="KXHIGHNY-26JUN02-T72",
            quantity=10,
            avg_price=55,
            updated_at=datetime.now(UTC),
        )
        assert p.quantity == 10

    def test_negative_quantity_short_position(self) -> None:
        p = DbPosition(
            id=2,
            ticker="KXHIGHNY-26JUN02-T72",
            quantity=-5,
            avg_price=40,
            updated_at=datetime.now(UTC),
        )
        assert p.quantity == -5

    def test_zero_quantity(self) -> None:
        p = DbPosition(
            id=3,
            ticker="KXHIGHNY-26JUN02-T72",
            quantity=0,
            avg_price=0,
            updated_at=datetime.now(UTC),
        )
        assert p.quantity == 0

    def test_avg_price_must_be_non_negative(self) -> None:
        with pytest.raises(ValueError):
            DbPosition(
                id=4,
                ticker="KXHIGHNY-26JUN02-T72",
                quantity=10,
                avg_price=-1,
                updated_at=datetime.now(UTC),
            )

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValueError):
            DbPosition(
                id=5,
                ticker="KXHIGHNY-26JUN02-T72",
                quantity=1,
                avg_price=50,
                updated_at=datetime.now(UTC),
                unknown_field="x",
            )


class TestListOpenPositions:
    def _seed_positions(self, conn: sqlite3.Connection) -> None:
        now = datetime.now(UTC).isoformat()
        conn.executemany(
            "INSERT INTO positions (ticker, quantity, avg_price, settlement_result, pnl_cents, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("LONG-A", 10, 55, None, 0, now),
                ("SHORT-B", -5, 40, None, 0, now),
                ("CLOSED-C", 0, 0, None, 0, now),
                ("SETTLED-D", 7, 30, 1, 0, now),
            ],
        )
        conn.commit()

    def test_returns_positive_and_negative_quantity(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_table(conn)
        self._seed_positions(conn)

        open_pos = list_open_positions(conn)
        tickers = [p.ticker for p in open_pos]

        assert "LONG-A" in tickers
        assert "SHORT-B" in tickers
        assert "CLOSED-C" not in tickers
        assert "SETTLED-D" not in tickers
        conn.close()

    def test_negative_quantity_position_has_correct_quantity(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_table(conn)
        self._seed_positions(conn)

        open_pos = list_open_positions(conn)
        short_pos = next(p for p in open_pos if p.ticker == "SHORT-B")
        assert short_pos.quantity == -5
        conn.close()


class TestCountOpen:
    def _seed_positions(self, conn: sqlite3.Connection) -> None:
        now = datetime.now(UTC).isoformat()
        conn.executemany(
            "INSERT INTO positions (ticker, quantity, avg_price, settlement_result, pnl_cents, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("LONG-A", 10, 55, None, 0, now),
                ("SHORT-B", -5, 40, None, 0, now),
                ("CLOSED-C", 0, 0, None, 0, now),
                ("SETTLED-D", 7, 30, 1, 0, now),
            ],
        )
        conn.commit()

    def test_counts_positive_and_negative_quantity(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_table(conn)
        self._seed_positions(conn)

        assert count_open(conn) == 2  # LONG-A + SHORT-B
        conn.close()
