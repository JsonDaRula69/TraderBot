"""Tests for simulation/data_loader.py — DataLoader with SQLite caching and quality checks."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from traderbot.kalshi.models import Market, MarketListResponse, Trade, TradeListResponse
from traderbot.simulation.data_loader import (
    DataLoader,
    DataQualityReport,
    QualityFlag,
    init_cache_tables,
)

if TYPE_CHECKING:
    from pathlib import Path


# --- Fixtures ---

def _make_market(
    ticker: str = "KX-TEST",
    question: str = "Test market?",
    status: str = "settled",
    volume: int = 5000,
    open_interest: int = 800,
    settlement_result: bool | None = True,
    close_time: datetime | None = None,
) -> Market:
    return Market(
        ticker=ticker,
        question=question,
        outcome_prices=["0.65", "0.35"],
        volume=volume,
        open_interest=open_interest,
        close_time=close_time or datetime(2026, 3, 31, 23, 59, 59, tzinfo=UTC),
        status=status,
        event_ticker="KX-EVENT",
        category="test",
        settlement_result=settlement_result,
    )


def _make_trade(
    ticker: str = "KX-TEST",
    price: int = 65,
    quantity: int = 10,
    side: str = "yes",
    timestamp: datetime | None = None,
) -> Trade:
    return Trade(
        ticker=ticker,
        price=price,
        quantity=quantity,
        side=side,
        timestamp=timestamp or datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
    )


@pytest.fixture
def db_conn(tmp_path: Path) -> sqlite3.Connection:
    """In-memory SQLite connection with cache tables initialized."""
    db_file = tmp_path / "cache.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    init_cache_tables(conn)
    yield conn
    conn.close()


@pytest.fixture
def mock_history() -> AsyncMock:
    """Mock HistoryService with default settled markets and trades responses."""
    history = AsyncMock()
    history.get_settled_markets = AsyncMock()
    history.get_historical_trades = AsyncMock()
    history.get_market_series = AsyncMock()
    return history


@pytest.fixture
def loader(db_conn: sqlite3.Connection, mock_history: AsyncMock) -> DataLoader:
    """DataLoader with in-memory SQLite and mock HistoryService."""
    return DataLoader(conn=db_conn, history=mock_history)


# --- init_cache_tables tests ---

class TestInitCacheTables:
    def test_creates_cached_markets_table(self, db_conn: sqlite3.Connection) -> None:
        rows = db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cached_markets'"
        ).fetchall()
        assert len(rows) == 1

    def test_creates_cached_trades_table(self, db_conn: sqlite3.Connection) -> None:
        rows = db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cached_trades'"
        ).fetchall()
        assert len(rows) == 1

    def test_idempotent_creation(self, db_conn: sqlite3.Connection) -> None:
        init_cache_tables(db_conn)
        init_cache_tables(db_conn)
        rows = db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cached_markets'"
        ).fetchall()
        assert len(rows) == 1


# --- get_markets tests ---

class TestGetMarkets:
    async def test_fetches_from_api_and_caches(self, loader: DataLoader, mock_history: AsyncMock) -> None:
        market = _make_market(ticker="KX-A")
        mock_history.get_settled_markets.return_value = MarketListResponse(
            markets=[market], cursor=None
        )

        result = await loader.get_markets(
            start=date(2026, 1, 1), end=date(2026, 3, 31)
        )

        assert len(result) == 1
        assert result[0].ticker == "KX-A"
        mock_history.get_settled_markets.assert_called()

    async def test_uses_cache_on_second_call(
        self, loader: DataLoader, mock_history: AsyncMock, db_conn: sqlite3.Connection
    ) -> None:
        market = _make_market(ticker="KX-B")
        mock_history.get_settled_markets.return_value = MarketListResponse(
            markets=[market], cursor=None
        )

        result1 = await loader.get_markets(start=date(2026, 1, 1), end=date(2026, 3, 31))
        result2 = await loader.get_markets(start=date(2026, 1, 1), end=date(2026, 3, 31))

        assert len(result1) == 1
        assert len(result2) == 1
        assert result2[0].ticker == "KX-B"
        assert mock_history.get_settled_markets.call_count == 1

    async def test_paginates_markets(self, loader: DataLoader, mock_history: AsyncMock) -> None:
        m1 = _make_market(ticker="KX-1")
        m2 = _make_market(ticker="KX-2")
        mock_history.get_settled_markets.side_effect = [
            MarketListResponse(markets=[m1], cursor="page2"),
            MarketListResponse(markets=[m2], cursor=None),
        ]

        result = await loader.get_markets(start=date(2026, 1, 1), end=date(2026, 3, 31))

        assert len(result) == 2
        assert mock_history.get_settled_markets.call_count == 2

    async def test_returns_empty_when_no_markets(self, loader: DataLoader, mock_history: AsyncMock) -> None:
        mock_history.get_settled_markets.return_value = MarketListResponse(
            markets=[], cursor=None
        )

        result = await loader.get_markets(start=date(2026, 1, 1), end=date(2026, 3, 31))

        assert result == []


# --- get_trades tests ---

class TestGetTrades:
    async def test_fetches_trades_from_api_and_caches(
        self, loader: DataLoader, mock_history: AsyncMock
    ) -> None:
        trade = _make_trade(ticker="KX-TEST")
        mock_history.get_historical_trades.return_value = TradeListResponse(
            trades=[trade], cursor=None
        )

        result = await loader.get_trades("KX-TEST")

        assert len(result) == 1
        assert result[0].ticker == "KX-TEST"
        mock_history.get_historical_trades.assert_called_once_with("KX-TEST", cursor=None)

    async def test_uses_cache_on_second_call(
        self, loader: DataLoader, mock_history: AsyncMock
    ) -> None:
        trade = _make_trade(ticker="KX-TEST")
        mock_history.get_historical_trades.return_value = TradeListResponse(
            trades=[trade], cursor=None
        )

        result1 = await loader.get_trades("KX-TEST")
        result2 = await loader.get_trades("KX-TEST")

        assert len(result1) == 1
        assert len(result2) == 1
        mock_history.get_historical_trades.assert_called_once()

    async def test_paginates_trades(self, loader: DataLoader, mock_history: AsyncMock) -> None:
        t1 = _make_trade(ticker="KX-TEST")
        t2 = _make_trade(ticker="KX-TEST", price=70)
        mock_history.get_historical_trades.side_effect = [
            TradeListResponse(trades=[t1], cursor="page2"),
            TradeListResponse(trades=[t2], cursor=None),
        ]

        result = await loader.get_trades("KX-TEST")

        assert len(result) == 2
        assert mock_history.get_historical_trades.call_count == 2

    async def test_returns_empty_when_no_trades(self, loader: DataLoader, mock_history: AsyncMock) -> None:
        mock_history.get_historical_trades.return_value = TradeListResponse(
            trades=[], cursor=None
        )

        result = await loader.get_trades("KX-NONE")

        assert result == []


# --- get_outcomes tests ---

class TestGetOutcomes:
    async def test_fetches_outcomes_for_tickers(
        self, loader: DataLoader, mock_history: AsyncMock
    ) -> None:
        market_yes = _make_market(ticker="KX-A", settlement_result=True)
        market_no = _make_market(ticker="KX-B", settlement_result=False)
        mock_history.get_market_series.side_effect = [market_yes, market_no]

        result = await loader.get_outcomes(["KX-A", "KX-B"])

        assert result == {"KX-A": True, "KX-B": False}

    async def test_handles_none_settlement_result(
        self, loader: DataLoader, mock_history: AsyncMock
    ) -> None:
        market_unsettled = _make_market(ticker="KX-C", settlement_result=None, status="open")
        mock_history.get_market_series.return_value = market_unsettled

        result = await loader.get_outcomes(["KX-C"])

        assert result == {"KX-C": False}

    async def test_returns_empty_for_empty_tickers(
        self, loader: DataLoader, mock_history: AsyncMock
    ) -> None:
        result = await loader.get_outcomes([])
        assert result == {}
        mock_history.get_market_series.assert_not_called()


# --- TTL freshness tests ---

class TestTTLFreshness:
    async def test_expired_market_cache_refetches(
        self, loader: DataLoader, mock_history: AsyncMock, db_conn: sqlite3.Connection
    ) -> None:
        market = _make_market(ticker="KX-TTL")
        mock_history.get_settled_markets.return_value = MarketListResponse(
            markets=[market], cursor=None
        )

        await loader.get_markets(start=date(2026, 1, 1), end=date(2026, 3, 31))

        stale_time = datetime.now(UTC) - timedelta(hours=2)
        db_conn.execute(
            "UPDATE cached_markets SET cached_at = ?",
            (stale_time.isoformat(),),
        )
        db_conn.commit()

        result = await loader.get_markets(start=date(2026, 1, 1), end=date(2026, 3, 31))
        assert len(result) == 1
        assert mock_history.get_settled_markets.call_count == 2

    async def test_expired_trade_cache_refetches(
        self, loader: DataLoader, mock_history: AsyncMock, db_conn: sqlite3.Connection
    ) -> None:
        trade = _make_trade(ticker="KX-TTL")
        mock_history.get_historical_trades.return_value = TradeListResponse(
            trades=[trade], cursor=None
        )

        await loader.get_trades("KX-TTL")

        stale_time = datetime.now(UTC) - timedelta(minutes=10)
        db_conn.execute(
            "UPDATE cached_trades SET cached_at = ?",
            (stale_time.isoformat(),),
        )
        db_conn.commit()

        result = await loader.get_trades("KX-TTL")
        assert len(result) == 1
        assert mock_history.get_historical_trades.call_count == 2

    async def test_custom_ttl_respected(self, db_conn: sqlite3.Connection, mock_history: AsyncMock) -> None:
        custom_loader = DataLoader(
            conn=db_conn, history=mock_history, market_ttl_hours=48, trade_ttl_minutes=120
        )
        market = _make_market(ticker="KX-CUSTOM")
        mock_history.get_settled_markets.return_value = MarketListResponse(
            markets=[market], cursor=None
        )

        result = await custom_loader.get_markets(start=date(2026, 1, 1), end=date(2026, 3, 31))
        assert len(result) == 1

        stale_25h = datetime.now(UTC) - timedelta(hours=25)
        db_conn.execute(
            "UPDATE cached_markets SET cached_at = ?",
            (stale_25h.isoformat(),),
        )
        db_conn.commit()

        await custom_loader.get_markets(start=date(2026, 1, 1), end=date(2026, 3, 31))
        assert mock_history.get_settled_markets.call_count == 1


# --- Data quality tests ---

class TestDataQuality:
    async def test_flags_low_liquidity(
        self, loader: DataLoader, mock_history: AsyncMock
    ) -> None:
        low_volume_market = _make_market(ticker="KX-LOW", volume=50, open_interest=10)
        mock_history.get_settled_markets.return_value = MarketListResponse(
            markets=[low_volume_market], cursor=None
        )

        result = await loader.get_markets(start=date(2026, 1, 1), end=date(2026, 3, 31))
        report = loader.quality_report(result)

        assert len(report.flags) >= 1
        assert any(f.flag_type == "low_liquidity" for f in report.flags)

    async def test_flags_incomplete_trades(
        self, loader: DataLoader, mock_history: AsyncMock
    ) -> None:
        market = _make_market(ticker="KX-INC", volume=5000)
        mock_history.get_settled_markets.return_value = MarketListResponse(
            markets=[market], cursor=None
        )
        mock_history.get_historical_trades.return_value = TradeListResponse(
            trades=[], cursor=None
        )

        markets = await loader.get_markets(start=date(2026, 1, 1), end=date(2026, 3, 31))
        trades = await loader.get_trades("KX-INC")
        report = loader.quality_report(markets, trades_by_ticker={"KX-INC": trades})

        assert any(f.flag_type == "no_trades" for f in report.flags)

    async def test_flags_settlement_inconsistency(
        self, loader: DataLoader, mock_history: AsyncMock
    ) -> None:
        market = _make_market(
            ticker="KX-SET",
            status="settled",
            settlement_result=True,
        )
        trade_no_hi = _make_trade(ticker="KX-SET", price=15, side="no")
        mock_history.get_settled_markets.return_value = MarketListResponse(
            markets=[market], cursor=None
        )
        mock_history.get_historical_trades.return_value = TradeListResponse(
            trades=[trade_no_hi], cursor=None
        )

        markets = await loader.get_markets(start=date(2026, 1, 1), end=date(2026, 3, 31))
        trades = await loader.get_trades("KX-SET")
        report = loader.quality_report(markets, trades_by_ticker={"KX-SET": trades})

        assert any(f.flag_type == "settlement_inconsistency" for f in report.flags)

    async def test_no_flags_for_clean_data(
        self, loader: DataLoader, mock_history: AsyncMock
    ) -> None:
        market = _make_market(ticker="KX-CLEAN", volume=5000, open_interest=800, settlement_result=True)
        trade = _make_trade(ticker="KX-CLEAN", price=60, side="yes")
        mock_history.get_settled_markets.return_value = MarketListResponse(
            markets=[market], cursor=None
        )
        mock_history.get_historical_trades.return_value = TradeListResponse(
            trades=[trade], cursor=None
        )

        markets = await loader.get_markets(start=date(2026, 1, 1), end=date(2026, 3, 31))
        trades = await loader.get_trades("KX-CLEAN")
        report = loader.quality_report(markets, trades_by_ticker={"KX-CLEAN": trades})

        assert len(report.flags) == 0

    async def test_quality_report_liquidity_threshold(
        self, loader: DataLoader, mock_history: AsyncMock
    ) -> None:
        market_at_threshold = _make_market(ticker="KX-THRESH", volume=99, open_interest=50)
        mock_history.get_settled_markets.return_value = MarketListResponse(
            markets=[market_at_threshold], cursor=None
        )

        result = await loader.get_markets(start=date(2026, 1, 1), end=date(2026, 3, 31))
        report = loader.quality_report(result)

        assert any(f.flag_type == "low_liquidity" and f.ticker == "KX-THRESH" for f in report.flags)


# --- DataQualityReport / QualityFlag model tests ---

class TestQualityModels:
    def test_quality_flag_creation(self) -> None:
        flag = QualityFlag(
            ticker="KX-TEST",
            flag_type="low_liquidity",
            message="Market has fewer than 100 trades",
        )
        assert flag.ticker == "KX-TEST"
        assert flag.flag_type == "low_liquidity"

    def test_data_quality_report_empty(self) -> None:
        report = DataQualityReport(total_markets=0, flags=[])
        assert report.total_markets == 0
        assert report.flags == []
        assert report.is_clean is True

    def test_data_quality_report_with_flags(self) -> None:
        flag = QualityFlag(
            ticker="KX-TEST",
            flag_type="low_liquidity",
            message="Low volume",
        )
        report = DataQualityReport(total_markets=1, flags=[flag])
        assert report.total_markets == 1
        assert len(report.flags) == 1
        assert report.is_clean is False

    def test_data_quality_report_strict_validation(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            QualityFlag(
                ticker="KX-TEST",
                flag_type="low_liquidity",
                message="Low volume",
                extra_field="disallowed",
            )
