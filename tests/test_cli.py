"""Tests for the TraderBot CLI."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from traderbot.cli import app

runner = CliRunner()


class TestMainHelp:
    def test_help_succeeds(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "traderbot" in result.output.lower() or "prediction" in result.output.lower()

    def test_subcommand_help(self):
        for cmd in ["scan", "positions", "audit", "trade", "heartbeat", "halt"]:
            result = runner.invoke(app, [cmd, "--help"])
            assert result.exit_code == 0, f"{cmd} --help failed: {result.output}"


class TestStubCommands:
    STUB_COMMANDS = [
        ("news", "Phase 7"),
        ("sentiment", "Phase 7"),
        ("backtest", "Phase 5"),
        ("paper", "Phase 5"),
        ("compare", "Phase 5"),
        ("performance", "Phase 5"),
        ("learnings", "Phase 6"),
    ]

    @pytest.mark.parametrize("cmd,phase", STUB_COMMANDS)
    def test_stub_not_yet_implemented(self, cmd, phase):
        result = runner.invoke(app, [cmd])
        assert result.exit_code == 0
        assert "Not yet implemented" in result.output
        assert phase in result.output


class TestScan:
    def test_scan_json_without_api(self):
        result = runner.invoke(app, ["scan", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_scan_default_without_api(self):
        result = runner.invoke(app, ["scan"])
        assert result.exit_code == 0
        assert "requires API connection" in result.output or "markets" in result.output.lower()


class TestTrade:
    def test_trade_rejected_with_defaults(self):
        result = runner.invoke(app, ["trade", "TEST-TICKER", "--direction", "yes", "--quantity", "1", "--price", "50"])
        assert result.exit_code == 0
        assert "rejected" in result.output.lower() or "executed" in result.output.lower()

    def test_trade_json_output(self):
        result = runner.invoke(
            app, ["trade", "TEST-TICKER", "--direction", "yes", "--quantity", "1", "--price", "50", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "outcome" in data
        assert data["ticker"] == "TEST-TICKER"
        assert data["outcome"] in ("executed", "rejected")


class TestPositions:
    def test_positions_json_empty(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["positions", "--db", str(db), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 0

    def test_positions_no_json(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["positions", "--db", str(db)])
        assert result.exit_code == 0
        assert "No open positions" in result.output or "positions" in result.output.lower()


class TestAudit:
    def test_audit_json_empty(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["audit", "--db", str(db), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 0

    def test_audit_no_json_empty(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["audit", "--db", str(db)])
        assert result.exit_code == 0
        assert "No decisions found" in result.output or "decision" in result.output.lower()


class TestHeartbeat:
    def test_heartbeat(self):
        result = runner.invoke(app, ["heartbeat"])
        assert result.exit_code == 0
        assert "Heartbeat" in result.output


class TestHalt:
    def test_halt_shows_status(self):
        result = runner.invoke(app, ["halt"])
        assert result.exit_code == 0
        assert "Circuit Breaker" in result.output or "breaker" in result.output.lower()

    def test_halt_json(self):
        result = runner.invoke(app, ["halt", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "level" in data
        assert "can_trade" in data

    def test_halt_force(self, tmp_path):
        state_file = tmp_path / "cb_state.json"
        with patch(
            "traderbot.risk.circuit_breaker.CircuitBreaker.__init__",
            return_value=None,
        ):
            from traderbot.risk.circuit_breaker import BreakerLevel, CircuitBreaker, CircuitBreakerState

            breaker = CircuitBreaker.__new__(CircuitBreaker)
            breaker._state_file = state_file
            breaker._state = CircuitBreakerState()

        with patch("traderbot.risk.circuit_breaker.CircuitBreaker", return_value=breaker):
            result = runner.invoke(app, ["halt", "--force", "--json"])
            assert result.exit_code == 0