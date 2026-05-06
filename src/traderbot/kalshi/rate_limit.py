"""Token bucket rate limiter for Kalshi API requests."""

from __future__ import annotations

import asyncio
import time


class TokenBucketRateLimiter:
    """Token bucket rate limiter that allows burst requests up to capacity,
    then enforces a steady rate of tokens_per_second.
    """

    def __init__(self, tokens_per_second: float, burst_capacity: int | None = None) -> None:
        self._rate = tokens_per_second
        self.tokens_per_second = tokens_per_second
        self._burst = burst_capacity or int(tokens_per_second * 2)
        self._tokens = float(self._burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a token is available."""
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
            await asyncio.sleep(1.0 / self._rate)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._last_refill = now
