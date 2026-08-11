from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from traderbot.db.pool import SQLiteConnectionPool
from traderbot.deploy.backfill_collector_types import CollectorSchemaError
from traderbot.deploy.backfill_models import CollectorCounts, TableCounts

_BATCH_SIZE: Final = 1000
type Column = tuple[str, str, int, int]
type ForecastRow = tuple[str, str, float, float, str, str, str, float]
type NwsRow = tuple[
    str, str, str, float | None, float | None, float | None, float | None, str | None
]
type ObservationRow = tuple[str, str, float, float, str, float]
type SourceRow = ForecastRow | NwsRow | ObservationRow


@dataclass(frozen=True, slots=True)
class _TableSpec:
    name: str
    columns: tuple[Column, ...]
    natural_key: tuple[str, ...]
    select_sql: str
    insert_sql: str


class _Cursor[T](Protocol):
    def fetchall(self) -> list[T]: ...


class _Connection[T](Protocol):
    def execute(self, sql: str, /) -> _Cursor[T]: ...


def _fetchall[T](connection: _Connection[T], sql: str) -> list[T]:
    return connection.execute(sql).fetchall()


_SPECS: Final = (
    _TableSpec(
        "weather_forecasts",
        (
            ("id", "INTEGER", 0, 1),
            ("snapshot_ts", "TEXT", 1, 0),
            ("city", "TEXT", 1, 0),
            ("latitude", "REAL", 1, 0),
            ("longitude", "REAL", 1, 0),
            ("model", "TEXT", 1, 0),
            ("valid_date", "TEXT", 1, 0),
            ("variable", "TEXT", 1, 0),
            ("value", "REAL", 1, 0),
        ),
        ("snapshot_ts", "city", "model", "valid_date", "variable"),
        """SELECT snapshot_ts, city, latitude, longitude, model,
valid_date, variable, value FROM weather_forecasts ORDER BY id""",
        """INSERT OR IGNORE INTO weather_forecasts
(snapshot_ts, city, latitude, longitude, model, valid_date, variable, value)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
    ),
    _TableSpec(
        "nws_forecasts",
        (
            ("id", "INTEGER", 0, 1),
            ("snapshot_ts", "TEXT", 1, 0),
            ("city", "TEXT", 1, 0),
            ("forecast_date", "TEXT", 1, 0),
            ("high_temp_f", "REAL", 0, 0),
            ("low_temp_f", "REAL", 0, 0),
            ("precip_prob", "REAL", 0, 0),
            ("wind_speed", "REAL", 0, 0),
            ("detailed_forecast", "TEXT", 0, 0),
        ),
        ("snapshot_ts", "city", "forecast_date"),
        """SELECT snapshot_ts, city, forecast_date, high_temp_f,
low_temp_f, precip_prob, wind_speed, detailed_forecast FROM nws_forecasts ORDER BY id""",
        """INSERT OR IGNORE INTO nws_forecasts
(snapshot_ts, city, forecast_date, high_temp_f, low_temp_f, precip_prob,
wind_speed, detailed_forecast) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
    ),
    _TableSpec(
        "weather_observations",
        (
            ("id", "INTEGER", 0, 1),
            ("date", "TEXT", 1, 0),
            ("city", "TEXT", 1, 0),
            ("latitude", "REAL", 1, 0),
            ("longitude", "REAL", 1, 0),
            ("variable", "TEXT", 1, 0),
            ("value", "REAL", 1, 0),
        ),
        ("date", "city", "variable"),
        """SELECT date, city, latitude, longitude, variable, value
FROM weather_observations ORDER BY id""",
        """INSERT OR IGNORE INTO weather_observations
(date, city, latitude, longitude, variable, value) VALUES (?, ?, ?, ?, ?, ?)""",
    ),
)


def _signature(connection: sqlite3.Connection, spec: _TableSpec) -> tuple[Column, ...]:
    typed: _Connection[tuple[int, str, str, int, str | None, int]] = connection
    rows: list[tuple[int, str, str, int, str | None, int]] = _fetchall(
        typed, f'PRAGMA table_info("{spec.name}")'
    )
    if any(default is not None for _, _, _, _, default, _ in rows):
        raise CollectorSchemaError(spec.name)
    names = tuple(row[1] for row in rows)
    if len(names) != len(set(names)):
        raise CollectorSchemaError(spec.name)
    return tuple(
        (name, declared.upper(), required, primary)
        for _, name, declared, required, _, primary in rows
    )


def _unique_keys(connection: sqlite3.Connection, spec: _TableSpec) -> set[tuple[str, ...]]:
    indexes: _Connection[tuple[int, str, int, str, int]] = connection
    keys: set[tuple[str, ...]] = set()
    index_rows: list[tuple[int, str, int, str, int]] = _fetchall(
        indexes, f'PRAGMA index_list("{spec.name}")'
    )
    for _, name, unique, _, _ in index_rows:
        if unique == 1:
            columns: _Connection[tuple[int, int, str]] = connection
            column_rows: list[tuple[int, int, str]] = _fetchall(
                columns, f'PRAGMA index_info("{name}")'
            )
            keys.add(tuple(row[2] for row in column_rows))
    return keys


def preflight_collector(connection: sqlite3.Connection) -> None:
    for spec in _SPECS:
        if _signature(connection, spec) != spec.columns:
            raise CollectorSchemaError(spec.name)
        if spec.natural_key not in _unique_keys(connection, spec):
            raise CollectorSchemaError(spec.name)


def _copy_table(
    source: sqlite3.Connection,
    pool: SQLiteConnectionPool,
    target: Path,
    spec: _TableSpec,
) -> TableCounts:
    cursor = source.execute(spec.select_sql)
    seen = 0
    inserted = 0
    while rows := cursor.fetchmany(_BATCH_SIZE):
        batch: Sequence[SourceRow] = rows
        seen += len(batch)
        with pool.connection(target) as target_connection:
            before = target_connection.total_changes
            _ = target_connection.executemany(spec.insert_sql, batch)
            inserted += target_connection.total_changes - before
    return TableCounts(seen=seen, inserted=inserted, duplicate=seen - inserted)


def copy_collector(
    source: sqlite3.Connection, target: Path, pool: SQLiteConnectionPool
) -> CollectorCounts:
    counts = tuple(_copy_table(source, pool, target, spec) for spec in _SPECS)
    return CollectorCounts(
        weather_forecasts=counts[0],
        nws_forecasts=counts[1],
        weather_observations=counts[2],
    )
