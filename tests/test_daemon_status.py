"""Tests for the shared daemon status object and health-tool integration (DD-016)."""

from __future__ import annotations

from collections.abc import Generator

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
def _reset_status() -> Generator[None]:
    reset()
    yield
    reset()


def test_default_snapshot() -> None:
    snap = snapshot()

    assert snap["websocket"] == WEBSOCKET_NOT_STARTED
    assert snap["data_pipeline"] == DATA_PIPELINE_STOPPED
    assert snap["upstream"] == []
    assert snap["database"] == "not_initialized"
    assert snap["chromadb"] == "not_initialized"
    assert snap["chromadb_lock"] == "not_held"


def test_setters_update_snapshot() -> None:
    set_websocket(WEBSOCKET_CONNECTED)
    set_data_pipeline(DATA_PIPELINE_RUNNING)

    snap = snapshot()
    assert snap["websocket"] == WEBSOCKET_CONNECTED
    assert snap["data_pipeline"] == DATA_PIPELINE_RUNNING


@pytest.mark.parametrize(
    ("websocket", "data_pipeline"),
    [
        pytest.param(WEBSOCKET_CONNECTED, DATA_PIPELINE_RUNNING, id="daemon"),
        pytest.param(WEBSOCKET_DISCONNECTED, DATA_PIPELINE_STOPPED, id="stdio-degraded"),
    ],
)
@pytest.mark.asyncio
async def test_health_reports_component_status(websocket: str, data_pipeline: str) -> None:
    set_websocket(websocket)
    set_data_pipeline(data_pipeline)

    result = await tools.traderbot__health(token=_SYSADMIN_TOKEN)

    assert result["status"] == "ok"
    assert result["components"] == {
        "mcp_server": "running",
        "auth": "hardcoded",
        "data_pipeline": data_pipeline,
        "websocket": websocket,
        "database": "not_initialized",
        "chromadb": "not_initialized",
        "chromadb_lock": "not_held",
    }


def test_fail_open_constant() -> None:
    assert WEBSOCKET_FAIL_OPEN == "fail_open"
