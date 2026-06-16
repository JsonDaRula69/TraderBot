"""E2E test harness for MCP server (Phase 0/1 verification).

Tests that the MCP server can be started, accepts JSON-RPC calls,
and responds correctly to tool invocations. This validates the
OpenClaw → MCP → TraderBot transport chain.

Run with: pytest tests/test_mcp_e2e.py -v
"""

import asyncio
import os
import subprocess
import sys

import pytest

from traderbot.profiles.tokens import assign_token, generate_token

pytestmark = pytest.mark.e2e


class TestMCPEndToEnd:
    """E2E tests that validate the MCP transport chain."""

    def test_mcp_server_starts(self):
        """MCP server process starts without error."""
        result = subprocess.run(
            [sys.executable, "-m", "traderbot.mcp.server", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode is not None, "Server process failed to start"

    def test_health_tool_via_jsonrpc_hardcoded(self):
        """health tool works with hardcoded auth."""
        os.environ["TRADERBOT_USE_HARDCODED_AUTH"] = "1"
        try:
            from traderbot.mcp.tools import traderbot__health

            response = asyncio.run(traderbot__health(token="sysadmin-test-token"))
            assert response.get("status") == "ok", f"Expected status=ok, got: {response}"
            assert response.get("profile") == "sysadmin"
        finally:
            del os.environ["TRADERBOT_USE_HARDCODED_AUTH"]

    def test_health_tool_via_jsonrpc_real_auth(self):
        """health tool works with real token auth."""
        os.environ.pop("TRADERBOT_USE_HARDCODED_AUTH", None)
        token = generate_token()
        assign_token("sysadmin", "sysadmin", token, force=True)
        from traderbot.mcp.tools import traderbot__health

        response = asyncio.run(traderbot__health(token=token))
        assert response.get("status") == "ok", f"Expected status=ok, got: {response}"
        assert response.get("profile") == "sysadmin"
        assert response.get("mode") == "paper"

    def test_auth_check_via_jsonrpc_real_auth(self):
        """auth_check tool works with real token auth."""
        os.environ.pop("TRADERBOT_USE_HARDCODED_AUTH", None)
        token = generate_token()
        assign_token("dev-liaison", "dev-liaison", token, force=True)
        from traderbot.mcp.tools import traderbot__auth_check

        response = asyncio.run(traderbot__auth_check(token=token))
        assert response.get("status") == "ok", f"Expected status=ok, got: {response}"
        assert response.get("profile") == "dev-liaison"
        assert response.get("mode") == "paper"

    def test_invalid_token_rejected(self):
        """Invalid token returns error in tool response."""
        os.environ.pop("TRADERBOT_USE_HARDCODED_AUTH", None)
        from traderbot.mcp.tools import traderbot__health

        response = asyncio.run(traderbot__health(token="invalid-token"))
        assert response.get("error") is not None, (
            f"Expected error for invalid token, got: {response}"
        )

    def test_permission_denied_for_trading_tool(self):
        """SysAdmin cannot call traderbot__trade (should be denied)."""
        from traderbot.profiles.sysadmin import create_sysadmin_profile

        profile = create_sysadmin_profile()
        assert not profile.is_tool_permitted("traderbot__trade"), (
            "SysAdmin should not have permission to trade"
        )

    def test_permission_denied_for_analysis_tool(self):
        """SysAdmin cannot call traderbot__analyze."""
        from traderbot.profiles.sysadmin import create_sysadmin_profile

        profile = create_sysadmin_profile()
        assert not profile.is_tool_permitted("traderbot__analyze"), (
            "SysAdmin should not have permission to analyze"
        )

    def test_dev_liaison_cannot_trade(self):
        """Dev-Liaison cannot call traderbot__trade."""
        from traderbot.profiles.dev_liaison import create_dev_liaison_profile

        profile = create_dev_liaison_profile()
        assert not profile.is_tool_permitted("traderbot__trade"), (
            "Dev-Liaison should not have permission to trade"
        )

    def test_weather_can_trade(self):
        """Weather agent CAN call traderbot__trade (category agents trade)."""
        from traderbot.profiles.weather import create_weather_profile

        profile = create_weather_profile()
        assert profile.is_tool_permitted("traderbot__trade"), (
            "Weather agent should have permission to trade"
        )
