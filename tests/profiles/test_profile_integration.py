"""Integration tests for profile-aware configuration and KalshiClient."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import SecretStr

from traderbot.kalshi.client import KalshiClient, KalshiConfig
from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.auth import ProfileAuthStore
from traderbot.profiles.models import TradingProfile
from traderbot.profiles.registry import ProfileRegistry
from traderbot.profiles.runtime import get_current_profile
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
def paper_profile():
    """Create a paper trading profile."""
    return TradingProfile(
        name="paper-agent",
        mode="paper",
        description="Paper trading profile",
        enabled_categories=[MarketCategory.POLITICS],
        risk_multiplier=0.5,
        max_position_per_market_pct=0.04,  # 4% (within 5% HARD_LIMIT)
        max_daily_loss_pct=0.015,  # 1.5% (within 2% HARD_LIMIT)
        max_drawdown_pct=0.08,  # 8% (within 10% HARD_LIMIT)
        max_open_positions=10,  # (within 20 HARD_LIMIT)
        min_liquidity_threshold=1200,  # (above 500 HARD_LIMIT)
        min_edge_pct=0.035,  # 3.5% (above 3% HARD_LIMIT)
    )


@pytest.fixture
def live_profile():
    """Create a live trading profile."""
    return TradingProfile(
        name="live-agent",
        mode="live",
        description="Live trading profile",
        enabled_categories=[MarketCategory.POLITICS],
        risk_multiplier=0.3,
        max_position_per_market_pct=0.03,  # 3% (within 5% HARD_LIMIT)
        max_daily_loss_pct=0.01,  # 1% (within 2% HARD_LIMIT)
        max_drawdown_pct=0.05,  # 5% (within 10% HARD_LIMIT)
        max_open_positions=5,  # (within 20 HARD_LIMIT)
        min_liquidity_threshold=1500,  # (above 500 HARD_LIMIT)
        min_edge_pct=0.04,  # 4% (above 3% HARD_LIMIT)
    )


def test_full_integration_create_profile_assign_token_resolve(
    mock_keyring, paper_profile, monkeypatch
):
    """Create profile → assign token → set env var → get_current_profile() → returns profile."""
    set_keyring(mock_keyring)
    
    # Create profile
    registry = ProfileRegistry(keyring_module=mock_keyring)
    registry.create_profile(paper_profile)
    
    # Assign token
    token = generate_token()
    assign_token(paper_profile.name, "agent-123", token)
    
    # Set environment variable
    monkeypatch.setenv("TRADERBOT_PROFILE_TOKEN", token)
    
    # Resolve profile
    resolved_profile = get_current_profile(keyring_module=mock_keyring)
    
    assert resolved_profile is not None
    assert resolved_profile.name == paper_profile.name
    assert resolved_profile.mode == paper_profile.mode
    assert resolved_profile.demo_mode is True


def test_kalshi_client_with_profile_uses_profile_credentials(mock_keyring, paper_profile):
    """KalshiClient with profile uses profile credentials."""
    set_keyring(mock_keyring)
    
    # Store profile-specific credentials
    auth_mgr = ProfileAuthStore(paper_profile, keyring_module=mock_keyring)
    auth_mgr.set_credentials("kalshi", "profile-key", "profile-secret")
    
    # Create KalshiClient with profile
    config = KalshiConfig(
        api_key=SecretStr("profile-key"),
        private_key_pem=SecretStr("profile-secret"),
        demo_mode=True,
    )
    client = KalshiClient(config=config)
    
    # Verify client uses profile credentials
    assert client._config.api_key.get_secret_value() == "profile-key"
    assert client._config.private_key_pem.get_secret_value() == "profile-secret"
    assert client._config.demo_mode is True


def test_kalshi_client_without_profile_uses_global_credentials(mock_keyring):
    """KalshiClient without profile uses global credentials (backward compatibility)."""
    set_keyring(mock_keyring)
    
    # Store global credentials
    from traderbot.auth import AuthManager
    
    global_auth = AuthManager(keyring_module=mock_keyring)
    global_auth.set_credential("kalshi", "api_key", "global-key")
    global_auth.set_credential("kalshi", "private_key_pem", "global-key")
    
    # Create KalshiClient without profile (existing behavior)
    config = KalshiConfig(
        api_key=SecretStr("global-key"),
        private_key_pem=SecretStr("global-key"),
        demo_mode=False,
    )
    client = KalshiClient(config=config)
    
    # Verify client uses global credentials
    assert client._config.api_key.get_secret_value() == "global-key"
    assert client._config.private_key_pem.get_secret_value() == "global-key"
    assert client._config.demo_mode is False


def test_profile_with_demo_mode_true_creates_demo_client(mock_keyring, paper_profile):
    """Profile with demo_mode=True creates KalshiClient in demo mode."""
    set_keyring(mock_keyring)
    
    # Store credentials
    auth_mgr = ProfileAuthStore(paper_profile, keyring_module=mock_keyring)
    auth_mgr.set_credentials("kalshi", "demo-key", "demo-secret")
    
    # Verify profile is in demo mode
    assert paper_profile.demo_mode is True
    
    # Create client with demo mode
    config = KalshiConfig(
        api_key=SecretStr("demo-key"),
        private_key_pem=SecretStr("demo-secret"),
        demo_mode=paper_profile.demo_mode,
    )
    client = KalshiClient(config=config)
    
    # Verify client is in demo mode
    assert client._config.demo_mode is True
    assert client._config.active_url == client._config.demo_url


def test_profile_with_demo_mode_false_creates_live_client(mock_keyring, live_profile):
    """Profile with demo_mode=False creates KalshiClient in live mode."""
    set_keyring(mock_keyring)
    
    # Store credentials
    auth_mgr = ProfileAuthStore(live_profile, keyring_module=mock_keyring)
    auth_mgr.set_credentials("kalshi", "live-key", "live-secret")
    
    # Verify profile is in live mode
    assert live_profile.demo_mode is False
    
    # Create client with live mode
    config = KalshiConfig(
        api_key=SecretStr("live-key"),
        private_key_pem=SecretStr("live-secret"),
        demo_mode=live_profile.demo_mode,
    )
    client = KalshiClient(config=config)
    
    # Verify client is in live mode
    assert client._config.demo_mode is False
    assert client._config.active_url == client._config.base_url


def test_multiple_profiles_with_different_credentials(
    mock_keyring, paper_profile, live_profile
):
    """Multiple profiles can have different credentials."""
    set_keyring(mock_keyring)
    
    # Store different credentials for each profile
    paper_auth = ProfileAuthStore(paper_profile, keyring_module=mock_keyring)
    paper_auth.set_credentials("kalshi", "paper-key", "paper-secret")
    
    live_auth = ProfileAuthStore(live_profile, keyring_module=mock_keyring)
    live_auth.set_credentials("kalshi", "live-key", "live-secret")
    
    # Verify each profile has its own credentials
    paper_creds = paper_auth.get_credentials("kalshi")
    live_creds = live_auth.get_credentials("kalshi")
    
    assert paper_creds == ("paper-key", "paper-secret")
    assert live_creds == ("live-key", "live-secret")
    assert paper_creds != live_creds


def test_profile_token_resolution_chain(
    mock_keyring, paper_profile, live_profile, monkeypatch
):
    """Token resolution correctly maps to different profiles."""
    set_keyring(mock_keyring)
    
    # Create both profiles
    registry = ProfileRegistry(keyring_module=mock_keyring)
    registry.create_profile(paper_profile)
    registry.create_profile(live_profile)
    
    # Assign different tokens
    paper_token = generate_token()
    live_token = generate_token()
    assign_token(paper_profile.name, "paper-agent", paper_token)
    assign_token(live_profile.name, "live-agent", live_token)
    
    # Test paper token resolution
    monkeypatch.setenv("TRADERBOT_PROFILE_TOKEN", paper_token)
    resolved = get_current_profile(keyring_module=mock_keyring)
    assert resolved is not None
    assert resolved.name == paper_profile.name
    assert resolved.mode == "paper"
    
    # Test live token resolution
    monkeypatch.setenv("TRADERBOT_PROFILE_TOKEN", live_token)
    resolved = get_current_profile(keyring_module=mock_keyring)
    assert resolved is not None
    assert resolved.name == live_profile.name
    assert resolved.mode == "live"


# Made with Bob