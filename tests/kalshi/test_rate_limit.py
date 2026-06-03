from __future__ import annotations

import asyncio
import time

import pytest

from traderbot.kalshi.rate_limit import TokenBucketRateLimiter


class TestTokenBucketRateLimiter:
    def test_default_burst_capacity(self) -> None:
        limiter = TokenBucketRateLimiter(tokens_per_second=10.0)
        assert limiter.tokens_per_second == 10.0
        assert limiter._burst == 20  # tokens_per_second * 2

    def test_custom_burst_capacity(self) -> None:
        limiter = TokenBucketRateLimiter(tokens_per_second=10.0, burst_capacity=5)
        assert limiter._burst == 5

    def test_negative_rate_defaults_to_20(self) -> None:
        limiter = TokenBucketRateLimiter(tokens_per_second=-5)
        assert limiter.tokens_per_second == 20.0
        assert limiter._rate == 20.0

    def test_zero_rate_defaults_to_20(self) -> None:
        limiter = TokenBucketRateLimiter(tokens_per_second=0)
        assert limiter.tokens_per_second == 20.0

    @pytest.mark.asyncio
    async def test_acquire_returns_immediately_with_tokens(self) -> None:
        limiter = TokenBucketRateLimiter(tokens_per_second=100.0)
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.5

    @pytest.mark.asyncio
    async def test_multiple_acquires(self) -> None:
        limiter = TokenBucketRateLimiter(tokens_per_second=100.0, burst_capacity=50)
        for _ in range(10):
            await limiter.acquire()

    @pytest.mark.asyncio
    async def test_bucket_refills(self) -> None:
        limiter = TokenBucketRateLimiter(tokens_per_second=100.0, burst_capacity=3)
        for _ in range(3):
            await limiter.acquire()
        # Bucket should be empty now
        assert limiter._tokens < 1.0
        # After a small delay, some tokens should have refilled
        await asyncio.sleep(0.2)
        assert limiter._tokens > 0.0
