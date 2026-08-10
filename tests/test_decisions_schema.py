"""Contract tests for per-agent decisions databases and storage names."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from traderbot.db import validation
from traderbot.db.decisions import DECISIONS_MIGRATIONS, init_decisions_db
from traderbot.db.validation import InvalidStorageNameError, validate_storage_name

_MANIFEST_START = "<!-- schema-manifest:start -->"
_MANIFEST_END = "<!-- schema-manifest:end -->"


def _manifest_tables() -> dict[str, dict[str, list[dict[str, str | int | bool | None]]]]:
    schema_doc = Path(__file__).parents[1] / "v2docs" / "08-database-schema.md"
    document = schema_doc.read_text(encoding="utf-8")
    manifest_text = document.split(_MANIFEST_START, maxsplit=1)[1].split(_MANIFEST_END, maxsplit=1)[
        0
    ]
    manifest = json.loads(manifest_text)
    return manifest["tables"]


def _table_info(db_path: Path, table: str) -> list[tuple[str, str, bool, str | None, int]]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    return [(str(row[1]), str(row[2]), bool(row[3]), row[4], int(row[5])) for row in rows]


def _created_indexes(db_path: Path) -> dict[str, tuple[str, ...]]:
    with sqlite3.connect(db_path) as connection:
        names = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'index' AND sql IS NOT NULL AND sql NOT LIKE 'CREATE UNIQUE INDEX%'"
        ).fetchall()
        return {
            str(row[0]): tuple(
                str(column[2])
                for column in connection.execute(f'PRAGMA index_info("{row[0]}")').fetchall()
            )
            for row in names
        }


def test_init_decisions_db_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "decisions.db"

    init_decisions_db(db_path)
    init_decisions_db(db_path)

    with sqlite3.connect(db_path) as connection:
        versions = connection.execute("SELECT version FROM schema_version").fetchall()
    assert versions == [(1,)]
    assert DECISIONS_MIGRATIONS[0].version == 1


def test_all_manifest_tables_have_exact_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "decisions.db"
    init_decisions_db(db_path)
    tables = _manifest_tables()

    with sqlite3.connect(db_path) as connection:
        actual_tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
    expected_tables = {name for name, table in tables.items() if table["scope"] == "per_agent"}
    assert actual_tables == expected_tables | {"schema_version"}

    for table_name in expected_tables:
        expected_columns = [
            (
                column["name"],
                column["type"],
                not bool(column["nullable"]),
                None if "default" not in column else str(column["default"]),
                column["pk_ordinal"],
            )
            for column in tables[table_name]["columns"]
        ]
        actual_columns = _table_info(db_path, table_name)
        assert actual_columns == expected_columns


def test_all_manifest_indexes_are_created(tmp_path: Path) -> None:
    db_path = tmp_path / "decisions.db"
    init_decisions_db(db_path)
    tables = _manifest_tables()
    expected = {
        index["name"]: tuple(index["columns"])
        for table in tables.values()
        if table["scope"] == "per_agent"
        for index in table["indexes"]
    }

    assert _created_indexes(db_path) == expected


def test_decision_does_not_require_a_position(tmp_path: Path) -> None:
    db_path = tmp_path / "decisions.db"
    init_decisions_db(db_path)
    decision_id = str(uuid.uuid4())

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                decision_id,
                "2026-08-09T12:00:00Z",
                "KXHIGHNY-26AUG09-T85",
                "yes",
                1,
                42,
                0.8,
                0.7,
                0.1,
                "{}",
                "executed",
                None,
                None,
                "paper",
                "weather",
                "weather-main",
            ),
        )
        stored = connection.execute("SELECT id FROM decisions").fetchone()
        positions = connection.execute("SELECT COUNT(*) FROM positions").fetchone()
        foreign_keys = connection.execute("PRAGMA foreign_key_list(decisions)").fetchall()

    assert stored == (decision_id,)
    assert positions == (0,)
    assert foreign_keys == []


@pytest.mark.parametrize(
    ("statement", "parameters"),
    [
        (
            "INSERT INTO portfolio_summary "
            "(profile, mode, initial_balance_cents, current_balance_cents) VALUES (?, ?, ?, ?)",
            ("weather-main", "invalid", 10000, 10000),
        ),
        (
            "INSERT INTO positions "
            "(ticker, status, mode, category, profile, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("TICKER", "invalid", "paper", "weather", "weather-main", "now"),
        ),
        (
            "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                "now",
                "TICKER",
                "invalid",
                1,
                50,
                0.5,
                0.5,
                0.1,
                "{}",
                "held",
                None,
                None,
                "paper",
                "weather",
                "weather-main",
            ),
        ),
    ],
)
def test_check_constraints_reject_invalid_values(
    tmp_path: Path, statement: str, parameters: tuple[str | int | float | None, ...]
) -> None:
    db_path = tmp_path / "decisions.db"
    init_decisions_db(db_path)

    with sqlite3.connect(db_path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(statement, parameters)


@pytest.mark.parametrize(
    "statements",
    [
        (
            "INSERT INTO positions (ticker, mode, category, profile, updated_at) "
            "VALUES ('TICKER', 'paper', 'weather', 'weather-main', 'now')",
        ),
        (
            "INSERT INTO forecast_snapshots "
            "(ticker, category, source, metric, predicted_value, predicted_for_date, "
            "snapshot_date, lead_time_days) VALUES "
            "('TICKER', 'weather', 'gfs', 'high_temp', 80, '2026-08-10', '2026-08-09', 1)",
        ),
        (
            "INSERT INTO bias_tracking "
            "(category, source, metric, predicted_value, predicted_at) "
            "VALUES ('weather', 'gfs', 'high_temp', 80, '2026-08-09')",
        ),
    ],
)
def test_unique_constraints_reject_duplicates(tmp_path: Path, statements: tuple[str]) -> None:
    db_path = tmp_path / "decisions.db"
    init_decisions_db(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute(statements[0])
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(statements[0])


@pytest.mark.parametrize("name", ["weather", "weather-main", "a", "a" * 44, "agent-7"])
def test_validate_storage_name_accepts_canonical_names(name: str) -> None:
    assert validate_storage_name(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "",
        "../weather",
        "weather/other",
        "weather\\other",
        "Weather",
        "weather_main",
        "a*",
        "a?",
        "a[",
        "sysadmin",
        "a" * 45,
        "-weather",
        "weather-",
    ],
)
def test_validate_storage_name_rejects_invalid_names(name: str) -> None:
    with pytest.raises(InvalidStorageNameError, match="invalid storage name"):
        validate_storage_name(name)


def test_validate_storage_name_rejects_resolved_path_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    outside = tmp_path / "outside"
    data_root.mkdir()
    outside.mkdir()
    (data_root / "weather").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(validation, "get_data_dir", lambda: data_root)

    with pytest.raises(InvalidStorageNameError, match="outside the TraderBot data directory"):
        validate_storage_name("weather")
