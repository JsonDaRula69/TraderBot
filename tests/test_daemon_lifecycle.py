"""Tests for the always-on daemon lifecycle (DD-016, DD-022).

These tests drive the real :func:`run_daemon` with mocked components so the
startup/shutdown ordering is exercised without touching the network.
"""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import traderbot.daemon as daemon_mod
from traderbot.daemon import run_daemon


@pytest.mark.asyncio
async def test_daemon_starts_and_shuts_down_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    cache = MagicMock()
    cache.start_persist_task = AsyncMock(side_effect=lambda: calls.append("cache:start"))
    cache.stop_persist_task = AsyncMock(side_effect=lambda: calls.append("cache:stop"))
    ws = MagicMock()
    ws.start = AsyncMock(side_effect=lambda: calls.append("ws:start"))
    ws.stop = AsyncMock(side_effect=lambda: calls.append("ws:stop"))
    data = MagicMock()
    data.start = AsyncMock(side_effect=lambda: calls.append("data:start"))
    data.stop = AsyncMock(side_effect=lambda: calls.append("data:stop"))
    client = AsyncMock()
    client.close = AsyncMock(side_effect=lambda: calls.append("client:close"))

    fake_components: dict[str, Any] = {
        "cache": cache,
        "client": client,
        "ws": ws,
        "data": data,
        "mcp_app": MagicMock(),
        "app": MagicMock(),
    }
    monkeypatch.setattr(daemon_mod, "build_components", AsyncMock(return_value=fake_components))

    # Capture the signal handlers run_daemon registers so the test can drive
    # the graceful shutdown path without sending real signals.
    captured: dict[Any, Callable[..., Any]] = {}
    loop = asyncio.get_running_loop()

    def _capture_signal_handler(sig: Any, callback: Callable[..., Any], *args: Any) -> None:
        captured[sig] = lambda: callback(*args)

    monkeypatch.setattr(loop, "add_signal_handler", _capture_signal_handler)

    # Do not bind a real uvicorn server; a no-op serve keeps the test hermetic.
    monkeypatch.setattr("uvicorn.Server.serve", AsyncMock())

    task = asyncio.create_task(run_daemon(port=9876, host="127.0.0.1", environment="production"))
    for _ in range(100):
        if calls.count("data:start") == 1:
            break
        await asyncio.sleep(0.02)
    assert "data:start" in calls

    # Drive graceful shutdown through the captured SIGTERM handler.
    assert signal.SIGTERM in captured
    captured[signal.SIGTERM]()
    await task

    assert calls == [
        "cache:start",
        "ws:start",
        "data:start",
        "data:stop",
        "ws:stop",
        "cache:stop",
        "client:close",
    ]
