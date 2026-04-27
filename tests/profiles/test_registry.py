"""Tests for ProfileRegistry with encrypted keyring storage."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.models import TradingProfile
from traderbot.profiles.registry import ProfileRegistry


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
def registry(mock_keyring: MockKeyring) -> ProfileRegistry:
    """Provide a ProfileRegistry with mock keyring."""
    return ProfileRegistry(keyring_module=mock_keyring)


@pytest.fixture
def sample_profile() -> TradingProfile:
    """Provide a sample trading profile."""
    return TradingProfile(
        name="test-profile",
        mode="paper",
        description="Test profile for unit tests",
        enabled_categories=[MarketCategory.POLITICS, MarketCategory.ECONOMICS],
        risk_multiplier=0.5,
        max_position_per_market_pct=0.03,  # 3% (within 5% limit)
        max_daily_loss_pct=0.015,  # 1.5% (within 2% limit)
        max_drawdown_pct=0.08,  # 8% (within 10% limit)
        max_open_positions=5,
        min_liquidity_threshold=1000,
        min_edge_pct=0.03,  # 3% (at minimum)
    )


@pytest.fixture
def another_profile() -> TradingProfile:
    """Provide another sample trading profile."""
    return TradingProfile(
        name="aggressive-trader",
        mode="live",
        description="Aggressive live trading profile",
        enabled_categories=[],
        risk_multiplier=0.8,
        max_position_per_market_pct=0.05,  # 5% (at limit)
        max_daily_loss_pct=0.02,  # 2% (at limit)
        max_drawdown_pct=0.10,  # 10% (at limit)
        max_open_positions=10,
        min_liquidity_threshold=1000,  # At minimum
        min_edge_pct=0.03,  # 3% (at minimum)
    )


def test_create_retrieve_profile(
    registry: ProfileRegistry, sample_profile: TradingProfile
) -> None:
    """Create profile and retrieve it — should match original."""
    registry.create_profile(sample_profile)
    retrieved = registry.get_profile("test-profile")

    assert retrieved is not None
    assert retrieved.name == sample_profile.name
    assert retrieved.mode == sample_profile.mode
    assert retrieved.description == sample_profile.description
    assert retrieved.enabled_categories == sample_profile.enabled_categories
    assert retrieved.risk_multiplier == sample_profile.risk_multiplier
    assert retrieved.max_position_per_market_pct == sample_profile.max_position_per_market_pct
    assert retrieved.max_daily_loss_pct == sample_profile.max_daily_loss_pct
    assert retrieved.max_drawdown_pct == sample_profile.max_drawdown_pct
    assert retrieved.max_open_positions == sample_profile.max_open_positions
    assert retrieved.min_liquidity_threshold == sample_profile.min_liquidity_threshold
    assert retrieved.min_edge_pct == sample_profile.min_edge_pct


def test_list_profiles(
    registry: ProfileRegistry,
    sample_profile: TradingProfile,
    another_profile: TradingProfile,
) -> None:
    """List profiles should return all created profile names."""
    registry.create_profile(sample_profile)
    registry.create_profile(another_profile)

    profiles = registry.list_profiles()
    assert len(profiles) == 2
    assert "test-profile" in profiles
    assert "aggressive-trader" in profiles


def test_delete_profile_keep_data(
    registry: ProfileRegistry, sample_profile: TradingProfile, tmp_path: Path
) -> None:
    """Delete profile with keep_data=True should remove from keyring but keep data dirs."""
    # Create profile
    registry.create_profile(sample_profile)
    assert registry.profile_exists("test-profile")

    # Create mock data directory
    data_dir = tmp_path / ".traderbot-paper"
    data_dir.mkdir()
    test_file = data_dir / "test.db"
    test_file.write_text("test data")

    # Delete with keep_data=True
    registry.delete_profile("test-profile", keep_data=True)

    # Profile should be gone from keyring
    assert not registry.profile_exists("test-profile")
    assert registry.get_profile("test-profile") is None

    # Data directory should still exist
    assert data_dir.exists()
    assert test_file.exists()


def test_delete_profile_remove_data(
    registry: ProfileRegistry, sample_profile: TradingProfile, tmp_path: Path, monkeypatch: Any
) -> None:
    """Delete profile with keep_data=False should remove profile and data dirs."""
    # Create profile
    registry.create_profile(sample_profile)
    assert registry.profile_exists("test-profile")

    # Create mock data directory in tmp_path
    data_dir = tmp_path / ".traderbot-paper"
    data_dir.mkdir()
    test_file = data_dir / "test.db"
    test_file.write_text("test data")

    # Monkeypatch Path.home() to return tmp_path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Delete with keep_data=False
    registry.delete_profile("test-profile", keep_data=False)

    # Profile should be gone
    assert not registry.profile_exists("test-profile")

    # Data directory should be gone
    assert not data_dir.exists()


def test_get_nonexistent_profile(registry: ProfileRegistry) -> None:
    """Get non-existent profile should return None."""
    result = registry.get_profile("does-not-exist")
    assert result is None


def test_create_duplicate_profile(
    registry: ProfileRegistry, sample_profile: TradingProfile
) -> None:
    """Creating duplicate profile should raise ValueError."""
    registry.create_profile(sample_profile)

    with pytest.raises(ValueError, match="Profile 'test-profile' already exists"):
        registry.create_profile(sample_profile)


def test_profile_exists(
    registry: ProfileRegistry, sample_profile: TradingProfile
) -> None:
    """Profile exists check should return True/False correctly."""
    assert not registry.profile_exists("test-profile")

    registry.create_profile(sample_profile)
    assert registry.profile_exists("test-profile")

    registry.delete_profile("test-profile")
    assert not registry.profile_exists("test-profile")


def test_delete_nonexistent_profile(registry: ProfileRegistry) -> None:
    """Deleting non-existent profile should not raise error."""
    # Should not raise
    registry.delete_profile("does-not-exist", keep_data=True)
    registry.delete_profile("does-not-exist", keep_data=False)


def test_list_profiles_empty(registry: ProfileRegistry) -> None:
    """List profiles on empty registry should return empty list."""
    profiles = registry.list_profiles()
    assert profiles == []

def test_update_profile_single_field(
    registry: ProfileRegistry, sample_profile: TradingProfile
) -> None:
    """Update a single field of an existing profile."""
    registry.create_profile(sample_profile)

    updated = registry.update_profile("test-profile", risk_multiplier=0.75)

    assert updated.risk_multiplier == 0.75
    assert updated.description == sample_profile.description
    assert updated.mode == sample_profile.mode


def test_update_profile_multiple_fields(
    registry: ProfileRegistry, sample_profile: TradingProfile
) -> None:
    """Update multiple fields of an existing profile."""
    registry.create_profile(sample_profile)

    updated = registry.update_profile(
        "test-profile",
        risk_multiplier=0.9,
        max_open_positions=15,
        description="Updated description",
    )

    assert updated.risk_multiplier == 0.9
    assert updated.max_open_positions == 15
    assert updated.description == "Updated description"
    assert updated.enabled_categories == sample_profile.enabled_categories


def test_update_profile_categories(
    registry: ProfileRegistry, sample_profile: TradingProfile
) -> None:
    """Update enabled_categories with string list."""
    registry.create_profile(sample_profile)

    updated = registry.update_profile(
        "test-profile",
        enabled_categories=["Politics", "Economics", "Science"],
    )

    assert MarketCategory.POLITICS in updated.enabled_categories
    assert MarketCategory.ECONOMICS in updated.enabled_categories
    assert MarketCategory.SCIENCE in updated.enabled_categories
    assert len(updated.enabled_categories) == 3


def test_update_profile_nonexistent(registry: ProfileRegistry) -> None:
    """Updating non-existent profile should raise ValueError."""
    with pytest.raises(ValueError, match="Profile 'nonexistent' not found"):
        registry.update_profile("nonexistent", risk_multiplier=0.5)


def test_update_profile_preserves_unmodified_fields(
    registry: ProfileRegistry, sample_profile: TradingProfile
) -> None:
    """Updating one field should not change other fields."""
    registry.create_profile(sample_profile)
    original_dict = sample_profile.model_dump(mode="json")

    updated = registry.update_profile("test-profile", risk_multiplier=0.99)

    assert updated.name == original_dict["name"]
    assert updated.mode == original_dict["mode"]
    assert updated.description == original_dict["description"]
    assert updated.risk_multiplier == 0.99
    assert updated.max_position_per_market_pct == original_dict["max_position_per_market_pct"]
    assert updated.max_daily_loss_pct == original_dict["max_daily_loss_pct"]
    assert updated.max_drawdown_pct == original_dict["max_drawdown_pct"]
    assert updated.max_open_positions == original_dict["max_open_positions"]
    assert updated.min_liquidity_threshold == original_dict["min_liquidity_threshold"]
    assert updated.min_edge_pct == original_dict["min_edge_pct"]


# Made with Bob
