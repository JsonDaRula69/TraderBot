"""Tests for profile-aware runtime configuration loading."""

from __future__ import annotations

import os
from unittest.mock import Mock

import pytest

from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.models import TradingProfile
from traderbot.profiles.registry import ProfileRegistry
from traderbot.profiles.runtime import (
    get_current_profile,
    get_runtime_context,
    load_profile_config,
)
from traderbot.profiles.tokens import assign_token, generate_token, set_keyring, _TOKENS_FILE


@pytest.fixture(autouse=True)
def _clean_tokens_file():
    _TOKENS_FILE.unlink(missing_ok=True)
    yield
    _TOKENS_FILE.unlink(missing_ok=True)


@pytest.fixture
def mock_keyring():
    """Mock keyring for testing."""
    mock = Mock()
    mock._store = {}

    def get_password(service: str, username: str) -> str | None:
        return mock._store.get((service, username))

    def set_password(service: str, username: str, password: str) -> None:
        mock._store[(service, username)] = password

    def delete_password(service: str, username: str) -> None:
        mock._store.pop((service, username), None)

    mock.get_password = get_password
    mock.set_password = set_password
    mock.delete_password = delete_password

    return mock


@pytest.fixture
def sample_profile():
    """Create a sample trading profile."""
    return TradingProfile(
        name="test-agent",
        mode="paper",
        description="Test profile",
        enabled_categories=[MarketCategory.POLITICS],
        risk_multiplier=0.5,
        max_position_per_market_pct=0.03,  # 3% (within 5% HARD_LIMIT)
        max_daily_loss_pct=0.015,  # 1.5% (within 2% HARD_LIMIT)
        max_drawdown_pct=0.08,  # 8% (within 10% HARD_LIMIT)
        max_open_positions=10,  # (within 20 HARD_LIMIT)
        min_liquidity_threshold=1500,  # (above 500 HARD_LIMIT)
        min_edge_pct=0.04,  # 4% (above 3% HARD_LIMIT)
    )


@pytest.fixture
def registry_with_profile(mock_keyring, sample_profile):
    """Create registry with a stored profile."""
    set_keyring(mock_keyring)
    registry = ProfileRegistry(keyring_module=mock_keyring)
    registry.create_profile(sample_profile)
    return registry


def test_get_current_profile_with_valid_token(
    mock_keyring, registry_with_profile, sample_profile, monkeypatch
):
    """Get current profile with valid token env var returns correct profile."""
    set_keyring(mock_keyring)
    
    # Generate and assign token
    token = generate_token()
    assign_token(sample_profile.name, "agent-123", token)
    
    # Set environment variable
    monkeypatch.setenv("TRADERBOT_PROFILE_TOKEN", token)
    
    # Get current profile
    profile = get_current_profile(keyring_module=mock_keyring)
    
    assert profile is not None
    assert profile.name == sample_profile.name
    assert profile.mode == sample_profile.mode
    assert profile.demo_mode is True


def test_get_current_profile_with_invalid_token(mock_keyring, monkeypatch):
    """Get current profile with invalid token returns None."""
    set_keyring(mock_keyring)
    
    # Set invalid token
    monkeypatch.setenv("TRADERBOT_PROFILE_TOKEN", "invalid-token")
    
    # Get current profile
    profile = get_current_profile(keyring_module=mock_keyring)
    
    assert profile is None


def test_get_current_profile_without_token_env_var(mock_keyring):
    """Get current profile without token env var returns None."""
    set_keyring(mock_keyring)
    
    # Ensure env var is not set
    if "TRADERBOT_PROFILE_TOKEN" in os.environ:
        del os.environ["TRADERBOT_PROFILE_TOKEN"]
    
    # Get current profile
    profile = get_current_profile(keyring_module=mock_keyring)
    
    assert profile is None


def test_load_profile_config(mock_keyring, sample_profile):
    """Load profile config returns dict with credentials, demo_mode, paths, limits."""
    set_keyring(mock_keyring)
    
    # Store credentials for the profile
    from traderbot.profiles.auth import ProfileAuthStore
    
    auth_mgr = ProfileAuthStore(sample_profile, keyring_module=mock_keyring)
    auth_mgr.set_credentials("kalshi", "test-key", "test-secret")
    
    # Load config
    config = load_profile_config(
        sample_profile,
        global_keyring=mock_keyring,
        profile_keyring=mock_keyring,
    )
    
    # Verify structure
    assert isinstance(config, dict)
    assert "credentials" in config
    assert "demo_mode" in config
    assert "paths" in config
    assert "limits" in config
    
    # Verify credentials
    assert config["credentials"]["kalshi"] == ("test-key", "test-secret")
    
    # Verify demo_mode
    assert config["demo_mode"] is True
    
    # Verify paths
    assert "db" in config["paths"]
    assert "chroma" in config["paths"]
    assert "audit" in config["paths"]
    
    # Verify limits
    assert config["limits"]["max_position_per_market_pct"] == 0.03
    assert config["limits"]["max_daily_loss_pct"] == 0.015
    assert config["limits"]["max_open_positions"] == 10


def test_load_profile_config_with_global_credentials_fallback(
    mock_keyring, sample_profile
):
    """Load profile config falls back to global credentials when profile has none."""
    set_keyring(mock_keyring)
    
    # Store global credentials
    from traderbot.auth import AuthManager
    
    global_auth = AuthManager(keyring_module=mock_keyring)
    global_auth.set_credential("kalshi", "api_key", "global-key")
    global_auth.set_credential("kalshi", "private_key_pem", "global-key")
    
    # Load config (profile has no credentials)
    config = load_profile_config(
        sample_profile,
        global_keyring=mock_keyring,
        profile_keyring=mock_keyring,
    )
    
    # Should fall back to global credentials
    assert config["credentials"]["kalshi"] == ("global-key", "global-key")


def test_get_runtime_context(
    mock_keyring, registry_with_profile, sample_profile, monkeypatch
):
    """Get runtime context returns full context dict."""
    set_keyring(mock_keyring)
    
    # Generate and assign token
    token = generate_token()
    assign_token(sample_profile.name, "agent-123", token)
    
    # Set environment variable
    monkeypatch.setenv("TRADERBOT_PROFILE_TOKEN", token)
    
    # Store credentials
    from traderbot.profiles.auth import ProfileAuthStore
    
    auth_mgr = ProfileAuthStore(sample_profile, keyring_module=mock_keyring)
    auth_mgr.set_credentials("kalshi", "test-key", "test-secret")
    
    # Get runtime context
    context = get_runtime_context(
        keyring_module=mock_keyring,
        global_keyring=mock_keyring,
        profile_keyring=mock_keyring,
    )
    
    # Verify structure
    assert isinstance(context, dict)
    assert "profile" in context
    assert "config" in context
    
    # Verify profile
    assert context["profile"].name == sample_profile.name
    
    # Verify config
    assert context["config"]["demo_mode"] is True
    assert context["config"]["credentials"]["kalshi"] == ("test-key", "test-secret")


def test_get_runtime_context_without_profile(mock_keyring):
    """Get runtime context without profile returns None for both profile and config."""
    set_keyring(mock_keyring)
    
    # Ensure no token env var
    if "TRADERBOT_PROFILE_TOKEN" in os.environ:
        del os.environ["TRADERBOT_PROFILE_TOKEN"]
    
    # Get runtime context
    context = get_runtime_context(keyring_module=mock_keyring)
    
    assert context["profile"] is None
    assert context["config"] is None


# Made with Bob