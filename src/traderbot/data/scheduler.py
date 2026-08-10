"""DataScheduler — per-source asyncio task scheduling (DD-028).

:class:`DataScheduler` owns the lifecycle of one asyncio task per provider,
running :meth:`BaseDataProvider.run`, which self-rate-limits via
:class:`~traderbot.data.base_provider.RateLimiter`. ``threading.Timer`` is
deliberately avoided — provider state is not thread-safe (constraint #248).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Iterable, Mapping

from traderbot.data.base_provider import BaseDataProvider

logger = logging.getLogger(__name__)


class DataScheduler:
    """Schedules one asyncio task per registered provider.

    Args:
        intervals: Optional per-source interval overrides keyed by provider
            name, applied before each provider task starts. Providers without
            an entry keep their own :attr:`BaseDataProvider.interval_seconds`.
    """

    def __init__(self, intervals: Mapping[str, float] | None = None) -> None:
        self._intervals: dict[str, float] = dict(intervals or {})
        #: Provider name -> running worker task.
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def interval_for(self, provider: BaseDataProvider) -> float:
        """Return the effective interval for ``provider`` (override wins)."""
        return self._intervals.get(provider.name, provider.interval_seconds)

    async def start(self, provider: BaseDataProvider) -> None:
        """Create the provider's worker task (idempotent per provider)."""
        name = provider.name
        existing = self._tasks.get(name)
        if existing is not None and not existing.done():
            return
        provider.set_interval(self.interval_for(provider))
        task = asyncio.create_task(provider.run(), name=f"data:{name}")
        self._tasks[name] = task
        logger.info("Scheduled data provider %r every %.3fs", name, provider.interval_seconds)

    async def start_all(self, providers: Iterable[BaseDataProvider]) -> None:
        """Create worker tasks for every provider in ``providers``."""
        for provider in providers:
            await self.start(provider)

    async def stop(self, provider_name: str) -> None:
        """Cancel one provider's task and await its completion (no-op if absent)."""
        task = self._tasks.pop(provider_name, None)
        if task is None:
            return
        if task.done():
            if not task.cancelled():
                exc = task.exception()
                if exc is not None:
                    logger.warning(
                        "Provider %r task finished with error", provider_name, exc_info=exc
                    )
            return
        _ = task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        logger.info("Stopped data provider %r", provider_name)

    async def stop_all(self) -> None:
        """Cancel every running provider task (no-op if nothing is running)."""
        for name in list(self._tasks):
            await self.stop(name)

    def is_running(self, provider_name: str) -> bool:
        """Return True if ``provider_name`` has a live worker task."""
        task = self._tasks.get(provider_name)
        return task is not None and not task.done()
