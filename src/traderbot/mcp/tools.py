"""MCP tool definitions for TraderBot (DD-015, DD-025, DD-035).

Phase 0: 4 initial tools — health, auth_check, profile_list, market_edge.
Every tool accepts `token` as first parameter for authentication.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from traderbot.mcp.resolver import resolve_token_adapter

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)


def _check_permissions(
    token: str, tool_name: str
) -> tuple[TradingProfile | None, str | None, dict | None]:
    """Authenticate and authorize a tool call.

    Tool names in MCP are short (e.g. 'health'), but permissions use
    the full prefixed form (e.g. 'traderbot__health'). This function
    adds the prefix before checking permissions.

    Returns (profile, agent_id, error_dict). If error_dict is not None,
    the call is unauthorized and error_dict should be returned directly.
    """
    profile, agent_id = resolve_token_adapter(token)
    if profile is None:
        return None, None, {"error": "Invalid or expired profile token"}

    # Permissions use full names (traderbot__*); tool names are short
    full_name = f"traderbot__{tool_name}"
    if not profile.is_tool_permitted(full_name):
        return (
            profile,
            agent_id,
            {"error": f"Permission denied: profile '{profile.name}' cannot use '{full_name}'"},
        )

    return profile, agent_id, None


async def traderbot__health(token: str) -> dict[str, Any]:
    """Combined health check: service, WebSocket, data, auth, circuit breakers."""
    profile, agent_id, err = _check_permissions(token, "health")
    if err is not None:
        return err

    return {
        "status": "ok",
        "mode": profile.mode,
        "agent_id": agent_id,
        "profile": profile.name,
        "timestamp": datetime.now(UTC).isoformat(),
        "components": {
            "mcp_server": "running",
            "auth": "hardcoded" if token in _hardcoded_token_map() else "resolved",
            "data_pipeline": "not_started",
            "websocket": "not_connected",
        },
    }


async def traderbot__auth_check(token: str) -> dict[str, Any]:
    """Verify all API credentials are valid."""
    profile, agent_id, err = _check_permissions(token, "auth_check")
    if err is not None:
        return err

    return {
        "status": "ok",
        "profile": profile.name,
        "agent_id": agent_id,
        "mode": profile.mode,
        "enabled_categories": [c.value for c in profile.enabled_categories]
        if profile.enabled_categories
        else ["all"],
        "permissions": profile.permissions if profile.permissions else ["all"],
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def traderbot__profile_list(token: str) -> dict[str, Any]:
    """List all profiles and their modes."""
    profile, agent_id, err = _check_permissions(token, "profile_list")
    if err is not None:
        return err

    profiles = {
        "sysadmin": {
            "mode": "paper",
            "categories": ["all"],
            "permissions": [
                "deny:traderbot__trade",
                "deny:traderbot__scan",
                "deny:traderbot__analyze",
                "deny:traderbot__market_edge",
                "deny:traderbot__market_prices",
                "deny:traderbot__weather_*",
            ],
        },
        "dev-liaison": {
            "mode": "paper",
            "categories": [],
            "permissions": [
                "traderbot__reference",
                "traderbot__health",
                "traderbot__auth_check",
                "traderbot__profile_list",
            ],
        },
    }

    return {
        "status": "ok",
        "caller": {"profile": profile.name, "agent_id": agent_id},
        "profiles": profiles,
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def traderbot__market_edge(token: str, category: str, ticker: str) -> dict[str, Any]:
    """Compute the estimated edge for a market (Phase 0: stub response)."""
    _profile, _agent_id, err = _check_permissions(token, "market_edge")
    if err is not None:
        return err

    return {
        "status": "stub",
        "message": "market_edge not yet implemented (Phase 0 skeleton)",
        "category": category,
        "ticker": ticker,
        "edge_pct": 0.0,
        "confidence": 0.0,
        "sample_size": 0,
    }


def _hardcoded_token_map() -> set[str]:
    """Return the set of valid hardcoded tokens for Phase 0 auth detection."""
    from traderbot.mcp.resolver import _HARDCODED_TOKENS

    return set(_HARDCODED_TOKENS.keys())


TOOL_DEFINITIONS = [
    {
        "name": "health",
        "description": "Combined health check: service, WebSocket, data, auth, circuit breakers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "token": {"type": "string", "description": "Profile authentication token"},
            },
            "required": ["token"],
        },
    },
    {
        "name": "auth_check",
        "description": "Verify all API credentials are valid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "token": {"type": "string", "description": "Profile authentication token"},
            },
            "required": ["token"],
        },
    },
    {
        "name": "profile_list",
        "description": "List all profiles and their modes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "token": {"type": "string", "description": "Profile authentication token"},
            },
            "required": ["token"],
        },
    },
    {
        "name": "market_edge",
        "description": "Compute the estimated edge for a market.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "token": {"type": "string", "description": "Profile authentication token"},
                "category": {
                    "type": "string",
                    "description": "Market category (e.g. weather, economics)",
                },
                "ticker": {"type": "string", "description": "Market ticker symbol"},
            },
            "required": ["token", "category", "ticker"],
        },
    },
]

TOOL_HANDLER_MAP = {
    "health": traderbot__health,
    "auth_check": traderbot__auth_check,
    "profile_list": traderbot__profile_list,
    "market_edge": traderbot__market_edge,
}
