"""Tests for risk/__init__.py — unified risk gate integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from traderbot.kalshi.models import PortfolioState, TradeRequest
from traderbot.risk import evaluate_trade
from traderbot.risk.circuit_breaker import CircuitBreaker

if TYPE_CHECKING:
    from pathlib import Path

PORTFOLIO_VALUE = 100_000_00  # $100k in cents


def _make_portfolio(**overrides) -> PortfolioState:
    defaults = dict(
        portfolio_value_cents=PORTFOLIO_VALUE,
        peak_value_cents=PORTFOLIO_VALUE,
        current_positions_value_cents=1_000_00,
        today_realized_loss_cents=0,
        today_unrealized_loss_cents=0,
        open_positions_count=1,
    )
    defaults.update(overrides)
    return PortfolioState(**defaults)


def _make_trade(**overrides) -> TradeRequest:
    defaults = dict(
        ticker="KX-TEST",
        direction="yes",
        quantity=5,
        price_cents=50,
        estimated_prob=0.6,
        confidence=0.8,
        edge_estimate=10.0,
        market_price_cents=55,
        market_open_interest=1000,
    )
    defaults.update(overrides)
    return TradeRequest(**defaults)


class TestEvaluateTrade:
    def test_approves_valid_trade(self, tmp_path: Path) -> None:
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        trade = _make_trade()
        portfolio = _make_portfolio()
        size = evaluate_trade(trade, portfolio, breaker)
        assert size > 0

    def test_rejects_when_breaker_tripped(self, tmp_path: Path) -> None:
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        portfolio = _make_portfolio(today_realized_loss_cents=90_000_00)
        trade = _make_trade()
        breaker.check(daily_loss_pct=0.9, drawdown_pct=0.1)
        size = evaluate_trade(trade, portfolio, breaker)
        assert size == 0

    def test_rejects_when_limits_violated(self, tmp_path: Path) -> None:
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        trade = _make_trade(quantity=100_000)
        portfolio = _make_portfolio(open_positions_count=100)
        size = evaluate_trade(trade, portfolio, breaker)
        assert size == 0

    def test_slow_level_reduces_position_size(self, tmp_path: Path) -> None:
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        trade = _make_trade()
        portfolio = _make_portfolio()

        normal_size = evaluate_trade(trade, portfolio, breaker)
        assert normal_size > 0

        slow_portfolio = _make_portfolio(today_realized_loss_cents=1_500_00)
        slow_breaker = CircuitBreaker(state_file=tmp_path / "cb_slow.json")
        slow_breaker.check(daily_loss_pct=0.015, drawdown_pct=0.0)

        slow_size = evaluate_trade(trade, slow_portfolio, slow_breaker)
        assert 0 < slow_size < normal_size
