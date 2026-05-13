"""Tests for profile-aware news pipeline: CLI resolution, category filtering."""

import os
from unittest.mock import patch

import pytest

from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.models import TradingProfile
from traderbot.profiles.runtime import get_current_profile


_SAMPLE_PROFILE = TradingProfile(
    name="test-agent",
    mode="paper",
    description="Test profile",
    risk_multiplier=0.5,
    max_position_per_market_pct=0.03,
    max_daily_loss_pct=0.01,
    max_drawdown_pct=0.05,
    max_open_positions=3,
    min_liquidity_threshold=1000,
    min_edge_pct=0.03,
    enabled_categories=[MarketCategory.ECONOMICS, MarketCategory.POLITICS],
)


class TestGetProfileFromEnv:
    """get_current_profile reads TRADERBOT_PROFILE_TOKEN env var."""

    @patch.dict(os.environ, {}, clear=True)
    def test_returns_none_without_token(self) -> None:
        os.environ.pop("TRADERBOT_PROFILE_TOKEN", None)
        result = get_current_profile()
        assert result is None


class TestCategoryFiltering:
    """Profile enabled_categories gates which categories are permitted."""

    def test_enabled_category_accepted(self) -> None:
        assert _SAMPLE_PROFILE.is_category_enabled(MarketCategory.ECONOMICS) is True

    def test_disabled_category_rejected(self) -> None:
        assert _SAMPLE_PROFILE.is_category_enabled(MarketCategory.WEATHER) is False

    def test_empty_categories_accepts_all(self) -> None:
        open_profile = TradingProfile(
            name="open-agent",
            mode="paper",
            description="Open profile",
            risk_multiplier=1.0,
            max_position_per_market_pct=0.05,
            max_daily_loss_pct=0.02,
            max_drawdown_pct=0.10,
            max_open_positions=20,
            min_liquidity_threshold=1000,
            min_edge_pct=0.03,
            enabled_categories=[],
        )
        assert open_profile.is_category_enabled(MarketCategory.ECONOMICS) is True
        assert open_profile.is_category_enabled(MarketCategory.SCIENCE_AND_TECHNOLOGY) is True


