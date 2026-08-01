from __future__ import annotations

from datetime import UTC, datetime

import pytest

from traderbot.kalshi.cache import (
    MARKET_TTL,
    ORDERBOOK_TTL,
    MarketDataCache,
    _resolve_settlement_db_path,
)
from traderbot.kalshi.provider import MarketSnapshot, OrderBookLevelSnapshot, OrderBookSnapshot


@pytest.fixture
def snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        ticker="TEST-MKT1",
        status="open",
        open_interest_cents=10_000_00,
        close_time=datetime(2026, 12, 31, 23, 59, 0, tzinfo=UTC),
    )


@pytest.fixture
def orderbook() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        yes_bids=(
            OrderBookLevelSnapshot(price_cents=50, size=200),
            OrderBookLevelSnapshot(price_cents=49, size=300),
        ),
        no_bids=(
            OrderBookLevelSnapshot(price_cents=50, size=200),
            OrderBookLevelSnapshot(price_cents=51, size=150),
        ),
        timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
    )


class TestConstants:
    def test_orderbook_ttl(self) -> None:
        assert ORDERBOOK_TTL == 30.0

    def test_market_ttl(self) -> None:
        assert MARKET_TTL == 60.0


class TestResolveSettlementDbPath:
    def test_default_path(self) -> None:
        path = _resolve_settlement_db_path(None)
        assert path.name == "settlement_cache.db"

    def test_with_profile(self) -> None:
        from traderbot.profiles.models import TradingProfile

        profile = TradingProfile(
            name="test",
            mode="paper",
            description="test profile",
            risk_multiplier=0.5,
            max_position_per_market_pct=10.0,
            max_daily_loss_pct=5.0,
            max_drawdown_pct=20.0,
            max_open_positions=5,
            min_liquidity_threshold=1000,
            min_edge_pct=1.0,
        )
        path = _resolve_settlement_db_path(profile)
        assert path.name == "settlement_cache.db"
        assert "test" in str(path)


class TestMarketDataCache:
    def test_init_creates_dir(self) -> None:
        cache = MarketDataCache()
        assert cache._settlement_db_path.parent.exists()

    @pytest.mark.asyncio
    async def test_get_market_miss(self) -> None:
        cache = MarketDataCache()
        result = await cache.get_market("NONEXISTENT")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get_market(self, snapshot: MarketSnapshot) -> None:
        cache = MarketDataCache()
        await cache.set_market("TEST-MKT1", snapshot)
        result = await cache.get_market("TEST-MKT1")
        assert result is not None
        assert result.ticker == "TEST-MKT1"
        assert result.status == "open"

    @pytest.mark.asyncio
    async def test_get_orderbook_miss(self) -> None:
        cache = MarketDataCache()
        result = await cache.get_orderbook("NONEXISTENT")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get_orderbook(self, orderbook: OrderBookSnapshot) -> None:
        cache = MarketDataCache()
        await cache.set_orderbook("TEST-MKT1", orderbook)
        result = await cache.get_orderbook("TEST-MKT1")
        assert result is not None
        assert len(result.yes_bids) == 2
