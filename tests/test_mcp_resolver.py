"""Unit tests for MCP token resolver (Phase 1: real auth with hardcoded fallback)."""

import os

from traderbot.mcp.resolver import resolve_token_adapter


class TestHardcodedTokenResolver:
    """Tests for the hardcoded auth path (TRADERBOT_USE_HARDCODED_AUTH=1)."""

    def test_sysadmin_token_resolves(self):
        os.environ["TRADERBOT_USE_HARDCODED_AUTH"] = "1"
        try:
            profile, agent_id = resolve_token_adapter("sysadmin-test-token")
            assert profile is not None
            assert profile.name == "sysadmin"
            assert agent_id == "sysadmin"
        finally:
            del os.environ["TRADERBOT_USE_HARDCODED_AUTH"]

    def test_dev_liaison_token_resolves(self):
        os.environ["TRADERBOT_USE_HARDCODED_AUTH"] = "1"
        try:
            profile, agent_id = resolve_token_adapter("dev-liaison-test-token")
            assert profile is not None
            assert profile.name == "dev-liaison"
            assert agent_id == "dev-liaison"
        finally:
            del os.environ["TRADERBOT_USE_HARDCODED_AUTH"]

    def test_weather_token_resolves(self):
        os.environ["TRADERBOT_USE_HARDCODED_AUTH"] = "1"
        try:
            profile, agent_id = resolve_token_adapter("weather-test-token")
            assert profile is not None
            assert profile.name == "weather"
            assert agent_id == "weather"
        finally:
            del os.environ["TRADERBOT_USE_HARDCODED_AUTH"]

    def test_invalid_token_returns_none(self):
        os.environ["TRADERBOT_USE_HARDCODED_AUTH"] = "1"
        try:
            profile, agent_id = resolve_token_adapter("invalid-token")
            assert profile is None
            assert agent_id is None
        finally:
            del os.environ["TRADERBOT_USE_HARDCODED_AUTH"]

    def test_empty_token_returns_none(self):
        os.environ["TRADERBOT_USE_HARDCODED_AUTH"] = "1"
        try:
            profile, agent_id = resolve_token_adapter("")
            assert profile is None
            assert agent_id is None
        finally:
            del os.environ["TRADERBOT_USE_HARDCODED_AUTH"]


class TestRealAuthResolver:
    """Tests for the real auth path (default: TRADERBOT_USE_HARDCODED_AUTH=0)."""

    def test_invalid_token_returns_none(self):
        os.environ.pop("TRADERBOT_USE_HARDCODED_AUTH", None)
        profile, agent_id = resolve_token_adapter("nonexistent-token-12345")
        assert profile is None
        assert agent_id is None

    def test_empty_token_returns_none(self):
        os.environ.pop("TRADERBOT_USE_HARDCODED_AUTH", None)
        profile, agent_id = resolve_token_adapter("")
        assert profile is None
        assert agent_id is None

    def test_real_token_resolves(self):
        """Test that a real token from the Fernet store resolves correctly."""
        from traderbot.profiles.tokens import assign_token, generate_token

        os.environ.pop("TRADERBOT_USE_HARDCODED_AUTH", None)
        token = generate_token()
        assign_token("sysadmin", "sysadmin", token, force=True)
        profile, agent_id = resolve_token_adapter(token)
        assert profile is not None
        assert profile.name == "sysadmin"
        assert agent_id == "sysadmin"
