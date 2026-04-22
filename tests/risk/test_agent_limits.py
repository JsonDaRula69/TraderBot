"""Tests for AgentRiskLimits — per-agent risk limits with HARD_LIMITS ceiling."""

import pytest

from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.models import TradingProfile
from traderbot.risk.agent_limits import AgentRiskLimits
from traderbot.risk.limits import HARD_LIMITS


@pytest.fixture
def profile_below_hard_limits() -> TradingProfile:
    """Profile with all limits below HARD_LIMITS."""
    return TradingProfile(
        name="conservative",
        mode="paper",
        description="Conservative profile",
        enabled_categories=[MarketCategory.POLITICS],
        risk_multiplier=0.5,
        max_position_per_market_pct=0.03,  # Below 0.05
        max_daily_loss_pct=0.01,  # Below 0.02
        max_drawdown_pct=0.05,  # Below 0.10
        max_open_positions=10,  # Below 20
        min_liquidity_threshold=2000,  # Above 1000
        min_edge_pct=0.05,  # Above 0.03
    )


@pytest.fixture
def profile_at_hard_limits() -> TradingProfile:
    """Profile with all limits exactly at HARD_LIMITS."""
    return TradingProfile(
        name="aggressive",
        mode="paper",
        description="Aggressive profile",
        enabled_categories=[],
        risk_multiplier=1.0,
        max_position_per_market_pct=0.05,  # At HARD_LIMITS
        max_daily_loss_pct=0.02,  # At HARD_LIMITS
        max_drawdown_pct=0.10,  # At HARD_LIMITS
        max_open_positions=20,  # At HARD_LIMITS
        min_liquidity_threshold=1000,  # At HARD_LIMITS
        min_edge_pct=0.03,  # At HARD_LIMITS
    )


def test_profile_below_hard_limits(profile_below_hard_limits: TradingProfile) -> None:
    """Profile with limits below HARD_LIMITS uses profile values."""
    limits = AgentRiskLimits(profile_below_hard_limits)

    # Should use profile values (more restrictive than HARD_LIMITS)
    assert limits.max_position_per_market_pct == 0.03
    assert limits.max_daily_loss_pct == 0.01
    assert limits.max_drawdown_pct == 0.05
    assert limits.max_open_positions == 10
    assert limits.min_liquidity_threshold == 2000
    assert limits.min_edge_pct == 0.05


def test_profile_at_hard_limits(profile_at_hard_limits: TradingProfile) -> None:
    """Profile with limits at HARD_LIMITS uses HARD_LIMITS values."""
    limits = AgentRiskLimits(profile_at_hard_limits)

    # Should use HARD_LIMITS values
    assert limits.max_position_per_market_pct == HARD_LIMITS["max_position_per_market_pct"]
    assert limits.max_daily_loss_pct == HARD_LIMITS["max_daily_loss_pct"]
    assert limits.max_drawdown_pct == HARD_LIMITS["max_drawdown_pct"]
    assert limits.max_open_positions == HARD_LIMITS["max_open_positions"]
    assert limits.min_liquidity_threshold == HARD_LIMITS["min_liquidity_threshold"]
    assert limits.min_edge_pct == HARD_LIMITS["min_edge_pct"]


def test_properties_immutable(profile_below_hard_limits: TradingProfile) -> None:
    """All properties are read-only."""
    limits = AgentRiskLimits(profile_below_hard_limits)

    with pytest.raises(AttributeError):
        limits.max_position_per_market_pct = 0.10  # type: ignore

    with pytest.raises(AttributeError):
        limits.max_daily_loss_pct = 0.05  # type: ignore

    with pytest.raises(AttributeError):
        limits.max_drawdown_pct = 0.20  # type: ignore

    with pytest.raises(AttributeError):
        limits.max_open_positions = 50  # type: ignore

    with pytest.raises(AttributeError):
        limits.min_liquidity_threshold = 500  # type: ignore

    with pytest.raises(AttributeError):
        limits.min_edge_pct = 0.01  # type: ignore


def test_min_liquidity_uses_max_logic(profile_below_hard_limits: TradingProfile) -> None:
    """min_liquidity_threshold uses max() not min() (higher is more restrictive)."""
    # Profile has 2000, HARD_LIMITS has 1000
    # Should use 2000 (the higher, more restrictive value)
    limits = AgentRiskLimits(profile_below_hard_limits)
    assert limits.min_liquidity_threshold == 2000

    # Create profile with liquidity below HARD_LIMITS
    profile_low_liquidity = TradingProfile(
        name="low_liquidity",
        mode="paper",
        description="Low liquidity profile",
        enabled_categories=[],
        risk_multiplier=1.0,
        max_position_per_market_pct=0.05,
        max_daily_loss_pct=0.02,
        max_drawdown_pct=0.10,
        max_open_positions=20,
        min_liquidity_threshold=1000,  # At HARD_LIMITS floor
        min_edge_pct=0.03,
    )
    limits_low = AgentRiskLimits(profile_low_liquidity)
    # Should use HARD_LIMITS value (1000) since it's the max
    assert limits_low.min_liquidity_threshold == 1000


def test_min_edge_uses_max_logic(profile_below_hard_limits: TradingProfile) -> None:
    """min_edge_pct uses max() not min() (higher is more restrictive)."""
    # Profile has 0.05, HARD_LIMITS has 0.03
    # Should use 0.05 (the higher, more restrictive value)
    limits = AgentRiskLimits(profile_below_hard_limits)
    assert limits.min_edge_pct == 0.05

    # Create profile with edge at HARD_LIMITS
    profile_low_edge = TradingProfile(
        name="low_edge",
        mode="paper",
        description="Low edge profile",
        enabled_categories=[],
        risk_multiplier=1.0,
        max_position_per_market_pct=0.05,
        max_daily_loss_pct=0.02,
        max_drawdown_pct=0.10,
        max_open_positions=20,
        min_liquidity_threshold=1000,
        min_edge_pct=0.03,  # At HARD_LIMITS floor
    )
    limits_low = AgentRiskLimits(profile_low_edge)
    # Should use HARD_LIMITS value (0.03) since it's the max
    assert limits_low.min_edge_pct == 0.03


def test_stores_profile_reference(profile_below_hard_limits: TradingProfile) -> None:
    """AgentRiskLimits stores reference to profile for category filtering."""
    limits = AgentRiskLimits(profile_below_hard_limits)
    
    # Should have access to profile for category checks
    assert hasattr(limits, "_profile")
    assert limits._profile.name == "conservative"
    assert limits._profile.is_category_enabled(MarketCategory.POLITICS)
    assert not limits._profile.is_category_enabled(MarketCategory.ECONOMICS)

# Made with Bob
