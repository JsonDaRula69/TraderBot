"""Failing-first proof for #219 — the daemon must recover from a fail-open credential start.

The defect: :func:`build_components` resolves the Kalshi credential pair once and constructs
the WebSocket manager and client with empty values when the secrets store is not yet
reachable. Nothing consumes the later recovery, so the fleet is permanently degraded (no
live market data, cache frozen) until a human restarts the daemon — a transient boot-order
race that violates the 24/7 autonomy rule.

The fix under test: a credential supervisor that re-resolves the pair, rebuilds the
credential-bound components and restarts the stream in place, with bounded backoff and no
credential material in the logs.
"""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import traderbot.daemon as daemon_mod
from traderbot.daemon import CredentialSupervisor, build_components, run_daemon
from traderbot.data.providers.settlement import SettlementMonitor
from traderbot.state import reset, snapshot


@pytest.fixture(autouse=True)
def _reset_status() -> Any:
    reset()
    yield
    reset()


class _DriverSleep:
    """Injected sleep that records intervals and stops the supervisor after `limit` calls."""

    def __init__(self, supervisor_holder: list[Any], limit: int) -> None:
        self.intervals: list[float] = []
        self._holder = supervisor_holder
        self._limit = limit

    async def __call__(self, seconds: float) -> None:
        self.intervals.append(seconds)
        if self._holder and len(self.intervals) >= self._limit:
            self._holder[0].stop()


@pytest.mark.asyncio
async def test_supervisor_does_nothing_while_credentials_are_healthy() -> None:
    holder: list[CredentialSupervisor] = []
    sleep = _DriverSleep(holder, limit=3)
    resolve = AsyncMock(return_value=(None, None))
    on_recovered = AsyncMock()

    supervisor = CredentialSupervisor(
        is_degraded=lambda: False,
        resolve=resolve,
        on_recovered=on_recovered,
        sleep=sleep,
    )
    holder.append(supervisor)
    await supervisor.run()

    assert resolve.await_count == 0, "no credential probing while the stream is healthy"
    assert on_recovered.await_count == 0
    assert supervisor.recoveries == 0


@pytest.mark.asyncio
async def test_supervisor_recovers_when_credentials_appear_after_fail_open() -> None:
    holder: list[CredentialSupervisor] = []
    sleep = _DriverSleep(holder, limit=3)
    resolve = AsyncMock(side_effect=[(None, None), (None, None), ("key-id", "pem-material")])
    on_recovered = AsyncMock()

    supervisor = CredentialSupervisor(
        is_degraded=lambda: True,
        resolve=resolve,
        on_recovered=on_recovered,
        probe_interval=5.0,
        max_interval=60.0,
        watch_interval=30.0,
        sleep=sleep,
    )
    holder.append(supervisor)
    await supervisor.run()

    assert supervisor.recoveries == 1, "the supervisor rebuilds once credentials resolve"
    assert on_recovered.await_count == 1
    assert on_recovered.await_args is not None
    assert on_recovered.await_args.args == ("key-id", "pem-material")
    assert sleep.intervals == [5.0, 10.0, 30.0], "two backoffs while degraded, then a watch sleep"
    assert supervisor.probes == 3


@pytest.mark.asyncio
async def test_supervisor_backs_off_monotonically_and_respects_the_cap() -> None:
    holder: list[CredentialSupervisor] = []
    sleep = _DriverSleep(holder, limit=6)
    resolve = AsyncMock(return_value=(None, None))

    supervisor = CredentialSupervisor(
        is_degraded=lambda: True,
        resolve=resolve,
        on_recovered=AsyncMock(),
        probe_interval=5.0,
        max_interval=60.0,
        sleep=sleep,
    )
    holder.append(supervisor)
    await supervisor.run()

    assert sleep.intervals == [5.0, 10.0, 20.0, 40.0, 60.0, 60.0], (
        "backoff must grow and then cap; never a busy loop"
    )
    assert supervisor.recoveries == 0


@pytest.mark.asyncio
async def test_supervisor_notices_a_midlife_fail_open() -> None:
    holder: list[CredentialSupervisor] = []
    sleep = _DriverSleep(holder, limit=4)
    degraded = {"value": False}
    recovered: list[tuple[str, str]] = []

    async def _on_recovered(api_key_: str, private_key_pem: str) -> None:
        recovered.append((api_key_, private_key_pem))
        degraded["value"] = False  # the rebuild restores the stream in the real daemon

    calls = {"n": 0}

    async def _watcher(seconds: float) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            degraded["value"] = True  # the stream fails open mid-life
        await sleep(seconds)

    supervisor = CredentialSupervisor(
        is_degraded=lambda: degraded["value"],
        resolve=AsyncMock(return_value=("key-id", "pem-material")),
        on_recovered=_on_recovered,
        sleep=_watcher,
        watch_interval=1.0,
        probe_interval=5.0,
    )
    holder.append(supervisor)
    await supervisor.run()

    assert supervisor.recoveries == 1, "a mid-life fail-open must be healed too"
    assert recovered == [("key-id", "pem-material")]


@pytest.mark.asyncio
async def test_supervisor_never_logs_credential_material(caplog: pytest.LogCaptureFixture) -> None:
    holder: list[CredentialSupervisor] = []
    sleep = _DriverSleep(holder, limit=2)
    secret = "SUPER-SECRET-KEY-ID"
    pem = "SUPER-SECRET-PEM-MATERIAL"

    supervisor = CredentialSupervisor(
        is_degraded=lambda: True,
        resolve=AsyncMock(return_value=(secret, pem)),
        on_recovered=AsyncMock(),
        sleep=sleep,
    )
    holder.append(supervisor)
    with caplog.at_level("DEBUG"):
        await supervisor.run()

    assert secret not in caplog.text, "credential material must never reach the logs"
    assert pem not in caplog.text


@pytest.mark.asyncio
async def test_recovery_failure_keeps_the_supervisor_probing() -> None:
    """A rebuild that raises must not kill the watcher; it retries on the next probe."""
    holder: list[CredentialSupervisor] = []
    sleep = _DriverSleep(holder, limit=3)
    degraded = {"value": True}
    attempts: list[tuple[str, str]] = []

    async def _on_recovered(api_key_: str, private_key_pem: str) -> None:
        attempts.append((api_key_, private_key_pem))
        if len(attempts) == 1:
            raise RuntimeError("rebuild blew up")
        degraded["value"] = False  # the retry rebuilds and restores the stream

    supervisor = CredentialSupervisor(
        is_degraded=lambda: degraded["value"],
        resolve=AsyncMock(return_value=("key-id", "pem-material")),
        on_recovered=_on_recovered,
        probe_interval=5.0,
        sleep=sleep,
    )
    holder.append(supervisor)
    await supervisor.run()

    assert len(attempts) == 2, "the first rebuild failed, the second succeeded"
    assert supervisor.recoveries == 1


@pytest.mark.asyncio
async def test_settlement_monitor_rebinds_to_a_rebuilt_client() -> None:
    stale = MagicMock()
    fresh = MagicMock()

    monitor = SettlementMonitor(stale)

    assert monitor.client is stale
    monitor.set_client(fresh)
    assert monitor.client is fresh, "the monitor must use the rebuilt client after recovery"


@pytest.mark.asyncio
async def test_run_daemon_wires_and_stops_the_credential_supervisor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The supervisor must be started with the daemon and stopped on shutdown."""
    started: list[Any] = []

    class _SpySupervisor:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
            self.stopped = False
            self.run = AsyncMock()
            started.append(self)

        def stop(self) -> None:
            self.stopped = True

    fake_components: dict[str, Any] = {
        "pool": MagicMock(),
        "chroma": MagicMock(),
        "access": MagicMock(),
        "cache": MagicMock(start_persist_task=AsyncMock(), stop_persist_task=AsyncMock()),
        "client": MagicMock(close=AsyncMock()),
        "ws": MagicMock(start=AsyncMock(), stop=AsyncMock(), fail_open_fired=False),
        "data": MagicMock(start=AsyncMock(), stop=AsyncMock()),
        "settlement": MagicMock(),
        "mcp_app": MagicMock(),
        "app": MagicMock(),
        "credentials_present": False,
    }

    monkeypatch.setattr(daemon_mod, "CredentialSupervisor", _SpySupervisor)
    monkeypatch.setattr(daemon_mod, "build_components", AsyncMock(return_value=fake_components))
    monkeypatch.setattr(daemon_mod, "start_scheduler", AsyncMock())
    monkeypatch.setattr(daemon_mod, "stop_scheduler", AsyncMock())
    monkeypatch.setattr(
        daemon_mod.uvicorn, "Server", MagicMock(return_value=MagicMock(serve=AsyncMock()))
    )

    captured: dict[int, Callable[..., None]] = {}
    loop = asyncio.get_running_loop()

    def _capture(sig: int, callback: Callable[..., None], *args: Any) -> None:
        captured[sig] = lambda: callback(*args)

    monkeypatch.setattr(loop, "add_signal_handler", _capture)

    task = asyncio.create_task(run_daemon(port=9878, host="127.0.0.1"))
    for _ in range(100):
        if started:
            break
        await asyncio.sleep(0.02)

    assert started, "run_daemon must construct the credential supervisor"
    assert started[0].kwargs["is_degraded"](), "missing credentials at build time is degraded"
    assert started[0].kwargs["resolve"] is not None

    captured[signal.SIGTERM]()
    await asyncio.wait_for(task, timeout=5)

    assert started[0].stopped, "shutdown must stop the supervisor before the components"


@pytest.mark.asyncio
async def test_build_components_reports_missing_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The supervisor's trigger is a build-time signal, not a re-read of the store."""
    secrets = MagicMock()
    secrets.get = MagicMock(return_value=None)

    monkeypatch.setattr(daemon_mod, "init_schema", lambda _p: None)
    monkeypatch.setattr(daemon_mod, "create_chroma_root", lambda _p: None)
    monkeypatch.setattr(daemon_mod, "SQLiteConnectionPool", MagicMock())
    monkeypatch.setattr(daemon_mod, "ChromaStore", MagicMock())
    monkeypatch.setattr(daemon_mod, "DatabaseAccess", MagicMock())
    monkeypatch.setattr(daemon_mod, "MarketCache", MagicMock())
    monkeypatch.setattr(daemon_mod, "KalshiClient", MagicMock())
    monkeypatch.setattr(daemon_mod, "KalshiWebSocketManager", MagicMock())
    monkeypatch.setattr(daemon_mod, "DataCollectionService", MagicMock())
    monkeypatch.setattr(daemon_mod, "SettlementMonitor", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(daemon_mod, "OpenMeteoProvider", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(daemon_mod, "NwsProvider", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(daemon_mod, "NewsProvider", MagicMock)
    monkeypatch.setattr(daemon_mod, "app", MagicMock())

    components = await build_components(secrets=secrets)

    assert components["credentials_present"] is False
    assert "settlement" in components
    assert snapshot()["websocket"] == "not_started"


@pytest.mark.asyncio
async def test_run_daemon_recovery_rebuilds_and_restarts_in_place(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Driving the daemon's real on_recovered must rebuild, rebind and retire in place."""
    started: list[Any] = []

    class _SpySupervisor:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
            self.stopped = False
            self.run = AsyncMock()
            started.append(self)

        def stop(self) -> None:
            self.stopped = True

    old_ws = MagicMock(start=AsyncMock(), stop=AsyncMock(), fail_open_fired=True)
    settlement = MagicMock()
    fake_components: dict[str, Any] = {
        "pool": MagicMock(),
        "chroma": MagicMock(),
        "access": MagicMock(),
        "cache": MagicMock(start_persist_task=AsyncMock(), stop_persist_task=AsyncMock()),
        "client": MagicMock(close=AsyncMock()),
        "ws": old_ws,
        "data": MagicMock(start=AsyncMock(), stop=AsyncMock()),
        "settlement": settlement,
        "mcp_app": MagicMock(),
        "app": MagicMock(),
        "credentials_present": False,
    }
    rebuilt_ws = MagicMock(start=AsyncMock(), stop=AsyncMock(), fail_open_fired=False)
    rebuilt_client = MagicMock(close=AsyncMock())

    monkeypatch.setattr(daemon_mod, "CredentialSupervisor", _SpySupervisor)
    monkeypatch.setattr(daemon_mod, "build_components", AsyncMock(return_value=fake_components))
    monkeypatch.setattr(daemon_mod, "start_scheduler", AsyncMock())
    monkeypatch.setattr(daemon_mod, "stop_scheduler", AsyncMock())
    monkeypatch.setattr(daemon_mod, "KalshiClient", MagicMock(return_value=rebuilt_client))
    monkeypatch.setattr(daemon_mod, "KalshiWebSocketManager", MagicMock(return_value=rebuilt_ws))
    monkeypatch.setattr(
        daemon_mod.uvicorn, "Server", MagicMock(return_value=MagicMock(serve=AsyncMock()))
    )

    captured: dict[int, Callable[..., None]] = {}
    loop = asyncio.get_running_loop()

    def _capture(sig: int, callback: Callable[..., None], *args: Any) -> None:
        captured[sig] = lambda: callback(*args)

    monkeypatch.setattr(loop, "add_signal_handler", _capture)

    task = asyncio.create_task(run_daemon(port=9879, host="127.0.0.1"))
    for _ in range(100):
        if started:
            break
        await asyncio.sleep(0.02)

    assert started, "run_daemon must construct the credential supervisor"
    degrade = started[0].kwargs["is_degraded"]
    assert degrade() is True, "a fail-open manager means the graph is degraded"

    await started[0].kwargs["on_recovered"]("key-id", "pem-material")

    old_ws.stop.assert_awaited()  # the stale fail-open manager must be retired
    rebuilt_ws.start.assert_awaited()  # the rebuilt manager must be started
    settlement.set_client.assert_called_once_with(rebuilt_client)
    assert fake_components["ws"] is rebuilt_ws
    assert fake_components["client"] is rebuilt_client
    assert degrade() is False, "the trigger must clear once the rebuild succeeded"

    captured[signal.SIGTERM]()
    await asyncio.wait_for(task, timeout=5)

    rebuilt_ws.stop.assert_awaited()  # shutdown stops the current manager, not the retired one
