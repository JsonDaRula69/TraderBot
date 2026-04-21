from datetime import datetime
import pytest
from pydantic import ValidationError
from traderbot.simulation.models import BacktestConfig, BacktestTrade, BacktestResult, Context
from traderbot.kalshi.models import Market, PortfolioState


def test_backtest_config_valid():
    config = BacktestConfig(
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2023, 12, 31),
        strategy_name="TestStrategy",
        initial_bankroll=1000000,
        slippage_model="linear"
    )
    assert config.initial_bankroll == 1000000


def test_backtest_config_invalid_float_bankroll():
    with pytest.raises(ValidationError):
        BacktestConfig(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            strategy_name="TestStrategy",
            initial_bankroll=100.5,
            slippage_model="linear"
        )


def test_backtest_config_extra_field():
    with pytest.raises(ValidationError):
        BacktestConfig(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            strategy_name="TestStrategy",
            initial_bankroll=1000000,
            slippage_model="linear",
            extra_field=123
        )


def test_backtest_trade_valid():
    trade = BacktestTrade(
        ticker="AAPL",
        direction="yes",
        entry_price=15000,
        exit_price=15500,
        quantity=1,
        timestamp=datetime(2023, 1, 1),
        pnl=500
    )
    assert trade.pnl == 500


def test_backtest_trade_invalid_quantity_type():
    with pytest.raises(ValidationError):
        BacktestTrade(
            ticker="AAPL",
            direction="yes",
            entry_price=15000,
            exit_price=15500,
            quantity=0.5,
            timestamp=datetime(2023, 1, 1),
            pnl=500
        )


def test_backtest_trade_invalid_quantity_zero():
    with pytest.raises(ValidationError):
        BacktestTrade(
            ticker="AAPL",
            direction="yes",
            entry_price=15000,
            exit_price=15500,
            quantity=0,
            timestamp=datetime(2023, 1, 1),
            pnl=500
        )


def test_backtest_result_valid():
    config = BacktestConfig(
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2023, 12, 31),
        strategy_name="Test",
        initial_bankroll=100000,
        slippage_model="linear"
    )
    trades = [
        BacktestTrade(
            ticker="AAPL",
            direction="yes",
            entry_price=15000,
            exit_price=15500,
            quantity=1,
            timestamp=datetime(2023, 1, 1),
            pnl=500
        )
    ]
    result = BacktestResult(
        total_pnl=500,
        win_rate=0.5,
        trade_count=1,
        sharpe_ratio=1.5,
        max_drawdown=0.05,
        brier_score=0.1,
        edge_capture=0.8,
        fill_rate=0.9,
        trades=trades,
        config=config
    )
    assert result.total_pnl == 500


def test_backtest_result_invalid_win_rate():
    with pytest.raises(ValidationError):
        BacktestResult(
            total_pnl=500,
            win_rate=1.5,
            trade_count=1,
            sharpe_ratio=1.5,
            max_drawdown=0.05,
            brier_score=0.1,
            edge_capture=0.8,
            fill_rate=0.9,
            trades=[],
            config=BacktestConfig(
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
                strategy_name="Test",
                initial_bankroll=100000,
                slippage_model="linear"
            )
        )


def test_context_valid():
    market = Market(
        ticker="KXBTCD-26MAR31-T55000",
        question="Bitcoin to hit $55k by Q1 2026?",
        outcome_prices=["yes", "no"],
        volume=0,
        open_interest=0,
        close_time=datetime.now(),
        state="open",
        event_ticker="BTC",
        category="Crypto"
    )
    portfolio = PortfolioState(
        portfolio_value_cents=1000000,
        peak_value_cents=1000000,
        current_positions_value_cents=1000000,
        today_realized_loss_cents=0,
        today_unrealized_loss_cents=0,
        open_positions_count=0
    )
    context = Context(
        portfolio=portfolio,
        market_data=[market],
        sentiment={"sentiment_score": 0.8},
        risk_state={"position_limit": 10000}
    )
    assert context.portfolio.portfolio_value_cents == 1000000


def test_context_extra_field():
    with pytest.raises(ValidationError):
        Context(
            portfolio=PortfolioState(portfolio_value_cents=1000000),
            market_data=[],
            sentiment={"sentiment_score": 0.8},
            risk_state={"position_limit": 10000},
            extra_field=123
        )