"""Tests for db/decisions.py — decision insert, query, and update operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from traderbot.db import get_connection, init_schema
from traderbot.db.decisions import (
    count,
    get,
    insert,
    list_by_date_range,
    list_by_outcome,
    list_by_ticker,
    update_actual_result,
)
from traderbot.kalshi.models import Decision

if TYPE_CHECKING:
    from pathlib import Path


def _make_decision(**overrides) -> Decision:
    defaults = dict(
        timestamp=datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC),
        ticker="KX-TEST",
        direction="yes",
        quantity=5,
        price=50,
        signal_strength=0.7,
        confidence=0.8,
        edge_estimate=0.1,
        risk_checks={"max_position": True, "daily_loss": True},
        outcome="executed",
        rejection_reason=None,
        actual_result=None,
    )
    defaults.update(overrides)
    return Decision(**defaults)


class TestInsertAndGet:
    def test_insert_returns_rowid(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            init_schema(conn)
            rowid = insert(conn, _make_decision())
        assert rowid == 1

    def test_get_by_id(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            init_schema(conn)
            rowid = insert(conn, _make_decision())
            result = get(conn, rowid)
        assert result.ticker == "KX-TEST"
        assert result.risk_checks == {"max_position": True, "daily_loss": True}

    def test_get_returns_none_for_unknown(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            init_schema(conn)
            result = get(conn, 999)
        assert result is None


class TestListByTicker:
    def test_filters_by_ticker(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            init_schema(conn)
            insert(conn, _make_decision(ticker="KX-A"))
            insert(conn, _make_decision(ticker="KX-B"))
            insert(conn, _make_decision(ticker="KX-A"))
            result = list_by_ticker(conn, "KX-A")
        assert len(result) == 2
        assert all(d.ticker == "KX-A" for d in result)


class TestListByDateRange:
    def test_filters_by_start_and_end(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            init_schema(conn)
            insert(conn, _make_decision(timestamp=datetime(2026, 1, 1, tzinfo=UTC)))
            insert(conn, _make_decision(timestamp=datetime(2026, 6, 1, tzinfo=UTC)))
            insert(conn, _make_decision(timestamp=datetime(2026, 12, 1, tzinfo=UTC)))
            result = list_by_date_range(
                conn,
                start=datetime(2026, 3, 1, tzinfo=UTC),
                end=datetime(2026, 9, 1, tzinfo=UTC),
            )
        assert len(result) == 1

    def test_no_filters_returns_all(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            init_schema(conn)
            insert(conn, _make_decision())
            insert(conn, _make_decision())
            result = list_by_date_range(conn)
        assert len(result) == 2


class TestListByOutcome:
    def test_filters_by_outcome(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            init_schema(conn)
            insert(conn, _make_decision(outcome="executed"))
            insert(conn, _make_decision(outcome="rejected"))
            insert(conn, _make_decision(outcome="executed"))
            result = list_by_outcome(conn, "executed")
        assert len(result) == 2
        assert all(d.outcome == "executed" for d in result)


class TestUpdateActualResult:
    def test_updates_result(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            init_schema(conn)
            rowid = insert(conn, _make_decision())
            update_actual_result(conn, rowid, True)
            result = get(conn, rowid)
        assert result.actual_result is True


class TestCount:
    def test_returns_total(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            init_schema(conn)
            assert count(conn) == 0
            insert(conn, _make_decision())
            insert(conn, _make_decision())
            assert count(conn) == 2
