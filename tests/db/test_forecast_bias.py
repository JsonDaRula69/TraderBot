from __future__ import annotations

import sqlite3

import pytest

from traderbot.db.forecast_bias import (
    init_table,
    query_bias,
    record_forecast,
)


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    init_table(c)
    return c


class TestInitTable:
    def test_creates_forecast_bias_table(self, conn: sqlite3.Connection) -> None:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='forecast_bias'"
        )
        assert cursor.fetchone() is not None


class TestRecordForecast:
    def test_records_one_entry(self, conn: sqlite3.Connection) -> None:
        record_forecast(conn, city="New York", forecast_high_f=70.0, actual_high_f=72.0)
        cursor = conn.execute("SELECT COUNT(*) FROM forecast_bias")
        assert cursor.fetchone()[0] == 1

    def test_computes_error_correctly(self, conn: sqlite3.Connection) -> None:
        record_forecast(conn, city="Chicago", forecast_high_f=60.0, actual_high_f=55.0)
        cursor = conn.execute("SELECT error_f FROM forecast_bias")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == -5.0

    def test_multiple_cities(self, conn: sqlite3.Connection) -> None:
        record_forecast(conn, "NYC", 70.0, 72.0)
        record_forecast(conn, "LA", 80.0, 78.0)
        record_forecast(conn, "NYC", 71.0, 70.0)
        cursor = conn.execute("SELECT COUNT(*) FROM forecast_bias")
        assert cursor.fetchone()[0] == 3


class TestQueryBias:
    def test_empty_table(self, conn: sqlite3.Connection) -> None:
        stats = query_bias(conn, "NYC")
        assert stats["count"] == 0

    def test_single_city_stats(self, conn: sqlite3.Connection) -> None:
        record_forecast(conn, "NYC", 70.0, 72.0)
        record_forecast(conn, "NYC", 71.0, 70.0)
        stats = query_bias(conn, "NYC")
        assert stats["count"] == 2
