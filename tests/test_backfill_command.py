from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_backfill_kalshi import FakeKalshiHistory, FixedClock
from traderbot.db.pool import SQLiteConnectionPool
from traderbot.deploy.backfill import BackfillPorts
from traderbot.deploy.backfill_command import BackfillCommandOptions, execute_backfill
from traderbot.kalshi.models import CutoffTimestamps


def test_json_command_writes_exactly_one_stdout_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pool = SQLiteConnectionPool()
    ports = BackfillPorts(
        client=FakeKalshiHistory(),
        pool=pool,
        clock=FixedClock(),
        default_collector_path=tmp_path / "missing-default.db",
    )
    try:
        code = execute_backfill(
            BackfillCommandOptions(months=6, json_output=True, target_db=tmp_path / "target.db"),
            ports,
        )
    finally:
        pool.shutdown()

    output = capsys.readouterr()
    assert code == 0
    assert output.err == ""
    assert len(output.out.splitlines()) == 1
    assert json.loads(output.out)["status"] == "complete"


def test_invalid_months_json_exits_two_without_target_write(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "target.db"
    pool = SQLiteConnectionPool()
    ports = BackfillPorts(
        client=FakeKalshiHistory(),
        pool=pool,
        clock=FixedClock(),
        default_collector_path=tmp_path / "missing-default.db",
    )
    try:
        code = execute_backfill(
            BackfillCommandOptions(months=0, json_output=True, target_db=target), ports
        )
    finally:
        pool.shutdown()

    output = capsys.readouterr()
    assert code == 2
    assert json.loads(output.out)["status"] == "invalid_input"
    assert not target.exists()


def test_human_command_renders_only_to_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pool = SQLiteConnectionPool()
    ports = BackfillPorts(
        client=FakeKalshiHistory(),
        pool=pool,
        clock=FixedClock(),
        default_collector_path=tmp_path / "missing-default.db",
    )
    try:
        code = execute_backfill(
            BackfillCommandOptions(months=6, target_db=tmp_path / "human.db"), ports
        )
    finally:
        pool.shutdown()

    output = capsys.readouterr()
    assert code == 0
    assert output.out == ""
    assert "TraderBot Backfill" in output.err


def test_unexpected_runtime_failure_is_typed_and_redacted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    class RuntimeFailingKalshi(FakeKalshiHistory):
        async def get_historical_cutoff(self) -> CutoffTimestamps:
            raise RuntimeError("secret-value-must-not-leak")

    pool = SQLiteConnectionPool()
    ports = BackfillPorts(
        client=RuntimeFailingKalshi(),
        pool=pool,
        clock=FixedClock(),
        default_collector_path=tmp_path / "missing-default.db",
    )
    try:
        code = execute_backfill(
            BackfillCommandOptions(months=6, json_output=True, target_db=tmp_path / "fail.db"),
            ports,
        )
    finally:
        pool.shutdown()

    output = capsys.readouterr()
    assert code == 1
    assert json.loads(output.out)["status"] == "failure"
    assert "secret-value-must-not-leak" not in output.out + output.err
