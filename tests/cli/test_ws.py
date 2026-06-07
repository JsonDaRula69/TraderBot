"""Tests for the WS daemon CLI commands, primarily `traderbot ws health`."""

from __future__ import annotations

import json
import os

import pytest
from typer.testing import CliRunner

from traderbot.cli import app
from traderbot.cli.ws import _is_pid_alive

runner = CliRunner()


class TestIsPidAlive:
    """Unit tests for _is_pid_alive helper."""

    def test_current_pid_is_alive(self) -> None:
        assert _is_pid_alive(os.getpid()) is True

    def test_nonexistent_pid_is_not_alive(self) -> None:
        assert _is_pid_alive(999999999) is False

    def test_init_pid_is_alive_on_unix(self) -> None:
        if os.name != "posix":
            pytest.skip("Unix-only test")
        assert _is_pid_alive(1) is True


class TestWsHealthCommand:
    """Tests for `traderbot ws health` CLI command."""

    def test_no_status_file_returns_1(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("traderbot.cli.ws.DAEMON_STATUS_PATH", tmp_path / "nonexistent.json")
        result = runner.invoke(app, ["ws", "health"])
        assert result.exit_code == 1
        assert "UNHEALTHY" in result.output
        assert "no status file" in result.output.lower()

    def test_stale_pid_corrects_status_file(self, tmp_path, monkeypatch) -> None:
        status_path = tmp_path / "ws_daemon.json"
        stale_data = {"pid": 999999999, "connected": True, "uptime": 1700000000.0}
        status_path.write_text(json.dumps(stale_data))
        monkeypatch.setattr("traderbot.cli.ws.DAEMON_STATUS_PATH", status_path)

        result = runner.invoke(app, ["ws", "health"])
        assert result.exit_code == 1
        assert "UNHEALTHY" in result.output
        assert "stale" in result.output.lower() or "corrected" in result.output.lower()

        corrected = json.loads(status_path.read_text())
        assert corrected["connected"] is False

    def test_alive_and_connected_returns_0(self, tmp_path, monkeypatch) -> None:
        status_path = tmp_path / "ws_daemon.json"
        healthy_data = {"pid": os.getpid(), "connected": True, "uptime": 1700000000.0}
        status_path.write_text(json.dumps(healthy_data))
        monkeypatch.setattr("traderbot.cli.ws.DAEMON_STATUS_PATH", status_path)

        result = runner.invoke(app, ["ws", "health"])
        assert result.exit_code == 0
        assert "HEALTHY" in result.output

    def test_alive_but_disconnected_returns_1(self, tmp_path, monkeypatch) -> None:
        status_path = tmp_path / "ws_daemon.json"
        degraded_data = {"pid": os.getpid(), "connected": False, "uptime": 1700000000.0}
        status_path.write_text(json.dumps(degraded_data))
        monkeypatch.setattr("traderbot.cli.ws.DAEMON_STATUS_PATH", status_path)

        result = runner.invoke(app, ["ws", "health"])
        assert result.exit_code == 1
        assert "DEGRADED" in result.output

    def test_status_file_missing_pid_returns_1(self, tmp_path, monkeypatch) -> None:
        status_path = tmp_path / "ws_daemon.json"
        status_path.write_text(json.dumps({"connected": True}))
        monkeypatch.setattr("traderbot.cli.ws.DAEMON_STATUS_PATH", status_path)

        result = runner.invoke(app, ["ws", "health"])
        assert result.exit_code == 1
        assert "UNHEALTHY" in result.output
        assert "missing PID" in result.output


class TestWsHealthStep:
    """Tests for step_ws_health in the heartbeat module."""

    def test_no_status_file_returns_not_running(self, tmp_path, monkeypatch) -> None:
        from traderbot.heartbeat import step_ws_health

        monkeypatch.setattr("traderbot.cli.ws.DAEMON_STATUS_PATH", tmp_path / "nonexistent.json")

        result = step_ws_health()
        assert result.status == "not_running"
        assert result.pid is None
        assert result.pid_alive is False

    def test_stale_pid_returns_stale(self, tmp_path, monkeypatch) -> None:
        from traderbot.heartbeat import step_ws_health

        status_path = tmp_path / "ws_daemon.json"
        status_path.write_text(json.dumps({"pid": 999999999, "connected": True}))
        monkeypatch.setattr("traderbot.cli.ws.DAEMON_STATUS_PATH", status_path)

        result = step_ws_health()
        assert result.status == "stale"
        assert result.pid == 999999999
        assert result.pid_alive is False
        assert result.connected is False

        corrected = json.loads(status_path.read_text())
        assert corrected["connected"] is False

    def test_healthy_daemon(self, tmp_path, monkeypatch) -> None:
        from traderbot.heartbeat import step_ws_health

        status_path = tmp_path / "ws_daemon.json"
        status_path.write_text(json.dumps({"pid": os.getpid(), "connected": True}))
        monkeypatch.setattr("traderbot.cli.ws.DAEMON_STATUS_PATH", status_path)

        result = step_ws_health()
        assert result.status == "healthy"
        assert result.pid_alive is True
        assert result.connected is True

    def test_disconnected_daemon(self, tmp_path, monkeypatch) -> None:
        from traderbot.heartbeat import step_ws_health

        status_path = tmp_path / "ws_daemon.json"
        status_path.write_text(json.dumps({"pid": os.getpid(), "connected": False}))
        monkeypatch.setattr("traderbot.cli.ws.DAEMON_STATUS_PATH", status_path)

        result = step_ws_health()
        assert result.status == "disconnected"
        assert result.pid_alive is True
        assert result.connected is False
