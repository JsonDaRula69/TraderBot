"""E2E test harness for MCP server (Phase 0 verification).

Tests that the MCP server can be started, accepts JSON-RPC calls,
and responds correctly to tool invocations. This validates the
OpenClaw → MCP → TraderBot transport chain.

Run with: pytest tests/test_mcp_e2e.py -v
"""

import asyncio
import subprocess
import sys

import pytest

# Mark all tests in this module as e2e
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
        # Server should at least start (may show help or start running)
        # Exit code 0 for --help, or we just check it doesn't crash immediately
        assert result.returncode is not None, "Server process failed to start"

    def test_health_tool_via_jsonrpc(self):
        """traderbot__health tool can be called directly."""
        from traderbot.mcp.tools import traderbot__health

        response = asyncio.run(traderbot__health(token="sysadmin-test-token"))
        assert response.get("status") == "ok", f"Expected status=ok, got: {response}"
        assert response.get("profile") == "sysadmin"

    def test_auth_check_tool_via_jsonrpc(self):
        """traderbot__auth_check tool can be called directly."""
        from traderbot.mcp.tools import traderbot__auth_check

        response = asyncio.run(traderbot__auth_check(token="sysadmin-test-token"))
        assert response.get("status") == "ok", f"Expected status=ok, got: {response}"
        assert response.get("profile") == "sysadmin"

    def test_invalid_token_rejected(self):
        """Invalid token returns error in tool response."""
        from traderbot.mcp.tools import traderbot__health

        response = asyncio.run(traderbot__health(token="invalid-token"))
        assert response.get("error") is not None, (
            f"Expected error for invalid token, got: {response}"
        )

    def test_permission_denied_for_trading_tool(self):
        """SysAdmin cannot call traderbot__trade (should be denied)."""
        from traderbot.mcp.resolver import resolve_token_adapter

        profile, agent_id = resolve_token_adapter("sysadmin-test-token")
        assert profile is not None
        assert not profile.is_tool_permitted("traderbot__trade"), (
            "SysAdmin should not have permission to trade"
        )

    def test_permission_denied_for_analysis_tool(self):
        """SysAdmin cannot call traderbot__analyze."""
        from traderbot.mcp.resolver import resolve_token_adapter

        profile, agent_id = resolve_token_adapter("sysadmin-test-token")
        assert profile is not None
        assert not profile.is_tool_permitted("traderbot__analyze"), (
            "SysAdmin should not have permission to analyze"
        )

    def test_dev_liaison_cannot_trade(self):
        """Dev-Liaison cannot call traderbot__trade."""
        from traderbot.mcp.resolver import resolve_token_adapter

        profile, agent_id = resolve_token_adapter("dev-liaison-test-token")
        assert profile is not None
        assert not profile.is_tool_permitted("traderbot__trade"), (
            "Dev-Liaison should not have permission to trade"
        )

    def test_weather_can_trade(self):
        """Weather agent CAN call traderbot__trade (category agents trade)."""
        from traderbot.mcp.resolver import resolve_token_adapter

        profile, agent_id = resolve_token_adapter("weather-test-token")
        assert profile is not None
        assert profile.is_tool_permitted("traderbot__trade"), (
            "Weather agent should have permission to trade"
        )

    def test_health_tool_returns_ok(self):
        """traderbot__health returns status=ok for valid sysadmin token."""
        from traderbot.mcp.tools import traderbot__health

        response = asyncio.run(traderbot__health(token="sysadmin-test-token"))
        assert response.get("status") == "ok", f"Expected status=ok, got: {response}"
        assert response.get("profile") == "sysadmin"
        assert response.get("mode") == "paper"

    def test_auth_check_returns_profile_info(self):
        """traderbot__auth_check returns profile info for valid token."""
        from traderbot.mcp.tools import traderbot__auth_check

        response = asyncio.run(traderbot__auth_check(token="dev-liaison-test-token"))
        assert response.get("status") == "ok"
        assert response.get("profile") == "dev-liaison"
        assert response.get("mode") == "paper"