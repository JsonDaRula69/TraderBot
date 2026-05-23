import sqlite3

import pytest

from experiments.v3.db_schema import create_tables, verify_schema


class TestCreateTables:
    def test_creates_all_tables(self):
        conn = sqlite3.connect(":memory:")
        create_tables(conn)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        names = {row[0] for row in cursor.fetchall()}
        for table in (
            "markets",
            "forecast_snapshots",
            "market_prices",
            "settlement_results",
            "forecast_accuracy",
            "orderbook_snapshots",
            "treatment_decisions",
            "experiment_runs",
        ):
            assert table in names, f"Table {table} not found"
        conn.close()

    def test_idempotent_if_not_exists(self):
        conn = sqlite3.connect(":memory:")
        create_tables(conn)
        create_tables(conn)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        names = {row[0] for row in cursor.fetchall()}
        assert "markets" in names
        conn.close()


class TestVerifySchema:
    def test_returns_true_for_full_schema(self):
        conn = sqlite3.connect(":memory:")
        create_tables(conn)
        assert verify_schema(conn) is True
        conn.close()

    def test_returns_false_if_table_missing(self):
        conn = sqlite3.connect(":memory:")
        create_tables(conn)
        conn.execute("DROP TABLE orderbook_snapshots")
        assert verify_schema(conn) is False
        conn.close()

    def test_returns_false_if_column_missing(self):
        conn = sqlite3.connect(":memory:")
        create_tables(conn)
        conn.execute("ALTER TABLE markets DROP COLUMN city")
        assert verify_schema(conn) is False
        conn.close()

    def test_orderbook_snapshots_exists(self):
        conn = sqlite3.connect(":memory:")
        create_tables(conn)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='orderbook_snapshots'")
        assert cursor.fetchone() is not None
        conn.close()
