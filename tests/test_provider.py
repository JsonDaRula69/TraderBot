"""Tests for traderbot.kalshi.provider — Protocol conformance, MockDataProvider, ProdDataProvider."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

import traderbot.kalshi.markets as markets_mod
from traderbot.kalshi.client import AuthenticationError
from traderbot.kalshi.models import Market
from traderbot.kalshi.provider import (
    MarketDataProvider,
    MarketSnapshot,
    MockDataProvider,
    OrderBookLevelSnapshot,
    OrderBookSnapshot,
    ProdAPIError,
    ProdDataProvider,
    SettlementResult,
)


def _ts(year: int = 2026, month: int = 6, day: int = 1) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


# --- Protocol conformance ---


class TestProtocolConformance:
    def test_mock_is_runtime_subclass(self) -> None:
        assert issubclass(MockDataProvider, MarketDataProvider)

    def test_prod_is_runtime_subclass(self) -> None:
        assert issubclass(ProdDataProvider, MarketDataProvider)


# --- MockDataProvider ---


class TestMockDataProvider:
    @pytest.fixture()
    def provider(self) -> MockDataProvider:
        market = MarketSnapshot(
            ticker="BTC-100K",
            status="open",
            open_interest_cents=500000,
            close_time=_ts(2026, 6, 1),
        )
        ob = OrderBookSnapshot(
            yes_bids=(
                OrderBookLevelSnapshot(price_cents=55, size=10),
                OrderBookLevelSnapshot(price_cents=50, size=20),
            ),
            no_bids=(
                OrderBookLevelSnapshot(price_cents=45, size=15),
            ),
            timestamp=_ts(2026, 5, 15),
        )
        settlement = SettlementResult(
            ticker="ETH-5K",
            outcome=True,
            settled_at=_ts(2026, 4, 1),
        )
        return MockDataProvider(
            markets={"BTC-100K": market},
            orderbooks={"BTC-100K": ob},
            settlements={"ETH-5K": settlement},
        )

    async def test_get_market_returns_configured_data(self, provider: MockDataProvider) -> None:
        result = await provider.get_market("BTC-100K")
        assert result.ticker == "BTC-100K"
        assert result.status == "open"
        assert result.open_interest_cents == 500000

    async def test_get_market_raises_on_missing(self, provider: MockDataProvider) -> None:
        with pytest.raises(ValueError, match="Market MISSING not found"):
            await provider.get_market("MISSING")

    async def test_get_orderbook_returns_configured_data(self, provider: MockDataProvider) -> None:
        result = await provider.get_orderbook("BTC-100K")
        assert len(result.yes_bids) == 2
        assert result.yes_bids[0].price_cents == 55
        assert result.yes_bids[0].size == 10
        assert len(result.no_bids) == 1
        assert result.no_bids[0].price_cents == 45

    async def test_get_orderbook_raises_on_missing(self, provider: MockDataProvider) -> None:
        with pytest.raises(ValueError, match="OrderBook MISSING not found"):
            await provider.get_orderbook("MISSING")

    async def test_get_settlement_returns_configured_data(self, provider: MockDataProvider) -> None:
        result = await provider.get_settlement("ETH-5K")
        assert result is not None
        assert result.ticker == "ETH-5K"
        assert result.outcome is True

    async def test_get_settlement_returns_none_on_missing(self, provider: MockDataProvider) -> None:
        result = await provider.get_settlement("NOPE")
        assert result is None

    async def test_default_empty_construction(self) -> None:
        empty = MockDataProvider()
        with pytest.raises(ValueError):
            await empty.get_market("ANY")


# --- Frozen dataclass immutability ---


class TestFrozenDataclasses:
    def test_market_snapshot_is_frozen(self) -> None:
        snap = MarketSnapshot(ticker="X", status="open", open_interest_cents=0, close_time=_ts())
        with pytest.raises(AttributeError):
            snap.ticker = "Y"  # type: ignore[misc]

    def test_orderbook_snapshot_is_frozen(self) -> None:
        ob = OrderBookSnapshot()
        with pytest.raises(AttributeError):
            ob.yes_bids = ()  # type: ignore[misc]

    def test_settlement_result_is_frozen(self) -> None:
        sr = SettlementResult(ticker="X", outcome=True, settled_at=_ts())
        with pytest.raises(AttributeError):
            sr.outcome = False  # type: ignore[misc]

    def test_orderbook_level_snapshot_is_frozen(self) -> None:
        level = OrderBookLevelSnapshot(price_cents=10, size=5)
        with pytest.raises(AttributeError):
            level.price_cents = 20  # type: ignore[misc]


# --- ProdDataProvider ---


def _make_mock_client() -> MagicMock:
    client = MagicMock()
    client.get = AsyncMock()
    return client


class TestProdDataProvider:
    @pytest.fixture()
    def mock_client(self) -> MagicMock:
        return _make_mock_client()

    @pytest.fixture()
    def provider(self, mock_client: MagicMock) -> ProdDataProvider:
        return ProdDataProvider(client=mock_client)

    async def test_protocol_conformance(self) -> None:
        assert issubclass(ProdDataProvider, MarketDataProvider)

    async def test_get_market_success(self, provider: ProdDataProvider, mock_client: MagicMock) -> None:
        market = Market(
            ticker="BTC-100K",
            question="Will BTC reach 100K?",
            outcome_prices=["0.55", "0.45"],
            volume=1000,
            open_interest=500000,
            close_time=datetime(2026, 6, 1, tzinfo=UTC),
            status="open",
            event_ticker="CRYPTO",
        )
        mock_client.get.return_value.status_code = 200
        mock_client.get.return_value.json.return_value = {"market": {}}
        mock_client.get.return_value.raise_for_status = MagicMock()

        original_get_market = markets_mod.MarketService.get_market

        async def fake_get_market(self_svc: object, ticker: str) -> Market:
            return market

        markets_mod.MarketService.get_market = fake_get_market
        try:
            result = await provider.get_market("BTC-100K")
            assert result.ticker == "BTC-100K"
            assert result.status == "open"
            assert result.open_interest_cents == 500000
            assert result.settlement_result is None
        finally:
            markets_mod.MarketService.get_market = original_get_market

    async def test_get_market_auth_failure(self, provider: ProdDataProvider, mock_client: MagicMock) -> None:
        original = markets_mod.MarketService.get_market

        async def raise_auth(self_svc: object, ticker: str) -> None:
            raise AuthenticationError("HTTP 401")

        markets_mod.MarketService.get_market = raise_auth
        try:
            with pytest.raises(ProdAPIError, match="authentication failed"):
                await provider.get_market("X")
        finally:
            markets_mod.MarketService.get_market = original

    async def test_get_settlement_unsettled(self, provider: ProdDataProvider, mock_client: MagicMock) -> None:
        market = Market(
            ticker="BTC-100K",
            question="Will BTC reach 100K?",
            outcome_prices=["0.55", "0.45"],
            volume=1000,
            open_interest=500000,
            close_time=datetime(2026, 6, 1, tzinfo=UTC),
            status="open",
            event_ticker="CRYPTO",
        )

        original = markets_mod.MarketService.get_market

        async def fake_get_market(self_svc: object, ticker: str) -> Market:
            return market

        markets_mod.MarketService.get_market = fake_get_market
        try:
            result = await provider.get_settlement("BTC-100K")
            assert result is None
        finally:
            markets_mod.MarketService.get_market = original

    async def test_get_settlement_success(self, provider: ProdDataProvider, mock_client: MagicMock) -> None:
        market = Market(
            ticker="ETH-5K",
            question="Will ETH reach 5K?",
            outcome_prices=["1.00", "0.00"],
            volume=2000,
            open_interest=800000,
            close_time=datetime(2026, 4, 1, tzinfo=UTC),
            status="settled",
            event_ticker="CRYPTO",
            settlement_result=True,
        )

        original = markets_mod.MarketService.get_market

        async def fake_get_market(self_svc: object, ticker: str) -> Market:
            return market

        markets_mod.MarketService.get_market = fake_get_market
        try:
            result = await provider.get_settlement("ETH-5K")
            assert result is not None
            assert result.ticker == "ETH-5K"
            assert result.outcome is True
            assert result.settled_at == datetime(2026, 4, 1, tzinfo=UTC)
        finally:
            markets_mod.MarketService.get_market = original


# --- ProdAPIError ---


class TestProdAPIError:
    def test_prod_api_error_is_exception(self) -> None:
        assert issubclass(ProdAPIError, Exception)
        err = ProdAPIError("timeout")
        assert str(err) == "timeout"
