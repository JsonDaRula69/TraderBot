"""Tests for the shared daemon status object and health-tool integration (DD-016)."""

from __future__ import annotations

import pytest

from traderbot.mcp import tools
from traderbot.state import (
    DATA_PIPELINE_RUNNING,
    DATA_PIPELINE_STOPPED,
    WEBSOCKET_CONNECTED,
    WEBSOCKET_DISCONNECTED,
    WEBSOCKET_FAIL_OPEN,
    WEBSOCKET_NOT_STARTED,
    reset,
    set_data_pipeline,
    set_websocket,
    snapshot,
)

# Matches the hardcoded Phase 0 sysadmin mapping in resolver.py.
_SYSADMIN_TOKEN = "sysadmin-test-token"


@pytest.fixture(autouse=True)
def _reset_status() -> None:
    reset()
    yield
    reset()


def test_default_snapshot() -> None:
    snap = snapshot()

    assert snap["websocket"] == WEBSOCKET_NOT_STARTED
    assert snap["data_pipeline"] == DATA_PIPELINE_STOPPED
    assert snap["upstream"] == []


def test_setters_update_snapshot() -> None:
    set_websocket(WEBSOCKET_CONNECTED)
    set_data_pipeline(DATA_PIPELINE_RUNNING)

    snap = snapshot()
    assert snap["websocket"] == WEBSOCKET_CONNECTED
    assert snap["data_pipeline"] == DATA_PIPELINE_RUNNING


@pytest.mark.asyncio
async def test_health_reports_real_status_when_running() -> None:
    # Simulate the daemon having started WS + data workers.
    set_websocket(WEBSOCKET_CONNECTED)
    set_data_pipeline(DATA_PIPELINE_RUNNING)

    result = await tools.traderbot__health(token=_SYSADMIN_TOKEN)

    assert result["status"] == "ok"
    assert result["components"]["websocket"] == WEBSOCKET_CONNECTED
    assert result["components"]["data_pipeline"] == DATA_PIPELINE_RUNNING


@pytest.mark.asyncio
async def test_health_reports_defaults_in_stdio_mode() -> None:
    # Fresh state (autouse fixture resets) — stdio dev fallback.
    set_websocket(WEBSOCKET_DISCONNECTED)
    set_data_pipeline(DATA_PIPELINE_STOPPED)

    result = await tools.traderbot__health(token=_SYSADMIN_TOKEN)

    assert result["status"] == "ok"
    assert result["components"]["websocket"] == WEBSOCKET_DISCONNECTED
    assert result["components"]["data_pipeline"] == DATA_PIPELINE_STOPPED


def test_fail_open_constant() -> None:
    assert WEBSOCKET_FAIL_OPEN == "fail_open"
