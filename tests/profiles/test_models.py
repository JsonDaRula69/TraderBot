"""Tests for TradingProfile model — TDD approach."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.models import TradingProfile
from traderbot.risk.limits import HARD_LIMITS


def test_create_paper_profile():
    """Valid paper profile creation with all required fields."""
    profile = TradingProfile(
        name="test-paper",
        mode="paper",
        description="Test paper trading profile",
        risk_multiplier=0.5,
        max_position_per_market_pct=0.03,
        max_daily_loss_pct=0.01,
        max_drawdown_pct=0.05,
        max_open_positions=10,
        min_liquidity_threshold=1000,
        min_edge_pct=0.03,
    )
    assert profile.name == "test-paper"
    assert profile.mode == "paper"
    assert profile.demo_mode is True
    assert profile.base_dir.endswith("/.traderbot/paper-test-paper") or profile.base_dir.endswith("\\.traderbot\\paper-test-paper")
    assert profile.keyring_prefix == "traderbot-paper-test-paper"
    assert profile.env_file == ".env.paper"


def test_create_live_profile():
    """Valid live profile creation with computed properties."""
    profile = TradingProfile(
        name="test-live",
        mode="live",
        description="Test live trading profile",
        risk_multiplier=1.0,
        max_position_per_market_pct=0.05,
        max_daily_loss_pct=0.02,
        max_drawdown_pct=0.10,
        max_open_positions=20,
        min_liquidity_threshold=1000,
        min_edge_pct=0.03,
    )
    assert profile.name == "test-live"
    assert profile.mode == "live"
    assert profile.demo_mode is False
    assert profile.base_dir.endswith("/.traderbot/live-test-live") or profile.base_dir.endswith("\\.traderbot\\live-test-live")
    assert profile.keyring_prefix == "traderbot-live-test-live"
    assert profile.env_file == ".env.live"


def test_risk_exceeds_hard_limits():
    """Risk params exceeding HARD_LIMITS should raise ValidationError."""
    # max_position_per_market_pct exceeds 0.05
    with pytest.raises(ValidationError, match="max_position_per_market_pct.*exceeds.*HARD_LIMITS"):
        TradingProfile(
            name="bad-profile",
            mode="paper",
            description="Invalid profile",
            risk_multiplier=0.5,
            max_position_per_market_pct=0.06,  # > 0.05
            max_daily_loss_pct=0.01,
            max_drawdown_pct=0.05,
            max_open_positions=10,
            min_liquidity_threshold=500,
            min_edge_pct=0.02,
        )


def test_risk_at_hard_limits():
    """Risk params at HARD_LIMITS ceiling should succeed."""
    profile = TradingProfile(
        name="max-risk",
        mode="paper",
        description="Profile at hard limits",
        risk_multiplier=1.0,
        max_position_per_market_pct=float(HARD_LIMITS["max_position_per_market_pct"]),
        max_daily_loss_pct=float(HARD_LIMITS["max_daily_loss_pct"]),
        max_drawdown_pct=float(HARD_LIMITS["max_drawdown_pct"]),
        max_open_positions=int(HARD_LIMITS["max_open_positions"]),
        min_liquidity_threshold=int(HARD_LIMITS["min_liquidity_threshold"]),
        min_edge_pct=float(HARD_LIMITS["min_edge_pct"]),
    )
    assert profile.max_position_per_market_pct == 0.05
    assert profile.max_daily_loss_pct == 0.02
    assert profile.max_drawdown_pct == 0.10


def test_empty_enabled_categories_permits_all():
    """Empty enabled_categories list should permit all categories."""
    profile = TradingProfile(
        name="all-categories",
        mode="paper",
        description="Profile with all categories enabled",
        enabled_categories=[],
        risk_multiplier=0.5,
        max_position_per_market_pct=0.03,
        max_daily_loss_pct=0.01,
        max_drawdown_pct=0.05,
        max_open_positions=10,
        min_liquidity_threshold=1000,
        min_edge_pct=0.03,
    )
    # All categories should be permitted
    assert profile.is_category_enabled(MarketCategory.ECONOMICS)
    assert profile.is_category_enabled(MarketCategory.POLITICS)
    assert profile.is_category_enabled(MarketCategory.SPORTS)
    assert profile.is_category_enabled(MarketCategory.SCIENCE_AND_TECHNOLOGY)


def test_specific_enabled_categories():
    """Only specified categories should be permitted."""
    profile = TradingProfile(
        name="econ-only",
        mode="paper",
        description="Economics-focused profile",
        enabled_categories=[MarketCategory.ECONOMICS, MarketCategory.POLITICS],
        risk_multiplier=0.5,
        max_position_per_market_pct=0.03,
        max_daily_loss_pct=0.01,
        max_drawdown_pct=0.05,
        max_open_positions=10,
        min_liquidity_threshold=1000,
        min_edge_pct=0.03,
    )
    assert profile.is_category_enabled(MarketCategory.ECONOMICS)
    assert profile.is_category_enabled(MarketCategory.POLITICS)
    assert not profile.is_category_enabled(MarketCategory.SPORTS)
    assert not profile.is_category_enabled(MarketCategory.SCIENCE_AND_TECHNOLOGY)


def test_category_not_in_list():
    """Category not in enabled_categories should return False."""
    profile = TradingProfile(
        name="sports-only",
        mode="paper",
        description="Sports-focused profile",
        enabled_categories=[MarketCategory.SPORTS],
        risk_multiplier=0.5,
        max_position_per_market_pct=0.03,
        max_daily_loss_pct=0.01,
        max_drawdown_pct=0.05,
        max_open_positions=10,
        min_liquidity_threshold=1000,
        min_edge_pct=0.03,
    )
    assert profile.is_category_enabled(MarketCategory.SPORTS)
    assert not profile.is_category_enabled(MarketCategory.ECONOMICS)
    assert not profile.is_category_enabled(MarketCategory.POLITICS)


def test_multiple_risk_params_exceed_limits():
    """Multiple risk params exceeding limits should fail validation."""
    with pytest.raises(ValidationError) as exc_info:
        TradingProfile(
            name="bad-multi",
            mode="paper",
            description="Multiple violations",
            risk_multiplier=0.5,
            max_position_per_market_pct=0.10,  # > 0.05
            max_daily_loss_pct=0.05,  # > 0.02
            max_drawdown_pct=0.05,
            max_open_positions=10,
            min_liquidity_threshold=500,
            min_edge_pct=0.02,
        )
    # Should mention at least one violation
    error_str = str(exc_info.value)
    assert "HARD_LIMITS" in error_str or "exceeds" in error_str


def test_max_open_positions_exceeds_limit():
    """max_open_positions exceeding HARD_LIMITS should fail."""
    with pytest.raises(ValidationError, match="max_open_positions.*exceeds.*HARD_LIMITS"):
        TradingProfile(
            name="too-many-positions",
            mode="paper",
            description="Too many positions",
            risk_multiplier=0.5,
            max_position_per_market_pct=0.03,
            max_daily_loss_pct=0.01,
            max_drawdown_pct=0.05,
            max_open_positions=25,  # > 20
            min_liquidity_threshold=500,
            min_edge_pct=0.02,
        )


def test_min_liquidity_below_threshold():
    """min_liquidity_threshold below HARD_LIMITS should fail."""
    with pytest.raises(ValidationError, match="min_liquidity_threshold.*below.*HARD_LIMITS"):
        TradingProfile(
            name="low-liquidity",
            mode="paper",
            description="Low liquidity threshold",
            risk_multiplier=0.5,
            max_position_per_market_pct=0.03,
            max_daily_loss_pct=0.01,
            max_drawdown_pct=0.05,
            max_open_positions=10,
            min_liquidity_threshold=500,  # < 1000
            min_edge_pct=0.02,
        )


def test_min_edge_below_threshold():
    """min_edge_pct below HARD_LIMITS should fail."""
    with pytest.raises(ValidationError, match="min_edge_pct.*below.*HARD_LIMITS"):
        TradingProfile(
            name="low-edge",
            mode="paper",
            description="Low edge threshold",
            risk_multiplier=0.5,
            max_position_per_market_pct=0.03,
            max_daily_loss_pct=0.01,
            max_drawdown_pct=0.05,
            max_open_positions=10,
            min_liquidity_threshold=1000,
            min_edge_pct=0.01,  # < 0.03
        )

# Made with Bob
