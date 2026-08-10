"""Isolated Phase 3 database and Chroma QA probes."""

from __future__ import annotations

import sqlite3
import statistics
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, TypedDict

from traderbot.db.access import DatabaseAccess
from traderbot.db.chroma_store import ChromaStore
from traderbot.db.migrations import (
    GLOBAL_MIGRATIONS,
    Migration,
    apply_migrations,
    init_schema,
    rollback_migration,
)
from traderbot.db.pool import SQLiteConnectionPool
from traderbot.db.security import create_chroma_root
from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.models import TradingProfile

type Mode = Literal["backtest", "paper", "live"]
type JsonValue = str | int | float | bool | None | Sequence["JsonValue"] | dict[str, "JsonValue"]

BENCHMARK_QUERY: Final = (
    "SELECT current_balance_cents FROM portfolio_summary WHERE profile=? AND mode=?"
)
WARMUP_COUNT: Final = 100
SAMPLE_COUNT: Final = 1000


class CheckEvidence(TypedDict):
    passed: bool
    details: dict[str, JsonValue]


class BenchmarkEvidence(TypedDict):
    query: str
    profile: str
    mode: str
    warmup_count: int
    sample_count: int
    median_ms: float
    p95_ms: float
    passed: bool


@dataclass(frozen=True, slots=True)
class IsolationEvidence:
    check: CheckEvidence
    cross_agent_successful_reads: int


def _profile(name: str, mode: Mode) -> TradingProfile:
    return TradingProfile(
        name=name,
        mode=mode,
        description="Phase 3 isolated QA fixture",
        risk_multiplier=0.5,
        max_position_per_market_pct=0.1,
        max_daily_loss_pct=0.05,
        max_drawdown_pct=0.1,
        max_open_positions=2,
        min_liquidity_threshold=10,
        min_edge_pct=1.0,
    )


def _write_marker(access: DatabaseAccess, profile: TradingProfile, value: str) -> None:
    with access.writable_decisions((profile, profile.name)) as connection:
        _ = connection.execute("CREATE TABLE IF NOT EXISTS qa_marker (value TEXT NOT NULL)")
        _ = connection.execute("INSERT INTO qa_marker VALUES (?)", (value,))


def _read_markers(access: DatabaseAccess, profile: TradingProfile) -> list[str]:
    markers: list[str] = []
    with access.readable_decisions((profile, profile.name)) as connections:
        for connection in connections:
            rows: list[tuple[str]] = connection.execute("SELECT value FROM qa_marker").fetchall()
            markers.extend(row[0] for row in rows)
    return markers


def migration_check(data_root: Path) -> CheckEvidence:
    database = data_root / "traderbot.db"
    init_schema(database)
    reapplied = apply_migrations(database, GLOBAL_MIGRATIONS)
    with sqlite3.connect(database) as connection:
        versions: list[tuple[int]] = connection.execute(
            "SELECT version FROM schema_version ORDER BY version"
        ).fetchall()
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
    expected = {
        "schema_version",
        "profiles",
        "config",
        "market_data",
        "orderbook",
        "weather_forecasts",
        "nws_forecasts",
        "settlement_cache",
    }
    return {
        "passed": versions == [(1,)] and tables == expected and reapplied == [],
        "details": {"versions": [row[0] for row in versions], "tables": sorted(tables)},
    }


def rollback_check(data_root: Path) -> CheckEvidence:
    database = data_root / "rollback" / "rollback.db"
    migrations = (
        Migration(1, "first", ("CREATE TABLE first (id INTEGER)",), ("DROP TABLE first",)),
        Migration(2, "second", ("CREATE TABLE second (id INTEGER)",), ("DROP TABLE second",)),
    )
    _ = apply_migrations(database, migrations)
    rolled_back = rollback_migration(database, migrations)
    with sqlite3.connect(database) as connection:
        versions: list[tuple[int]] = connection.execute(
            "SELECT version FROM schema_version ORDER BY version"
        ).fetchall()
        second_exists = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='second'"
        ).fetchone()
    return {
        "passed": rolled_back == 2 and versions == [(1,)] and second_exists == (0,),
        "details": {"rolled_back": rolled_back, "versions": [row[0] for row in versions]},
    }


def isolation_check(data_root: Path, pool: SQLiteConnectionPool) -> IsolationEvidence:
    access = DatabaseAccess(pool, data_root)
    for name in ("qa-weather", "qa-economics"):
        for mode in ("backtest", "paper", "live"):
            _write_marker(access, _profile(name, mode), f"{name}:{mode}")
    weather_paper = _read_markers(access, _profile("qa-weather", "paper"))
    economics_paper = _read_markers(access, _profile("qa-economics", "paper"))
    cross_reads = sum("qa-economics" in value for value in weather_paper) + sum(
        "qa-weather" in value for value in economics_paper
    )
    readonly_rejections = 0
    profile = _profile("qa-weather", "live")
    with access.readable_decisions((profile, profile.name)) as handles:
        readonly_handles = len(handles)
        for connection in handles:
            try:
                _ = connection.execute("INSERT INTO qa_marker VALUES ('forbidden')")
            except sqlite3.OperationalError as error:
                if error.sqlite_errorname == "SQLITE_READONLY":
                    readonly_rejections += 1
    passed = (
        cross_reads == 0
        and "qa-weather:live" not in weather_paper
        and readonly_rejections == readonly_handles
    )
    return IsolationEvidence(
        check={
            "passed": passed,
            "details": {
                "weather_paper": weather_paper,
                "economics_paper": economics_paper,
                "readonly_handles": readonly_handles,
                "readonly_rejections": readonly_rejections,
            },
        },
        cross_agent_successful_reads=cross_reads,
    )


def category_delete_check(data_root: Path) -> CheckEvidence:
    chroma_root = data_root / "chromadb"
    create_chroma_root(chroma_root)
    with ChromaStore(chroma_root) as store:
        store.add(MarketCategory.WEATHER, "news", ["shared"], [[1.0, 0.0, 0.0]], None, None)
        store.add(MarketCategory.ECONOMICS, "news", ["shared"], [[0.0, 1.0, 0.0]], None, None)
        weather_before = store.get(MarketCategory.WEATHER, "news", ["shared"], None, None)
        store.delete(MarketCategory.WEATHER, "news", ["shared"], None)
        weather_after = store.get(MarketCategory.WEATHER, "news", ["shared"], None, None)
        economics_after = store.get(MarketCategory.ECONOMICS, "news", ["shared"], None, None)
    passed = (
        weather_before["ids"] == ["weather:shared"]
        and weather_after["ids"] == []
        and economics_after["ids"] == ["economics:shared"]
    )
    return {
        "passed": passed,
        "details": {
            "weather_before": list(weather_before["ids"]),
            "weather_after": list(weather_after["ids"]),
            "economics_after": list(economics_after["ids"]),
        },
    }


def benchmark(data_root: Path, pool: SQLiteConnectionPool) -> BenchmarkEvidence:
    access = DatabaseAccess(pool, data_root)
    profile = _profile("qa-benchmark", "paper")
    parameters = (profile.name, profile.mode)
    with access.writable_decisions((profile, profile.name)) as connection:
        _ = connection.execute(
            "INSERT INTO portfolio_summary "
            "(profile, mode, initial_balance_cents, current_balance_cents) "
            "VALUES (?, ?, ?, ?)",
            (*parameters, 10_000, 10_123),
        )
    with access.readable_decisions((profile, profile.name)) as connections:
        connection = connections[0]
        for _ in range(WARMUP_COUNT):
            _ = connection.execute(BENCHMARK_QUERY, parameters).fetchone()
        samples: list[int] = []
        valid_results = 0
        for _ in range(SAMPLE_COUNT):
            started = time.perf_counter_ns()
            row = connection.execute(BENCHMARK_QUERY, parameters).fetchone()
            samples.append(time.perf_counter_ns() - started)
            if row == (10_123,):
                valid_results += 1
    median_ms = statistics.median(samples) / 1_000_000
    p95_ms = sorted(samples)[949] / 1_000_000
    return {
        "query": BENCHMARK_QUERY,
        "profile": profile.name,
        "mode": profile.mode,
        "warmup_count": WARMUP_COUNT,
        "sample_count": len(samples),
        "median_ms": median_ms,
        "p95_ms": p95_ms,
        "passed": valid_results == SAMPLE_COUNT and median_ms < 10 and p95_ms < 10,
    }
