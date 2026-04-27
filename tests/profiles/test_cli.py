"""Tests for profile management CLI commands."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from traderbot.cli import app
from traderbot.kalshi.models import MarketCategory
from traderbot.profiles.models import TradingProfile
from traderbot.profiles.registry import ProfileRegistry
from traderbot.profiles.auth import ProfileAuthStore
from traderbot.profiles import tokens
from traderbot.risk.limits import HARD_LIMITS


class MockKeyring:
    """Mock keyring that behaves like the real one."""
    
    def __init__(self):
        self._store = {}
    
    def get_password(self, service, username):
        return self._store.get((service, username))
    
    def set_password(self, service, username, password):
        self._store[(service, username)] = password
    
    def delete_password(self, service, username):
        if (service, username) in self._store:
            del self._store[(service, username)]


@pytest.fixture
def mock_keyring():
    """Mock keyring for testing."""
    return MockKeyring()


@pytest.fixture(autouse=True)
def setup_mock_keyring(mock_keyring, monkeypatch):
    """Automatically set up mock keyring for all tests."""
    # Clear the store before each test
    mock_keyring._store.clear()
    
    # Patch keyring at the module level using sys.modules
    import sys
    monkeypatch.setitem(sys.modules, 'keyring', mock_keyring)
    
    # Also set the global keyring instance in tokens module
    tokens._keyring_instance = mock_keyring
    
    yield
    
    # Clean up after test
    tokens._keyring_instance = None


@pytest.fixture
def registry(mock_keyring):
    """ProfileRegistry with mock keyring."""
    return ProfileRegistry(keyring_module=mock_keyring)


@pytest.fixture
def runner():
    """CLI test runner."""
    return CliRunner()


def test_profile_create_and_list(runner, registry, mock_keyring):
    """Create profile → list → shows in list."""
    # Create profile
    result = runner.invoke(app, [
        "profile", "create", "test-profile",
        "--mode", "paper",
        "--description", "Test profile for CLI",
    ])
    
    if result.exit_code != 0:
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr if hasattr(result, 'stderr') else 'N/A'}")
        print(f"Exception: {result.exception if hasattr(result, 'exception') else 'N/A'}")
    
    assert result.exit_code == 0, f"Command failed with output: {result.stdout}"
    assert "Created profile 'test-profile'" in result.stdout
    
    # List profiles
    result = runner.invoke(app, ["profile", "list"])
    
    assert result.exit_code == 0
    assert "test-profile" in result.stdout
    assert "paper" in result.stdout


def test_profile_create_with_options(runner, registry, mock_keyring):
    """Create profile with custom risk parameters."""
    result = runner.invoke(app, [
        "profile", "create", "custom-profile",
        "--mode", "paper",
        "--description", "Custom risk params",
        "--categories", "politics,economics",
        "--risk-multiplier", "0.5",
        "--max-position-pct", "0.03",  # 3% (within 5% HARD_LIMIT)
        "--max-daily-loss-pct", "0.01",  # 1% (within 2% HARD_LIMIT)
        "--max-drawdown-pct", "0.08",  # 8% (within 10% HARD_LIMIT)
        "--max-open-positions", "15",  # Within 20 HARD_LIMIT
        "--min-liquidity", "1500",  # Above 1000 HARD_LIMIT
        "--min-edge-pct", "0.04",  # 4% (above 3% HARD_LIMIT)
    ])
    
    if result.exit_code != 0:
        print(f"STDOUT: {result.stdout}")
        if hasattr(result, 'exception') and result.exception:
            import traceback
            traceback.print_exception(type(result.exception), result.exception, result.exception.__traceback__)
    
    assert result.exit_code == 0, f"Command failed: {result.stdout}"
    assert "Created profile 'custom-profile'" in result.stdout
    
    # Verify profile was created with correct params
    profile = registry.get_profile("custom-profile")
    assert profile is not None
    assert profile.risk_multiplier == 0.5
    assert profile.max_position_per_market_pct == 0.03
    assert profile.max_daily_loss_pct == 0.01
    assert profile.max_drawdown_pct == 0.08
    assert profile.max_open_positions == 15
    assert profile.min_liquidity_threshold == 1500
    assert profile.min_edge_pct == 0.04
    assert MarketCategory.POLITICS in profile.enabled_categories
    assert MarketCategory.ECONOMICS in profile.enabled_categories


def test_profile_show(runner, registry, mock_keyring):
    """Show profile → returns correct details."""
    # Create profile first
    profile = TradingProfile(
        name="show-test",
        mode="paper",
        description="Profile for show test",
        risk_multiplier=0.8,
        max_position_per_market_pct=HARD_LIMITS["max_position_per_market_pct"],
        max_daily_loss_pct=HARD_LIMITS["max_daily_loss_pct"],
        max_drawdown_pct=HARD_LIMITS["max_drawdown_pct"],
        max_open_positions=int(HARD_LIMITS["max_open_positions"]),
        min_liquidity_threshold=int(HARD_LIMITS["min_liquidity_threshold"]),
        min_edge_pct=HARD_LIMITS["min_edge_pct"],
    )
    registry.create_profile(profile)
    
    # Show profile
    result = runner.invoke(app, ["profile", "show", "show-test"])
    
    assert result.exit_code == 0
    assert "show-test" in result.stdout
    assert "paper" in result.stdout
    assert "Profile for show test" in result.stdout
    assert "0.8" in result.stdout


def test_profile_show_json(runner, registry, mock_keyring):
    """Show profile with JSON output → valid JSON."""
    # Create profile first
    profile = TradingProfile(
        name="json-test",
        mode="live",
        description="JSON output test",
        risk_multiplier=0.6,
        max_position_per_market_pct=HARD_LIMITS["max_position_per_market_pct"],
        max_daily_loss_pct=HARD_LIMITS["max_daily_loss_pct"],
        max_drawdown_pct=HARD_LIMITS["max_drawdown_pct"],
        max_open_positions=int(HARD_LIMITS["max_open_positions"]),
        min_liquidity_threshold=int(HARD_LIMITS["min_liquidity_threshold"]),
        min_edge_pct=HARD_LIMITS["min_edge_pct"],
    )
    registry.create_profile(profile)
    
    # Show profile with JSON
    result = runner.invoke(app, ["profile", "show", "json-test", "--json"])
    
    assert result.exit_code == 0
    
    # Parse JSON output
    data = json.loads(result.stdout)
    assert data["name"] == "json-test"
    assert data["mode"] == "live"
    assert data["description"] == "JSON output test"
    assert data["risk_multiplier"] == 0.6


def test_profile_list_json(runner, registry, mock_keyring):
    """List profiles with JSON output → valid JSON."""
    # Create multiple profiles
    for i in range(3):
        profile = TradingProfile(
            name=f"profile-{i}",
            mode="paper",
            description=f"Profile {i}",
            risk_multiplier=0.5,
            max_position_per_market_pct=HARD_LIMITS["max_position_per_market_pct"],
            max_daily_loss_pct=HARD_LIMITS["max_daily_loss_pct"],
            max_drawdown_pct=HARD_LIMITS["max_drawdown_pct"],
            max_open_positions=int(HARD_LIMITS["max_open_positions"]),
            min_liquidity_threshold=int(HARD_LIMITS["min_liquidity_threshold"]),
            min_edge_pct=HARD_LIMITS["min_edge_pct"],
        )
        registry.create_profile(profile)
    
    # List profiles with JSON
    result = runner.invoke(app, ["profile", "list", "--json"])
    
    assert result.exit_code == 0
    
    # Parse JSON output
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 3
    assert all("name" in p for p in data)


def test_profile_delete(runner, registry, mock_keyring):
    """Delete profile → no longer in list."""
    # Create profile
    profile = TradingProfile(
        name="delete-test",
        mode="paper",
        description="To be deleted",
        risk_multiplier=0.5,
        max_position_per_market_pct=HARD_LIMITS["max_position_per_market_pct"],
        max_daily_loss_pct=HARD_LIMITS["max_daily_loss_pct"],
        max_drawdown_pct=HARD_LIMITS["max_drawdown_pct"],
        max_open_positions=int(HARD_LIMITS["max_open_positions"]),
        min_liquidity_threshold=int(HARD_LIMITS["min_liquidity_threshold"]),
        min_edge_pct=HARD_LIMITS["min_edge_pct"],
    )
    registry.create_profile(profile)
    
    # Verify it exists
    assert registry.profile_exists("delete-test")
    
    # Delete profile
    result = runner.invoke(app, ["profile", "delete", "delete-test"])
    
    assert result.exit_code == 0
    assert "Deleted profile 'delete-test'" in result.stdout
    
    # Verify it's gone
    assert not registry.profile_exists("delete-test")


def test_profile_assign_token(runner, registry, mock_keyring):
    """Assign token → assignments list shows mapping."""
    # Create profile
    profile = TradingProfile(
        name="assign-test",
        mode="paper",
        description="Token assignment test",
        risk_multiplier=0.5,
        max_position_per_market_pct=HARD_LIMITS["max_position_per_market_pct"],
        max_daily_loss_pct=HARD_LIMITS["max_daily_loss_pct"],
        max_drawdown_pct=HARD_LIMITS["max_drawdown_pct"],
        max_open_positions=int(HARD_LIMITS["max_open_positions"]),
        min_liquidity_threshold=int(HARD_LIMITS["min_liquidity_threshold"]),
        min_edge_pct=HARD_LIMITS["min_edge_pct"],
    )
    registry.create_profile(profile)
    
    # Assign token
    result = runner.invoke(app, [
        "profile", "assign", "assign-test", "test-agent-123"
    ])
    
    assert result.exit_code == 0
    assert "Assigned token" in result.stdout
    assert "assign-test" in result.stdout
    assert "test-agent-123" in result.stdout
    
    # List assignments
    result = runner.invoke(app, ["profile", "assignments"])
    
    assert result.exit_code == 0
    assert "assign-test" in result.stdout
    assert "test-agent-123" in result.stdout


def test_profile_revoke_token(runner, registry, mock_keyring):
    """Revoke token → assignments list no longer shows mapping."""
    # Create profile and assign token
    profile = TradingProfile(
        name="revoke-test",
        mode="paper",
        description="Token revocation test",
        risk_multiplier=0.5,
        max_position_per_market_pct=HARD_LIMITS["max_position_per_market_pct"],
        max_daily_loss_pct=HARD_LIMITS["max_daily_loss_pct"],
        max_drawdown_pct=HARD_LIMITS["max_drawdown_pct"],
        max_open_positions=int(HARD_LIMITS["max_open_positions"]),
        min_liquidity_threshold=int(HARD_LIMITS["min_liquidity_threshold"]),
        min_edge_pct=HARD_LIMITS["min_edge_pct"],
    )
    registry.create_profile(profile)
    
    # Assign token
    runner.invoke(app, ["profile", "assign", "revoke-test", "revoke-agent"])
    
    # Verify assignment exists
    result = runner.invoke(app, ["profile", "assignments"])
    assert "revoke-test" in result.stdout
    
    # Revoke token
    result = runner.invoke(app, ["profile", "revoke", "revoke-test"])
    
    assert result.exit_code == 0
    assert "Revoked token" in result.stdout
    
    # Verify assignment is gone
    result = runner.invoke(app, ["profile", "assignments"])
    assert "revoke-test" not in result.stdout


def test_profile_assignments_json(runner, registry, mock_keyring):
    """List assignments with JSON output → valid JSON."""
    # Create profile and assign token
    profile = TradingProfile(
        name="json-assign",
        mode="paper",
        description="JSON assignments test",
        risk_multiplier=0.5,
        max_position_per_market_pct=HARD_LIMITS["max_position_per_market_pct"],
        max_daily_loss_pct=HARD_LIMITS["max_daily_loss_pct"],
        max_drawdown_pct=HARD_LIMITS["max_drawdown_pct"],
        max_open_positions=int(HARD_LIMITS["max_open_positions"]),
        min_liquidity_threshold=int(HARD_LIMITS["min_liquidity_threshold"]),
        min_edge_pct=HARD_LIMITS["min_edge_pct"],
    )
    registry.create_profile(profile)
    runner.invoke(app, ["profile", "assign", "json-assign", "json-agent"])
    
    # List assignments with JSON
    result = runner.invoke(app, ["profile", "assignments", "--json"])
    
    assert result.exit_code == 0
    
    # Parse JSON output
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert any(a["profile"] == "json-assign" for a in data)


def test_profile_create_duplicate_fails(runner, registry, mock_keyring):
    """Creating duplicate profile should fail."""
    # Create first profile
    runner.invoke(app, [
        "profile", "create", "duplicate",
        "--mode", "paper",
        "--description", "First",
    ])
    
    # Try to create duplicate
    result = runner.invoke(app, [
        "profile", "create", "duplicate",
        "--mode", "paper",
        "--description", "Second",
    ])
    
    assert result.exit_code != 0
    assert "already exists" in result.stdout.lower()


def test_profile_show_nonexistent(runner, registry, mock_keyring):
    """Showing nonexistent profile should fail gracefully."""
    result = runner.invoke(app, ["profile", "show", "nonexistent"])
    
    assert result.exit_code != 0
    assert "not found" in result.stdout.lower()


def test_profile_delete_nonexistent(runner, registry, mock_keyring):
    """Deleting nonexistent profile should not error."""
    result = runner.invoke(app, ["profile", "delete", "nonexistent"])
    
    # Should succeed but warn
    assert result.exit_code == 0


def test_profile_update(runner, registry, mock_keyring):
    """Update profile → shows updated values."""
    profile = TradingProfile(
        name="update-test",
        mode="paper",
        description="Original description",
        risk_multiplier=0.5,
        max_position_per_market_pct=HARD_LIMITS["max_position_per_market_pct"],
        max_daily_loss_pct=HARD_LIMITS["max_daily_loss_pct"],
        max_drawdown_pct=HARD_LIMITS["max_drawdown_pct"],
        max_open_positions=int(HARD_LIMITS["max_open_positions"]),
        min_liquidity_threshold=int(HARD_LIMITS["min_liquidity_threshold"]),
        min_edge_pct=HARD_LIMITS["min_edge_pct"],
    )
    registry.create_profile(profile)

    result = runner.invoke(app, [
        "profile", "update", "update-test",
        "--risk-multiplier", "0.8",
        "--description", "Updated description",
    ])

    assert result.exit_code == 0, f"Command failed: {result.stdout}"
    assert "Updated profile 'update-test'" in result.stdout

    updated = registry.get_profile("update-test")
    assert updated.risk_multiplier == 0.8
    assert updated.description == "Updated description"


def test_profile_update_multiple_fields(runner, registry, mock_keyring):
    """Update multiple fields at once."""
    profile = TradingProfile(
        name="multi-update-test",
        mode="paper",
        description="Original",
        risk_multiplier=0.5,
        max_position_per_market_pct=HARD_LIMITS["max_position_per_market_pct"],
        max_daily_loss_pct=HARD_LIMITS["max_daily_loss_pct"],
        max_drawdown_pct=HARD_LIMITS["max_drawdown_pct"],
        max_open_positions=int(HARD_LIMITS["max_open_positions"]),
        min_liquidity_threshold=int(HARD_LIMITS["min_liquidity_threshold"]),
        min_edge_pct=HARD_LIMITS["min_edge_pct"],
    )
    registry.create_profile(profile)

    result = runner.invoke(app, [
        "profile", "update", "multi-update-test",
        "--risk-multiplier", "0.9",
        "--max-open-positions", "15",
        "--categories", "politics,economics",
    ])

    assert result.exit_code == 0, f"Command failed: {result.stdout}"

    updated = registry.get_profile("multi-update-test")
    assert updated.risk_multiplier == 0.9
    assert updated.max_open_positions == 15
    assert MarketCategory.POLITICS in updated.enabled_categories
    assert MarketCategory.ECONOMICS in updated.enabled_categories


def test_profile_update_nonexistent(runner, registry, mock_keyring):
    """Updating nonexistent profile should fail."""
    result = runner.invoke(app, [
        "profile", "update", "nonexistent",
        "--risk-multiplier", "0.5",
    ])

    assert result.exit_code != 0
    assert "not found" in result.stdout.lower()


def test_profile_update_no_fields(runner, registry, mock_keyring):
    """Updating with no fields should warn."""
    profile = TradingProfile(
        name="no-field-update",
        mode="paper",
        description="Test",
        risk_multiplier=0.5,
        max_position_per_market_pct=HARD_LIMITS["max_position_per_market_pct"],
        max_daily_loss_pct=HARD_LIMITS["max_daily_loss_pct"],
        max_drawdown_pct=HARD_LIMITS["max_drawdown_pct"],
        max_open_positions=int(HARD_LIMITS["max_open_positions"]),
        min_liquidity_threshold=int(HARD_LIMITS["min_liquidity_threshold"]),
        min_edge_pct=HARD_LIMITS["min_edge_pct"],
    )
    registry.create_profile(profile)

    result = runner.invoke(app, ["profile", "update", "no-field-update"])

    assert result.exit_code == 0
    assert "No fields to update" in result.stdout


def test_profile_discover_agents_empty(runner, registry, mock_keyring, monkeypatch):
    """Discover agents with no workspace should show empty."""
    def mock_discover():
        return []

    monkeypatch.setattr("traderbot.profiles.discovery.discover_agents", mock_discover)

    result = runner.invoke(app, ["profile", "discover-agents"])

    assert result.exit_code == 0
    assert "No agents found" in result.stdout


def test_profile_discover_agents_with_agents(runner, registry, mock_keyring, monkeypatch):
    """Discover agents with agents present."""
    def mock_discover():
        return [
            {"agent_id": "agent1", "name": "Agent One", "path": "/path/to/agent1"},
            {"agent_id": "agent2", "name": "Agent Two", "path": "/path/to/agent2"},
        ]

    monkeypatch.setattr("traderbot.profiles.discovery.discover_agents", mock_discover)

    result = runner.invoke(app, ["profile", "discover-agents"])

    assert result.exit_code == 0
    assert "agent1" in result.stdout
    assert "Agent One" in result.stdout
    assert "agent2" in result.stdout
    assert "Agent Two" in result.stdout


def test_profile_discover_agents_json(runner, registry, mock_keyring, monkeypatch):
    """Discover agents JSON output."""
    def mock_discover():
        return [
            {"agent_id": "agent1", "name": "Agent One", "path": "/path/to/agent1"},
        ]

    monkeypatch.setattr("traderbot.profiles.discovery.discover_agents", mock_discover)

    result = runner.invoke(app, ["profile", "discover-agents", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert len(data) == 1
    assert data[0]["agent_id"] == "agent1"


def test_profile_set_auth(runner, registry, mock_keyring):
    """Set auth credentials for a profile."""
    profile = TradingProfile(
        name="auth-test",
        mode="paper",
        description="Auth test",
        risk_multiplier=0.5,
        max_position_per_market_pct=HARD_LIMITS["max_position_per_market_pct"],
        max_daily_loss_pct=HARD_LIMITS["max_daily_loss_pct"],
        max_drawdown_pct=HARD_LIMITS["max_drawdown_pct"],
        max_open_positions=int(HARD_LIMITS["max_open_positions"]),
        min_liquidity_threshold=int(HARD_LIMITS["min_liquidity_threshold"]),
        min_edge_pct=HARD_LIMITS["min_edge_pct"],
    )
    registry.create_profile(profile)

    result = runner.invoke(app, [
        "profile", "set-auth", "auth-test", "kalshi", "my-key-id"
    ], input="my-secret-value\n")

    assert result.exit_code == 0, f"Command failed: {result.stdout}"
    assert "Stored credentials" in result.stdout


def test_profile_set_auth_nonexistent_profile(runner, registry, mock_keyring):
    """Set auth for nonexistent profile should fail."""
    result = runner.invoke(app, [
        "profile", "set-auth", "nonexistent", "kalshi", "key"
    ], input="secret\n")

    assert result.exit_code != 0
    assert "not found" in result.stdout.lower()


def test_profile_auth(runner, registry, mock_keyring):
    """Show auth credentials for a profile."""
    profile = TradingProfile(
        name="auth-show-test",
        mode="paper",
        description="Auth show test",
        risk_multiplier=0.5,
        max_position_per_market_pct=HARD_LIMITS["max_position_per_market_pct"],
        max_daily_loss_pct=HARD_LIMITS["max_daily_loss_pct"],
        max_drawdown_pct=HARD_LIMITS["max_drawdown_pct"],
        max_open_positions=int(HARD_LIMITS["max_open_positions"]),
        min_liquidity_threshold=int(HARD_LIMITS["min_liquidity_threshold"]),
        min_edge_pct=HARD_LIMITS["min_edge_pct"],
    )
    registry.create_profile(profile)

    auth_store = ProfileAuthStore(profile, keyring_module=mock_keyring)
    auth_store.set_credentials("kalshi", "key-id-123", "secret-value")

    result = runner.invoke(app, ["profile", "auth", "auth-show-test"])

    assert result.exit_code == 0, f"Command failed: {result.stdout}"
    assert "kalshi" in result.stdout


def test_profile_auth_json(runner, registry, mock_keyring):
    """Show auth credentials as JSON."""
    profile = TradingProfile(
        name="auth-json-test",
        mode="paper",
        description="Auth JSON test",
        risk_multiplier=0.5,
        max_position_per_market_pct=HARD_LIMITS["max_position_per_market_pct"],
        max_daily_loss_pct=HARD_LIMITS["max_daily_loss_pct"],
        max_drawdown_pct=HARD_LIMITS["max_drawdown_pct"],
        max_open_positions=int(HARD_LIMITS["max_open_positions"]),
        min_liquidity_threshold=int(HARD_LIMITS["min_liquidity_threshold"]),
        min_edge_pct=HARD_LIMITS["min_edge_pct"],
    )
    registry.create_profile(profile)

    auth_store = ProfileAuthStore(profile, keyring_module=mock_keyring)
    auth_store.set_credentials("kalshi", "key-id-123", "secret-value")

    result = runner.invoke(app, ["profile", "auth", "auth-json-test", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert len(data) == 1
    assert data[0]["service"] == "kalshi"
    assert data[0]["key"] == "key-id-123"


def test_profile_auth_nonexistent_profile(runner, registry, mock_keyring):
    """Show auth for nonexistent profile should fail."""
    result = runner.invoke(app, ["profile", "auth", "nonexistent"])

    assert result.exit_code != 0
    assert "not found" in result.stdout.lower()


def test_profile_auth_no_credentials(runner, registry, mock_keyring):
    """Show auth when no credentials configured."""
    profile = TradingProfile(
        name="no-creds-test",
        mode="paper",
        description="No creds test",
        risk_multiplier=0.5,
        max_position_per_market_pct=HARD_LIMITS["max_position_per_market_pct"],
        max_daily_loss_pct=HARD_LIMITS["max_daily_loss_pct"],
        max_drawdown_pct=HARD_LIMITS["max_drawdown_pct"],
        max_open_positions=int(HARD_LIMITS["max_open_positions"]),
        min_liquidity_threshold=int(HARD_LIMITS["min_liquidity_threshold"]),
        min_edge_pct=HARD_LIMITS["min_edge_pct"],
    )
    registry.create_profile(profile)

    result = runner.invoke(app, ["profile", "auth", "no-creds-test"])

    assert result.exit_code == 0
    assert "No credentials configured" in result.stdout


# Made with Bob