"""Tests for traderbot.db.experiment_schema."""

import sqlite3

from traderbot.db.experiment_schema import create_tables


def test_creates_all_tables() -> None:
    """create_tables should create all 5 experiment tables."""
    conn = sqlite3.connect(":memory:")
    create_tables(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = {r[0] for r in rows}
    expected = {"markets", "forecast_snapshots", "market_prices", "settlement_actuals", "agent_decisions"}
    assert expected.issubset(table_names), f"Missing tables: {expected - table_names}"
    conn.close()


def test_idempotent() -> None:
    """Calling create_tables twice should not raise."""
    conn = sqlite3.connect(":memory:")
    create_tables(conn)
    create_tables(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    assert len(rows) >= 5
    conn.close()


def test_agent_decisions_has_run_id() -> None:
    """agent_decisions table should have a run_id column."""
    conn = sqlite3.connect(":memory:")
    create_tables(conn)
    cols = conn.execute("PRAGMA table_info(agent_decisions)").fetchall()
    col_names = {c[1] for c in cols}
    assert "run_id" in col_names, f"run_id not in columns: {col_names}"
    conn.close()


def test_foreign_keys() -> None:
    """Inserting a market then a forecast referencing it should succeed."""
    conn = sqlite3.connect(":memory:")
    create_tables(conn)
    conn.execute(
        "INSERT INTO markets (ticker, question, city, city_prefix, lat, lon, timezone, "
        "resolution_date, close_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("NYC-25C", "Will NYC hit 25C?", "New York", "NYC", 40.7, -74.0, "EST", "2025-07-01", "2025-06-30T23:00"),
    )
    conn.execute(
        "INSERT INTO forecast_snapshots (ticker, forecast_temp_f, source, days_before, snapshot_date) "
        "VALUES (?, ?, ?, ?, ?)",
        ("NYC-25C", 78.5, "GFS", 3, "2025-06-27"),
    )
    rows = conn.execute("SELECT COUNT(*) FROM forecast_snapshots").fetchone()
    assert rows[0] == 1
    conn.close()