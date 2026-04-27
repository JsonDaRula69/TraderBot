"""Tests for profile-aware news pipeline: CLI resolution, category filtering, credential chain."""

import os
from unittest.mock import patch

import pytest

from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.auth import ProfileAuthStore
from traderbot.profiles.config import resolve_kalshi_credentials, resolve_newsapi_key
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


class MockKeyring:
    """In-memory keyring mock for testing."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        self._store.pop((service, username), None)

    def keys(self) -> list[tuple[str, str]]:
        return list(self._store.keys())


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
        assert open_profile.is_category_enabled(MarketCategory.CRYPTO) is True


class TestCredentialResolution:
    """Profile-aware credential resolution falls back correctly."""

    def test_profile_credentials_take_priority(self) -> None:
        mock_kr = MockKeyring()
        mock_kr.set_password(
            "traderbot.profiles.test-agent.kalshi",
            "credentials",
            '{"key": "profile-key", "secret": "profile-secret", "created_at": "2025-01-01T00:00:00+00:00"}',
        )
        store = ProfileAuthStore(_SAMPLE_PROFILE, keyring_module=mock_kr)
        creds = store.get_credentials("kalshi")
        assert creds is not None
        assert creds[0] == "profile-key"

    def test_resolve_newsapi_key_returns_env_fallback(self) -> None:
        mock_kr = MockKeyring()
        with patch.dict(os.environ, {"NEWSAPI_KEY": "env-key-123"}):
            key = resolve_newsapi_key(None, global_keyring=mock_kr)
            assert key == "env-key-123"

    def test_resolve_newsapi_key_none_when_no_source(self) -> None:
        mock_kr = MockKeyring()
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("NEWSAPI_KEY", None)
            key = resolve_newsapi_key(None, global_keyring=mock_kr)
            assert key is None