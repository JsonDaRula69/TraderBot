"""Contract tests tying the documented schema manifest to migration constants."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from traderbot.db.decisions import DECISIONS_MIGRATIONS
from traderbot.db.migrations import GLOBAL_MIGRATIONS, Migration
from traderbot.deploy.verify_schema import (
    DECISIONS_INDEXES,
    DECISIONS_SCHEMA_VERSION,
    DECISIONS_TABLES,
    GLOBAL_INDEXES,
    GLOBAL_SCHEMA_VERSION,
    GLOBAL_TABLES,
)

_MANIFEST_START = "<!-- schema-manifest:start -->"
_MANIFEST_END = "<!-- schema-manifest:end -->"


class _Scope(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True, strict=True)

    tables: list[str]


class _Column(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True, strict=True)

    name: str
    type: str
    nullable: bool
    pk_ordinal: int
    default: str | int | None = None


class _Table(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True, strict=True)

    columns: list[_Column]


class _Manifest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True, strict=True)

    scopes: dict[str, _Scope]
    tables: dict[str, _Table]


def _manifest() -> _Manifest:
    document = (Path(__file__).parents[1] / "v2docs" / "08-database-schema.md").read_text(
        encoding="utf-8"
    )
    payload = document.split(_MANIFEST_START, maxsplit=1)[1].split(_MANIFEST_END, maxsplit=1)[0]
    return _Manifest.model_validate_json(payload)


type ColumnSignature = tuple[str, str, bool, str | None, int]


def _migration_schema(migrations: Sequence[Migration]) -> dict[str, tuple[ColumnSignature, ...]]:
    with sqlite3.connect(":memory:") as connection:
        for migration in migrations:
            for statement in migration.up_sql:
                _ = connection.execute(statement)
        rows: list[tuple[str]] = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        schema: dict[str, tuple[ColumnSignature, ...]] = {}
        for (table_name,) in rows:
            columns: list[tuple[int, str, str, int, str | None, int]] = connection.execute(
                f'PRAGMA table_info("{table_name}")'
            ).fetchall()
            schema[table_name] = tuple(
                (
                    name,
                    declared_type,
                    not bool(not_null or pk_ordinal),
                    default,
                    pk_ordinal,
                )
                for _, name, declared_type, not_null, default, pk_ordinal in columns
            )
    return schema


def _manifest_columns(table: _Table) -> tuple[ColumnSignature, ...]:
    return tuple(
        (
            column.name,
            column.type,
            column.nullable,
            None if column.default is None else str(column.default),
            column.pk_ordinal,
        )
        for column in table.columns
    )


def test_manifest_json_scopes_match_migration_constants() -> None:
    manifest = _manifest()
    global_tables = manifest.scopes["global"].tables
    per_agent_tables = manifest.scopes["per_agent"].tables
    global_schema = _migration_schema(GLOBAL_MIGRATIONS)
    per_agent_schema = _migration_schema(DECISIONS_MIGRATIONS)

    assert set(global_tables) == set(global_schema) | {"schema_version"}
    assert set(per_agent_tables) == set(per_agent_schema)
    for table_name, columns in global_schema.items():
        assert _manifest_columns(manifest.tables[table_name]) == columns


def test_verifier_static_contract_matches_deliberate_schema_authorities() -> None:
    global_schema = _migration_schema(GLOBAL_MIGRATIONS)
    decisions_schema = _migration_schema(DECISIONS_MIGRATIONS)

    assert GLOBAL_SCHEMA_VERSION == max(item.version for item in GLOBAL_MIGRATIONS)
    assert DECISIONS_SCHEMA_VERSION == max(item.version for item in DECISIONS_MIGRATIONS)
    assert GLOBAL_TABLES == frozenset(global_schema) | {"schema_version"}
    assert DECISIONS_TABLES == frozenset(decisions_schema) | {"schema_version"}
    with sqlite3.connect(":memory:") as connection:
        for migration in GLOBAL_MIGRATIONS:
            for statement in migration.up_sql:
                _ = connection.execute(statement)
        global_rows: list[tuple[str]] = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        global_indexes = {row[0] for row in global_rows}
    with sqlite3.connect(":memory:") as connection:
        for migration in DECISIONS_MIGRATIONS:
            for statement in migration.up_sql:
                _ = connection.execute(statement)
        decision_rows: list[tuple[str]] = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        decision_indexes = {row[0] for row in decision_rows}
    assert GLOBAL_INDEXES == frozenset(global_indexes)
    assert DECISIONS_INDEXES == frozenset(decision_indexes)
