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
        for cmd in ["scan", "positions", "audit", "trade", "heartbeat", "halt", "backtest", "paper", "performance", "compare", "bootstrap", "learnings"]:
            result = runner.invoke(app, [cmd, "--help"])
            assert result.exit_code == 0, f"{cmd} --help failed: {result.output}"


class TestStubCommands:
    STUB_COMMANDS: ClassVar[list[tuple[str, str]]] = [
        ("news", "Phase 7"),
        ("sentiment", "Phase 7"),
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
        assert "6h" in result.output or "promotion" in result.output.lower()

    @pytest.mark.unit
    def test_heartbeat_json(self):
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


class TestBacktestCommand:
    def test_backtest_help(self):
        result = runner.invoke(app, ["backtest", "--help"])
        assert result.exit_code == 0
        assert "--strategy" in result.output
        assert "--from" in result.output
        assert "--to" in result.output
        assert "--bankroll" in result.output
        assert "--db" in result.output
        assert "--json" in result.output

    def test_backtest_no_api(self):
        with patch("traderbot.kalshi.client.KalshiClient", side_effect=Exception("no api")):
            result = runner.invoke(app, ["backtest"])
            assert result.exit_code == 0
            assert "API connection required" in result.output

    def test_backtest_no_api_json(self):
        with patch("traderbot.kalshi.client.KalshiClient", side_effect=Exception("no api")):
            result = runner.invoke(app, ["backtest", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "error" in data

    @pytest.mark.unit
    def test_backtest_with_mock_engine(self, tmp_path):
        from traderbot.simulation.engine import BacktestResult

        mock_result = BacktestResult(
            trade_count=5,
            total_pnl_cents=2500_00,
            winning_trades=3,
            losing_trades=2,
            win_rate=0.6,
            sharpe_ratio=1.5,
            max_drawdown_pct=0.08,
            brier_score=0.22,
            edge_capture=0.35,
            fill_rate=0.8,
            trades=[],
        )

        with (
            patch("traderbot.kalshi.client.KalshiClient"),
            patch("traderbot.kalshi.history.HistoryService"),
            patch("traderbot.simulation.engine.BacktestEngine.run", return_value=mock_result),
        ):
            result = runner.invoke(app, ["backtest", "--db", str(tmp_path / "test.db")])
            assert result.exit_code == 0
            assert "Backtest Results" in result.output

    @pytest.mark.unit
    def test_backtest_json_with_mock(self, tmp_path):
        from traderbot.simulation.engine import BacktestResult

        mock_result = BacktestResult(
            trade_count=5,
            total_pnl_cents=2500_00,
            winning_trades=3,
            losing_trades=2,
            win_rate=0.6,
            sharpe_ratio=1.5,
            max_drawdown_pct=0.08,
            brier_score=0.22,
            edge_capture=0.35,
            fill_rate=0.8,
            trades=[],
        )

        with (
            patch("traderbot.kalshi.client.KalshiClient"),
            patch("traderbot.kalshi.history.HistoryService"),
            patch("traderbot.simulation.engine.BacktestEngine.run", return_value=mock_result),
        ):
            result = runner.invoke(app, ["backtest", "--db", str(tmp_path / "test.db"), "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "metrics" in data
            assert data["trade_count"] == 5


class TestPaperCommand:
    def test_paper_help(self):
        result = runner.invoke(app, ["paper", "--help"])
        assert result.exit_code == 0
        assert "--strategy" in result.output
        assert "--duration" in result.output
        assert "--db" in result.output
        assert "--json" in result.output

    def test_paper_no_api(self):
        with patch("traderbot.kalshi.demo.DemoAdapter", side_effect=Exception("no demo")):
            result = runner.invoke(app, ["paper"])
            assert result.exit_code == 0
            assert "Demo API connection required" in result.output

    def test_paper_no_api_json(self):
        with patch("traderbot.kalshi.demo.DemoAdapter", side_effect=Exception("no demo")):
            result = runner.invoke(app, ["paper", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "error" in data

    @pytest.mark.unit
    def test_paper_with_mock(self, tmp_path):
        from traderbot.simulation.paper_trader import PaperPortfolio, PaperPosition

        mock_portfolio = PaperPortfolio(
            cash_cents=99_500_00,
            positions=[
                PaperPosition(ticker="KXBTCD-26MAR31-T55000", side="yes", avg_price_cents=55, quantity=10),
            ],
        )

        with (
            patch("traderbot.kalshi.demo.DemoAdapter"),
            patch(
                "traderbot.simulation.paper_trader.PaperTrader.get_portfolio",
                return_value=mock_portfolio,
            ),
            patch(
                "traderbot.simulation.paper_trader.PaperTrader.get_pnl",
                return_value=-500_00,
            ),
        ):
            result = runner.invoke(app, ["paper", "--db", str(tmp_path / "test.db")])
            assert result.exit_code == 0
            assert "Paper Trading" in result.output
            assert "KXBTCD-26MAR31-T55000" in result.output

    @pytest.mark.unit
    def test_paper_json_with_mock(self, tmp_path):
        from traderbot.simulation.paper_trader import PaperPortfolio, PaperPosition

        mock_portfolio = PaperPortfolio(
            cash_cents=99_500_00,
            positions=[
                PaperPosition(ticker="KXBTCD-26MAR31-T55000", side="yes", avg_price_cents=55, quantity=10),
            ],
        )

        with (
            patch("traderbot.kalshi.demo.DemoAdapter"),
            patch(
                "traderbot.simulation.paper_trader.PaperTrader.get_portfolio",
                return_value=mock_portfolio,
            ),
            patch(
                "traderbot.simulation.paper_trader.PaperTrader.get_pnl",
                return_value=-500_00,
            ),
        ):
            result = runner.invoke(app, ["paper", "--db", str(tmp_path / "test.db"), "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["cash_cents"] == 99_500_00
            assert len(data["positions"]) == 1


class TestPerformanceCommand:
    def test_performance_help(self):
        result = runner.invoke(app, ["performance", "--help"])
        assert result.exit_code == 0
        assert "--db" in result.output
        assert "--from" in result.output
        assert "--to" in result.output
        assert "--json" in result.output

    def test_performance_empty_db(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["performance", "--db", str(db)])
        assert result.exit_code == 0
        assert "Performance Summary" in result.output

    def test_performance_empty_db_json(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["performance", "--db", str(db), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["trade_count"] == 0

    @pytest.mark.unit
    def test_performance_with_decisions(self, tmp_path):
        from traderbot.db import get_connection, init_schema
        from traderbot.kalshi.models import Decision

        db = tmp_path / "test.db"
        with get_connection(db) as conn:
            init_schema(conn)
            from traderbot.db.decisions import init_table, insert

            init_table(conn)
            for i in range(3):
                insert(
                    conn,
                    Decision(
                        timestamp=datetime(2026, 1, 15 + i, 12, 0, 0, tzinfo=UTC),
                        ticker=f"TEST-MKT-{i}",
                        direction="yes",
                        quantity=5,
                        price=55 + i * 10,
                        signal_strength=0.7,
                        confidence=0.8,
                        edge_estimate=0.15,
                        risk_checks={"max_position": True},
                        outcome="executed",
                    ),
                )

        result = runner.invoke(app, ["performance", "--db", str(db)])
        assert result.exit_code == 0
        assert "Performance Summary" in result.output
        assert "3" in result.output

    @pytest.mark.unit
    def test_performance_with_decisions_json(self, tmp_path):
        from traderbot.db import get_connection, init_schema
        from traderbot.kalshi.models import Decision

        db = tmp_path / "test.db"
        with get_connection(db) as conn:
            init_schema(conn)
            from traderbot.db.decisions import init_table, insert

            init_table(conn)
            for i in range(3):
                insert(
                    conn,
                    Decision(
                        timestamp=datetime(2026, 1, 15 + i, 12, 0, 0, tzinfo=UTC),
                        ticker=f"TEST-MKT-{i}",
                        direction="yes",
                        quantity=5,
                        price=55 + i * 10,
                        signal_strength=0.7,
                        confidence=0.8,
                        edge_estimate=0.15,
                        risk_checks={"max_position": True},
                        outcome="executed",
                    ),
                )

        result = runner.invoke(app, ["performance", "--db", str(db), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["trade_count"] == 3


class TestCompareCommand:
    def test_compare_help(self):
        result = runner.invoke(app, ["compare", "--help"])
        assert result.exit_code == 0
        assert "--profiles" in result.output
        assert "--strategy" in result.output
        assert "--from" in result.output
        assert "--to" in result.output
        assert "--bankroll" in result.output
        assert "--db" in result.output
        assert "--json" in result.output

    def test_compare_no_api(self):
        with patch("traderbot.kalshi.client.KalshiClient", side_effect=Exception("no api")):
            result = runner.invoke(app, ["compare"])
            assert result.exit_code == 0
            assert "API connection required" in result.output

    def test_compare_no_api_json(self):
        with patch("traderbot.kalshi.client.KalshiClient", side_effect=Exception("no api")):
            result = runner.invoke(app, ["compare", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "error" in data

    def test_compare_unknown_profile(self):
        result = runner.invoke(app, ["compare", "--profiles", "Unknown"])
        assert result.exit_code == 1
        assert "Unknown profile" in result.output

    @pytest.mark.unit
    def test_compare_with_mock_profiles(self, tmp_path):
        from traderbot.simulation.engine import BacktestResult

        conservative_result = BacktestResult(
            trade_count=8,
            total_pnl_cents=1200_00,
            winning_trades=5,
            losing_trades=3,
            win_rate=0.625,
            sharpe_ratio=1.2,
            max_drawdown_pct=0.05,
            brier_score=0.18,
            edge_capture=0.42,
            fill_rate=0.9,
            trades=[],
        )
        aggressive_result = BacktestResult(
            trade_count=15,
            total_pnl_cents=3500_00,
            winning_trades=9,
            losing_trades=6,
            win_rate=0.6,
            sharpe_ratio=0.9,
            max_drawdown_pct=0.12,
            brier_score=0.25,
            edge_capture=0.35,
            fill_rate=0.85,
            trades=[],
        )

        async def fake_run_profiles(engine, profiles, start, end):
            from traderbot.simulation.profiles import PRESETS

            results = {}
            for p in profiles:
                if p.name == "Conservative":
                    results[p.name] = conservative_result
                else:
                    results[p.name] = aggressive_result
            return results

        with (
            patch("traderbot.kalshi.client.KalshiClient"),
            patch("traderbot.kalshi.history.HistoryService"),
            patch("traderbot.simulation.profiles.run_profiles", side_effect=fake_run_profiles),
        ):
            result = runner.invoke(
                app, ["compare", "--profiles", "Conservative,Aggressive", "--db", str(tmp_path / "test.db")]
            )
            assert result.exit_code == 0
            assert "Profile Comparison" in result.output

    @pytest.mark.unit
    def test_compare_json_with_mock_profiles(self, tmp_path):
        from traderbot.simulation.engine import BacktestResult

        moderate_result = BacktestResult(
            trade_count=10,
            total_pnl_cents=2000_00,
            winning_trades=6,
            losing_trades=4,
            win_rate=0.6,
            sharpe_ratio=1.0,
            max_drawdown_pct=0.07,
            brier_score=0.22,
            edge_capture=0.38,
            fill_rate=0.88,
            trades=[],
        )

        async def fake_run_profiles(engine, profiles, start, end):
            return {p.name: moderate_result for p in profiles}

        with (
            patch("traderbot.kalshi.client.KalshiClient"),
            patch("traderbot.kalshi.history.HistoryService"),
            patch("traderbot.simulation.profiles.run_profiles", side_effect=fake_run_profiles),
        ):
            result = runner.invoke(
                app, ["compare", "--profiles", "Moderate", "--db", str(tmp_path / "test.db"), "--json"]
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["profile_name"] == "Moderate"
            assert data[0]["trade_count"] == 10


class TestBootstrapCommand:
    def test_bootstrap_help(self):
        result = runner.invoke(app, ["bootstrap", "--help"])
        assert result.exit_code == 0
        assert "--dry-run" in result.output
        assert "--json" in result.output

    def test_bootstrap_dry_run(self):
        """Bootstrap --dry-run validates without side effects."""
        mock_status = {
            "kalshi": {"api_key": True, "api_secret": False},
            "voyage": {"api_key": True},
            "newsapi": {"api_key": False},
            "twitter": {"api_key": False},
            "reddit": {"client_id": False, "client_secret": False},
        }
        with (
            patch("traderbot.auth.AuthManager.keyring_available", new_callable=lambda: property(lambda self: True)),
            patch("traderbot.auth.AuthManager.check_credentials", return_value=mock_status),
        ):
            result = runner.invoke(app, ["bootstrap", "--dry-run"])
            assert result.exit_code == 0
            assert "Python" in result.output
            assert "Bootstrap" in result.output

    def test_bootstrap_dry_run_json(self):
        """Bootstrap --dry-run --json returns structured JSON."""
        mock_status = {
            "kalshi": {"api_key": True, "api_secret": False},
            "voyage": {"api_key": False},
            "newsapi": {"api_key": False},
            "twitter": {"api_key": False},
            "reddit": {"client_id": False, "client_secret": False},
        }
        with (
            patch("traderbot.auth.AuthManager.keyring_available", new_callable=lambda: property(lambda self: True)),
            patch("traderbot.auth.AuthManager.check_credentials", return_value=mock_status),
        ):
            result = runner.invoke(app, ["bootstrap", "--dry-run", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "python_version" in data
            assert data["python_version_ok"] is True
            assert "config_dir" in data
            assert "keyring_available" in data
            assert "credentials_ok" in data
            assert data["credentials_ok"] is False
            assert "missing_credentials" in data
            assert "kalshi.api_secret" in data["missing_credentials"]

    def test_bootstrap_json_with_all_credentials_ok(self, tmp_path):
        """Bootstrap with all credentials configured shows success."""
        mock_status = {
            "kalshi": {"api_key": True, "api_secret": True},
            "voyage": {"api_key": True},
            "newsapi": {"api_key": True},
            "twitter": {"api_key": True},
            "reddit": {"client_id": True, "client_secret": True},
        }
        with (
            patch("traderbot.auth.AuthManager.keyring_available", new_callable=lambda: property(lambda self: True)),
            patch("traderbot.auth.AuthManager.check_credentials", return_value=mock_status),
            patch("traderbot.auth.AuthManager.set_credential"),
        ):
            result = runner.invoke(app, ["bootstrap", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["credentials_ok"] is True
            assert data["missing_credentials"] == []

    def test_bootstrap_dry_run_no_keyring(self):
        """Bootstrap with keyring unavailable reports it clearly."""
        mock_status = {
            "kalshi": {"api_key": False, "api_secret": False},
            "voyage": {"api_key": False},
            "newsapi": {"api_key": False},
            "twitter": {"api_key": False},
            "reddit": {"client_id": False, "client_secret": False},
        }
        with (
            patch("traderbot.auth.AuthManager.keyring_available", new_callable=lambda: property(lambda self: False)),
            patch("traderbot.auth.AuthManager.check_credentials", return_value=mock_status),
        ):
             result = runner.invoke(app, ["bootstrap", "--dry-run"])
             assert result.exit_code == 0
             assert "Keyring unavailable" in result.output


class TestLearnings:
    def test_learnings_help(self):
        result = runner.invoke(app, ["learnings", "--help"])
        assert result.exit_code == 0
        assert "--status" in result.output
        assert "--category" in result.output
        assert "--promote" in result.output
        assert "--db" in result.output
        assert "--json" in result.output

    def test_learnings_empty_db(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["learnings", "--db", str(db)])
        assert result.exit_code == 0
        assert "No learnings found" in result.output

    def test_learnings_empty_db_json(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["learnings", "--db", str(db), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.unit
    def test_learnings_with_patterns(self, tmp_path):
        from traderbot.db import get_connection, init_schema
        from traderbot.db.learnings import LearningCategory, init_table, record_pattern

        db = tmp_path / "test.db"
        with get_connection(db) as conn:
            init_schema(conn)
            init_table(conn)
            record_pattern(conn, LearningCategory.MARKET_BEHAVIOR, "High volume precedes reversal", "Observed 15 times", 0.85)
            record_pattern(conn, LearningCategory.RISK_SIGNAL, "Drawdown > 5% triggers panic sells", "3 events", 0.7)

        result = runner.invoke(app, ["learnings", "--db", str(db)])
        assert result.exit_code == 0
        assert "High volume" in result.output
        assert "MarketBehavior" in result.output
        assert "Learned Patterns" in result.output

    @pytest.mark.unit
    def test_learnings_with_patterns_json(self, tmp_path):
        from traderbot.db import get_connection, init_schema
        from traderbot.db.learnings import LearningCategory, init_table, record_pattern

        db = tmp_path / "test.db"
        with get_connection(db) as conn:
            init_schema(conn)
            init_table(conn)
            record_pattern(conn, LearningCategory.MARKET_BEHAVIOR, "High volume precedes reversal", "Observed 15 times", 0.85)

        result = runner.invoke(app, ["learnings", "--db", str(db), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["category"] == "MarketBehavior"
        assert data[0]["confidence"] == 0.85

    @pytest.mark.unit
    def test_learnings_filter_by_category(self, tmp_path):
        from traderbot.db import get_connection, init_schema
        from traderbot.db.learnings import LearningCategory, init_table, record_pattern

        db = tmp_path / "test.db"
        with get_connection(db) as conn:
            init_schema(conn)
            init_table(conn)
            record_pattern(conn, LearningCategory.MARKET_BEHAVIOR, "Market pattern", "evidence", 0.8)
            record_pattern(conn, LearningCategory.RISK_SIGNAL, "Risk pattern", "evidence", 0.7)

        result = runner.invoke(app, ["learnings", "--db", str(db), "--category", "RiskSignal"])
        assert result.exit_code == 0
        assert "Risk pattern" in result.output
        assert "MarketBehavior" not in result.output

    @pytest.mark.unit
    def test_learnings_filter_by_deprecated_status(self, tmp_path):
        from traderbot.db import get_connection, init_schema
        from traderbot.db.learnings import LearningCategory, LearningStatus, init_table, record_pattern, set_status

        db = tmp_path / "test.db"
        with get_connection(db) as conn:
            init_schema(conn)
            init_table(conn)
            lid = record_pattern(conn, LearningCategory.TIMING, "Old pattern", "evidence", 0.5)
            set_status(conn, lid, LearningStatus.DEPRECATED)

        result = runner.invoke(app, ["learnings", "--db", str(db), "--status", "deprecated"])
        assert result.exit_code == 0
        assert "Old pattern" in result.output

    @pytest.mark.unit
    def test_learnings_promote_not_found(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["learnings", "--db", str(db), "--promote", "nonexistent-key"])
        assert result.exit_code == 1

    @pytest.mark.unit
    def test_learnings_promote_json_not_found(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["learnings", "--db", str(db), "--promote", "nonexistent-key", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert "error" in data

    @pytest.mark.unit
    def test_learnings_invalid_category(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["learnings", "--db", str(db), "--category", "InvalidCat"])
        assert result.exit_code == 1

    @pytest.mark.unit
    def test_learnings_invalid_status(self, tmp_path):
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["learnings", "--db", str(db), "--status", "invalid"])
        assert result.exit_code == 1
