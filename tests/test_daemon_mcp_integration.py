"""Integration test: daemon serves MCP over streamable-http (DD-016).

Starts the real :func:`run_daemon` with a mocked component graph (real
streamable-http app + seeded MarketCache), connects over HTTP, and calls
``health`` and ``market_prices`` through the live transport.
"""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

import traderbot.daemon as daemon_mod
from traderbot.daemon import run_daemon
from traderbot.kalshi.ws_cache import MarketCache
from traderbot.mcp.server import app
from traderbot.state import set_market_cache


@pytest.mark.asyncio
async def test_daemon_serves_mcp_over_streamable_http(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache = MarketCache(db_path=tmp_path / "cache.db")
    cache.update_ticker("KXWETHRM0700M", last_price=0.55, bid=0.54, ask=0.56, volume=100)
    # The real build_components registers the cache in module state; the mocked
    # graph below skips that, so seed the shared cache reference explicitly.
    set_market_cache(cache)

    fake_components: dict[str, Any] = {
        "cache": cache,
        "client": AsyncMock(),
        "chroma": MagicMock(),
        "pool": MagicMock(),
        "access": MagicMock(),
        "ws": MagicMock(),
        "data": MagicMock(),
        "mcp_app": app.streamable_http_app(),
        "app": app,
    }
    fake_components["ws"].start = AsyncMock()
    fake_components["ws"].stop = AsyncMock()
    fake_components["data"].start = AsyncMock()
    fake_components["data"].stop = AsyncMock()
    fake_components["cache"].start_persist_task = AsyncMock()
    fake_components["cache"].stop_persist_task = AsyncMock()
    monkeypatch.setattr(daemon_mod, "build_components", AsyncMock(return_value=fake_components))
    monkeypatch.setattr(daemon_mod, "start_scheduler", AsyncMock())
    monkeypatch.setattr(daemon_mod, "stop_scheduler", AsyncMock())

    captured: dict[Any, Callable[..., Any]] = {}
    loop = asyncio.get_running_loop()

    def _capture_signal_handler(sig: Any, callback: Callable[..., Any], *args: Any) -> None:
        captured[sig] = lambda: callback(*args)

    monkeypatch.setattr(loop, "add_signal_handler", _capture_signal_handler)

    port = 9877
    task = asyncio.create_task(run_daemon(port=port, host="127.0.0.1", environment="production"))

    # Wait for the HTTP server to accept connections before connecting.
    url = f"http://127.0.0.1:{port}/mcp"
    for _ in range(100):
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            break
        except OSError:
            await asyncio.sleep(0.05)
    else:
        pytest.fail("daemon HTTP server never became ready")

    async with streamable_http_client(url) as (client_streams, server_streams):
        async with ClientSession(client_streams, server_streams) as session:
            _ = await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert "health" in names
            assert "market_prices" in names

            health = await session.call_tool("health", {"token": "sysadmin-test-token"})
            assert health.is_error is False
            import json

            health_text = json.loads(health.content[0].text)
            assert health_text["status"] == "ok"

            prices = await session.call_tool(
                "market_prices",
                {"token": "weather-test-token", "ticker": "KXWETHRM0700M"},
            )
            assert prices.is_error is False
            prices_text = json.loads(prices.content[0].text)
            assert prices_text["ticker"] == "KXWETHRM0700M"
            assert prices_text["current_price"] == 0.55

    # Drive graceful shutdown through the captured SIGTERM handler.
    assert signal.SIGTERM in captured
    captured[signal.SIGTERM]()
    await task

    fake_components["data"].stop.assert_awaited_once()
    fake_components["ws"].stop.assert_awaited_once()
    fake_components["cache"].stop_persist_task.assert_awaited_once()
