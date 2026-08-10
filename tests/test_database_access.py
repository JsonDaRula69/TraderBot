"""Behavioral tests for mode-routed decisions database access."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal

import pytest

from traderbot.db.access import (
    DatabaseAccess,
    DatabaseAccessDeniedError,
    InvalidDatabasePathError,
)
from traderbot.db.pool import SQLiteConnectionPool
from traderbot.db.validation import InvalidStorageNameError
from traderbot.profiles.models import TradingProfile

type Mode = Literal["backtest", "paper", "live"]
type Identity = tuple[TradingProfile, str]


class _RollbackProbeError(RuntimeError):
    pass


def _profile(name: str, mode: Mode) -> TradingProfile:
    return TradingProfile(
        name=name,
        mode=mode,
        description=f"{name} test profile",
        risk_multiplier=0.5,
        max_position_per_market_pct=0.1,
        max_daily_loss_pct=0.05,
        max_drawdown_pct=0.1,
        max_open_positions=2,
        min_liquidity_threshold=10,
        min_edge_pct=1.0,
    )


def _identity(name: str, mode: Mode, agent_id: str | None = None) -> Identity:
    return _profile(name, mode), agent_id or name


def _write_marker(access: DatabaseAccess, identity: Identity, marker: str) -> None:
    with access.writable_decisions(identity) as connection:
        _ = connection.execute("CREATE TABLE access_marker (value TEXT NOT NULL)")
        _ = connection.execute("INSERT INTO access_marker VALUES (?)", (marker,))


def _read_markers(access: DatabaseAccess, identity: Identity) -> list[str]:
    with access.readable_decisions(identity) as connections:
        markers: list[str] = []
        for connection in connections:
            rows: list[tuple[str]] = connection.execute(
                "SELECT value FROM access_marker"
            ).fetchall()
            markers.append(rows[0][0])
        return markers


def test_missing_read_database_returns_no_handles_without_creating_files(tmp_path: Path) -> None:
    # Given: no storage has been deployed for a backtest profile.
    pool = SQLiteConnectionPool()
    access = DatabaseAccess(pool, tmp_path)

    # When: the profile requests readable decisions.
    with access.readable_decisions(_identity("weather", "backtest")) as connections:
        assert connections == ()

    # Then: read access did not synthesize directories or database files.
    assert list(tmp_path.iterdir()) == []
    pool.shutdown()


def test_writable_access_lazily_initializes_and_commits(tmp_path: Path) -> None:
    # Given: a profile with no decisions database.
    pool = SQLiteConnectionPool()
    access = DatabaseAccess(pool, tmp_path)
    identity = _identity("weather", "paper")
    db_path = tmp_path / "paper-weather" / "db" / "decisions.db"

    # When: its first authorized write context exits normally.
    with access.writable_decisions(identity) as connection:
        _ = connection.execute("CREATE TABLE committed_value (value INTEGER)")
        _ = connection.execute("INSERT INTO committed_value VALUES (7)")

    # Then: schema initialization and the caller transaction are committed.
    assert db_path.is_file()
    with access.readable_decisions(identity) as connections:
        assert len(connections) == 1
        assert connections[0].execute("SELECT value FROM committed_value").fetchone() == (7,)
        assert connections[0].execute("SELECT version FROM schema_version").fetchall() == [(1,)]
    pool.shutdown()


def test_writable_access_rolls_back_on_exception(tmp_path: Path) -> None:
    # Given: an initialized decisions database with an empty probe table.
    pool = SQLiteConnectionPool()
    access = DatabaseAccess(pool, tmp_path)
    identity = _identity("weather", "paper")
    with access.writable_decisions(identity) as connection:
        _ = connection.execute("CREATE TABLE rollback_value (value INTEGER)")

    # When: caller code raises after inserting a row.
    with pytest.raises(_RollbackProbeError):
        with access.writable_decisions(identity) as connection:
            _ = connection.execute("INSERT INTO rollback_value VALUES (9)")
            raise _RollbackProbeError

    # Then: the pooled writable transaction was rolled back.
    with access.readable_decisions(identity) as connections:
        assert connections[0].execute("SELECT COUNT(*) FROM rollback_value").fetchone() == (0,)
    pool.shutdown()


@pytest.mark.parametrize("mode", ["backtest", "paper", "live"])
def test_every_readable_handle_rejects_writes_with_sqlite_readonly(
    tmp_path: Path, mode: Mode
) -> None:
    # Given: all databases visible to the requested mode exist.
    pool = SQLiteConnectionPool()
    access = DatabaseAccess(pool, tmp_path)
    for deployed_mode in ("backtest", "paper", "live"):
        _write_marker(access, _identity("weather", deployed_mode), deployed_mode)

    # When/Then: every returned handle is a real SQLite URI read-only connection.
    with access.readable_decisions(_identity("weather", mode)) as connections:
        for connection in connections:
            with pytest.raises(sqlite3.OperationalError) as raised:
                _ = connection.execute("INSERT INTO access_marker VALUES ('forbidden')")
            assert raised.value.sqlite_errorname == "SQLITE_READONLY"
    pool.shutdown()


def test_backtest_reads_backtest_only(tmp_path: Path) -> None:
    pool = SQLiteConnectionPool()
    access = DatabaseAccess(pool, tmp_path)
    for mode in ("backtest", "paper", "live"):
        _write_marker(access, _identity("weather", mode), mode)

    assert _read_markers(access, _identity("weather", "backtest")) == ["backtest"]
    pool.shutdown()


def test_paper_reads_backtest_and_paper_but_not_live(tmp_path: Path) -> None:
    pool = SQLiteConnectionPool()
    access = DatabaseAccess(pool, tmp_path)
    for mode in ("backtest", "paper", "live"):
        _write_marker(access, _identity("weather", mode), mode)

    assert _read_markers(access, _identity("weather", "paper")) == ["backtest", "paper"]
    pool.shutdown()


def test_live_reads_backtest_paper_and_live(tmp_path: Path) -> None:
    pool = SQLiteConnectionPool()
    access = DatabaseAccess(pool, tmp_path)
    for mode in ("backtest", "paper", "live"):
        _write_marker(access, _identity("weather", mode), mode)

    assert _read_markers(access, _identity("weather", "live")) == [
        "backtest",
        "paper",
        "live",
    ]
    pool.shutdown()


def test_category_identity_cannot_read_another_profile_database(tmp_path: Path) -> None:
    # Given: weather and crypto have separate deployed paper databases.
    pool = SQLiteConnectionPool()
    access = DatabaseAccess(pool, tmp_path)
    _write_marker(access, _identity("weather", "paper"), "weather-private")
    _write_marker(access, _identity("crypto", "paper"), "crypto-private")

    # When/Then: crypto's resolved identity sees only crypto's path.
    assert _read_markers(access, _identity("crypto", "paper", "crypto-worker")) == [
        "crypto-private"
    ]
    pool.shutdown()


@pytest.mark.parametrize("invalid_name", ["../weather", "paper_weather", "Weather"])
def test_invalid_profile_identity_raises_typed_error(tmp_path: Path, invalid_name: str) -> None:
    pool = SQLiteConnectionPool()
    access = DatabaseAccess(pool, tmp_path)

    with pytest.raises(InvalidStorageNameError):
        with access.readable_decisions((_profile(invalid_name, "paper"), "worker")):
            pytest.fail("invalid profile identities must not reach storage")
    pool.shutdown()


def test_invalid_agent_identity_raises_typed_error(tmp_path: Path) -> None:
    pool = SQLiteConnectionPool()
    access = DatabaseAccess(pool, tmp_path)

    with pytest.raises(InvalidStorageNameError):
        with access.readable_decisions(_identity("weather", "paper", "../worker")):
            pytest.fail("invalid agent identities must not reach storage")
    pool.shutdown()


def test_symlinked_profile_directory_is_rejected(tmp_path: Path) -> None:
    pool = SQLiteConnectionPool()
    access = DatabaseAccess(pool, tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "paper-weather").symlink_to(outside, target_is_directory=True)

    with pytest.raises(InvalidDatabasePathError):
        with access.readable_decisions(_identity("weather", "paper")):
            pytest.fail("symlinked profile storage must not be opened")
    pool.shutdown()


@pytest.mark.parametrize(
    "identity",
    [(_profile("sysadmin", "paper"), "worker"), (_profile("weather", "paper"), "sysadmin")],
)
def test_partial_sysadmin_identity_is_denied(tmp_path: Path, identity: Identity) -> None:
    pool = SQLiteConnectionPool()
    access = DatabaseAccess(pool, tmp_path)

    with pytest.raises(DatabaseAccessDeniedError):
        with access.all_agent_decisions(identity):
            pytest.fail("only the canonical sysadmin pair may enumerate databases")
    pool.shutdown()


def test_sysadmin_enumerates_existing_databases_only(tmp_path: Path) -> None:
    # Given: two deployed agents and one empty directory that resembles a deployment.
    pool = SQLiteConnectionPool()
    access = DatabaseAccess(pool, tmp_path)
    _write_marker(access, _identity("weather", "backtest"), "weather-backtest")
    _write_marker(access, _identity("crypto", "live"), "crypto-live")
    (tmp_path / "paper-undeployed" / "db").mkdir(parents=True)

    # When: canonical SysAdmin enumerates decisions files.
    with access.all_agent_decisions((_profile("sysadmin", "paper"), "sysadmin")) as connections:
        markers: list[str] = []
        for connection in connections:
            rows: list[tuple[str]] = connection.execute(
                "SELECT value FROM access_marker"
            ).fetchall()
            markers.append(rows[0][0])

    # Then: only existing files were opened and no undeployed path was synthesized.
    assert sorted(markers) == ["crypto-live", "weather-backtest"]
    assert not (tmp_path / "paper-undeployed" / "db" / "decisions.db").exists()
    pool.shutdown()
