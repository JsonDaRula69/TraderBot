"""Tests for db/positions.py — position CRUD and weighted-average updates."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from traderbot.db import get_connection, init_schema
from traderbot.db.positions import delete, get, list_all, update_avg_price, upsert
from traderbot.kalshi.models import Position

if TYPE_CHECKING:
    from pathlib import Path


def _make_position(**overrides) -> Position:
    defaults = dict(
        ticker="KX-TEST",
        quantity=10,
        avg_price=50,
        settlement_result=None,
    )
    defaults.update(overrides)
    return Position(**defaults)


class TestCrud:
    def test_upsert_and_get(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            init_schema(conn)
            pos = _make_position()
            upsert(conn, pos)
            result = get(conn, "KX-TEST")
        assert result is not None
        assert result.ticker == "KX-TEST"
        assert result.quantity == 10
        assert result.avg_price == 50

    def test_get_returns_none_for_unknown(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            init_schema(conn)
            result = get(conn, "NOPE")
        assert result is None

    def test_list_all_ordered_by_ticker(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            init_schema(conn)
            upsert(conn, _make_position(ticker="B-TICKER"))
            upsert(conn, _make_position(ticker="A-TICKER"))
            result = list_all(conn)
        assert len(result) == 2
        assert result[0].ticker == "A-TICKER"
        assert result[1].ticker == "B-TICKER"

    def test_delete(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            init_schema(conn)
            upsert(conn, _make_position())
            delete(conn, "KX-TEST")
            result = get(conn, "KX-TEST")
        assert result is None

    def test_upsert_updates_existing(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            init_schema(conn)
            upsert(conn, _make_position(quantity=10, avg_price=50))
            upsert(conn, _make_position(quantity=20, avg_price=60))
            result = get(conn, "KX-TEST")
        assert result is not None
        assert result.quantity == 20
        assert result.avg_price == 60


class TestUpdateAvgPrice:
    def test_weighted_average(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            init_schema(conn)
            upsert(conn, _make_position(quantity=10, avg_price=50))
            update_avg_price(conn, "KX-TEST", additional_quantity=5, new_price_cents=60)
            result = get(conn, "KX-TEST")
        assert result is not None
        assert result.quantity == 15
        assert result.avg_price == 53

    def test_raises_for_unknown_ticker(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            init_schema(conn)
            with pytest.raises(ValueError, match="Position not found"):
                update_avg_price(conn, "NOPE", additional_quantity=1, new_price_cents=50)