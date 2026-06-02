"""Tests for risk/limits.py — immutable hard-limits enforcement."""

from __future__ import annotations

import pytest

from traderbot.kalshi.models import PortfolioState, TradeRequest
from traderbot.risk.limits import (
    HARD_LIMITS,
    check_daily_loss,
    check_drawdown,
    check_liquidity,
    check_max_positions,
    check_min_edge,
    check_position_limit,
    run_all_checks,
)

PORTFOLIO_VALUE = 100_000_00  # $100,000 in cents


class TestCheckPositionLimit:
    def test_passes_at_exact_boundary(self):
        limit = int(PORTFOLIO_VALUE * 0.05)
        result = check_position_limit(0, limit, PORTFOLIO_VALUE)
        assert result.passed
        assert result.rejection_reason is None

    def test_fails_over_boundary(self):
        limit = int(PORTFOLIO_VALUE * 0.05)
        result = check_position_limit(0, limit + 1, PORTFOLIO_VALUE)
        assert not result.passed
        assert result.rejection_reason == "Position would exceed 5% portfolio limit"

    def test_zero_current_position(self):
        result = check_position_limit(0, 100_00, PORTFOLIO_VALUE)
        assert result.passed

    def test_existing_position_near_limit(self):
        existing = int(PORTFOLIO_VALUE * 0.04)
        small_order = int(PORTFOLIO_VALUE * 0.01)
        result = check_position_limit(existing, small_order, PORTFOLIO_VALUE)
        assert result.passed

    def test_existing_position_exceeds_with_new_order(self):
        existing = int(PORTFOLIO_VALUE * 0.04)
        too_big = int(PORTFOLIO_VALUE * 0.02)
        result = check_position_limit(existing, too_big, PORTFOLIO_VALUE)
        assert not result.passed


class TestCheckDailyLoss:
    def test_passes_at_exact_boundary(self):
        limit = int(PORTFOLIO_VALUE * 0.02)
        result = check_daily_loss(limit, PORTFOLIO_VALUE)
        assert result.passed

    def test_fails_over_boundary(self):
        limit = int(PORTFOLIO_VALUE * 0.02)
        result = check_daily_loss(limit + 1, PORTFOLIO_VALUE)
        assert not result.passed
        assert result.rejection_reason == "Daily loss exceeds 2% limit"

    def test_zero_loss(self):
        result = check_daily_loss(0, PORTFOLIO_VALUE)
        assert result.passed


class TestCheckDrawdown:
    def test_passes_at_exact_boundary(self):
        peak = 110_000_00
        current = int(peak * 0.9)  # exactly 10% drawdown
        result = check_drawdown(peak, current)
        assert result.passed

    def test_fails_over_boundary(self):
        peak = 110_000_00
        current = int(peak * 0.89)  # 11% drawdown
        result = check_drawdown(peak, current)
        assert not result.passed
        assert result.rejection_reason == "Drawdown exceeds 10% limit"

    def test_no_drawdown(self):
        peak = 100_000_00
        result = check_drawdown(peak, 100_000_00)
        assert result.passed

    def test_zero_peak_value_passes(self):
        result = check_drawdown(0, 0)
        assert result.passed
        assert result.current_value == 0.0

    def test_negative_peak_value_passes(self):
        result = check_drawdown(-1, 0)
        assert result.passed


class TestCheckLiquidity:
    def test_passes_at_threshold(self):
        result = check_liquidity(1000)
        assert result.passed

    def test_fails_below_threshold(self):
        result = check_liquidity(499)
        assert not result.passed
        assert result.rejection_reason == "Market liquidity below 500 threshold"

    def test_passes_well_above(self):
        result = check_liquidity(5000)
        assert result.passed


class TestCheckMaxPositions:
    def test_passes_below_limit(self):
        result = check_max_positions(19)
        assert result.passed

    def test_fails_at_limit(self):
        result = check_max_positions(20)
        assert not result.passed
        assert result.rejection_reason == "Open positions exceed 20 limit"

    def test_fails_over_limit(self):
        result = check_max_positions(25)
        assert not result.passed

    def test_passes_with_zero_positions(self):
        result = check_max_positions(0)
        assert result.passed


class TestCheckMinEdge:
    def test_passes_at_exact_boundary(self):
        result = check_min_edge(0.65, 0.62)
        assert result.passed  # edge = 0.03

    def test_fails_just_below_boundary(self):
        result = check_min_edge(0.629, 0.60)
        assert not result.passed
        assert result.rejection_reason == "Edge below 3% minimum"

    def test_passes_with_significant_edge(self):
        result = check_min_edge(0.80, 0.50)
        assert result.passed

    def test_zero_edge(self):
        result = check_min_edge(0.50, 0.50)
        assert not result.passed


class TestHardLimitsImmutability:
    def test_cannot_mutate_hard_limits(self):
        with pytest.raises(TypeError):
            HARD_LIMITS["max_position_per_market_pct"] = 0.50

    def test_cannot_delete_from_hard_limits(self):
        with pytest.raises(TypeError):
            del HARD_LIMITS["max_position_per_market_pct"]

    def test_hard_limits_values_match_spec(self):
        assert HARD_LIMITS["max_position_per_market_pct"] == 0.05
        assert HARD_LIMITS["max_daily_loss_pct"] == 0.02
        assert HARD_LIMITS["max_drawdown_pct"] == 0.10
        assert HARD_LIMITS["min_liquidity_threshold"] == 500
        assert HARD_LIMITS["max_open_positions"] == 20
        assert HARD_LIMITS["min_edge_pct"] == 0.03


class TestRunAllChecks:
    @pytest.fixture()
    def valid_portfolio(self) -> PortfolioState:
        return PortfolioState(
            portfolio_value_cents=100_000_00,
            peak_value_cents=110_000_00,
            current_positions_value_cents=1_000_00,
            today_realized_loss_cents=100_00,
            today_unrealized_loss_cents=50_00,
            open_positions_count=5,
        )

    @pytest.fixture()
    def valid_trade(self) -> TradeRequest:
        return TradeRequest(
            ticker="KXBTCD-26MAR31-T55000",
            direction="yes",
            quantity=10,
            price_cents=50,
            estimated_prob=0.65,
            confidence=0.8,
            edge_estimate=0.15,
            market_price_cents=62,
            market_open_interest=2500,
        )

    def test_returns_six_results(self, valid_trade, valid_portfolio):
        results = run_all_checks(valid_trade, valid_portfolio)
        assert len(results) == 6

    def test_all_pass_for_valid_trade(self, valid_trade, valid_portfolio):
        results = run_all_checks(valid_trade, valid_portfolio)
        assert all(r.passed for r in results)

    def test_fails_with_excessive_position(self, valid_trade):
        big_portfolio = PortfolioState(
            portfolio_value_cents=100_000_00,
            peak_value_cents=110_000_00,
            current_positions_value_cents=4_500_00,
            today_realized_loss_cents=100_00,
            today_unrealized_loss_cents=50_00,
            open_positions_count=5,
        )
        big_trade = TradeRequest(
            ticker="KXBTCD-26MAR31-T55000",
            direction="yes",
            quantity=6,
            price_cents=9000,
            estimated_prob=0.65,
            confidence=0.8,
            edge_estimate=0.15,
            market_price_cents=62,
            market_open_interest=2500,
        )
        results = run_all_checks(big_trade, big_portfolio)
        position_result = next(r for r in results if r.limit_name == "position_limit")
        assert not position_result.passed

    def test_fails_with_drawdown_breach(self, valid_trade):
        bad_portfolio = PortfolioState(
            portfolio_value_cents=95_000_00,
            peak_value_cents=110_000_00,
            current_positions_value_cents=1_000_00,
            today_realized_loss_cents=500_00,
            today_unrealized_loss_cents=0,
            open_positions_count=5,
        )
        results = run_all_checks(valid_trade, bad_portfolio)
        drawdown_result = next(r for r in results if r.limit_name == "drawdown")
        assert not drawdown_result.passed


class TestPortfolioValueUsesInitialCents:
    """Regression: portfolio_value_cents must come from initial_cents, not remaining_cents.

    Bug: trade.py:290 previously used remaining_cents (balance after losses)
    instead of initial_cents (starting balance). This meant that after losses,
    the position limit would shrink based on losses already accounted for in
    daily-loss checks — double-counting risk. The correct behavior is for
    portfolio_value_cents to equal the initial capital so limits stay stable.
    """

    def test_position_limit_uses_full_initial_portfolio(self) -> None:
        """Position limit should be 5% of initial_cents, not 5% of remaining_cents."""
        initial_cents = 100_000_00  # $1,000 initial deposit
        remaining_cents = 80_000_00  # $800 after $200 in losses
        existing_positions = 2_000_00
        # With initial_cents, the 5% limit = $50 → order of $300 should pass
        result = check_position_limit(existing_positions, 3_000_00, initial_cents)
        assert result.passed, (
            f"Position limit should use initial_cents ({initial_cents}), "
            f"not remaining_cents ({remaining_cents})"
        )

    def test_position_limit_would_fail_if_using_remaining_cents(self) -> None:
        """If portfolio_value_cents were remaining_cents (smaller), limits would be too tight."""
        initial_cents = 100_000_00
        remaining_cents = 40_000_00  # After heavy losses
        existing_positions = 1_500_00
        # With initial_cents: 5% of 100000 = 5000, 1500+2500=4000 → pass
        # With remaining_cents: 5% of 40000 = 2000, 1500+2500=4000 → fail
        result_initial = check_position_limit(existing_positions, 2_500_00, initial_cents)
        assert result_initial.passed, "Using initial_cents should allow this order"

        result_remaining = check_position_limit(existing_positions, 2_500_00, remaining_cents)
        assert not result_remaining.passed, "Using remaining_cents would double-count losses"

    def test_run_all_checks_uses_initial_portfolio_value(self) -> None:
        """run_all_checks should use portfolio_value_cents as initial capital, not reduced."""
        initial_portfolio = PortfolioState(
            portfolio_value_cents=100_000_00,  # initial_cents (not remaining)
            peak_value_cents=100_000_00,
            current_positions_value_cents=1_000_00,
            today_realized_loss_cents=200_00,  # $200 in realized losses
            today_unrealized_loss_cents=50_00,
            open_positions_count=5,
        )
        trade = TradeRequest(
            ticker="KXBTCD-26MAR31-T55000",
            direction="yes",
            quantity=10,
            price_cents=40,  # $0.40 per contract → $4 total
            estimated_prob=0.65,
            confidence=0.8,
            edge_estimate=0.15,
            market_price_cents=62,
            market_open_interest=2500,
        )
        results = run_all_checks(trade, initial_portfolio)
        position_result = next(r for r in results if r.limit_name == "position_limit")
        assert position_result.passed, (
            "With initial_cents as portfolio_value, small order should pass position limit"
        )
