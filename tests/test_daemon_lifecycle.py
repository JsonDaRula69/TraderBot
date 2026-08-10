"""Tests for the always-on daemon lifecycle (DD-016, DD-022).

These tests drive the real :func:`run_daemon` with mocked components so the
startup/shutdown ordering is exercised without touching the network.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import traderbot.daemon as daemon_mod
from traderbot.daemon import build_components, run_daemon
from traderbot.state import reset, snapshot


@pytest.fixture(autouse=True)
def _reset_status() -> Generator[None]:
    reset()
    yield
    reset()


@pytest.mark.asyncio
async def test_build_components_initializes_storage_before_consumers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    pool = MagicMock()
    chroma = MagicMock()
    cache = MagicMock()
    client = MagicMock()
    ws = MagicMock()
    data = MagicMock()
    mcp_app = MagicMock()
    mcp_server = MagicMock()
    mcp_server.streamable_http_app.return_value = mcp_app
    secrets = MagicMock()
    secrets.get.side_effect = ["api-key", "private-key"]

    monkeypatch.setattr(daemon_mod, "init_schema", lambda _path: calls.append("migration"))
    monkeypatch.setattr(
        daemon_mod,
        "SQLiteConnectionPool",
        lambda: calls.append("pool") or pool,
    )
    monkeypatch.setattr(
        daemon_mod,
        "create_chroma_root",
        lambda _path: calls.append("chroma-root"),
    )
    monkeypatch.setattr(
        daemon_mod,
        "ChromaStore",
        lambda _path: calls.append("chroma") or chroma,
    )
    monkeypatch.setattr(
        daemon_mod,
        "DatabaseAccess",
        lambda _pool, _root: calls.append("access") or MagicMock(),
    )
    monkeypatch.setattr(
        daemon_mod,
        "KalshiClient",
        lambda **_kwargs: calls.append("client") or client,
    )
    monkeypatch.setattr(
        daemon_mod,
        "MarketCache",
        lambda _pool, _path: calls.append("cache") or cache,
    )
    monkeypatch.setattr(
        daemon_mod,
        "KalshiWebSocketManager",
        lambda **_kwargs: calls.append("ws") or ws,
    )
    monkeypatch.setattr(
        daemon_mod,
        "DataCollectionService",
        lambda: calls.append("data") or data,
    )
    monkeypatch.setattr(daemon_mod, "SettlementMonitor", lambda *_args: MagicMock())
    monkeypatch.setattr(daemon_mod, "OpenMeteoProvider", lambda *_args: MagicMock())
    monkeypatch.setattr(daemon_mod, "NwsProvider", lambda *_args: MagicMock())
    monkeypatch.setattr(daemon_mod, "NewsProvider", MagicMock)
    monkeypatch.setattr(daemon_mod, "app", mcp_server)

    components = await build_components(
        secrets,
        db_path=tmp_path / "traderbot.db",
        data_root=tmp_path,
    )

    assert calls == [
        "migration",
        "pool",
        "chroma-root",
        "chroma",
        "access",
        "client",
        "cache",
        "ws",
        "data",
    ]
    assert components["pool"] is pool
    assert components["chroma"] is chroma
    assert snapshot()["database"] == "initialized"
    assert snapshot()["chromadb"] == "initialized"
    assert snapshot()["chromadb_lock"] == "held"


@pytest.mark.asyncio
async def test_migration_failure_aborts_before_component_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pool = MagicMock()
    chroma = MagicMock()
    monkeypatch.setattr(daemon_mod, "init_schema", MagicMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(daemon_mod, "SQLiteConnectionPool", pool)
    monkeypatch.setattr(daemon_mod, "ChromaStore", chroma)

    with pytest.raises(RuntimeError, match="boom"):
        await build_components(MagicMock(), db_path=tmp_path / "traderbot.db", data_root=tmp_path)

    pool.assert_not_called()
    chroma.assert_not_called()
    assert snapshot()["database"] == "not_initialized"


@pytest.mark.asyncio
async def test_chroma_failure_releases_pool_and_resets_storage_health(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pool = MagicMock()
    monkeypatch.setattr(daemon_mod, "init_schema", MagicMock())
    monkeypatch.setattr(daemon_mod, "SQLiteConnectionPool", MagicMock(return_value=pool))
    monkeypatch.setattr(daemon_mod, "create_chroma_root", MagicMock())
    monkeypatch.setattr(daemon_mod, "ChromaStore", MagicMock(side_effect=RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        await build_components(MagicMock(), db_path=tmp_path / "traderbot.db", data_root=tmp_path)

    pool.shutdown.assert_called_once_with()
    assert snapshot()["database"] == "not_initialized"
    assert snapshot()["chromadb"] == "not_initialized"
    assert snapshot()["chromadb_lock"] == "not_held"


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
    chroma = MagicMock()
    chroma.close.side_effect = lambda: calls.append("chroma:close")
    pool = MagicMock()
    pool.shutdown.side_effect = lambda: calls.append("pool:shutdown")

    fake_components: dict[str, Any] = {
        "cache": cache,
        "client": client,
        "chroma": chroma,
        "pool": pool,
        "access": MagicMock(),
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
        "chroma:close",
        "pool:shutdown",
    ]


def test_stdio_server_exits_cleanly_on_eof() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "traderbot.mcp.server"],
        input="",
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr


def test_chroma_lock_is_released_when_owner_process_exits(tmp_path: Path) -> None:
    home = tmp_path / "home"
    chroma_root = home / ".traderbot" / "chromadb"
    chroma_root.mkdir(parents=True, mode=0o700)
    chroma_root.chmod(0o700)
    lock_path = chroma_root / "chromadb.lock"
    lock_path.write_bytes(b"\0")
    lock_path.chmod(0o600)
    script = (
        "from pathlib import Path; "
        "from traderbot.db.chroma_store import ChromaStore; "
        f"store = ChromaStore(Path({str(chroma_root)!r}))"
    )
    environment = os.environ | {"HOME": str(home), "USERPROFILE": str(home)}

    first = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
        env=environment,
    )
    second = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
        env=environment,
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
