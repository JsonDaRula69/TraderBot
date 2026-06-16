"""Unit tests for MCP server (Phase 0: tool registration and basic server setup)."""

import pytest

from traderbot.mcp.server import app
from traderbot.mcp.tools import TOOL_DEFINITIONS, TOOL_HANDLER_MAP


class TestMCPToolDefinitions:
    def test_four_tools_defined(self):
        assert len(TOOL_DEFINITIONS) == 4

    def test_tool_names_use_double_underscore(self):
        for td in TOOL_DEFINITIONS:
            assert td["name"].startswith("traderbot__"), f"Tool {td['name']} doesn't follow traderbot__ naming"

    def test_all_tools_have_handlers(self):
        for td in TOOL_DEFINITIONS:
            assert td["name"] in TOOL_HANDLER_MAP, f"Tool {td['name']} has no handler"

    def test_health_tool_exists(self):
        names = [td["name"] for td in TOOL_DEFINITIONS]
        assert "traderbot__health" in names

    def test_auth_check_tool_exists(self):
        names = [td["name"] for td in TOOL_DEFINITIONS]
        assert "traderbot__auth_check" in names

    def test_profile_list_tool_exists(self):
        names = [td["name"] for td in TOOL_DEFINITIONS]
        assert "traderbot__profile_list" in names

    def test_market_edge_tool_exists(self):
        names = [td["name"] for td in TOOL_DEFINITIONS]
        assert "traderbot__market_edge" in names

    def test_each_tool_has_description(self):
        for td in TOOL_DEFINITIONS:
            assert len(td.get("description", "")) > 0, f"Tool {td['name']} has no description"

    def test_each_tool_has_required_token_param(self):
        for td in TOOL_DEFINITIONS:
            schema = td.get("inputSchema", {})
            properties = schema.get("properties", {})
            required = schema.get("required", [])
            assert "token" in properties, f"Tool {td['name']} missing token parameter"
            assert "token" in required, f"Tool {td['name']} token not marked as required"


class TestMCPServerApp:
    def test_app_exists(self):
        assert app is not None

    def test_app_is_server(self):
        from mcp.server.lowlevel.server import Server
        assert isinstance(app, Server)