"""MCP tool definitions for TraderBot (DD-015, DD-025, DD-035).

Phase 0: 4 initial tools — health, auth_check, profile_list, market_edge.
Every tool accepts `token` as first parameter for authentication.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, ClassVar, Final, TypedDict

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from traderbot.mcp.auth import check_category_access
from traderbot.mcp.resolver import resolve_token_adapter
from traderbot.profiles import ProfileRegistry

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]
type ErrorResult = JsonObject

_JSON_OBJECT_ADAPTER: Final[TypeAdapter[JsonObject]] = TypeAdapter(JsonObject)


class ToolDefinition(TypedDict):
    name: str
    description: str
    inputSchema: JsonObject


class HealthInput(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    token: str


class AuthCheckInput(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    token: str


class ProfileListInput(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    token: str


class MarketEdgeInput(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    token: str
    category: str
    ticker: str


def _check_permissions(
    token: JsonValue, tool_name: str, category: str | None = None
) -> tuple[TradingProfile | None, str | None, ErrorResult | None]:
    """Authenticate and authorize a tool call.

    Tool names in MCP are short (e.g. 'health'), but permissions use
    the full prefixed form (e.g. 'traderbot__health'). This function
    adds the prefix before checking permissions.

    Returns (profile, agent_id, error_dict). If error_dict is not None,
    the call is unauthorized and error_dict should be returned directly.
    """
    if not isinstance(token, str):
        return None, None, {"error": "Invalid input: token must be a string"}

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

    category_error = check_category_access(profile, agent_id, category, full_name)
    if category_error is not None:
        return profile, agent_id, _JSON_OBJECT_ADAPTER.validate_python(category_error)

    return profile, agent_id, None


async def traderbot__health(token: str, **kwargs: JsonValue) -> JsonObject:
    """Combined health check: service, WebSocket, data, auth, circuit breakers."""
    profile, agent_id, err = _check_permissions(token, "health", category=None)
    if err is not None:
        return err

    try:
        _input = HealthInput.model_validate({"token": token, **kwargs})
    except ValidationError as exc:
        return {"error": f"Invalid input: {exc}"}

    assert profile is not None
    use_hardcoded_auth = os.environ.get("TRADERBOT_USE_HARDCODED_AUTH", "1") != "0"

    return {
        "status": "ok",
        "mode": profile.mode,
        "agent_id": agent_id,
        "profile": profile.name,
        "timestamp": datetime.now(UTC).isoformat(),
        "components": {
            "mcp_server": "running",
            "auth": "hardcoded" if use_hardcoded_auth else "resolved",
            "data_pipeline": "not_started",
            "websocket": "not_connected",
        },
    }


async def traderbot__auth_check(token: str, **kwargs: JsonValue) -> JsonObject:
    """Validate the profile token and report its access context."""
    profile, agent_id, err = _check_permissions(token, "auth_check", category=None)
    if err is not None:
        return err

    try:
        _input = AuthCheckInput.model_validate({"token": token, **kwargs})
    except ValidationError as exc:
        return {"error": f"Invalid input: {exc}"}

    assert profile is not None
    enabled_categories: list[JsonValue] = (
        [category.value for category in profile.enabled_categories]
        if profile.enabled_categories
        else ["all"]
    )
    permissions: list[JsonValue] = list(profile.permissions) if profile.permissions else ["all"]

    return {
        "status": "ok",
        "profile": profile.name,
        "agent_id": agent_id,
        "mode": profile.mode,
        "enabled_categories": enabled_categories,
        "permissions": permissions,
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def traderbot__profile_list(token: str, **kwargs: JsonValue) -> JsonObject:
    """List all profiles and their modes."""
    profile, agent_id, err = _check_permissions(token, "profile_list", category=None)
    if err is not None:
        return err

    try:
        _input = ProfileListInput.model_validate({"token": token, **kwargs})
    except ValidationError as exc:
        return {"error": f"Invalid input: {exc}"}

    assert profile is not None
    profiles = _JSON_OBJECT_ADAPTER.validate_python(ProfileRegistry().list_profiles())

    return {
        "status": "ok",
        "caller": {"profile": profile.name, "agent_id": agent_id},
        "profiles": profiles,
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def traderbot__market_edge(token: str, **kwargs: JsonValue) -> JsonObject:
    """Compute the estimated edge for a market (Phase 0: stub response)."""
    raw_category = kwargs.get("category")
    category = raw_category if isinstance(raw_category, str) else None
    _profile, _agent_id, err = _check_permissions(token, "market_edge", category=category)
    if err is not None:
        return err

    try:
        input_data = MarketEdgeInput.model_validate({"token": token, **kwargs})
    except ValidationError as exc:
        return {"error": f"Invalid input: {exc}"}

    return {
        "status": "stub",
        "message": "market_edge not yet implemented (Phase 0 skeleton)",
        "category": input_data.category,
        "ticker": input_data.ticker,
        "edge_pct": 0.0,
        "confidence": 0.0,
        "sample_size": 0,
    }


TOOL_DEFINITIONS: tuple[ToolDefinition, ...] = (
    {
        "name": "health",
        "description": "Combined health check: service, WebSocket, data, auth, circuit breakers.",
        "inputSchema": _JSON_OBJECT_ADAPTER.validate_python(HealthInput.model_json_schema()),
    },
    {
        "name": "auth_check",
        "description": "Validate the profile token and report its access context.",
        "inputSchema": _JSON_OBJECT_ADAPTER.validate_python(AuthCheckInput.model_json_schema()),
    },
    {
        "name": "profile_list",
        "description": "List all profiles and their modes.",
        "inputSchema": _JSON_OBJECT_ADAPTER.validate_python(ProfileListInput.model_json_schema()),
    },
    {
        "name": "market_edge",
        "description": "Compute the estimated edge for a market.",
        "inputSchema": _JSON_OBJECT_ADAPTER.validate_python(MarketEdgeInput.model_json_schema()),
    },
)

TOOL_HANDLER_MAP = {
    "health": traderbot__health,
    "auth_check": traderbot__auth_check,
    "profile_list": traderbot__profile_list,
    "market_edge": traderbot__market_edge,
}
