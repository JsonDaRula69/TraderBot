"""Shared runtime status for the Phase 2 daemon components (DD-016).

The daemon updates :data:`service_status` as its WebSocket manager and
data-collection workers change state; the :func:`traderbot__health` MCP tool
reads it so that reported status reflects real component state instead of
hardcoded placeholders. Module-level singleton to avoid an injection seam
between the daemon orchestrator and the MCP tool layer.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from traderbot.kalshi.ws_cache import MarketCache

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]

WEBSOCKET_NOT_STARTED = "not_started"
WEBSOCKET_CONNECTED = "connected"
WEBSOCKET_DISCONNECTED = "disconnected"
WEBSOCKET_FAIL_OPEN = "fail_open"

DATA_PIPELINE_STOPPED = "stopped"
DATA_PIPELINE_RUNNING = "running"


@dataclass(frozen=True, slots=True)
class ServiceStatus:
    """Live status snapshot of the daemon's WebSocket and data workers."""

    websocket: str = WEBSOCKET_NOT_STARTED
    data_pipeline: str = DATA_PIPELINE_STOPPED
    upstream: tuple[str, ...] = ()
    database_initialized: bool = False
    chromadb_initialized: bool = False
    chromadb_lock_held: bool = False


service_status: ServiceStatus = ServiceStatus()

_cache: MarketCache | None = None


def set_market_cache(cache: MarketCache | None) -> None:
    """Point the MCP tool layer at the daemon's live MarketCache instance."""
    global _cache
    _cache = cache


def get_market_cache() -> MarketCache | None:
    """Return the daemon's live MarketCache, if the daemon has started."""
    return _cache


def set_websocket(status: str) -> None:
    """Record the WebSocket manager's connection status."""
    global service_status
    service_status = replace(service_status, websocket=status)


def set_data_pipeline(status: str) -> None:
    """Record the data-collection workers' running state."""
    global service_status
    service_status = replace(service_status, data_pipeline=status)


def set_storage_health(
    database_initialized: bool,
    chromadb_initialized: bool,
    chromadb_lock_held: bool,
) -> None:
    global service_status
    service_status = replace(
        service_status,
        database_initialized=database_initialized,
        chromadb_initialized=chromadb_initialized,
        chromadb_lock_held=chromadb_lock_held,
    )


def snapshot() -> JsonObject:
    """Return a JSON-serializable status snapshot for health reporting."""
    return {
        "websocket": service_status.websocket,
        "data_pipeline": service_status.data_pipeline,
        "upstream": list(service_status.upstream),
        "database": "initialized" if service_status.database_initialized else "not_initialized",
        "chromadb": "initialized" if service_status.chromadb_initialized else "not_initialized",
        "chromadb_lock": "held" if service_status.chromadb_lock_held else "not_held",
    }


def reset() -> None:
    """Reset status to defaults (used in tests and before daemon start)."""
    global service_status
    service_status = ServiceStatus()
