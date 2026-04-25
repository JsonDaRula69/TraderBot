"""Tests for credential resolution chain."""

from __future__ import annotations

import pytest

from traderbot.auth import AuthManager
from traderbot.profiles.config import resolve_kalshi_credentials
from traderbot.profiles.auth import ProfileAuthStore
from traderbot.profiles.models import TradingProfile
from traderbot.kalshi.models import MarketCategory


class MockKeyring:
    """Mock keyring for testing."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        key = (service, username)
        if key in self._store:
            del self._store[key]


@pytest.fixture
def mock_keyring() -> MockKeyring:
    """Provide a mock keyring for testing."""
    return MockKeyring()


@pytest.fixture
def test_profile(mock_keyring: MockKeyring) -> TradingProfile:
    """Create a test trading profile."""
    return TradingProfile(
        name="test-profile",
        mode="paper",
        description="Test profile for config tests",
        enabled_categories=[MarketCategory.POLITICS],
        risk_multiplier=0.5,
        max_position_per_market_pct=0.05,
        max_daily_loss_pct=0.02,
        max_drawdown_pct=0.10,
        max_open_positions=5,
        min_liquidity_threshold=1000,
        min_edge_pct=0.03,
    )


def test_resolve_with_profile_credentials(test_profile: TradingProfile, mock_keyring: MockKeyring) -> None:
    """Profile with credentials returns profile credentials."""
    # Set profile credentials
    auth_mgr = ProfileAuthStore(test_profile, keyring_module=mock_keyring)
    auth_mgr.set_credentials("kalshi", "profile-key", "profile-secret")
    
    # Resolve should return profile credentials
    key, secret = resolve_kalshi_credentials(test_profile, profile_keyring=mock_keyring)
    assert key == "profile-key"
    assert secret == "profile-secret"


def test_resolve_fallback_to_global(test_profile: TradingProfile, mock_keyring: MockKeyring) -> None:
    """Profile without credentials falls back to global AuthManager."""
    # Set global credentials
    global_auth = AuthManager(keyring_module=mock_keyring, keyring_available=True)
    global_auth.set_credential("kalshi", "api_key", "global-key")
    global_auth.set_credential("kalshi", "api_secret", "global-secret")
    
    # Profile has no credentials, should fall back to global
    key, secret = resolve_kalshi_credentials(test_profile, global_keyring=mock_keyring, profile_keyring=mock_keyring)
    assert key == "global-key"
    assert secret == "global-secret"


def test_resolve_no_credentials_raises(test_profile: TradingProfile, mock_keyring: MockKeyring) -> None:
    """No credentials anywhere raises ValueError."""
    # Neither profile nor global has credentials
    with pytest.raises(ValueError, match="No Kalshi credentials configured"):
        resolve_kalshi_credentials(test_profile, global_keyring=mock_keyring, profile_keyring=mock_keyring)


def test_resolve_none_profile_uses_global(mock_keyring: MockKeyring) -> None:
    """None profile falls back to global credentials."""
    # Set global credentials
    global_auth = AuthManager(keyring_module=mock_keyring, keyring_available=True)
    global_auth.set_credential("kalshi", "api_key", "global-key")
    global_auth.set_credential("kalshi", "api_secret", "global-secret")
    
    # No profile provided, should use global
    key, secret = resolve_kalshi_credentials(None, global_keyring=mock_keyring)
    assert key == "global-key"
    assert secret == "global-secret"


def test_resolve_profile_overrides_global(test_profile: TradingProfile, mock_keyring: MockKeyring) -> None:
    """Profile credentials override global credentials."""
    # Set both global and profile credentials
    global_auth = AuthManager(keyring_module=mock_keyring, keyring_available=True)
    global_auth.set_credential("kalshi", "api_key", "global-key")
    global_auth.set_credential("kalshi", "api_secret", "global-secret")
    
    profile_auth = ProfileAuthStore(test_profile, keyring_module=mock_keyring)
    profile_auth.set_credentials("kalshi", "profile-key", "profile-secret")
    
    # Should prefer profile credentials
    key, secret = resolve_kalshi_credentials(test_profile, global_keyring=mock_keyring, profile_keyring=mock_keyring)
    assert key == "profile-key"
    assert secret == "profile-secret"

# Made with Bob
