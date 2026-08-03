from collections.abc import Awaitable, Callable
from typing import Final

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.shared.memory import create_client_server_memory_streams
from mcp.types import TextContent
from pydantic import TypeAdapter

from traderbot.mcp.server import app
from traderbot.mcp.tools import JsonObject
from traderbot.profiles.tokens import LocalTokenStore

pytestmark = pytest.mark.e2e

_JSON_OBJECT_ADAPTER: Final[TypeAdapter[JsonObject]] = TypeAdapter(JsonObject)


def _round_trip(scenario: Callable[[ClientSession], Awaitable[None]]) -> None:
    async def run_scenario() -> None:
        async with create_client_server_memory_streams() as (client_streams, server_streams):
            async with anyio.create_task_group() as task_group:
                _ = task_group.start_soon(
                    app.run, *server_streams, app.create_initialization_options()
                )
                async with ClientSession(*client_streams) as session:
                    _ = await session.initialize()
                    await scenario(session)
                task_group.cancel_scope.cancel()

    anyio.run(run_scenario)


def test_real_auth_market_edge_succeeds_over_transport(real_auth: LocalTokenStore) -> None:
    real_auth.store_token("weather", "weather-real-agent", "real-weather-e2e-token")

    async def scenario(session: ClientSession) -> None:
        result = await session.call_tool(
            "market_edge",
            {
                "token": "real-weather-e2e-token",
                "category": "weather",
                "ticker": "KXWEATHER-26",
            },
        )

        assert result.is_error is False
        content = result.content[0]
        assert isinstance(content, TextContent)
        payload = _JSON_OBJECT_ADAPTER.validate_json(content.text)
        assert payload["status"] == "stub"
        assert payload["category"] == "weather"

    _round_trip(scenario)


def test_real_auth_category_denial_is_protocol_error(real_auth: LocalTokenStore) -> None:
    real_auth.store_token("weather", "weather-real-agent", "real-weather-denied-token")

    async def scenario(session: ClientSession) -> None:
        result = await session.call_tool(
            "market_edge",
            {
                "token": "real-weather-denied-token",
                "category": "economics",
                "ticker": "KXGDP-26",
            },
        )

        assert result.is_error is True
        content = result.content[0]
        assert isinstance(content, TextContent)
        payload = _JSON_OBJECT_ADAPTER.validate_json(content.text)
        assert payload == {
            "error": "Category 'economics' not enabled for agent 'weather-real-agent'"
        }

    _round_trip(scenario)
