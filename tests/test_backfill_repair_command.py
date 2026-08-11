from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from tests.test_backfill_kalshi import FakeKalshiHistory, FixedClock
from traderbot.db.pool import SQLiteConnectionPool
from traderbot.deploy import backfill_command
from traderbot.deploy.backfill import BackfillPorts, BackfillRequest
from traderbot.deploy.backfill_command import BackfillCommandOptions, execute_backfill
from traderbot.deploy.backfill_models import BackfillResult
from traderbot.deploy.backfill_ports import BackfillDependencies, BackfillRuntime
from traderbot.deploy.backfill_reporter import JsonReporter
from traderbot.kalshi.models import CutoffTimestamps
from traderbot.secrets.store import SecretsStore


class _CanaryFailure(Exception):
    pass


class _FailingRuntimeKalshi(FakeKalshiHistory):
    def __init__(self, canary: str) -> None:
        super().__init__()
        self._canary = canary

    async def get_historical_cutoff(self) -> CutoffTimestamps:
        raise _CanaryFailure(self._canary)


class _CleanupDependencies:
    def __init__(self, root: Path, canary: str) -> None:
        self.default_collector_path = root / "missing.db"
        self._canary = canary
        self.cleaned = False

    def now(self) -> datetime:
        return FixedClock().now()

    @asynccontextmanager
    async def open_runtime(self) -> AsyncIterator[BackfillRuntime]:
        pool = SQLiteConnectionPool()
        try:
            yield BackfillRuntime(client=_FailingRuntimeKalshi(self._canary), pool=pool)
        finally:
            pool.shutdown()
            self.cleaned = True


def _ports(tmp_path: Path) -> tuple[BackfillPorts, SQLiteConnectionPool]:
    pool = SQLiteConnectionPool()
    return (
        BackfillPorts(
            client=FakeKalshiHistory(),
            pool=pool,
            clock=FixedClock(),
            default_collector_path=tmp_path / "missing-default.db",
        ),
        pool,
    )


def test_explicit_missing_source_exits_two_without_dependency_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "target-parent" / "target.db"
    calls = 0

    def forbidden_factory() -> tuple[SecretsStore, str]:
        nonlocal calls
        calls += 1
        raise _CanaryFailure("factory must remain lazy")

    monkeypatch.setattr(backfill_command, "build_secrets_store_selection", forbidden_factory)
    code = execute_backfill(
        BackfillCommandOptions(
            months=6,
            collector_db=tmp_path / "missing-explicit.db",
            target_db=target,
            json_output=True,
        )
    )

    output = capsys.readouterr()
    assert code == 2
    assert calls == 0
    assert json.loads(output.out)["status"] == "invalid_input"
    assert output.err == ""
    assert not target.parent.exists()


@pytest.mark.parametrize("failure_type", [KeyError, _CanaryFailure, OSError])
def test_unexpected_run_exception_is_exhaustively_redacted_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    failure_type: type[Exception],
) -> None:
    canary = f"UNEXPECTED-{uuid4()}"

    async def fail_run(
        request: BackfillRequest, dependencies: BackfillDependencies
    ) -> BackfillResult:
        _ = (request, dependencies)
        raise failure_type(canary)

    monkeypatch.setattr(backfill_command, "run_backfill", fail_run)
    ports, pool = _ports(tmp_path)
    caplog.set_level(logging.DEBUG)
    try:
        code = execute_backfill(
            BackfillCommandOptions(
                months=6,
                target_db=tmp_path / "target.db",
                json_output=True,
            ),
            ports,
        )
    finally:
        pool.shutdown()

    output = capsys.readouterr()
    payload = json.loads(output.out)
    observed = output.out + output.err + caplog.text + repr(payload) + json.dumps(payload)
    assert code == 1
    assert payload["status"] == "failure"
    assert payload["failures"][0]["code"] == "runtime_failure"
    assert len(output.out.splitlines()) == 1
    assert canary not in observed
    assert failure_type.__name__ not in observed


def test_unexpected_run_exception_is_redacted_in_human_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canary = f"HUMAN-{uuid4()}"

    async def fail_run(
        request: BackfillRequest, dependencies: BackfillDependencies
    ) -> BackfillResult:
        _ = (request, dependencies)
        raise _CanaryFailure(canary)

    monkeypatch.setattr(backfill_command, "run_backfill", fail_run)
    ports, pool = _ports(tmp_path)
    try:
        code = execute_backfill(
            BackfillCommandOptions(months=6, target_db=tmp_path / "target.db"), ports
        )
    finally:
        pool.shutdown()

    output = capsys.readouterr()
    assert code == 1
    assert output.out == ""
    assert "runtime_failure" in output.err
    assert canary not in output.err


def test_unexpected_reporter_exception_uses_safe_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canary = f"RENDER-{uuid4()}"

    def fail_render(reporter: JsonReporter, result: BackfillResult) -> None:
        _ = (reporter, result)
        raise _CanaryFailure(canary)

    monkeypatch.setattr(backfill_command.JsonReporter, "render", fail_render)
    ports, pool = _ports(tmp_path)
    try:
        code = execute_backfill(
            BackfillCommandOptions(
                months=6,
                target_db=tmp_path / "target.db",
                json_output=True,
            ),
            ports,
        )
    finally:
        pool.shutdown()

    output = capsys.readouterr()
    assert code == 1
    assert json.loads(output.out)["failures"][0]["code"] == "runtime_failure"
    assert len(output.out.splitlines()) == 1
    assert canary not in output.out + output.err


def test_unexpected_runtime_exception_cleans_dependencies_before_redaction(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    canary = f"CLEANUP-{uuid4()}"
    dependencies = _CleanupDependencies(tmp_path, canary)

    code = execute_backfill(
        BackfillCommandOptions(
            months=6,
            target_db=tmp_path / "target.db",
            json_output=True,
        ),
        dependencies,
    )

    output = capsys.readouterr()
    assert code == 1
    assert dependencies.cleaned
    assert canary not in output.out + output.err


def test_new_target_under_symlinked_system_temp_root_is_allowed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ports, pool = _ports(tmp_path)
    try:
        code = execute_backfill(
            BackfillCommandOptions(
                months=6,
                target_db=tmp_path / "new-target.db",
                json_output=True,
            ),
            ports,
        )
    finally:
        pool.shutdown()

    output = capsys.readouterr()
    assert code == 0
    assert json.loads(output.out)["status"] == "complete"
