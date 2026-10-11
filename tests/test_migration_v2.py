from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from traderbot.db.migrations import GLOBAL_MIGRATIONS, init_schema, rollback_migration

_V1_TABLES = {
    "profiles",
    "config",
    "market_data",
    "orderbook",
    "weather_forecasts",
    "nws_forecasts",
    "settlement_cache",
}
_V2_TABLES = {
    "weather_observations",
    "kalshi_markets",
    "kalshi_candlesticks",
    "kalshi_forecast_history",
}


def _tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _indexes(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def test_global_migration_v2_creates_exact_tables_and_indexes(tmp_path: Path) -> None:
    db_path = tmp_path / "global.db"

    init_schema(db_path)

    with sqlite3.connect(db_path) as connection:
        assert _tables(connection) == _V1_TABLES | _V2_TABLES | {"schema_version"}
        assert {
            "idx_weather_observations_city_date",
            "idx_kalshi_markets_event",
            "idx_kalshi_markets_series",
            "idx_kalshi_markets_category_status",
            "idx_kalshi_markets_status_close",
            "idx_kalshi_candlesticks_ticker_ts",
            "idx_kalshi_forecast_event_ts",
        }.issubset(_indexes(connection))
        assert connection.execute(
            "SELECT version FROM schema_version ORDER BY version"
        ).fetchall() == [(1,), (2,)]


def test_global_migration_v2_is_idempotent_and_preserves_v1_sql(tmp_path: Path) -> None:
    db_path = tmp_path / "idempotent.db"
    v1_sql = GLOBAL_MIGRATIONS[0].up_sql

    init_schema(db_path)
    init_schema(db_path)

    assert GLOBAL_MIGRATIONS[0].version == 1
    assert GLOBAL_MIGRATIONS[0].down_sql is None
    assert GLOBAL_MIGRATIONS[0].up_sql == v1_sql
    assert tuple(migration.version for migration in GLOBAL_MIGRATIONS) == (1, 2)


def test_global_migration_v2_constraints_reject_invalid_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "constraints.db"
    init_schema(db_path)

    with sqlite3.connect(db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO weather_observations VALUES (?, ?, ?, ?, ?, ?)",
                ("2026-08-11", "NYC", 91.0, -74.0, "temperature_2m_max", 80.0),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO kalshi_candlesticks "
                "(ticker, period_interval, end_period_ts, source, volume_fp, open_interest_fp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("KX-NYC", 5, 1, "collector", "1.00", "2.00"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO kalshi_forecast_history "
                "(event_ticker, series_ticker, end_period_ts, period_interval, percentile, "
                "raw_numerical_forecast, numerical_forecast, formatted_forecast) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("EV", "SER", 1, 60, 10000, "1.25", "1.25", "1.25"),
            )


def test_rollback_v2_only_preserves_v1_tables_and_data(tmp_path: Path) -> None:
    db_path = tmp_path / "rollback.db"
    init_schema(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO config (key, value) VALUES ('preserved', 'yes')")
        connection.execute(
            "INSERT INTO weather_observations VALUES (?, ?, ?, ?, ?, ?)",
            ("2026-08-11", "NYC", 40.7, -74.0, "temperature_2m_max", 80.0),
        )

    assert rollback_migration(db_path, GLOBAL_MIGRATIONS, version=2) == 2

    with sqlite3.connect(db_path) as connection:
        assert _V2_TABLES.isdisjoint(_tables(connection))
        assert _V1_TABLES.issubset(_tables(connection))
        assert connection.execute(
            "SELECT value FROM config WHERE key = 'preserved'"
        ).fetchone() == ("yes",)
        assert connection.execute("SELECT version FROM schema_version").fetchall() == [(1,)]
