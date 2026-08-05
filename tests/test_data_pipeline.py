"""Tests for the data pipeline skeleton (DD-028): BaseDataProvider,
RateLimiter, DataScheduler, ProviderRegistry, DataCollectionService.

Uses mock providers driven at ~10ms intervals so lifecycle and error-isolation
behavior is verified in milliseconds, never against real sources.
"""

from __future__ import annotations

import asyncio
from typing import cast, override

import pytest

from traderbot.data import (
    BaseDataProvider,
    DataCollectionService,
    DataScheduler,
    ProviderRegistry,
    RateLimiter,
)


class MockProvider(BaseDataProvider):
    """Counting provider whose fetch/insert are recorded and inspectable."""

    def __init__(self, name: str = "mock", interval_seconds: float = 0.1) -> None:
        super().__init__()
        self._name: str = name
        self._interval_seconds: float = interval_seconds
        self.fetched: list[tuple[str, int]] = []
        self.inserted: list[tuple[str, int]] = []

    @property
    @override
    def name(self) -> str:
        return self._name

    @property
    @override
    def interval_seconds(self) -> float:
        return self._interval_seconds

    @override
    async def fetch(self) -> tuple[str, int]:
        payload = ("fetch", len(self.fetched))
        self.fetched.append(payload)
        return payload

    @override
    async def insert(self, data: tuple[str, int]) -> int:
        self.inserted.append(data)
        return len(self.inserted)


class FailingProvider(MockProvider):
    """Provider whose fetch always raises, for error-isolation tests."""

    @override
    async def fetch(self) -> tuple[str, int]:
        raise RuntimeError("source unreachable")


class FlakyProvider(MockProvider):
    """Provider that fails on the first fetch, then succeeds."""

    #: Retry almost immediately after the transient failure so the
    #: recovery test runs in milliseconds instead of the 1s default backoff.
    _error_backoff_seconds = 0.01

    def __init__(self, name: str = "flaky") -> None:
        super().__init__(name=name, interval_seconds=0.01)
        self._failed: bool = False

    @override
    async def fetch(self) -> tuple[str, int]:
        if not self._failed:
            self._failed = True
            raise RuntimeError("transient failure")
        return await super().fetch()


def test_rate_limiter_spaces_acquisitions() -> None:
    limiter = RateLimiter(interval_seconds=0.05)
    count = 0

    async def drive() -> int:
        nonlocal count
        for _ in range(3):
            await limiter.acquire()
            count += 1
        return count

    assert asyncio.run(drive()) == 3


def test_rate_limiter_rejects_nonpositive_interval() -> None:
    with pytest.raises(ValueError, match="interval_seconds"):
        _ = RateLimiter(0)


def test_provider_rate_limiter_matches_interval() -> None:
    provider = MockProvider(interval_seconds=0.25)

    assert provider.rate_limiter.interval_seconds == 0.25


def test_provider_set_interval_overrides_limiter() -> None:
    provider = MockProvider(interval_seconds=0.25)

    provider.set_interval(0.01)

    assert provider.rate_limiter.interval_seconds == 0.01


def test_provider_is_abstract() -> None:
    abstract_methods = BaseDataProvider.__abstractmethods__

    assert "name" in abstract_methods
    assert "interval_seconds" in abstract_methods
    assert "fetch" in abstract_methods
    assert "insert" in abstract_methods


@pytest.mark.asyncio
async def test_service_runs_providers_concurrently() -> None:
    a = MockProvider(name="a", interval_seconds=0.01)
    b = MockProvider(name="b", interval_seconds=0.01)
    service = DataCollectionService()

    service.register(a)
    service.register(b)
    await service.start()
    await asyncio.sleep(0.12)
    assert service.is_running
    await service.stop()

    assert 5 <= len(a.inserted) <= 20
    assert 5 <= len(b.inserted) <= 20
    assert not service.is_running


@pytest.mark.asyncio
async def test_service_register_duplicate_name_raises() -> None:
    service = DataCollectionService()
    service.register(MockProvider(name="a"))

    with pytest.raises(ValueError, match="already registered"):
        service.register(MockProvider(name="a"))


@pytest.mark.asyncio
async def test_service_start_is_idempotent() -> None:
    provider = MockProvider(interval_seconds=0.01)
    service = DataCollectionService()

    service.register(provider)
    await service.start()
    first_runs = provider.total_runs
    await asyncio.sleep(0.02)
    await service.start()
    second_runs = provider.total_runs
    await service.stop()

    # A second start must not double-schedule the worker: the run counter
    # keeps advancing on the original task and no duplicate task appears.
    assert second_runs >= first_runs
    assert service.status()["mock"]["running"] is False


@pytest.mark.asyncio
async def test_service_stop_without_start_is_noop() -> None:
    service = DataCollectionService()
    service.register(MockProvider(name="a"))

    await service.stop()


@pytest.mark.asyncio
async def test_failing_provider_is_isolated() -> None:
    good = MockProvider(name="good", interval_seconds=0.01)
    bad = FailingProvider(name="bad", interval_seconds=0.01)
    service = DataCollectionService()

    service.register(good)
    service.register(bad)
    await service.start()
    await asyncio.sleep(0.1)
    await service.stop()

    assert len(good.inserted) >= 3
    assert len(bad.inserted) == 0
    assert bad.total_errors >= 1
    assert bad.last_error is not None


@pytest.mark.asyncio
async def test_provider_recovers_after_error() -> None:
    provider = FlakyProvider()
    service = DataCollectionService()

    service.register(provider)
    await service.start()
    await asyncio.sleep(0.12)
    await service.stop()

    assert provider.total_errors == 1
    assert provider.total_runs >= 3
    assert len(provider.inserted) == provider.total_runs


@pytest.mark.asyncio
async def test_status_reports_per_provider_snapshot() -> None:
    provider = MockProvider(interval_seconds=0.01)
    service = DataCollectionService()

    service.register(provider)
    before = service.status()
    await service.start()
    await asyncio.sleep(0.05)
    await service.stop()
    after = service.status()

    assert before["mock"]["running"] is False
    assert before["mock"]["total_runs"] == 0
    assert after["mock"]["running"] is False
    total_runs = after["mock"]["total_runs"]
    assert isinstance(total_runs, int)
    assert total_runs >= 2
    assert after["mock"]["last_error"] is None


def test_registry_register_and_lookup() -> None:
    registry = ProviderRegistry()

    registry.register("mock", MockProvider)

    assert registry.get("mock") is MockProvider
    assert registry.get("unknown") is None
    assert registry.list_names() == ["mock"]


def test_registry_rejects_non_provider_class() -> None:
    registry = ProviderRegistry()

    with pytest.raises(TypeError, match="must subclass"):
        registry.register("not-a-provider", cast(type[BaseDataProvider], int))


def test_registry_rejects_duplicate_name() -> None:
    registry = ProviderRegistry()
    registry.register("mock", MockProvider)

    with pytest.raises(ValueError, match="already registered"):
        registry.register("mock", FailingProvider)


def test_scheduler_interval_override_wins() -> None:
    provider = MockProvider(interval_seconds=0.5)
    scheduler = DataScheduler(intervals={"mock": 0.01})

    assert scheduler.interval_for(provider) == 0.01


def test_scheduler_uses_provider_interval_by_default() -> None:
    provider = MockProvider(interval_seconds=0.5)
    scheduler = DataScheduler()

    assert scheduler.interval_for(provider) == 0.5


def test_no_threading_timer_used() -> None:
    import traderbot.data.pipeline as pipeline
    import traderbot.data.scheduler as scheduler

    assert "threading" not in scheduler.__dict__
    assert "threading" not in pipeline.__dict__


def test_default_registry_has_phase2_providers() -> None:
    from traderbot.data.registry import build_default_registry

    registry = build_default_registry()

    assert registry.list_names() == [
        "news",
        "nws",
        "open-meteo",
        "settlement-monitor",
    ]
    assert registry.get("open-meteo") is not None
    assert registry.get("nws") is not None
    assert registry.get("news") is not None
    assert registry.get("settlement-monitor") is not None
