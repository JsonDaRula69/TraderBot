from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from tests.deploy_wizard_fakes import FakeEnvironment, FakePhase45, FakePhase678
from traderbot.deploy.backfill_collector import prepare_collector_source
from traderbot.deploy.deploy_state import DeployStateError, load_deploy_state
from traderbot.deploy.phase45_runtime import Phase45Adapter
from traderbot.deploy.phase678_runtime import Phase678Adapter
from traderbot.deploy.wizard_command import execute_deploy
from traderbot.deploy.wizard_contracts import WizardPorts


class CleanupCanaryError(RuntimeError):
    pass


def _collector(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        _ = connection.executescript(
            """
CREATE TABLE weather_forecasts(
  id INTEGER PRIMARY KEY, snapshot_ts TEXT NOT NULL, city TEXT NOT NULL,
  latitude REAL NOT NULL, longitude REAL NOT NULL, model TEXT NOT NULL,
  valid_date TEXT NOT NULL, variable TEXT NOT NULL, value REAL NOT NULL);
CREATE UNIQUE INDEX uq_weather_forecasts
  ON weather_forecasts(snapshot_ts, city, model, valid_date, variable);
CREATE TABLE nws_forecasts(
  id INTEGER PRIMARY KEY, snapshot_ts TEXT NOT NULL, city TEXT NOT NULL,
  forecast_date TEXT NOT NULL, high_temp_f REAL, low_temp_f REAL,
  precip_prob REAL, wind_speed REAL, detailed_forecast TEXT);
CREATE UNIQUE INDEX uq_nws_forecasts
  ON nws_forecasts(snapshot_ts, city, forecast_date);
CREATE TABLE weather_observations(
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, city TEXT NOT NULL,
  latitude REAL NOT NULL, longitude REAL NOT NULL, variable TEXT NOT NULL,
  value REAL NOT NULL);
CREATE UNIQUE INDEX uq_weather_observations
  ON weather_observations(date, city, variable);
"""
        )


def test_prepared_collector_survives_until_step6(tmp_path: Path) -> None:
    # Given: a valid collector is prepared and the original is removed.
    source = tmp_path / "collector.db"
    _collector(source)

    # When: ownership transfers to the late-step adapter.
    with prepare_collector_source(source) as prepared:
        source.unlink()
        adapter = Phase678Adapter(prepared)

        # Then: the exact immutable snapshot remains live for Step 6.
        assert adapter.prepared_collector_path == prepared.path
        assert prepared.path.exists()


def test_prepared_collector_cleanup_occurs_once(tmp_path: Path) -> None:
    # Given: one prepared collector snapshot.
    source = tmp_path / "collector.db"
    _collector(source)

    # When: its owning context exits.
    with prepare_collector_source(source) as prepared:
        snapshot = prepared.path
        assert snapshot.exists()

    # Then: the snapshot is removed without touching the source.
    assert not snapshot.exists()
    assert source.exists()


def test_invalid_collector_precedes_secret_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: config points to an incompatible collector and a forbidden secret factory.
    source = tmp_path / "collector.db"
    _ = source.write_bytes(b"not sqlite")
    config = tmp_path / "deploy.json"
    _ = config.write_text(
        json.dumps(
            {
                "categories": ["weather"],
                "mode": "backtest",
                "collector_db": str(source),
                "data_root": str(tmp_path / "data"),
                "approvals": {
                    "install_openclaw": False,
                    "setup_openclaw": False,
                    "create_agents": False,
                    "heartbeat_change": False,
                    "sandbox_apply": False,
                },
                "heartbeat_every": "preserve",
            }
        )
    )
    calls = 0

    def forbidden(_origin: str) -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr("traderbot.deploy.wizard_command.select_deploy_secrets", forbidden)

    # When: the config crosses the deploy boundary.
    code = execute_deploy(config, True)

    # Then: validation exits 2 before secret construction or state mutation.
    output = capsys.readouterr()
    assert code == 2
    assert calls == 0
    assert output.out == '{"error":"invalid_request"}\n'
    assert not (tmp_path / "data").exists()


def test_cleanup_failure_returns_sanitized_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a complete injected deployment and an owned cleanup failure.
    config = tmp_path / "deploy.json"
    _ = config.write_text(
        json.dumps(
            {
                "categories": ["weather"],
                "mode": "backtest",
                "data_root": str(tmp_path / "data"),
                "category_workspaces": {"weather": str(tmp_path / "weather")},
                "approvals": {
                    "install_openclaw": False,
                    "setup_openclaw": False,
                    "create_agents": True,
                    "heartbeat_change": False,
                    "sandbox_apply": False,
                },
                "heartbeat_every": "preserve",
            }
        )
    )

    class Selection:
        store: None = None

        @staticmethod
        def close() -> None:
            raise CleanupCanaryError("CLEANUP-CANARY")

    environment = FakeEnvironment(phase45=FakePhase45(), phase678=FakePhase678())

    def selection_factory(_origin: str) -> Selection:
        return Selection()

    def ports_factory(
        _store: None,
        _phase45: Phase45Adapter,
    ) -> WizardPorts:
        return environment.ports()

    monkeypatch.setattr(
        "traderbot.deploy.wizard_command.select_deploy_secrets",
        selection_factory,
    )
    monkeypatch.setattr(
        "traderbot.deploy.wizard_command.build_wizard_ports",
        ports_factory,
    )

    # When: the owned selection closes after a successful wizard run.
    code = execute_deploy(config, True)

    # Then: cleanup changes the exit to one and remains sanitized.
    output = capsys.readouterr()
    assert code == 1
    assert output.out == '{"error":"runtime_failure"}\n'
    assert "CANARY" not in output.out + output.err


def test_data_root_file_precedes_secret_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Given: the configured data root is a regular file.
    root = tmp_path / "data"
    _ = root.write_text("not a directory", encoding="utf-8")
    config = tmp_path / "deploy.json"
    _ = config.write_text(
        json.dumps(
            {
                "categories": ["weather"],
                "mode": "backtest",
                "data_root": str(root),
                "approvals": {
                    "install_openclaw": False,
                    "setup_openclaw": False,
                    "create_agents": False,
                    "heartbeat_change": False,
                    "sandbox_apply": False,
                },
                "heartbeat_every": "preserve",
            }
        ),
        encoding="utf-8",
    )
    calls = 0

    def forbidden(_origin: str) -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr("traderbot.deploy.wizard_command.select_deploy_secrets", forbidden)

    # When: config crosses the CLI boundary.
    code = execute_deploy(config, True)

    # Then: it exits invalid before factories.
    assert code == 2
    assert calls == 0
    assert capsys.readouterr().out == '{"error":"invalid_request"}\n'


def test_insecure_state_mode_is_rejected(tmp_path: Path) -> None:
    # Given: deploy state is readable but group/world-readable.
    root = tmp_path / "data"
    root.mkdir(mode=0o700)
    state = root / "deploy-state.json"
    _ = state.write_text(
        '{"schema_version":1,"steps":[],"bootstrap_registered":false}',
        encoding="utf-8",
    )
    state.chmod(0o644)

    # When/Then: state cannot be trusted.
    with pytest.raises(DeployStateError):
        _ = load_deploy_state(root)


@pytest.mark.parametrize("unsafe_kind", ["symlink", "directory", "oversized", "malformed"])
def test_unsafe_deploy_state_is_rejected(tmp_path: Path, unsafe_kind: str) -> None:
    # Given: an owner-only data root with an unsafe state object.
    root = tmp_path / "data"
    root.mkdir(mode=0o700)
    state = root / "deploy-state.json"
    if unsafe_kind == "symlink":
        outside = tmp_path / "outside.json"
        _ = outside.write_text("{}", encoding="utf-8")
        state.symlink_to(outside)
    elif unsafe_kind == "directory":
        state.mkdir()
    elif unsafe_kind == "oversized":
        _ = state.write_bytes(b"x" * 1_048_577)
        state.chmod(0o600)
    else:
        _ = state.write_text("{", encoding="utf-8")
        state.chmod(0o600)

    # When/Then: unsafe state cannot be trusted for resumability.
    with pytest.raises(DeployStateError):
        _ = load_deploy_state(root)


def test_linked_data_root_ancestor_precedes_secret_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Given: the configured root traverses a linked ancestor.
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    linked = tmp_path / "linked"
    linked.symlink_to(outside, target_is_directory=True)
    config = tmp_path / "deploy.json"
    _ = config.write_text(
        json.dumps(
            {
                "categories": ["weather"],
                "mode": "backtest",
                "data_root": str(linked / "data"),
                "approvals": {
                    "install_openclaw": False,
                    "setup_openclaw": False,
                    "create_agents": False,
                    "heartbeat_change": False,
                    "sandbox_apply": False,
                },
                "heartbeat_every": "preserve",
            }
        ),
        encoding="utf-8",
    )
    calls = 0

    def forbidden(_origin: str) -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr("traderbot.deploy.wizard_command.select_deploy_secrets", forbidden)

    # When: the config crosses the CLI boundary.
    code = execute_deploy(config, True)

    # Then: it exits invalid before factories.
    assert code == 2
    assert calls == 0
    assert capsys.readouterr().out == '{"error":"invalid_request"}\n'


def test_descriptor_mode_race_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: lstat sees secure state while fstat sees a substituted public descriptor.
    root = tmp_path / "data"
    root.mkdir(mode=0o700)
    state = root / "deploy-state.json"
    _ = state.write_text(
        '{"schema_version":1,"steps":[],"bootstrap_registered":false}',
        encoding="utf-8",
    )
    state.chmod(0o600)
    actual_fstat = os.fstat

    def public_fstat(descriptor: int) -> os.stat_result:
        info = actual_fstat(descriptor)
        values = list(info)
        mode = int(values[0])
        values[0] = (mode & ~0o777) | 0o644
        return os.stat_result(values)

    monkeypatch.setattr(os, "fstat", public_fstat)

    # When/Then: post-open metadata is independently rejected.
    with pytest.raises(DeployStateError):
        _ = load_deploy_state(root)


def test_cleanup_oserror_is_runtime_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: configuration is valid and owned cleanup raises OSError.
    config = tmp_path / "deploy.json"
    _ = config.write_text(
        json.dumps(
            {
                "categories": ["weather"],
                "mode": "backtest",
                "data_root": str(tmp_path / "data"),
                "category_workspaces": {"weather": str(tmp_path / "weather")},
                "approvals": {
                    "install_openclaw": False,
                    "setup_openclaw": False,
                    "create_agents": True,
                    "heartbeat_change": False,
                    "sandbox_apply": False,
                },
                "heartbeat_every": "preserve",
            }
        ),
        encoding="utf-8",
    )
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=FakePhase678())

    class Selection:
        store: None = None

        @staticmethod
        def close() -> None:
            raise OSError("CLOSE-CANARY")

    def selection_factory(_origin: str) -> Selection:
        return Selection()

    def ports_factory(
        _store: None,
        _phase45: Phase45Adapter,
    ) -> WizardPorts:
        return environment.ports()

    monkeypatch.setattr(
        "traderbot.deploy.wizard_command.select_deploy_secrets",
        selection_factory,
    )
    monkeypatch.setattr(
        "traderbot.deploy.wizard_command.build_wizard_ports",
        ports_factory,
    )

    # When: cleanup runs after the successful wizard.
    code = execute_deploy(config, True)

    # Then: cleanup is runtime failure, not invalid input, and remains redacted.
    output = capsys.readouterr()
    assert code == 1
    assert output.out == '{"error":"runtime_failure"}\n'
    assert "CANARY" not in output.out + output.err
