from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path

from traderbot.kalshi.cache import MarketDataCache
from traderbot.kalshi.provider import (
    MarketSnapshot,
    OrderBookLevelSnapshot,
    OrderBookSnapshot,
)


def _market(ticker: str = "TEST") -> MarketSnapshot:
    return MarketSnapshot(
        ticker=ticker,
        status="open",
        open_interest_cents=5_000_00,
        close_time=datetime(2026, 12, 31, 23, 59, 0, tzinfo=UTC),
    )


def _orderbook(ticker: str = "TEST") -> OrderBookSnapshot:
    return OrderBookSnapshot(
        yes_bids=(OrderBookLevelSnapshot(price_cents=50, size=100),),
        no_bids=(OrderBookLevelSnapshot(price_cents=50, size=100),),
        timestamp=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
    )


def _make_cache(db_path: str | Path) -> MarketDataCache:
    cache = MarketDataCache.__new__(MarketDataCache)
    cache._profile = None
    cache._lock = asyncio.Lock()
    cache._market_cache = {}
    cache._orderbook_cache = {}
    cache._settlement_db_path = db_path
    return cache


class TestMarketCacheTTL:
    async def test_stored_market_is_hit_before_ttl(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path / "test_cache_ttl.db")
        snap = _market()
        await cache.set_market("TEST", snap)
        result = await cache.get_market("TEST")
        assert result is not None
        assert result.ticker == "TEST"

    async def test_stored_market_expires_after_ttl(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path / "test_cache_expire.db")
        snap = _market()
        now = time.monotonic()
        cache._market_cache["EXPIRED"] = (snap, now - 1)
        result = await cache.get_market("EXPIRED")
        assert result is None

    async def test_missing_market_returns_none(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path / "test_cache_miss.db")
        result = await cache.get_market("MISSING")
        assert result is None


class TestOrderbookCacheTTL:
    async def test_stored_orderbook_is_hit_before_ttl(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path / "test_ob_hit.db")
        ob = _orderbook()
        await cache.set_orderbook("TEST", ob)
        result = await cache.get_orderbook("TEST")
        assert result is not None

    async def test_expired_orderbook_returns_none(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path / "test_ob_expire.db")
        ob = _orderbook()
        now = time.monotonic()
        cache._orderbook_cache["EXPIRED"] = (ob, now - 1)
        result = await cache.get_orderbook("EXPIRED")
        assert result is None


class TestInvalidate:
    async def test_invalidate_removes_entries(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path / "test_invalidate.db")
        await cache.set_market("A", _market("A"))
        await cache.set_orderbook("A", _orderbook("A"))
        await cache.invalidate("A")
        assert await cache.get_market("A") is None
        assert await cache.get_orderbook("A") is None

    async def test_invalidate_all_clears_caches(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path / "test_invalidate_all.db")
        await cache.set_market("A", _market("A"))
        await cache.set_market("B", _market("B"))
        await cache.invalidate_all()
        assert await cache.get_market("A") is None
        assert await cache.get_market("B") is None


class TestBatchMethods:
    async def test_get_markets_batch_returns_cached(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path / "test_batch.db")
        await cache.set_market("A", _market("A"))
        await cache.set_market("B", _market("B"))
        result = await cache.get_markets_batch(["A", "B", "C"])
        assert "A" in result
        assert "B" in result
        assert "C" not in result

    async def test_get_orderbooks_batch(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path / "test_ob_batch.db")
        await cache.set_orderbook("X", _orderbook("X"))
        await cache.set_orderbook("Y", _orderbook("Y"))
        result = await cache.get_orderbooks_batch(["X", "Y", "Z"])
        assert "X" in result
        assert "Y" in result
        assert "Z" not in result


class TestSettlementPersistence:
    def test_set_and_get_settlement(self, tmp_path: Path) -> None:
        db_path = tmp_path / "settlement.db"
        cache = _make_cache(db_path)
        cache._init_settlement_table()

        settled_at = datetime(2025, 1, 2, 0, 0, 0, tzinfo=UTC)
        cache.set_settlement("TEST-MKT", outcome=True, settled_at=settled_at)

        result = cache.get_settlement("TEST-MKT")
        assert result is not None
        assert result.outcome is True
        assert result.ticker == "TEST-MKT"

    def test_settlement_persists_across_instances(self, tmp_path: Path) -> None:
        db_path = tmp_path / "settlement.db"

        cache1 = _make_cache(db_path)
        cache1._init_settlement_table()

        settled_at = datetime(2025, 1, 2, 0, 0, 0, tzinfo=UTC)
        cache1.set_settlement("TEST-MKT", outcome=True, settled_at=settled_at)

        cache2 = _make_cache(db_path)
        cache2._init_settlement_table()

        result = cache2.get_settlement("TEST-MKT")
        assert result is not None
        assert result.outcome is True

    def test_batch_settlement_operations(self, tmp_path: Path) -> None:
        db_path = tmp_path / "settlement_batch.db"
        cache = _make_cache(db_path)
        cache._init_settlement_table()

        settled_at = datetime(2025, 1, 2, 0, 0, 0, tzinfo=UTC)
        cache.set_settlements_batch({
            "A": (True, settled_at),
            "B": (False, settled_at),
        })

        batch = cache.get_settlements_batch(["A", "B", "C"])
        assert "A" in batch
        assert batch["A"].outcome is True
        assert "B" in batch
        assert batch["B"].outcome is False
        assert "C" not in batch

    def test_get_nonexistent_settlement_returns_none(self, tmp_path: Path) -> None:
        db_path = tmp_path / "settlement_none.db"
        cache = _make_cache(db_path)
        cache._init_settlement_table()

        result = cache.get_settlement("NONEXISTENT")
        assert result is None
