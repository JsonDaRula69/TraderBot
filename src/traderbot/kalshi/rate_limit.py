"""Token bucket rate limiter for Kalshi API requests."""

from __future__ import annotations

import asyncio
import time


class TokenBucketRateLimiter:
    """Token bucket rate limiter that allows burst requests up to capacity,
    then enforces a steady rate of tokens_per_second.

    Supports separate read/write buckets when configured with read/write rates.
    When only tokens_per_second is provided, both buckets share the same rate.
    """

    def __init__(
        self,
        tokens_per_second: float = 20.0,
        burst_capacity: int | None = None,
        read_rate: float | None = None,
        write_rate: float | None = None,
        read_burst: int | None = None,
        write_burst: int | None = None,
    ) -> None:
        if read_rate is not None and write_rate is not None:
            self._read_bucket = _Bucket(read_rate, read_burst or int(read_rate * 2))
            self._write_bucket = _Bucket(write_rate, write_burst or int(write_rate * 2))
            self._dual = True
        else:
            self._read_bucket = _Bucket(tokens_per_second, burst_capacity or int(tokens_per_second * 2))
            self._write_bucket = self._read_bucket
            self._dual = False

        self.tokens_per_second = tokens_per_second

    @property
    def read_rate(self) -> float:
        return self._read_bucket.rate

    @property
    def write_rate(self) -> float:
        return self._write_bucket.rate

    async def acquire_read(self) -> None:
        await self._read_bucket.acquire()

    async def acquire_write(self) -> None:
        await self._write_bucket.acquire()

    async def acquire(self) -> None:
        await self.acquire_read()

    def reconfigure(
        self,
        read_rate: float | None = None,
        write_rate: float | None = None,
        read_burst: int | None = None,
        write_burst: int | None = None,
    ) -> None:
        if read_rate is not None:
            self._read_bucket = _Bucket(read_rate, read_burst or int(read_rate * 2))
        if write_rate is not None:
            self._write_bucket = _Bucket(write_rate, write_burst or int(write_rate * 2))
        if read_rate is not None or write_rate is not None:
            self._dual = True


class _Bucket:
    def __init__(self, rate: float, burst: int) -> None:
        self.rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
            await asyncio.sleep(1.0 / self.rate)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._burst, self._tokens + elapsed * self.rate)
        self._last_refill = now
