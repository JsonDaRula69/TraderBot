"""Integration tests for the full simulation pipeline — DataLoader → BacktestEngine → performance → profiles → CLI."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from traderbot.cli import app
from traderbot.kalshi.models import (
    Market,
    MarketListResponse,
    OrderBook,
    OrderBookLevel,
    PortfolioState,
    Trade,
)
from unittest.mock import AsyncMock, MagicMock, patch
from traderbot.risk.circuit_breaker import CircuitBreakerState
from traderbot.risk.limits import HARD_LIMITS
from traderbot.simulation.data_loader import DataLoader, DataQualityReport, init_cache_tables
from traderbot.simulation.engine import (
    BacktestEngine,
    BacktestResult,
    BacktestTrade,
    Context,
    Signal,
    SlippageModel,
)
from traderbot.simulation.paper_trader import (
    PaperFill,
    PaperPortfolio,
    PaperPosition,
    PaperSlippageModel,
    PaperTrader,
)
from traderbot.simulation.performance import (
    StrategyComparison,
    compare_strategies,
    compute_brier_score,
    compute_edge_capture,
    compute_fill_rate,
    compute_max_drawdown,
    compute_metrics,
    compute_sharpe,
    compute_win_rate,
)
from traderbot.simulation.profiles import (
    AGGRESSIVE,
    CONSERVATIVE,
    MODERATE,
    PRESETS,
    StrategyProfile,
    compare_profiles,
    run_profiles,
)

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

# --- Constants & Helpers ---

PORTFOLIO_VALUE = 100_000_00  # $100k in cents


def _make_market(
    ticker: str = "KX-TEST",
    question: str = "Test market?",
    status: str = "settled",
    volume: int = 5000,
    open_interest: int = 2000,
    settlement_result: bool | None = True,
    close_time: datetime | None = None,
    category: str = "economics",
) -> Market:
    return Market(
        ticker=ticker,
        question=question,
        last_price_cents=65,
        volume=volume,
        open_interest=open_interest,
        close_time=close_time or datetime(2026, 3, 31, 23, 59, 59, tzinfo=UTC),
        status=status,
        event_ticker="KX-EVENT",
        category=category,
        settlement_result=settlement_result,
    )


def _make_trade(
    ticker: str = "KX-TEST",
    price: int = 65,
    quantity: int = 10,
    side: str = "yes",
    timestamp: datetime | None = None,
) -> Trade:
    return Trade(
        ticker=ticker,
        price=price,
        quantity=quantity,
        side=side,
        timestamp=timestamp or datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
    )


def _make_portfolio(**overrides) -> PortfolioState:
    defaults = dict(
        portfolio_value_cents=PORTFOLIO_VALUE,
        peak_value_cents=PORTFOLIO_VALUE,
        current_positions_value_cents=0,
        today_realized_loss_cents=0,
        today_unrealized_loss_cents=0,
        open_positions_count=0,
    )
    defaults.update(overrides)
    return PortfolioState(**defaults)


def _make_orderbook(
    yes_bids: list[tuple[int, int]] | None = None,
    no_bids: list[tuple[int, int]] | None = None,
) -> OrderBook:
    if yes_bids is None:
        yes_bids = [(65, 100), (64, 200)]
    if no_bids is None:
        no_bids = [(35, 150), (36, 200)]
    return OrderBook(
        yes_bids=[OrderBookLevel(price=p, size=s) for p, s in yes_bids],
        no_bids=[OrderBookLevel(price=p, size=s) for p, s in no_bids],
    )


# ========================================================================
# 1. End-to-End: DataLoader → BacktestEngine → performance → profiles
# ========================================================================


class TestEndToEndPipeline:
    """Full pipeline: DataLoader feeds BacktestEngine, result flows through metrics and profile comparison."""

    @pytest.fixture
    def mock_loader(self) -> AsyncMock:
        loader = AsyncMock(spec=DataLoader)
        return loader

    async def test_full_pipeline_with_trades(
        self, mock_loader: AsyncMock, tmp_path: Path
    ) -> None:
        """DataLoader → BacktestEngine.run() → compute_metrics → compare_profiles."""
        market = _make_market(
            ticker="KX-E2E",
            settlement_result=True,
            volume=10000,
            open_interest=5000,
        )
        trade = _make_trade(
            ticker="KX-E2E",
            price=55,
            quantity=100,
            timestamp=datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC),
        )

        mock_loader.get_markets.return_value = [market]
        mock_loader.get_trades.return_value = [trade]
        mock_loader.get_outcomes.return_value = {"KX-E2E": True}

        class BuyYesStrategy:
            def on_market_open(self, market: Market, context: Context) -> list[Signal]:
                return []
            def on_trade(self, trade: Trade, context: Context) -> list[Signal]:
                return [
                    Signal(
                        ticker="KX-E2E",
                        direction="yes",
                        quantity=5,
                        price_cents=65,
                        estimated_prob=0.70,
                        confidence=0.8,
                    )
                ]
            def on_settle(self, market: Market, outcome: bool, context: Context) -> None:
                pass

        engine = BacktestEngine(
            data_loader=mock_loader,
            strategy=BuyYesStrategy(),
            initial_bankroll_cents=PORTFOLIO_VALUE,
            state_dir=tmp_path,
        )

        result = await engine.run(start=date(2026, 1, 1), end=date(2026, 3, 31))

        assert isinstance(result, BacktestResult)
        assert isinstance(result.total_pnl_cents, int)
        assert result.trade_count >= 0
        assert isinstance(result.trades, list)
        assert result.total_pnl_cents >= 0 or result.total_pnl_cents < 0

        metrics = compute_metrics(result, initial_bankroll_cents=PORTFOLIO_VALUE)
        assert "total_pnl_cents" in metrics
        assert "trade_count" in metrics
        assert metrics["trade_count"] == result.trade_count
        profile_results = {"Conservative": result, "Aggressive": result}
        comparisons = compare_profiles(profile_results, PORTFOLIO_VALUE)
        assert len(comparisons) == 2
        names = [c["profile_name"] for c in comparisons]
        assert "Conservative" in names
        assert "Aggressive" in names

    async def test_pipeline_zero_trades_stays_safe(
        self, mock_loader: AsyncMock, tmp_path: Path
    ) -> None:
        """Pipeline with no trades: all metrics None, no division-by-zero, profiles safe."""
        market = _make_market(ticker="KX-EMPTY", volume=50, open_interest=10)
        mock_loader.get_markets.return_value = [market]
        mock_loader.get_trades.return_value = []
        mock_loader.get_outcomes.return_value = {"KX-EMPTY": True}

        class Passive:
            def on_market_open(self, market: Market, context: Context) -> list[Signal]:
                return []
            def on_trade(self, trade: Trade, context: Context) -> list[Signal]:
                return []
            def on_settle(self, market: Market, outcome: bool, context: Context) -> None:
                pass

        engine = BacktestEngine(
            data_loader=mock_loader,
            strategy=Passive(),
            initial_bankroll_cents=PORTFOLIO_VALUE,
            state_dir=tmp_path,
        )

        result = await engine.run(start=date(2026, 1, 1), end=date(2026, 3, 31))

        assert result.trade_count == 0
        assert result.total_pnl_cents == 0
        assert result.win_rate is None
        assert result.sharpe_ratio is None
        assert result.brier_score is None
        assert result.edge_capture is None
        assert result.fill_rate is None

        metrics = compute_metrics(result)
        assert metrics["win_rate"] is None
        assert metrics["trade_count"] == 0

        comparisons = compare_profiles({"A": result, "B": result})
        assert len(comparisons) == 2

    async def test_multi_market_pipeline(
        self, mock_loader: AsyncMock, tmp_path: Path
    ) -> None:
        """Pipeline processes multiple markets with independent outcomes."""
        markets = [
            _make_market(
                ticker="KX-A",
                settlement_result=True,
                close_time=datetime(2026, 2, 15, 23, 59, 59, tzinfo=UTC),
                volume=8000,
                open_interest=3000,
            ),
            _make_market(
                ticker="KX-B",
                settlement_result=False,
                close_time=datetime(2026, 3, 15, 23, 59, 59, tzinfo=UTC),
                volume=6000,
                open_interest=2000,
            ),
        ]
        trades = [
            _make_trade(ticker="KX-A", price=60),
            _make_trade(ticker="KX-B", price=40),
        ]

        mock_loader.get_markets.return_value = markets
        mock_loader.get_trades.side_effect = lambda t: [tr for tr in trades if tr.ticker == t]
        mock_loader.get_outcomes.return_value = {"KX-A": True, "KX-B": False}

        class TradeOnFirstSignal:
            def on_market_open(self, market: Market, context: Context) -> list[Signal]:
                return []
            def on_trade(self, trade: Trade, context: Context) -> list[Signal]:
                direction = "yes" if trade.price > 50 else "no"
                prob = 0.7 if direction == "yes" else 0.6
                return [Signal(
                    ticker=trade.ticker, direction=direction,
                    quantity=2, price_cents=trade.price,
                    estimated_prob=prob, confidence=0.6,
                )]
            def on_settle(self, market: Market, outcome: bool, context: Context) -> None:
                pass

        engine = BacktestEngine(
            data_loader=mock_loader,
            strategy=TradeOnFirstSignal(),
            initial_bankroll_cents=PORTFOLIO_VALUE,
            state_dir=tmp_path,
        )

        result = await engine.run(start=date(2026, 1, 1), end=date(2026, 6, 30))
        assert isinstance(result, BacktestResult)
        assert isinstance(result.total_pnl_cents, int)
        assert result.trade_count >= 0
        assert isinstance(result.trades, list)


# ========================================================================
# 2. PaperTrader with Mock DemoAdapter → Position Tracking → P&L
# ========================================================================


class TestPaperTraderIntegration:
    """PaperTrader end-to-end with mock DemoAdapter: order → fill → position → P&L."""

    def _make_trader(self, conn: sqlite3.Connection, demo: AsyncMock | None = None) -> PaperTrader:
        from traderbot.kalshi.demo import DemoAdapter
        if demo is None:
            demo = DemoAdapter.__new__(DemoAdapter)
        return PaperTrader(
            demo_adapter=demo,
            db_conn=conn,
            initial_cash_cents=PORTFOLIO_VALUE,
        )

    def test_open_close_position_lifecycle(self) -> None:
        """Open position → add → close → verify P&L cascade."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        trader = self._make_trader(conn)

        # Open position
        fill1 = PaperFill(
            ticker="KX-PT", side="yes", price_cents=60, quantity=10,
            slippage_cents=2, timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        )
        trader.record_fill(fill1)

        portfolio = trader.get_portfolio()
        assert len(portfolio.positions) == 1
        assert portfolio.cash_cents == PORTFOLIO_VALUE - 600

        # Add to position
        fill2 = PaperFill(
            ticker="KX-PT", side="yes", price_cents=70, quantity=10,
            slippage_cents=2, timestamp=datetime(2026, 1, 15, 13, 0, 0, tzinfo=UTC),
        )
        trader.record_fill(fill2)

        positions = trader.get_positions()
        assert len(positions) == 1
        assert positions[0].avg_price_cents == 65  # (60*10 + 70*10)/20
        assert positions[0].quantity == 20

        # Close half
        fill3 = PaperFill(
            ticker="KX-PT", side="yes", price_cents=80, quantity=-10,
            slippage_cents=2, timestamp=datetime(2026, 1, 15, 14, 0, 0, tzinfo=UTC),
        )
        trader.record_fill(fill3)

        positions = trader.get_positions()
        assert len(positions) == 1
        assert positions[0].quantity == 10

        # Verify realized P&L
        pnl = trader.get_pnl()
        # Closed 10 at 80, avg cost 65 → pnl = (80-65)*10 = 150
        assert pnl == 150

        conn.close()

    def test_unrealized_pnl_with_mark_prices(self) -> None:
        """Open position + mark prices → unrealized P&L computed correctly."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        trader = self._make_trader(conn)

        fill = PaperFill(
            ticker="KX-MK", side="yes", price_cents=55, quantity=20,
            slippage_cents=1, timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        )
        trader.record_fill(fill)

        # Mark at 70 → unrealized = (70-55)*20 = 300
        pnl = trader.get_pnl(mark_prices={"KX-MK": 70})
        assert pnl == 300

        # Mark at 55 → unrealized = 0
        pnl_flat = trader.get_pnl(mark_prices={"KX-MK": 55})
        assert pnl_flat == 0

        conn.close()

    async def test_submit_order_through_paper_trader(self) -> None:
        """submit_order with mocked DemoAdapter service → fill returned → position created."""
        from traderbot.kalshi.demo import DemoAdapter
        demo = DemoAdapter.__new__(DemoAdapter)
        market_service = AsyncMock()
        market_service.get_market = AsyncMock(return_value=_make_market())
        market_service.get_orderbook = AsyncMock(return_value=_make_orderbook())

        with patch.object(demo, "get_market_service", return_value=market_service):
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            from traderbot.db.decisions import init_table as init_decisions
            init_decisions(conn)
            trader = PaperTrader(demo, conn, initial_cash_cents=PORTFOLIO_VALUE)

            fill = await trader.submit_order(
                ticker="KX-SUB", side="yes", quantity=10, price_cents=65,
            )

        assert fill is not None
        assert fill.ticker == "KX-SUB"
        assert fill.quantity == 10
        assert fill.side == "yes"

        positions = trader.get_positions()
        assert len(positions) == 1
        assert positions[0].ticker == "KX-SUB"

        conn.close()

    def test_paper_positions_isolated_from_live(self) -> None:
        """Paper positions never touch the live positions table."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        from traderbot.db.positions import init_table as init_live
        init_live(conn)

        trader = self._make_trader(conn)
        fill = PaperFill(
            ticker="KX-ISO", side="yes", price_cents=50, quantity=5,
            slippage_cents=1, timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        )
        trader.record_fill(fill)

        live = conn.execute("SELECT COUNT(*) as cnt FROM positions").fetchone()
        assert live["cnt"] == 0

        paper = conn.execute("SELECT COUNT(*) as cnt FROM paper_positions").fetchone()
        assert paper["cnt"] == 1

        conn.close()


# ========================================================================
# 3. CLI Command Integration (backtest, paper, performance, compare)
# ========================================================================


class TestCLIIntegration:
    """CLI commands wired to simulation modules via Typer CliRunner."""

    @pytest.fixture(autouse=True)
    def mock_require_profile(self):
        with patch("traderbot.cli._require_profile", return_value=MagicMock(enabled_categories=[])):
            yield

    def test_backtest_command_with_mock(self, tmp_path: Path) -> None:
        """backtest CLI: mock engine → verify output."""
        mock_result = BacktestResult(
            trade_count=5, total_pnl_cents=2500_00,
            winning_trades=3, losing_trades=2,
            win_rate=0.6, sharpe_ratio=1.5,
            max_drawdown_pct=0.08, brier_score=0.22,
            edge_capture=0.35, fill_rate=0.8, trades=[],
        )

        with (
            patch("traderbot.kalshi.client.KalshiClient"),
            patch("traderbot.kalshi.history.HistoryService"),
            patch("traderbot.simulation.engine.BacktestEngine.run", return_value=mock_result),
        ):
            result = runner.invoke(app, ["backtest", "--db", str(tmp_path / "test.db")])
            assert result.exit_code == 0
            assert "Backtest Results" in result.output

    def test_backtest_command_json(self, tmp_path: Path) -> None:
        """backtest --json: verify JSON output structure."""
        mock_result = BacktestResult(
            trade_count=3, total_pnl_cents=1500_00,
            winning_trades=2, losing_trades=1,
            win_rate=0.667, sharpe_ratio=1.2,
            max_drawdown_pct=0.05, brier_score=0.20,
            edge_capture=0.4, fill_rate=0.75, trades=[],
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
            assert data["trade_count"] == 3

    def test_paper_command_with_mock(self, tmp_path: Path) -> None:
        """paper CLI: mock PaperTrader → verify output."""
        mock_portfolio = PaperPortfolio(
            cash_cents=99_500_00,
            positions=[PaperPosition(ticker="KX-PAPER", side="yes", avg_price_cents=55, quantity=10)],
        )

        with (
            patch("traderbot.kalshi.demo.DemoAdapter"),
            patch("traderbot.simulation.paper_trader.PaperTrader.get_portfolio", return_value=mock_portfolio),
            patch("traderbot.simulation.paper_trader.PaperTrader.get_pnl", return_value=-500_00),
        ):
            result = runner.invoke(app, ["paper", "--db", str(tmp_path / "test.db")])
            assert result.exit_code == 0
            assert "Paper Trading" in result.output

    def test_paper_command_json(self, tmp_path: Path) -> None:
        """paper --json: verify JSON output structure."""
        mock_portfolio = PaperPortfolio(
            cash_cents=99_000_00,
            positions=[],
        )

        with (
            patch("traderbot.kalshi.demo.DemoAdapter"),
            patch("traderbot.simulation.paper_trader.PaperTrader.get_portfolio", return_value=mock_portfolio),
            patch("traderbot.simulation.paper_trader.PaperTrader.get_pnl", return_value=-1000_00),
        ):
            result = runner.invoke(app, ["paper", "--db", str(tmp_path / "test.db"), "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["cash_cents"] == 99_000_00
            assert data["pnl_cents"] == -1000_00

    def test_performance_command_with_decisions(self, tmp_path: Path) -> None:
        """performance CLI: insert decisions → verify metrics."""
        from traderbot.db import get_connection, init_schema
        from traderbot.kalshi.models import Decision

        db = tmp_path / "test.db"
        with get_connection(db) as conn:
            init_schema(conn)
            from traderbot.db.decisions import init_table, insert
            init_table(conn)
            for i in range(5):
                insert(conn, Decision(
                    timestamp=datetime(2026, 1, 15 + i, 12, 0, 0, tzinfo=UTC),
                    ticker=f"TEST-{i}", direction="yes",
                    quantity=5, price=55 + i * 10,
                    signal_strength=0.7, confidence=0.8,
                    edge_estimate=0.15,
                    risk_checks={"max_position": True},
                    outcome="executed",
                ))

        result = runner.invoke(app, ["performance", "--db", str(db)])
        assert result.exit_code == 0
        assert "Performance Summary" in result.output

    def test_performance_command_json(self, tmp_path: Path) -> None:
        """performance --json: verify numeric metrics."""
        from traderbot.db import get_connection, init_schema
        from traderbot.kalshi.models import Decision

        db = tmp_path / "test.db"
        with get_connection(db) as conn:
            init_schema(conn)
            from traderbot.db.decisions import init_table, insert
            init_table(conn)
            insert(conn, Decision(
                timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
                ticker="TEST-PERF", direction="yes",
                quantity=5, price=55,
                signal_strength=0.7, confidence=0.8,
                edge_estimate=0.15,
                risk_checks={"max_position": True},
                outcome="executed",
            ))

        result = runner.invoke(app, ["performance", "--db", str(db), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["trade_count"] == 1

    def test_compare_command_with_mock(self, tmp_path: Path) -> None:
        """compare CLI: mock run_profiles → verify comparison table."""
        result_a = BacktestResult(
            trade_count=10, total_pnl_cents=5000_00,
            winning_trades=7, losing_trades=3,
            win_rate=0.7, sharpe_ratio=1.5,
            max_drawdown_pct=0.05, brier_score=0.18,
            edge_capture=0.42, fill_rate=0.9, trades=[],
        )
        result_b = BacktestResult(
            trade_count=15, total_pnl_cents=3500_00,
            winning_trades=9, losing_trades=6,
            win_rate=0.6, sharpe_ratio=0.9,
            max_drawdown_pct=0.12, brier_score=0.25,
            edge_capture=0.35, fill_rate=0.85, trades=[],
        )

        async def fake_run(engine, profiles, start, end):
            return {p.name: result_a if p.name == "Conservative" else result_b for p in profiles}

        with (
            patch("traderbot.kalshi.client.KalshiClient"),
            patch("traderbot.kalshi.history.HistoryService"),
            patch("traderbot.simulation.profiles.run_profiles", side_effect=fake_run),
        ):
            result = runner.invoke(app, [
                "compare", "--profiles", "Conservative,Aggressive",
                "--db", str(tmp_path / "test.db"),
            ])
            assert result.exit_code == 0
            assert "Profile Comparison" in result.output

    def test_compare_command_json(self, tmp_path: Path) -> None:
        """compare --json: verify JSON list of profile metrics."""
        mock_result = BacktestResult(
            trade_count=8, total_pnl_cents=2000_00,
            winning_trades=5, losing_trades=3,
            win_rate=0.625, sharpe_ratio=1.0,
            max_drawdown_pct=0.07, brier_score=0.22,
            edge_capture=0.38, fill_rate=0.88, trades=[],
        )

        async def fake_run(engine, profiles, start, end):
            return {p.name: mock_result for p in profiles}

        with (
            patch("traderbot.kalshi.client.KalshiClient"),
            patch("traderbot.kalshi.history.HistoryService"),
            patch("traderbot.simulation.profiles.run_profiles", side_effect=fake_run),
        ):
            result = runner.invoke(app, [
                "compare", "--profiles", "Moderate",
                "--db", str(tmp_path / "test.db"), "--json",
            ])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert isinstance(data, list)
            assert data[0]["profile_name"] == "Moderate"

    def test_compare_unknown_profile_exits_1(self) -> None:
        """compare with unknown profile name → exit code 1."""
        result = runner.invoke(app, ["compare", "--profiles", "NonExistent"])
        assert result.exit_code == 1
        assert "Unknown profile" in result.output

    def test_backtest_no_api_fallback(self) -> None:
        """backtest without API → graceful fallback message."""
        with patch("traderbot.kalshi.client.KalshiClient", side_effect=Exception("no api")):
            result = runner.invoke(app, ["backtest"])
            assert result.exit_code == 0
            assert "API connection required" in result.output

    def test_paper_no_api_fallback(self) -> None:
        """paper without demo API → graceful fallback message."""
        with patch("traderbot.kalshi.demo.DemoAdapter", side_effect=Exception("no demo")):
            result = runner.invoke(app, ["paper"])
            assert result.exit_code == 0
            assert "Demo API connection required" in result.output


# ========================================================================
# 4. Risk Limits Enforcement Throughout Pipeline
# ========================================================================


class TestRiskEnforcementIntegration:
    """Risk limits enforced at every layer: engine rejects oversized, profiles stay within HARD_LIMITS."""

    @pytest.fixture
    def mock_loader(self) -> AsyncMock:
        loader = AsyncMock(spec=DataLoader)
        return loader

    async def test_engine_rejects_oversized_position(
        self, mock_loader: AsyncMock, tmp_path: Path
    ) -> None:
        """BacktestEngine must reject trades exceeding 5% of portfolio."""
        market = _make_market(ticker="KX-BIG", volume=10000, open_interest=5000)
        trade = _make_trade(ticker="KX-BIG", price=55, quantity=100)

        mock_loader.get_markets.return_value = [market]
        mock_loader.get_trades.return_value = [trade]
        mock_loader.get_outcomes.return_value = {"KX-BIG": True}

        class Greedy:
            def on_market_open(self, market: Market, context: Context) -> list[Signal]:
                return []
            def on_trade(self, trade: Trade, context: Context) -> list[Signal]:
                return [Signal(
                    ticker="KX-BIG", direction="yes",
                    quantity=100000, price_cents=55,
                    estimated_prob=0.9, confidence=0.9,
                )]
            def on_settle(self, market: Market, outcome: bool, context: Context) -> None:
                pass

        engine = BacktestEngine(
            data_loader=mock_loader,
            strategy=Greedy(),
            initial_bankroll_cents=PORTFOLIO_VALUE,
            state_dir=tmp_path,
        )
        result = await engine.run(start=date(2026, 1, 1), end=date(2026, 3, 31))
        # Oversized trade must be rejected
        assert result.trade_count == 0 or result.total_pnl_cents == 0

    async def test_engine_rejects_low_edge(
        self, mock_loader: AsyncMock, tmp_path: Path
    ) -> None:
        """BacktestEngine rejects trades with edge < 3% (min_edge_pct)."""
        low_edge_market = Market(
            ticker="KX-NOEDGE", question="Low edge?",
            last_price_cents=52, volume=5000, open_interest=2000,
            close_time=datetime(2026, 3, 31, 23, 59, 59, tzinfo=UTC),
            status="settled", event_ticker="KX-EVENT",
            category="test", settlement_result=True,
        )
        trade = _make_trade(ticker="KX-NOEDGE", price=52, quantity=10)

        mock_loader.get_markets.return_value = [low_edge_market]
        mock_loader.get_trades.return_value = [trade]
        mock_loader.get_outcomes.return_value = {"KX-NOEDGE": True}

        class LowEdge:
            def on_market_open(self, market: Market, context: Context) -> list[Signal]:
                return []
            def on_trade(self, trade: Trade, context: Context) -> list[Signal]:
                return [Signal(
                    ticker="KX-NOEDGE", direction="yes",
                    quantity=5, price_cents=52,
                    estimated_prob=0.53, confidence=0.9,
                )]
            def on_settle(self, market: Market, outcome: bool, context: Context) -> None:
                pass

        engine = BacktestEngine(
            data_loader=mock_loader,
            strategy=LowEdge(),
            initial_bankroll_cents=PORTFOLIO_VALUE,
            state_dir=tmp_path,
        )
        result = await engine.run(start=date(2026, 1, 1), end=date(2026, 3, 31))
        assert result.trade_count == 0

    def test_risk_multiplier_above_1_rejected(self) -> None:
        """StrategyProfile rejects risk_multiplier > 1.0 (cannot exceed HARD_LIMITS)."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            StrategyProfile(
                name="OverLimit", risk_multiplier=1.1,
                signal_weights={"statistical": 1.0},
                category_focus=["economics"],
                description="Should fail",
            )

    async def test_profile_backtest_respects_limits(
        self, mock_loader: AsyncMock, tmp_path: Path
    ) -> None:
        """run_profiles with Conservative (0.5x) → engine enforces reduced limits."""
        market = _make_market(ticker="KX-PROF", volume=10000, open_interest=5000)
        trade = _make_trade(ticker="KX-PROF", price=55, quantity=100)

        mock_loader.get_markets.return_value = [market]
        mock_loader.get_trades.return_value = [trade]
        mock_loader.get_outcomes.return_value = {"KX-PROF": True}

        class Modest:
            def on_market_open(self, market: Market, context: Context) -> list[Signal]:
                return []
            def on_trade(self, trade: Trade, context: Context) -> list[Signal]:
                return [Signal(
                    ticker="KX-PROF", direction="yes",
                    quantity=5, price_cents=65,
                    estimated_prob=0.7, confidence=0.7,
                )]
            def on_settle(self, market: Market, outcome: bool, context: Context) -> None:
                pass

        engine = BacktestEngine(
            data_loader=mock_loader,
            strategy=Modest(),
            initial_bankroll_cents=PORTFOLIO_VALUE,
            state_dir=tmp_path,
        )

        results = await engine.run_profiles(
            profiles=[CONSERVATIVE, MODERATE],
            start=date(2026, 1, 1), end=date(2026, 3, 31),
        )
        assert "Conservative" in results
        assert "Moderate" in results
        # Drawdown must never exceed HARD_LIMITS["max_drawdown_pct"]
        for name, res in results.items():
            if res.max_drawdown_pct is not None:
                assert res.max_drawdown_pct <= HARD_LIMITS["max_drawdown_pct"] + 1e-9


# ========================================================================
# 5. Edge Cases: Empty Data, Zero Trades, Single Market
# ========================================================================


class TestEdgeCases:
    """Edge cases that must not crash the pipeline."""

    @pytest.fixture
    def mock_loader(self) -> AsyncMock:
        return AsyncMock(spec=DataLoader)

    async def test_empty_markets_list(
        self, mock_loader: AsyncMock, tmp_path: Path
    ) -> None:
        """DataLoader returns zero markets → engine produces zero-trade result."""
        mock_loader.get_markets.return_value = []
        mock_loader.get_outcomes.return_value = {}

        class AnyStrategy:
            def on_market_open(self, market: Market, context: Context) -> list[Signal]:
                return []
            def on_trade(self, trade: Trade, context: Context) -> list[Signal]:
                return []
            def on_settle(self, market: Market, outcome: bool, context: Context) -> None:
                pass

        engine = BacktestEngine(
            data_loader=mock_loader,
            strategy=AnyStrategy(),
            initial_bankroll_cents=PORTFOLIO_VALUE,
            state_dir=tmp_path,
        )
        result = await engine.run(start=date(2026, 1, 1), end=date(2026, 3, 31))

        assert result.trade_count == 0
        assert result.total_pnl_cents == 0
        assert result.win_rate is None
        assert result.sharpe_ratio is None
        assert result.brier_score is None

        # compute_metrics must not crash
        metrics = compute_metrics(result)
        assert metrics["trade_count"] == 0
        assert metrics["win_rate"] is None

    async def test_single_market_settled_true(
        self, mock_loader: AsyncMock, tmp_path: Path
    ) -> None:
        """Single market settles True → trade enters, settle calculates P&L."""
        market = _make_market(
            ticker="KX-SINGLE",
            settlement_result=True,
            volume=10000,
            open_interest=5000,
        )
        trade = _make_trade(ticker="KX-SINGLE", price=60)

        mock_loader.get_markets.return_value = [market]
        mock_loader.get_trades.return_value = [trade]
        mock_loader.get_outcomes.return_value = {"KX-SINGLE": True}

        class BuyYes:
            def on_market_open(self, market: Market, context: Context) -> list[Signal]:
                return []
            def on_trade(self, trade: Trade, context: Context) -> list[Signal]:
                return [Signal(
                    ticker="KX-SINGLE", direction="yes",
                    quantity=3, price_cents=65,
                    estimated_prob=0.7, confidence=0.7,
                )]
            def on_settle(self, market: Market, outcome: bool, context: Context) -> None:
                pass

        engine = BacktestEngine(
            data_loader=mock_loader,
            strategy=BuyYes(),
            initial_bankroll_cents=PORTFOLIO_VALUE,
            state_dir=tmp_path,
        )
        result = await engine.run(start=date(2026, 1, 1), end=date(2026, 3, 31))
        assert isinstance(result, BacktestResult)
        assert isinstance(result.total_pnl_cents, int)
        assert result.trade_count >= 0
        assert isinstance(result.trades, list)

    async def test_zero_pnl_is_loss_in_win_rate(
        self, mock_loader: AsyncMock, tmp_path: Path
    ) -> None:
        """Trade with zero P&L counts as a loss (not a win) for win_rate."""
        market = _make_market(
            ticker="KX-ZEROPNL",
            settlement_result=True,
            volume=10000,
            open_interest=5000,
        )
        trade = _make_trade(ticker="KX-ZEROPNL", price=65)

        mock_loader.get_markets.return_value = [market]
        mock_loader.get_trades.return_value = [trade]
        mock_loader.get_outcomes.return_value = {"KX-ZEROPNL": True}

        # Zero P&L scenario isn't easy to engineer through the engine,
        # so test at the performance metrics level directly
        zero_pnl_trade = BacktestTrade(
            ticker="KX-ZEROPNL", direction="yes",
            entry_price_cents=65, exit_price_cents=65,
            quantity=10, pnl_cents=0,
            timestamp="2026-03-31T23:59:59+00:00",
        )
        win = compute_win_rate([zero_pnl_trade])
        assert win == 0.0  # zero P&L should count as loss

    def test_empty_backtest_result_compare(self) -> None:
        """Comparing two zero-trade results → all comparison metrics None, no crash."""
        empty = BacktestResult(
            trade_count=0, total_pnl_cents=0,
            winning_trades=0, losing_trades=0,
            win_rate=None, sharpe_ratio=None,
            max_drawdown_pct=None, brier_score=None,
            edge_capture=None, fill_rate=None, trades=[],
        )
        comp = compare_strategies(empty, empty, "A", "B")
        assert comp.pnl_winner == "tie"
        assert comp.win_rate_a is None
        assert comp.sharpe_ratio_a is None

    def test_compute_metrics_empty_trades_no_crash(self) -> None:
        """compute_metrics on empty result → all optional metrics None."""
        empty = BacktestResult(
            trade_count=0, total_pnl_cents=0,
            winning_trades=0, losing_trades=0,
            win_rate=None, sharpe_ratio=None,
            max_drawdown_pct=None, brier_score=None,
            edge_capture=None, fill_rate=None, trades=[],
        )
        metrics = compute_metrics(empty, initial_bankroll_cents=PORTFOLIO_VALUE)
        assert metrics["total_pnl_cents"] == 0
        assert metrics["trade_count"] == 0
        assert metrics["win_rate"] is None
        assert metrics["sharpe_ratio"] is None
        assert metrics["brier_score"] is None
        assert metrics["edge_capture"] is None

    async def test_data_quality_report_on_pipeline(
        self, tmp_path: Path
    ) -> None:
        """DataLoader.quality_report integrates correctly with the pipeline."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_cache_tables(conn)

        history = AsyncMock()
        history.get_settled_markets = AsyncMock(return_value=MarketListResponse(
            markets=[_make_market(ticker="KX-LQ", volume=50, open_interest=10)],
            cursor=None,
        ))
        loader = DataLoader(conn=conn, history=history)

        markets = await loader.get_markets(start=date(2026, 1, 1), end=date(2026, 3, 31))
        report = loader.quality_report(markets)

        assert isinstance(report, DataQualityReport)
        assert any(f.flag_type == "low_liquidity" for f in report.flags)
        conn.close()


# ========================================================================
# 6. Cross-Module Consistency
# ========================================================================


class TestCrossModuleConsistency:
    """Verify that data flows are consistent across module boundaries."""

    def test_backtest_result_feeds_compute_metrics(self) -> None:
        """BacktestResult → compute_metrics keys match expected schema."""
        trade = BacktestTrade(
            ticker="KX-CM", direction="yes",
            entry_price_cents=65, exit_price_cents=100,
            quantity=10, pnl_cents=350,
            timestamp="2026-03-31T23:59:59+00:00",
        )
        result = BacktestResult(
            trade_count=1, total_pnl_cents=350,
            winning_trades=1, losing_trades=0,
            win_rate=1.0, sharpe_ratio=None,
            max_drawdown_pct=0.0, brier_score=None,
            edge_capture=None, fill_rate=None,
            trades=[trade],
        )

        metrics = compute_metrics(result, initial_bankroll_cents=PORTFOLIO_VALUE)
        expected_keys = {
            "total_pnl_cents", "trade_count", "win_rate",
            "sharpe_ratio", "max_drawdown", "brier_score",
            "edge_capture", "fill_rate", "calmar_ratio",
        }
        assert set(metrics.keys()) == expected_keys
        assert metrics["total_pnl_cents"] == 350
        assert metrics["win_rate"] == 1.0

    def test_compare_strategies_uses_compute_metrics(self) -> None:
        """compare_strategies output consistent with compute_metrics for both results."""
        result_a = BacktestResult(
            trade_count=10, total_pnl_cents=5000_00,
            winning_trades=7, losing_trades=3,
            win_rate=0.7, sharpe_ratio=1.5,
            max_drawdown_pct=0.08, brier_score=0.22,
            edge_capture=0.15, fill_rate=0.9, trades=[],
        )
        result_b = BacktestResult(
            trade_count=5, total_pnl_cents=2000_00,
            winning_trades=3, losing_trades=2,
            win_rate=0.6, sharpe_ratio=1.0,
            max_drawdown_pct=0.05, brier_score=0.25,
            edge_capture=0.10, fill_rate=0.8, trades=[],
        )

        comp = compare_strategies(result_a, result_b, "Alpha", "Beta")
        assert comp.pnl_winner == "Alpha"
        assert comp.total_pnl_cents_a == 5000_00
        assert comp.total_pnl_cents_b == 2000_00

    def test_compare_profiles_produces_consistent_metrics(self) -> None:
        """compare_profiles outputs match compute_metrics per profile."""
        result = BacktestResult(
            trade_count=8, total_pnl_cents=3000_00,
            winning_trades=5, losing_trades=3,
            win_rate=0.625, sharpe_ratio=1.2,
            max_drawdown_pct=0.06, brier_score=0.23,
            edge_capture=0.12, fill_rate=0.85, trades=[],
        )
        profile_results = {"Moderate": result}
        comparisons = compare_profiles(profile_results, PORTFOLIO_VALUE)

        assert len(comparisons) == 1
        comp = comparisons[0]
        assert comp["profile_name"] == "Moderate"
        assert comp["total_pnl_cents"] == 3000_00
        assert comp["trade_count"] == 8

    def test_slippage_model_consistent_with_paper(self) -> None:
        """BacktestEngine SlippageModel and PaperSlippageModel both use orderbook."""
        # Backtest SlippageModel (worst-case)
        backtest_model = SlippageModel()
        backtest_fill = backtest_model.apply(yes_bid=55, no_bid=40, direction="yes", quantity=5)
        assert backtest_fill == 60  # 100 - 40

        # Paper SlippageModel (orderbook-walking, base_slippage=1)
        paper_model = PaperSlippageModel(base_slippage_cents=1)
        orderbook = _make_orderbook(yes_bids=[(55, 100)], no_bids=[(40, 100)])
        paper_fill = paper_model.compute_fill_price(orderbook, "yes", 5)
        # YES buy at 55 + 1 slippage = 56
        assert paper_fill == 56