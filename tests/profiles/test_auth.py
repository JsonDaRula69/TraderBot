"""Tests for per-profile authentication storage."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

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
def test_profile() -> TradingProfile:
    """Create a test trading profile."""
    return TradingProfile(
        name="test-profile",
        mode="paper",
        description="Test profile for auth tests",
        enabled_categories=[MarketCategory.POLITICS],
        risk_multiplier=0.5,
        max_position_per_market_pct=0.05,
        max_daily_loss_pct=0.02,
        max_drawdown_pct=0.10,
        max_open_positions=5,
        min_liquidity_threshold=1000,
        min_edge_pct=0.03,
    )


@pytest.fixture
def auth_manager(test_profile: TradingProfile, mock_keyring: MockKeyring) -> ProfileAuthStore:
    """Create a ProfileAuthStore with mock keyring."""
    return ProfileAuthStore(test_profile, keyring_module=mock_keyring)


def test_set_and_retrieve_credentials(auth_manager: ProfileAuthStore, mock_keyring: MockKeyring) -> None:
    """Set credentials and retrieve them successfully."""
    # Set credentials
    auth_manager.set_credentials("kalshi", "test-key-123", "test-secret-456")
    
    # Retrieve credentials
    result = auth_manager.get_credentials("kalshi")
    assert result is not None
    key, secret = result
    assert key == "test-key-123"
    assert secret == "test-secret-456"
    
    # Verify stored in correct namespace
    service_name = "traderbot.profiles.test-profile.kalshi"
    stored = mock_keyring.get_password(service_name, "credentials")
    assert stored is not None
    data = json.loads(stored)
    assert data["key"] == "test-key-123"
    assert data["secret"] == "test-secret-456"
    assert "created_at" in data


def test_get_nonexistent_credentials(auth_manager: ProfileAuthStore) -> None:
    """Get credentials that don't exist returns None."""
    result = auth_manager.get_credentials("kalshi")
    assert result is None


def test_delete_credentials(auth_manager: ProfileAuthStore) -> None:
    """Delete credentials removes them from keyring."""
    # Set credentials
    auth_manager.set_credentials("kalshi", "key", "secret")
    assert auth_manager.get_credentials("kalshi") is not None
    
    # Delete credentials
    auth_manager.delete_credentials("kalshi")
    
    # Verify they're gone
    assert auth_manager.get_credentials("kalshi") is None


def test_has_credentials(auth_manager: ProfileAuthStore) -> None:
    """has_credentials returns correct boolean."""
    # Initially no credentials
    assert not auth_manager.has_credentials("kalshi")
    
    # Set credentials
    auth_manager.set_credentials("kalshi", "key", "secret")
    assert auth_manager.has_credentials("kalshi")
    
    # Delete credentials
    auth_manager.delete_credentials("kalshi")
    assert not auth_manager.has_credentials("kalshi")


def test_list_services(auth_manager: ProfileAuthStore) -> None:
    """list_services returns all configured services."""
    # Initially empty
    assert auth_manager.list_services() == []
    
    # Add multiple services
    auth_manager.set_credentials("kalshi", "key1", "secret1")
    auth_manager.set_credentials("voyage", "key2", "secret2")
    auth_manager.set_credentials("newsapi", "key3", "secret3")
    
    # List should return all three
    services = auth_manager.list_services()
    assert sorted(services) == ["kalshi", "newsapi", "voyage"]


def test_isolated_credentials_per_profile(mock_keyring: MockKeyring) -> None:
    """Different profiles have isolated credential storage."""
    # Create two profiles
    profile1 = TradingProfile(
        name="profile1",
        mode="paper",
        description="First profile",
        risk_multiplier=0.5,
        max_position_per_market_pct=0.05,
        max_daily_loss_pct=0.02,
        max_drawdown_pct=0.10,
        max_open_positions=5,
        min_liquidity_threshold=1000,
        min_edge_pct=0.03,
    )
    profile2 = TradingProfile(
        name="profile2",
        mode="paper",
        description="Second profile",
        risk_multiplier=0.5,
        max_position_per_market_pct=0.05,
        max_daily_loss_pct=0.02,
        max_drawdown_pct=0.10,
        max_open_positions=5,
        min_liquidity_threshold=1000,
        min_edge_pct=0.03,
    )
    
    # Create auth managers
    auth1 = ProfileAuthStore(profile1, keyring_module=mock_keyring)
    auth2 = ProfileAuthStore(profile2, keyring_module=mock_keyring)
    
    # Set different credentials for each
    auth1.set_credentials("kalshi", "key1", "secret1")
    auth2.set_credentials("kalshi", "key2", "secret2")
    
    # Verify isolation
    creds1 = auth1.get_credentials("kalshi")
    creds2 = auth2.get_credentials("kalshi")
    
    assert creds1 is not None
    assert creds2 is not None
    assert creds1[0] == "key1"
    assert creds1[1] == "secret1"
    assert creds2[0] == "key2"
    assert creds2[1] == "secret2"


def test_created_at_timestamp(auth_manager: ProfileAuthStore, mock_keyring: MockKeyring) -> None:
    """Stored credentials include ISO8601 timestamp."""
    auth_manager.set_credentials("kalshi", "key", "secret")
    
    service_name = "traderbot.profiles.test-profile.kalshi"
    stored = mock_keyring.get_password(service_name, "credentials")
    assert stored is not None
    
    data = json.loads(stored)
    assert "created_at" in data
    
    # Verify it's a valid ISO8601 timestamp
    timestamp = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
    assert timestamp.tzinfo is not None
    # Should be recent (within last minute)
    now = datetime.now(timezone.utc)
    assert (now - timestamp).total_seconds() < 60

# Made with Bob
