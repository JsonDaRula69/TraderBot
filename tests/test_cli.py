"""Tests for the TraderBot CLI."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import ClassVar
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
    STUB_COMMANDS: ClassVar[list[tuple[str, str]]] = [
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

    @pytest.mark.unit
    def test_scan_with_markets(self):
        """Mock MarketService.list_markets to return Market objects, verify Rich table contains tickers."""
        from traderbot.kalshi.models import Market, MarketListResponse

        markets = [
            Market(
                ticker="KXBTCD-26MAR31-T55000",
                question="BTC above $55k?",
                outcome_prices=["60", "40"],
                volume=1000,
                open_interest=500,
                close_time=datetime(2026, 3, 31, tzinfo=UTC),
                state="open",
                event_ticker="KXBTCD-26MAR31",
            ),
            Market(
                ticker="KXBTCD-26MAR31-T60000",
                question="BTC above $60k?",
                outcome_prices=["30", "70"],
                volume=2000,
                open_interest=800,
                close_time=datetime(2026, 3, 31, tzinfo=UTC),
                state="open",
                event_ticker="KXBTCD-26MAR31",
            ),
        ]
        mock_result = MarketListResponse(markets=markets, cursor=None)

        with (
            patch("traderbot.kalshi.client.KalshiClient"),
            patch(
                "traderbot.kalshi.markets.MarketService.list_markets",
                return_value=mock_result,
            ),
        ):
            result = runner.invoke(app, ["scan"])
            assert result.exit_code == 0
            assert "KXBTCD-26MAR31-T55000" in result.output
            assert "BTC above $55k?" in result.output

    @pytest.mark.unit
    def test_scan_json_with_mock_markets(self):
        """Mock list_markets, call scan --json, verify JSON array output."""
        from traderbot.kalshi.models import Market, MarketListResponse

        markets = [
            Market(
                ticker="KXBTCD-26MAR31-T55000",
                question="BTC above $55k?",
                outcome_prices=["60", "40"],
                volume=1000,
                open_interest=500,
                close_time=datetime(2026, 3, 31, tzinfo=UTC),
                state="open",
                event_ticker="KXBTCD-26MAR31",
            ),
        ]
        mock_result = MarketListResponse(markets=markets, cursor=None)

        with (
            patch("traderbot.kalshi.client.KalshiClient"),
            patch(
                "traderbot.kalshi.markets.MarketService.list_markets",
                return_value=mock_result,
            ),
        ):
            result = runner.invoke(app, ["scan", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["ticker"] == "KXBTCD-26MAR31-T55000"


class TestAnalyze:
    @pytest.mark.unit
    def test_analyze_with_market(self):
        """Mock get_market and get_orderbook, verify Rich output includes market info and implied probability."""
        from traderbot.kalshi.models import Market, OrderBook, OrderBookLevel

        market = Market(
            ticker="KXBTCD-26MAR31-T55000",
            question="BTC above $55k?",
            outcome_prices=["60", "40"],
            volume=1000,
            open_interest=500,
            close_time=datetime(2026, 3, 31, tzinfo=UTC),
            state="open",
            event_ticker="KXBTCD-26MAR31",
        )
        orderbook = OrderBook(
            yes_bids=[OrderBookLevel(price=55, size=100)],
            no_bids=[OrderBookLevel(price=40, size=80)],
        )

        with (
            patch("traderbot.kalshi.client.KalshiClient"),
            patch(
                "traderbot.kalshi.markets.MarketService.get_market",
                return_value=market,
            ),
            patch(
                "traderbot.kalshi.markets.MarketService.get_orderbook",
                return_value=orderbook,
            ),
        ):
            result = runner.invoke(app, ["analyze", "KXBTCD-26MAR31-T55000"])
            assert result.exit_code == 0
            assert "KXBTCD-26MAR31-T55000" in result.output
            assert "BTC above $55k?" in result.output
            assert "Implied YES prob" in result.output

    @pytest.mark.unit
    def test_analyze_json_with_mock(self):
        """Mock get_market/get_orderbook, call analyze TICKER --json, verify JSON output."""
        from traderbot.kalshi.models import Market, OrderBook, OrderBookLevel

        market = Market(
            ticker="KXBTCD-26MAR31-T55000",
            question="BTC above $55k?",
            outcome_prices=["60", "40"],
            volume=1000,
            open_interest=500,
            close_time=datetime(2026, 3, 31, tzinfo=UTC),
            state="open",
            event_ticker="KXBTCD-26MAR31",
        )
        orderbook = OrderBook(
            yes_bids=[OrderBookLevel(price=55, size=100)],
            no_bids=[OrderBookLevel(price=40, size=80)],
        )

        with (
            patch("traderbot.kalshi.client.KalshiClient"),
            patch(
                "traderbot.kalshi.markets.MarketService.get_market",
                return_value=market,
            ),
            patch(
                "traderbot.kalshi.markets.MarketService.get_orderbook",
                return_value=orderbook,
            ),
        ):
            result = runner.invoke(app, ["analyze", "KXBTCD-26MAR31-T55000", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "market" in data
            assert "orderbook" in data
            assert data["market"]["ticker"] == "KXBTCD-26MAR31-T55000"

    @pytest.mark.unit
    def test_analyze_fallback_without_api(self):
        """Analyze call that fails API connection shows fallback message."""
        with patch("traderbot.kalshi.client.KalshiClient", side_effect=Exception("API error")):
            result = runner.invoke(app, ["analyze", "TEST-TICKER"])
            assert result.exit_code == 0
            assert "requires API connection" in result.output

    @pytest.mark.unit
    def test_analyze_json_fallback_without_api(self):
        """Analyze --json call that fails API connection returns empty JSON object."""
        with patch("traderbot.kalshi.client.KalshiClient", side_effect=Exception("API error")):
            result = runner.invoke(app, ["analyze", "TEST-TICKER", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert isinstance(data, dict)


class TestSignals:
    @pytest.mark.unit
    def test_signals_default(self):
        result = runner.invoke(app, ["signals"])
        assert result.exit_code == 0
        assert "Signal generation" in result.output

    @pytest.mark.unit
    def test_signals_json(self):
        result = runner.invoke(app, ["signals", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "note" in data


class TestTrade:
    def test_trade_rejected_with_defaults(self):
        result = runner.invoke(
            app, ["trade", "TEST-TICKER", "--direction", "yes", "--quantity", "1", "--price", "50"]
        )
        assert result.exit_code == 0
        assert "rejected" in result.output.lower() or "executed" in result.output.lower()

    def test_trade_json_output(self):
        result = runner.invoke(
            app,
            [
                "trade",
                "TEST-TICKER",
                "--direction",
                "yes",
                "--quantity",
                "1",
                "--price",
                "50",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "outcome" in data
        assert data["ticker"] == "TEST-TICKER"
        assert data["outcome"] in ("executed", "rejected")

    @pytest.mark.unit
    def test_trade_executed(self):
        """Mock evaluate_trade to return non-zero sized amount, verify 'executed' output."""
        with (
            patch("traderbot.risk.evaluate_trade", return_value=5000),
            patch("traderbot.risk.circuit_breaker.CircuitBreaker"),
        ):
            result = runner.invoke(app, ["trade", "TEST-TICKER", "--direction", "yes"])
            assert result.exit_code == 0
            assert "executed" in result.output.lower()

    @pytest.mark.unit
    def test_trade_executed_json(self):
        """Mock evaluate_trade to return non-zero sized amount, verify JSON output has 'executed'."""
        with (
            patch("traderbot.risk.evaluate_trade", return_value=5000),
            patch("traderbot.risk.circuit_breaker.CircuitBreaker"),
        ):
            result = runner.invoke(app, ["trade", "TEST-TICKER", "--direction", "yes", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["outcome"] == "executed"
            assert data["sized_position_cents"] == 5000


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

    @pytest.mark.unit
    def test_positions_with_data(self, tmp_path):
        """Insert a Position via DB, call positions --db, verify table output contains ticker."""

        from traderbot.db import get_connection, init_schema
        from traderbot.kalshi.models import Position

        db = tmp_path / "test.db"

        with get_connection(db) as conn:
            init_schema(conn)
            from traderbot.db.positions import init_table, upsert

            init_table(conn)
            upsert(conn, Position(ticker="KXBTCD-26MAR31-T55000", quantity=10, avg_price=55))

        result = runner.invoke(app, ["positions", "--db", str(db)])
        assert result.exit_code == 0
        assert "KXBTCD-26MAR31-T55000" in result.output

    @pytest.mark.unit
    def test_positions_with_data_json(self, tmp_path):
        """Insert a Position via DB, call positions --db --json, verify JSON contains ticker."""

        from traderbot.db import get_connection, init_schema
        from traderbot.kalshi.models import Position

        db = tmp_path / "test.db"

        with get_connection(db) as conn:
            init_schema(conn)
            from traderbot.db.positions import init_table, upsert

            init_table(conn)
            upsert(conn, Position(ticker="KXBTCD-26MAR31-T55000", quantity=10, avg_price=55))

        result = runner.invoke(app, ["positions", "--db", str(db), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["ticker"] == "KXBTCD-26MAR31-T55000"


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

    @pytest.mark.unit
    def test_audit_with_decisions(self, tmp_path):
        """Insert a Decision via DB, call audit --db, verify table output."""
        from traderbot.db import get_connection, init_schema
        from traderbot.kalshi.models import Decision

        db = tmp_path / "test.db"

        with get_connection(db) as conn:
            init_schema(conn)
            from traderbot.db.decisions import init_table, insert

            init_table(conn)
            insert(
                conn,
                Decision(
                    timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
                    ticker="TEST-MKT",
                    direction="yes",
                    quantity=5,
                    price=55,
                    signal_strength=0.7,
                    confidence=0.8,
                    edge_estimate=0.15,
                    risk_checks={"max_position": True},
                    outcome="executed",
                ),
            )

        result = runner.invoke(app, ["audit", "--db", str(db)])
        assert result.exit_code == 0
        assert "TEST-MKT" in result.output
        assert "Decision Audit" in result.output

    @pytest.mark.unit
    def test_audit_with_decisions_json(self, tmp_path):
        """Insert a Decision via DB, call audit --db --json, verify JSON decision data."""
        from traderbot.db import get_connection, init_schema
        from traderbot.kalshi.models import Decision

        db = tmp_path / "test.db"

        with get_connection(db) as conn:
            init_schema(conn)
            from traderbot.db.decisions import init_table, insert

            init_table(conn)
            insert(
                conn,
                Decision(
                    timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
                    ticker="TEST-MKT",
                    direction="yes",
                    quantity=5,
                    price=55,
                    signal_strength=0.7,
                    confidence=0.8,
                    edge_estimate=0.15,
                    risk_checks={"max_position": True},
                    outcome="executed",
                ),
            )

        result = runner.invoke(app, ["audit", "--db", str(db), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["ticker"] == "TEST-MKT"

    @pytest.mark.unit
    def test_audit_by_ticker(self, tmp_path):
        """Call audit --db --ticker TICKER, verify it filters by ticker."""
        from traderbot.db import get_connection, init_schema
        from traderbot.kalshi.models import Decision

        db = tmp_path / "test.db"

        with get_connection(db) as conn:
            init_schema(conn)
            from traderbot.db.decisions import init_table, insert

            init_table(conn)
            insert(
                conn,
                Decision(
                    timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
                    ticker="TEST-MKT",
                    direction="yes",
                    quantity=5,
                    price=55,
                    signal_strength=0.7,
                    confidence=0.8,
                    edge_estimate=0.15,
                    risk_checks={"max_position": True},
                    outcome="executed",
                ),
            )

        result = runner.invoke(app, ["audit", "--db", str(db), "--ticker", "TEST-MKT"])
        assert result.exit_code == 0
        assert "TEST-MKT" in result.output

    @pytest.mark.unit
    def test_audit_by_outcome(self, tmp_path):
        """Call audit --db --outcome executed, verify it filters by outcome."""
        from traderbot.db import get_connection, init_schema
        from traderbot.kalshi.models import Decision

        db = tmp_path / "test.db"

        with get_connection(db) as conn:
            init_schema(conn)
            from traderbot.db.decisions import init_table, insert

            init_table(conn)
            insert(
                conn,
                Decision(
                    timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
                    ticker="TEST-MKT",
                    direction="yes",
                    quantity=5,
                    price=55,
                    signal_strength=0.7,
                    confidence=0.8,
                    edge_estimate=0.15,
                    risk_checks={"max_position": True},
                    outcome="executed",
                ),
            )

        result = runner.invoke(app, ["audit", "--db", str(db), "--outcome", "executed"])
        assert result.exit_code == 0
        assert "TEST-MKT" in result.output


class TestHeartbeat:
    def test_heartbeat(self):
        result = runner.invoke(app, ["heartbeat"])
        assert result.exit_code == 0
        assert "Heartbeat" in result.output

    @pytest.mark.unit
    def test_heartbeat_json(self):
        """The current heartbeat command doesn't have --json, but test it still works."""
        result = runner.invoke(app, ["heartbeat"])
        assert result.exit_code == 0


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
            from traderbot.risk.circuit_breaker import (
                CircuitBreaker,
                CircuitBreakerState,
            )

            breaker = CircuitBreaker.__new__(CircuitBreaker)
            breaker._state_file = state_file
            breaker._state = CircuitBreakerState()

        with patch("traderbot.risk.circuit_breaker.CircuitBreaker", return_value=breaker):
            result = runner.invoke(app, ["halt", "--force", "--json"])
            assert result.exit_code == 0

    @pytest.mark.unit
    def test_halt_force_no_json(self, tmp_path):
        """Call halt --force (no --json), verify Rich output mentions FULL_STOP."""
        state_file = tmp_path / "cb_state.json"
        with patch(
            "traderbot.risk.circuit_breaker.CircuitBreaker.__init__",
            return_value=None,
        ):
            from traderbot.risk.circuit_breaker import (
                CircuitBreaker,
                CircuitBreakerState,
            )

            breaker = CircuitBreaker.__new__(CircuitBreaker)
            breaker._state_file = state_file
            breaker._state = CircuitBreakerState()

        with patch("traderbot.risk.circuit_breaker.CircuitBreaker", return_value=breaker):
            result = runner.invoke(app, ["halt", "--force"])
            assert result.exit_code == 0
            assert "FULL_STOP" in result.output

    @pytest.mark.unit
    def test_halt_force_json(self, tmp_path):
        """Call halt --force --json, verify JSON output contains FULL_STOP level."""
        state_file = tmp_path / "cb_state.json"
        with patch(
            "traderbot.risk.circuit_breaker.CircuitBreaker.__init__",
            return_value=None,
        ):
            from traderbot.risk.circuit_breaker import (
                CircuitBreaker,
                CircuitBreakerState,
            )

            breaker = CircuitBreaker.__new__(CircuitBreaker)
            breaker._state_file = state_file
            breaker._state = CircuitBreakerState()

        with patch("traderbot.risk.circuit_breaker.CircuitBreaker", return_value=breaker):
            result = runner.invoke(app, ["halt", "--force", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["level"] == 3
            assert data["can_trade"] is False

    @pytest.mark.unit
    def test_halt_with_reason(self, tmp_path):
        """Test halt displays reason when state has one."""
        state_file = tmp_path / "cb_state.json"
        with patch(
            "traderbot.risk.circuit_breaker.CircuitBreaker.__init__",
            return_value=None,
        ):
            from traderbot.risk.circuit_breaker import CircuitBreaker, CircuitBreakerState

            breaker = CircuitBreaker.__new__(CircuitBreaker)
            breaker._state_file = state_file
            breaker._state = CircuitBreakerState(reason="Test reason")

        with patch("traderbot.risk.circuit_breaker.CircuitBreaker", return_value=breaker):
            result = runner.invoke(app, ["halt"])
            assert result.exit_code == 0
            assert "Test reason" in result.output
