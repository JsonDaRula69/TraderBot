"""Abstract base class for data providers and the asyncio rate limiter.

:class:`BaseDataProvider` subclasses fetch data from a single external source
and persist it through :meth:`BaseDataProvider.insert`. The
:class:`~traderbot.data.scheduler.DataScheduler` runs each provider's
:meth:`BaseDataProvider.run` worker loop as its own asyncio task. Spacing
between iterations is enforced by :class:`RateLimiter`, which uses an
:class:`asyncio.Lock` — provider state is not thread-safe (constraint #248),
so ``threading.Timer`` is deliberately avoided.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Final

logger = logging.getLogger(__name__)

#: Default seconds to sleep after a failed iteration before retrying.
_ERROR_BACKOFF_SECONDS: Final = 1.0


class RateLimiter:
    """Asyncio rate limiter enforcing a minimum spacing between acquisitions.

    :meth:`acquire` blocks until at least ``interval_seconds`` have elapsed
    since the previous acquisition. The check-and-sleep runs under an
    :class:`asyncio.Lock`, so concurrent callers cannot interleave and no
    threading primitives are required.
    """

    def __init__(self, interval_seconds: float) -> None:
        if interval_seconds <= 0:
            raise ValueError(f"interval_seconds must be > 0, got {interval_seconds}")
        self._interval_seconds: float = interval_seconds
        self._lock: asyncio.Lock = asyncio.Lock()
        #: Loop time at which the next :meth:`acquire` may pass.
        self._next_slot: float = 0.0

    @property
    def interval_seconds(self) -> float:
        return self._interval_seconds

    def set_interval(self, interval_seconds: float) -> None:
        if interval_seconds <= 0:
            raise ValueError(f"interval_seconds must be > 0, got {interval_seconds}")
        self._interval_seconds = interval_seconds

    async def acquire(self) -> None:
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            if now < self._next_slot:
                await asyncio.sleep(self._next_slot - now)
            self._next_slot = loop.time() + self._interval_seconds


class BaseDataProvider(ABC):
    """ABC for scheduled data providers.

    Subclasses implement :attr:`name`, :attr:`interval_seconds`, :meth:`fetch`,
    and :meth:`insert`. :meth:`fetch` returns a payload (e.g. a Pydantic model
    or a JSON-serializable dict) that :meth:`run` passes to :meth:`insert`.
    :meth:`run` is the worker loop the scheduler drives: it rate-limits,
    fetches, inserts, and isolates per-iteration failures so one provider's
    errors never stop the others.
    """

    #: Seconds to sleep after a failed iteration before retrying; subclasses
    #: may shorten this (tests) or lengthen it per source.
    _error_backoff_seconds: ClassVar[float] = _ERROR_BACKOFF_SECONDS

    def __init__(self) -> None:
        #: Lazily built :class:`RateLimiter` (needs :attr:`interval_seconds`).
        self._rate_limiter: RateLimiter | None = None
        #: Loop time of the last successful iteration (None until first run).
        self._last_run_at: float | None = None
        #: ``Type: message`` of the last failed iteration, if any.
        self._last_error: str | None = None
        #: Total successful iterations.
        self._total_runs: int = 0
        #: Total failed iterations.
        self._total_errors: int = 0

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        logger.info("Data provider initialized: %s", cls.__name__)

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique logical name of this provider (registry key)."""

    @property
    @abstractmethod
    def interval_seconds(self) -> float:
        """Preferred minimum seconds between fetch cycles."""

    @property
    def rate_limiter(self) -> RateLimiter:
        if self._rate_limiter is None:
            self._rate_limiter = RateLimiter(self.interval_seconds)
        return self._rate_limiter

    def set_interval(self, interval_seconds: float) -> None:
        """Override the rate-limit interval (used by the scheduler)."""
        if self._rate_limiter is None:
            self._rate_limiter = RateLimiter(interval_seconds)
        else:
            self._rate_limiter.set_interval(interval_seconds)

    @abstractmethod
    async def fetch(self) -> Any:
        """Fetch the latest payload from the source.

        Returns:
            The raw payload, passed to :meth:`insert` by :meth:`run`.
        """

    @abstractmethod
    async def insert(self, data: Any) -> int:
        """Persist a fetched payload.

        Args:
            data: Payload returned by :meth:`fetch`.

        Returns:
            Row id or count from the persistence layer.
        """

    async def run(self) -> None:
        """Worker loop: rate-limited fetch + insert until cancelled.

        A raised exception in one iteration is logged and the loop sleeps
        ``_error_backoff_seconds`` before retrying, so a single failure
        neither kills this task nor the other providers sharing the scheduler.
        """
        while True:
            try:
                await self.rate_limiter.acquire()
                data = await self.fetch()
                _ = await self.insert(data)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._record_error(exc)
                logger.exception("Data provider %r iteration failed", self.name)
                await asyncio.sleep(self._error_backoff_seconds)
            else:
                self._record_success()

    @property
    def last_run_at(self) -> float | None:
        return self._last_run_at

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def total_runs(self) -> int:
        return self._total_runs

    @property
    def total_errors(self) -> int:
        return self._total_errors

    def _record_success(self) -> None:
        self._total_runs += 1
        self._last_run_at = asyncio.get_running_loop().time()

    def _record_error(self, exc: BaseException) -> None:
        self._total_errors += 1
        self._last_error = f"{type(exc).__name__}: {exc}"
