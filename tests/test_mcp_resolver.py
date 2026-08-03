"""Unit tests for MCP token resolver (Phase 0: hardcoded auth)."""

import pytest

from traderbot.mcp.resolver import resolve_token_adapter
from traderbot.profiles.tokens import LocalTokenStore


class TestHardcodedTokenResolver:
    @pytest.fixture(autouse=True)
    def _hardcoded_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TRADERBOT_USE_HARDCODED_AUTH", "1")

    def test_sysadmin_token_resolves(self):
        profile, agent_id = resolve_token_adapter("sysadmin-test-token")
        assert profile is not None
        assert profile.name == "sysadmin"
        assert agent_id == "sysadmin"

    def test_dev_liaison_token_resolves(self):
        profile, agent_id = resolve_token_adapter("dev-liaison-test-token")
        assert profile is not None
        assert profile.name == "dev-liaison"
        assert agent_id == "dev-liaison"

    def test_weather_token_resolves(self):
        profile, agent_id = resolve_token_adapter("weather-test-token")
        assert profile is not None
        assert profile.name == "weather"
        assert agent_id == "weather"

    def test_invalid_token_returns_none(self):
        profile, agent_id = resolve_token_adapter("invalid-token")
        assert profile is None
        assert agent_id is None

    def test_empty_token_returns_none(self):
        profile, agent_id = resolve_token_adapter("")
        assert profile is None
        assert agent_id is None

    def test_hardcoded_auth_env_var(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TRADERBOT_USE_HARDCODED_AUTH", "1")

        profile, agent_id = resolve_token_adapter("sysadmin-test-token")

        assert profile is not None
        assert profile.name == "sysadmin"
        assert agent_id == "sysadmin"


def test_real_auth_resolves(real_auth: LocalTokenStore) -> None:
    real_auth.store_token("weather", "weather-agent", "real-weather-token")

    profile, agent_id = resolve_token_adapter("real-weather-token")

    assert profile is not None
    assert profile.name == "weather"
    assert agent_id == "weather-agent"


def test_real_auth_invalid_token(real_auth: LocalTokenStore) -> None:
    real_auth.store_token("weather", "weather-agent", "known-real-token")

    assert resolve_token_adapter("invalid-real-token") == (None, None)


def test_real_auth_missing_file(real_auth: LocalTokenStore) -> None:
    assert real_auth.token_file.exists() is False

    assert resolve_token_adapter("missing-real-token") == (None, None)


def test_hardcoded_auth_default_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRADERBOT_USE_HARDCODED_AUTH", raising=False)

    profile, agent_id = resolve_token_adapter("sysadmin-test-token")

    assert profile is not None
    assert profile.name == "sysadmin"
    assert agent_id == "sysadmin"
