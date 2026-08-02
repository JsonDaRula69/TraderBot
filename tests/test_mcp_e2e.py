"""E2E test harness for MCP server (Phase 0 verification).

Tests that the MCP server accepts real JSON-RPC exchanges — initialize,
tools/list, and tools/call — through the actual protocol layer, validating
the OpenClaw → MCP → TraderBot transport chain in-process (no subprocess,
no external network). Uses mcp's in-memory stream transport so the full
message framing and handler dispatch run unchanged.

Run with: pytest tests/test_mcp_e2e.py -v
"""

import asyncio
import json

import pytest
from mcp.client.session import ClientSession
from mcp.shared.memory import create_client_server_memory_streams

from traderbot.mcp.server import app

# Mark all tests in this module as e2e
pytestmark = pytest.mark.e2e


class TestMCPEndToEnd:
    """E2E tests that validate the MCP transport chain."""

    def _round_trip(self, scenario):
        """Run a scenario against the real server over in-memory JSON-RPC streams.

        scenario is an async callable receiving an initialized ClientSession.
        """

        async def _run():
            async with create_client_server_memory_streams() as (client_streams, server_streams):
                server_task = asyncio.create_task(
                    app.run(*server_streams, app.create_initialization_options())
                )
                try:
                    async with ClientSession(*client_streams) as session:
                        await session.initialize()
                        await scenario(session)
                finally:
                    server_task.cancel()
                    try:
                        await server_task
                    except asyncio.CancelledError:
                        pass

        asyncio.run(_run())

    def test_jsonrpc_initialize_and_list_tools(self):
        """initialize + tools/list return exactly the 4 Phase 0 tools."""

        async def scenario(session):
            result = await session.list_tools()
            names = {t.name for t in result.tools}
            assert names == {"health", "auth_check", "profile_list", "market_edge"}

        self._round_trip(scenario)

    def test_jsonrpc_call_tool_health(self):
        """tools/call health returns status=ok for a valid sysadmin token."""

        async def scenario(session):
            result = await session.call_tool("health", {"token": "sysadmin-test-token"})
            assert result.is_error is False
            text = json.loads(result.content[0].text)
            assert text["status"] == "ok"
            assert text["profile"] == "sysadmin"
            assert text["mode"] == "paper"

        self._round_trip(scenario)

    def test_jsonrpc_call_tool_auth_check(self):
        """tools/call auth_check returns profile info for a valid token."""

        async def scenario(session):
            result = await session.call_tool(
                "auth_check", {"token": "dev-liaison-test-token"}
            )
            assert result.is_error is False
            text = json.loads(result.content[0].text)
            assert text["status"] == "ok"
            assert text["profile"] == "dev-liaison"

        self._round_trip(scenario)

    def test_jsonrpc_call_tool_invalid_token(self):
        """An invalid token is rejected with an error result over the transport."""

        async def scenario(session):
            result = await session.call_tool("health", {"token": "bogus-token"})
            assert result.is_error is True
            text = json.loads(result.content[0].text)
            assert "Invalid or expired profile token" in text["error"]

        self._round_trip(scenario)

    def test_jsonrpc_call_tool_unknown_tool(self):
        """An unknown tool name returns an error result over the transport."""

        async def scenario(session):
            result = await session.call_tool("nonexistent_tool", {})
            assert result.is_error is True
            text = json.loads(result.content[0].text)
            assert "Unknown tool" in text["error"]

        self._round_trip(scenario)
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
