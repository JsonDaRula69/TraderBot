"""Tests for profile-token rotation (DD-037 §4).

Covers the :class:`TokenRotationManager` (rotate_all / rotate_one /
get_staleness, 24-hour failure suspension, local-only rejection) and the
:class:`RotationScheduler` asyncio lifecycle. The Infisical backend is faked
with the recorded-call client from ``test_secrets_store``; the scheduler is
driven with a tiny interval so tests run in milliseconds, never wall-clock
hours.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from tests.test_secrets_store import FakeInfisicalClient, FakeLocalStore
from traderbot.mcp.resolver import _SUSPENDED_PROFILES
from traderbot.secrets.rotation import (
    DEFAULT_INTERVAL_HOURS,
    RotationScheduler,
    TokenRotationManager,
)
from traderbot.secrets.store import SecretsStore

CATEGORIES = ["weather"]
PERMISSIONS = ["market_edge"]


def _store(client: FakeInfisicalClient | None = None) -> SecretsStore:
    return SecretsStore(infisical_client=client or FakeInfisicalClient())


def _seed(store: SecretsStore, agent_id: str, token: str) -> None:
    store.store_profile_token(
        agent_id=agent_id,
        token=token,
        profile=f"{agent_id}-profile",
        categories=CATEGORIES,
        permissions=PERMISSIONS,
    )


def _manager(client: FakeInfisicalClient | None = None) -> TokenRotationManager:
    return TokenRotationManager(_store(client))


def test_rotate_all_replaces_tokens_and_old_tokens_fail_to_resolve() -> None:
    client = FakeInfisicalClient()
    store = _store(client)
    _seed(store, "weather", "old-weather")
    _seed(store, "sysadmin", "old-sys")
    manager = _manager(client)

    rotated = manager.rotate_all()

    assert set(rotated) == {"weather", "sysadmin"}
    assert rotated["weather"] != "old-weather"
    assert rotated["sysadmin"] != "old-sys"
    assert store.resolve_profile_token("old-weather") is None
    assert store.resolve_profile_token("old-sys") is None
    assert store.resolve_profile_token(rotated["weather"]) == ("weather-profile", "weather")
    assert store.resolve_profile_token(rotated["sysadmin"]) == ("sysadmin-profile", "sysadmin")


def test_rotate_all_uses_rotate_profile_token_composite() -> None:
    client = FakeInfisicalClient()
    store = _store(client)
    _seed(store, "weather", "old-weather")
    manager = _manager(client)
    client.secrets.calls.clear()

    _ = manager.rotate_all()

    update_calls = [c for c in client.secrets.calls if c[0] == "update"]
    assert len(update_calls) == 1
    assert update_calls[0][1]["current_secret_name"] == "weather_token"
    assert update_calls[0][1]["project_slug"] == "TraderBot Agent Tokens"
    assert update_calls[0][1]["environment_slug"] == "prod"


def test_rotate_one_returns_new_token() -> None:
    client = FakeInfisicalClient()
    store = _store(client)
    _seed(store, "weather", "old-weather")
    manager = _manager(client)

    new_token = manager.rotate_one("weather")

    assert new_token != "old-weather"
    entry = store.get_profile_token("weather")
    assert entry is not None
    assert entry["token"] == new_token


def test_rotate_one_unknown_agent_raises_key_error() -> None:
    manager = _manager()

    with pytest.raises(KeyError, match="No profile token stored"):
        _ = manager.rotate_one("nobody")


def test_rotate_all_isolates_per_agent_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeInfisicalClient()
    store = _store(client)
    _seed(store, "weather", "old-weather")
    _seed(store, "sysadmin", "old-sys")
    manager = TokenRotationManager(store)

    original = store.rotate_profile_token

    def _boom(agent_id: str, new_token: str) -> None:
        if agent_id == "weather":
            raise RuntimeError("infisical down")
        original(agent_id, new_token)

    monkeypatch.setattr(store, "rotate_profile_token", _boom)

    rotated = manager.rotate_all()

    assert "sysadmin" in rotated
    assert "weather" not in rotated


def test_24h_continuous_failure_suspends_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeInfisicalClient()
    store = _store(client)
    _seed(store, "weather", "old-weather")
    manager = TokenRotationManager(store)
    _SUSPENDED_PROFILES.discard("weather")

    def _boom(agent_id: str, new_token: str) -> None:
        raise RuntimeError("infisical down")

    monkeypatch.setattr(store, "rotate_profile_token", _boom)

    _ = manager.rotate_all()
    assert "weather" not in _SUSPENDED_PROFILES
    manager._failures["weather"] = time.time() - 25 * 3600.0
    _ = manager.rotate_all()

    assert "weather" in _SUSPENDED_PROFILES


def test_successful_rotation_clears_failure_tracking() -> None:
    client = FakeInfisicalClient()
    store = _store(client)
    _seed(store, "weather", "old-weather")
    manager = _manager(client)
    manager._failures["weather"] = time.time() - 25 * 3600.0
    _SUSPENDED_PROFILES.discard("weather")

    _ = manager.rotate_one("weather")

    assert "weather" not in manager._failures
    assert "weather" not in _SUSPENDED_PROFILES


def test_local_only_store_raises_not_implemented() -> None:
    manager = TokenRotationManager(SecretsStore(local_store=FakeLocalStore()))

    with pytest.raises(NotImplementedError, match="Infisical"):
        _ = manager.rotate_all()
    with pytest.raises(NotImplementedError, match="Infisical"):
        _ = manager.rotate_one("weather")


def test_get_staleness_returns_hours_since_rotation() -> None:
    client = FakeInfisicalClient()
    store = _store(client)
    _seed(store, "weather", "old-weather")
    manager = _manager(client)
    manager._rotated_at["weather"] = time.time() - 2 * 3600.0

    staleness = manager.get_staleness()

    assert staleness["weather"] == pytest.approx(2.0, abs=0.1)


def test_get_staleness_omits_never_rotated_agents() -> None:
    client = FakeInfisicalClient()
    store = _store(client)
    _seed(store, "weather", "old-weather")
    manager = _manager(client)

    assert manager.get_staleness() == {}


@pytest.mark.asyncio
async def test_scheduler_start_stop_rotates_on_interval() -> None:
    client = FakeInfisicalClient()
    store = _store(client)
    _seed(store, "weather", "old-weather")
    manager = _manager(client)
    scheduler = RotationScheduler(manager, interval_hours=0.00001)

    await scheduler.start()
    await asyncio.sleep(0.15)
    await scheduler.stop()

    entry = store.get_profile_token("weather")
    assert entry is not None
    assert entry["token"] != "old-weather"


@pytest.mark.asyncio
async def test_scheduler_start_is_idempotent() -> None:
    manager = _manager()
    scheduler = RotationScheduler(manager, interval_hours=0.0001)

    await scheduler.start()
    first = scheduler._task
    await scheduler.start()
    second = scheduler._task
    await scheduler.stop()

    assert first is second


@pytest.mark.asyncio
async def test_scheduler_stop_without_start_is_noop() -> None:
    manager = _manager()
    scheduler = RotationScheduler(manager)

    await scheduler.stop()


def test_default_interval_is_four_hours() -> None:
    assert DEFAULT_INTERVAL_HOURS == 4.0


def test_no_threading_timer_used() -> None:
    import traderbot.secrets.rotation as rotation

    assert "threading" not in rotation.__dict__
    assert "Timer" not in rotation.__dict__


def test_scheduler_uses_asyncio_lock() -> None:
    manager = _manager()
    scheduler = RotationScheduler(manager)

    assert isinstance(scheduler._lock, asyncio.Lock)
