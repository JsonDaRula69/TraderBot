"""Negative regression: MCP server fails closed when the token parameter is missing.

Tests that calling `traderbot__health` through the in-process MCP transport with
no `token` argument returns an error result. When the injection hook is absent
and the model omits the token, `traderbot__health(token: str)` raises `TypeError`
for the missing required positional argument, and the server's handler catches it
at server.py:77, returning `{"error": "Invalid arguments for health: ..."}` with
`is_error=True`. This proves the server does not silently proceed without auth.

Run with: pytest tests/test_missing_token.py -v
"""

import json

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.shared.memory import create_client_server_memory_streams

from traderbot.mcp.server import app

# Mark all tests in this module as e2e
pytestmark = pytest.mark.e2e


class TestMissingToken:
    """Negative regression: missing token is rejected over the transport."""

    @pytest.fixture(autouse=True)
    def _hardcoded_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TRADERBOT_USE_HARDCODED_AUTH", "1")

    def _round_trip(self, scenario):
        """Run a scenario against the real server over in-memory JSON-RPC streams.

        scenario is an async callable receiving an initialized ClientSession.
        """

        async def _run():
            async with create_client_server_memory_streams() as (client_streams, server_streams):
                async with anyio.create_task_group() as task_group:
                    _ = task_group.start_soon(
                        app.run, *server_streams, app.create_initialization_options()
                    )
                    async with ClientSession(*client_streams) as session:
                        _ = await session.initialize()
                        await scenario(session)
                    task_group.cancel_scope.cancel()

        anyio.run(_run)

    def test_missing_token_returns_error(self):
        """Calling health with no token is rejected with an error result.

        When the token injection hook is absent and the model omits the token,
        the server fails closed instead of proceeding without auth.
        """

        async def scenario(session):
            result = await session.call_tool("health", {})
            assert result.is_error is True
            text = json.loads(result.content[0].text)
            assert "Invalid arguments for health" in text["error"]

        self._round_trip(scenario)
