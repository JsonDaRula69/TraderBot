"""Unit tests for MCP token resolver (Phase 0: hardcoded auth)."""

import os

from traderbot.mcp.resolver import resolve_token_adapter


class TestHardcodedTokenResolver:
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

    def test_hardcoded_auth_env_var(self):
        os.environ["TRADERBOT_USE_HARDCODED_AUTH"] = "1"
        try:
            profile, agent_id = resolve_token_adapter("sysadmin-test-token")
            assert profile is not None
            assert profile.name == "sysadmin"
        finally:
            del os.environ["TRADERBOT_USE_HARDCODED_AUTH"]