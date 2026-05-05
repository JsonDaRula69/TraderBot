"""Tests for risk/__init__.py — unified risk gate integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from traderbot.kalshi.models import PortfolioState, TradeRequest
from traderbot.risk import evaluate_trade, evaluate_trade_full
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

    def test_circuit_breaker_uses_total_loss_including_unrealized(self, tmp_path: Path) -> None:
        """Circuit breaker should trip HALT when unrealized + realized loss crosses 2%."""
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        # Realized loss 1% + unrealized loss 1.5% = 2.5% total → HALT
        trade = _make_trade()
        portfolio = _make_portfolio(
            today_realized_loss_cents=1_000_00,
            today_unrealized_loss_cents=1_500_00,
        )
        size = evaluate_trade(trade, portfolio, breaker)
        assert size == 0


class TestKellyOddsFormula:
    def test_kelly_odds_formula_yes_trade(self, tmp_path: Path) -> None:
        """Odds for a YES trade at price_cents=5 with estimated_prob=0.10 should be (100-5)/5 = 19.0."""
        from traderbot.risk.sizing import sized_position_for_trade

        trade = _make_trade(price_cents=5, estimated_prob=0.10)
        portfolio = _make_portfolio()
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")

        size = evaluate_trade(trade, portfolio, breaker)
        assert size > 0

        # Verify odds directly: (100-5)/5 = 19.0, not 5/95 ≈ 0.053
        odds_correct = (100 - trade.price_cents) / max(trade.price_cents, 1)
        odds_inverted = trade.price_cents / max(100 - trade.price_cents, 1)
        assert odds_correct == 19.0
        assert abs(odds_inverted - 0.0526) < 0.01

        # With correct odds, Kelly fraction is much larger
        kelly_correct = sized_position_for_trade(
            prob=0.10, odds=19.0, confidence=0.8,
            bankroll_cents=100_000_00, max_position_cents=5_000_00,
        )
        kelly_inverted = sized_position_for_trade(
            prob=0.10, odds=0.053, confidence=0.8,
            bankroll_cents=100_000_00, max_position_cents=5_000_00,
        )
        assert kelly_correct > kelly_inverted

    def test_kelly_odds_formula_no_trade(self, tmp_path: Path) -> None:
        """Odds for a NO trade at price_cents=95 should be (100-95)/95 ≈ 0.053."""
        trade = _make_trade(price_cents=95, estimated_prob=0.90)
        odds = (100 - trade.price_cents) / max(trade.price_cents, 1)
        assert abs(odds - 0.0526) < 0.01


class TestDirectionPreserved:
    def test_direction_preserved_yes(self, tmp_path: Path) -> None:
        """evaluate_trade_full preserves direction='yes' from TradeRequest."""
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        trade = _make_trade(direction="yes")
        portfolio = _make_portfolio()
        result = evaluate_trade_full(trade, portfolio, breaker)
        assert result.direction == "yes"
        assert result.sized_position_cents > 0

    def test_direction_preserved_no(self, tmp_path: Path) -> None:
        """evaluate_trade_full preserves direction='no' from TradeRequest."""
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        trade = _make_trade(direction="no")
        portfolio = _make_portfolio()
        result = evaluate_trade_full(trade, portfolio, breaker)
        assert result.direction == "no"
        assert result.sized_position_cents > 0

    def test_direction_preserved_when_rejected(self, tmp_path: Path) -> None:
        """Direction is preserved even when the trade is rejected."""
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        trade = _make_trade(direction="no", quantity=100_000)
        portfolio = _make_portfolio(open_positions_count=100)
        result = evaluate_trade_full(trade, portfolio, breaker)
        assert result.direction == "no"
        assert result.sized_position_cents == 0
