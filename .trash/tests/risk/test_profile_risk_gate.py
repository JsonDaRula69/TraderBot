"""Tests for profile-aware risk gate with category filtering."""

from __future__ import annotations

import pytest
from typing import TYPE_CHECKING

from traderbot.kalshi.models import MarketCategory, PortfolioState, TradeRequest
from traderbot.profiles.models import TradingProfile
from traderbot.risk import RiskCheckError, evaluate_trade
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
        market_category=MarketCategory.ECONOMICS,
    )
    defaults.update(overrides)
    return TradeRequest(**defaults)


def _make_profile(**overrides) -> TradingProfile:
    defaults = dict(
        name="test-agent",
        mode="paper",
        description="Test profile",
        enabled_categories=[],
        risk_multiplier=1.0,
        max_position_per_market_pct=0.05,
        max_daily_loss_pct=0.02,
        max_drawdown_pct=0.10,
        max_open_positions=20,
        min_liquidity_threshold=1000,
        min_edge_pct=0.03,
    )
    defaults.update(overrides)
    return TradingProfile(**defaults)


class TestCategoryFiltering:
    """Test category filtering with profile-aware risk gate."""

    def test_category_allowed_when_in_enabled_list(self, tmp_path: Path) -> None:
        """Trade in allowed category should be approved (if other checks pass)."""
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        profile = _make_profile(enabled_categories=[MarketCategory.ECONOMICS, MarketCategory.POLITICS])
        trade = _make_trade(market_category=MarketCategory.ECONOMICS)
        portfolio = _make_portfolio()

        size = evaluate_trade(trade, portfolio, breaker, profile=profile)
        assert size > 0

    def test_category_rejected_when_not_in_enabled_list(self, tmp_path: Path) -> None:
        """Trade in disallowed category should be rejected."""
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        profile = _make_profile(enabled_categories=[MarketCategory.POLITICS])
        trade = _make_trade(market_category=MarketCategory.ECONOMICS)
        portfolio = _make_portfolio()

        size = evaluate_trade(trade, portfolio, breaker, profile=profile)
        assert size == 0

    def test_empty_categories_allows_all(self, tmp_path: Path) -> None:
        """Empty enabled_categories list should allow all categories."""
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        profile = _make_profile(enabled_categories=[])
        trade = _make_trade(market_category=MarketCategory.SPORTS)
        portfolio = _make_portfolio()

        size = evaluate_trade(trade, portfolio, breaker, profile=profile)
        assert size > 0

    def test_none_category_bypasses_filter(self, tmp_path: Path) -> None:
        """Trade with None category should bypass category filtering."""
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        profile = _make_profile(enabled_categories=[MarketCategory.POLITICS])
        trade = _make_trade(market_category=None)
        portfolio = _make_portfolio()

        size = evaluate_trade(trade, portfolio, breaker, profile=profile)
        assert size > 0


class TestProfileLimitsOverride:
    """Test that profile limits override HARD_LIMITS."""

    def test_profile_with_lower_position_limit(self, tmp_path: Path) -> None:
        """Profile with lower position limit should be enforced."""
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        # Profile with 2% position limit (vs 5% HARD_LIMITS)
        profile = _make_profile(max_position_per_market_pct=0.02)
        trade = _make_trade()
        portfolio = _make_portfolio()

        # Get size with profile
        profile_size = evaluate_trade(trade, portfolio, breaker, profile=profile)

        # Get size without profile (HARD_LIMITS)
        hard_limits_size = evaluate_trade(trade, portfolio, breaker, profile=None)

        # Profile size should be smaller due to lower limit
        assert profile_size > 0
        assert hard_limits_size > 0
        assert profile_size < hard_limits_size

    def test_risk_multiplier_reduces_position_size(self, tmp_path: Path) -> None:
        """Profile with risk_multiplier 0.5 should size at 50% of normal."""
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        profile_full = _make_profile(risk_multiplier=1.0)
        profile_half = _make_profile(risk_multiplier=0.5)
        trade = _make_trade()
        portfolio = _make_portfolio()

        size_full = evaluate_trade(trade, portfolio, breaker, profile=profile_full)
        size_half = evaluate_trade(trade, portfolio, breaker, profile=profile_half)

        assert size_full > 0
        assert size_half > 0
        assert size_half == size_full // 2


class TestBackwardCompatibility:
    """Test that no profile provided uses HARD_LIMITS (backward compatibility)."""

    def test_no_profile_uses_hard_limits(self, tmp_path: Path) -> None:
        """No profile provided should use HARD_LIMITS behavior."""
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        trade = _make_trade()
        portfolio = _make_portfolio()

        size = evaluate_trade(trade, portfolio, breaker, profile=None)
        assert size > 0

    def test_no_profile_ignores_category(self, tmp_path: Path) -> None:
        """No profile provided should not filter by category."""
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        # Any category should work without profile
        trade = _make_trade(market_category=MarketCategory.WEATHER)
        portfolio = _make_portfolio()

        size = evaluate_trade(trade, portfolio, breaker, profile=None)
        assert size > 0


class TestProfileWithOtherRiskChecks:
    """Test that profile-aware gate still enforces all other risk checks."""

    def test_profile_respects_circuit_breaker(self, tmp_path: Path) -> None:
        """Profile-aware gate should still respect circuit breaker."""
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        profile = _make_profile()
        portfolio = _make_portfolio(today_realized_loss_cents=90_000_00)
        trade = _make_trade()

        # Trip the breaker
        breaker.check(daily_loss_pct=0.9, drawdown_pct=0.1)

        size = evaluate_trade(trade, portfolio, breaker, profile=profile)
        assert size == 0

    def test_profile_respects_liquidity_check(self, tmp_path: Path) -> None:
        """Profile-aware gate should still enforce liquidity checks."""
        breaker = CircuitBreaker(state_file=tmp_path / "cb.json")
        profile = _make_profile()
        trade = _make_trade(market_open_interest=500)  # Below 1000 threshold
        portfolio = _make_portfolio()

        with pytest.raises(RiskCheckError):
            evaluate_trade(trade, portfolio, breaker, profile=profile)


# Made with Bob