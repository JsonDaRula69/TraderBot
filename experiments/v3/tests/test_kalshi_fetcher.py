"""Tests for kalshi_fetcher — fetching and persisting Kalshi market data."""

import json
import sqlite3
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from experiments.v3.data_sources.kalshi_fetcher import (
    extract_prices_at_timestep,
    fetch_market_details,
    fetch_orderbook_snapshot,
    fetch_settled_markets,
    fetch_trade_history,
    save_to_db,
)
from experiments.v3.db_schema import create_tables
from traderbot.kalshi.models import (
    Market,
    MarketListResponse,
    OrderBook,
    OrderBookLevel,
    Trade,
    TradeListResponse,
)


def _make_market(
    ticker: str = "KXHIGHNY-26MAY18-T84",
    event_ticker: str = "KXHIGHNY-26MAY18",
    series_ticker: str = "KXHIGHNY",
    settlement_result: bool | None = True,
) -> Market:
    """Build a minimal Market instance for testing."""
    return Market(
        ticker=ticker,
        question="Will NYC high exceed 84F?",
        outcome_prices=["85", "15"],
        volume=1000,
        open_interest=500,
        close_time=datetime(2026, 5, 18, tzinfo=UTC),
        status="settled",
        event_ticker=event_ticker,
        series_ticker=series_ticker,
        settlement_result=settlement_result,
    )


def _make_trade(ticker: str, price_cents: int, ts: datetime) -> Trade:
    return Trade(
        ticker=ticker,
        price=price_cents,
        quantity=10,
        side="yes",
        timestamp=ts,
    )


# ---------------------------------------------------------------------------
# Test 1: fetch_settled_markets filters KXHIGH correctly
# ---------------------------------------------------------------------------


class TestFetchSettledMarkets:
    @pytest.mark.asyncio
    async def test_filters_kxhigh_prefix(self):
        """Only markets with KXHIGH event_ticker prefix are returned."""
        history_svc = MagicMock()
        history_svc.get_settled_markets = AsyncMock(
            return_value=MarketListResponse(
                markets=[
                    _make_market(
                        ticker="KXHIGHNY-26MAY18-T84",
                        event_ticker="KXHIGHNY-26MAY18",
                    ),
                    _make_market(
                        ticker="OTHER-26MAY18-T50",
                        event_ticker="OTHER-26MAY18",
                        series_ticker="OTHER",
                    ),
                ],
                cursor=None,
            )
        )

        result = await fetch_settled_markets(history_svc, event_prefix="KXHIGH")

        assert len(result) == 1
        assert result[0]["ticker"] == "KXHIGHNY-26MAY18-T84"

    @pytest.mark.asyncio
    async def test_returns_all_three_strike_types(self):
        """Results include less, greater, and between strike types."""
        history_svc = MagicMock()
        history_svc.get_settled_markets = AsyncMock(
            return_value=MarketListResponse(
                markets=[
                    _make_market(
                        ticker="KXHIGHNY-26MAY18-T84",
                        event_ticker="KXHIGHNY-26MAY18",
                    ),
                    _make_market(
                        ticker="KXHIGHNY-26MAY18-B84.5",
                        event_ticker="KXHIGHNY-26MAY18",
                    ),
                    _make_market(
                        ticker="KXHIGHNY-26MAY18-L84",
                        event_ticker="KXHIGHNY-26MAY18",
                    ),
                ],
                cursor=None,
            )
        )

        result = await fetch_settled_markets(history_svc, event_prefix="KXHIGH")

        assert len(result) == 3
        tickers = {r["ticker"] for r in result}
        assert "KXHIGHNY-26MAY18-T84" in tickers
        assert "KXHIGHNY-26MAY18-B84.5" in tickers
        assert "KXHIGHNY-26MAY18-L84" in tickers

    @pytest.mark.asyncio
    async def test_empty_result_when_no_kxhigh(self):
        """Returns empty list if no markets match the prefix."""
        history_svc = MagicMock()
        history_svc.get_settled_markets = AsyncMock(
            return_value=MarketListResponse(markets=[], cursor=None)
        )

        result = await fetch_settled_markets(history_svc, event_prefix="KXHIGH")

        assert result == []

    @pytest.mark.asyncio
    async def test_dict_contains_required_keys(self):
        """Each dict has ticker, settlement, city, strike_type, threshold."""
        history_svc = MagicMock()
        history_svc.get_settled_markets = AsyncMock(
            return_value=MarketListResponse(
                markets=[_make_market()],
                cursor=None,
            )
        )

        result = await fetch_settled_markets(history_svc, event_prefix="KXHIGH")

        assert len(result) == 1
        entry = result[0]
        for key in ("ticker", "settlement", "city", "strike_type", "threshold"):
            assert key in entry, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# Test 2: extract_prices_at_timestep — last trade per window only
# ---------------------------------------------------------------------------


class TestExtractPricesAtTimestep:
    def test_returns_last_trade_per_window(self):
        """Each timestep window uses only the last trade before window close."""
        trades = [
            {"timestamp": "2026-05-15T10:00:00", "yes_price": 80.0, "no_price": 20.0, "count": 5},
            {"timestamp": "2026-05-15T14:00:00", "yes_price": 85.0, "no_price": 15.0, "count": 8},
            {"timestamp": "2026-05-16T10:00:00", "yes_price": 70.0, "no_price": 30.0, "count": 3},
            {"timestamp": "2026-05-16T15:00:00", "yes_price": 75.0, "no_price": 25.0, "count": 4},
            {"timestamp": "2026-05-17T09:00:00", "yes_price": 90.0, "no_price": 10.0, "count": 12},
        ]
        windows = [
            ("2026-05-15T00:00:00", "2026-05-15T23:59:59"),
            ("2026-05-16T00:00:00", "2026-05-16T23:59:59"),
            ("2026-05-17T00:00:00", "2026-05-17T23:59:59"),
        ]

        result = extract_prices_at_timestep(trades, windows)

        assert len(result) == 3
        # Window 1: last trade is 14:00 (85/15/8)
        assert result[0]["yes_price"] == 85.0
        assert result[0]["no_price"] == 15.0
        assert result[0]["trade_count"] == 8
        # Window 2: last trade is 15:00 (75/25/4)
        assert result[1]["yes_price"] == 75.0
        assert result[1]["no_price"] == 25.0
        assert result[1]["trade_count"] == 4
        # Window 3: only trade is 09:00 (90/10/12)
        assert result[2]["yes_price"] == 90.0
        assert result[2]["no_price"] == 10.0
        assert result[2]["trade_count"] == 12

    def test_no_trades_in_window_skipped(self):
        """Windows with zero trades produce no entry."""
        trades = [
            {"timestamp": "2026-05-15T10:00:00", "yes_price": 80.0, "no_price": 20.0, "count": 5},
        ]
        windows = [
            ("2026-05-15T00:00:00", "2026-05-15T23:59:59"),
            ("2026-05-16T00:00:00", "2026-05-16T23:59:59"),
        ]

        result = extract_prices_at_timestep(trades, windows)

        assert len(result) == 1
        assert result[0]["yes_price"] == 80.0


# ---------------------------------------------------------------------------
# Test 3: extract_prices_at_timestep — NEVER include post-settlement trades
# ---------------------------------------------------------------------------


class TestExtractPricesNoFuturePeeking:
    def test_post_settlement_trade_excluded(self):
        """A trade after the window close time is NEVER included."""
        trades = [
            {"timestamp": "2026-05-17T22:00:00", "yes_price": 90.0, "no_price": 10.0, "count": 5},
            # This trade is AFTER settlement (future peeking)
            {"timestamp": "2026-05-18T02:00:00", "yes_price": 100.0, "no_price": 0.0, "count": 99},
        ]
        windows = [
            ("2026-05-17T00:00:00", "2026-05-17T23:59:59"),
        ]

        result = extract_prices_at_timestep(trades, windows)

        assert len(result) == 1
        assert result[0]["yes_price"] == 90.0
        assert result[0]["trade_count"] == 5
        # The 100.0 post-settlement trade is excluded

    def test_trade_exactly_at_window_close_excluded(self):
        """A trade at exactly the window close timestamp is excluded (strict <)."""
        trades = [
            {"timestamp": "2026-05-17T23:59:59", "yes_price": 95.0, "no_price": 5.0, "count": 7},
        ]
        windows = [
            ("2026-05-17T00:00:00", "2026-05-17T23:59:59"),
        ]

        result = extract_prices_at_timestep(trades, windows)

        # Trade AT the boundary is excluded since we use strict <
        # But if the boundary IS the trade time, it's ambiguous. Let's verify
        # the trade at exactly window_end is excluded to prevent peeking.
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Test 4: fetch_orderbook_snapshot extracts correctly
# ---------------------------------------------------------------------------


class TestFetchOrderbookSnapshot:
    @pytest.mark.asyncio
    async def test_extracts_orderbook_fields(self):
        """Correct extraction of yes_bids_json, best_yes_bid, implied_prob."""
        ob = OrderBook(
            yes_bids=[
                OrderBookLevel(price=90, size=50),
                OrderBookLevel(price=85, size=100),
            ],
            no_bids=[
                OrderBookLevel(price=15, size=200),
                OrderBookLevel(price=20, size=150),
            ],
        )

        market_svc = MagicMock()
        market_svc.get_orderbook = AsyncMock(return_value=ob)

        result = await fetch_orderbook_snapshot(market_svc, "KXHIGHNY-26MAY18-T84")

        assert "yes_bids_json" in result
        assert "no_bids_json" in result
        assert result["best_yes_bid"] == pytest.approx(0.90)
        assert result["best_no_bid"] == pytest.approx(0.15)
        assert result["implied_prob"] == pytest.approx(0.90)

        # Verify JSON is valid
        yes_bids = json.loads(result["yes_bids_json"])
        assert len(yes_bids) == 2
        assert yes_bids[0]["price"] == 90

    @pytest.mark.asyncio
    async def test_empty_orderbook(self):
        """Handles empty orderbook gracefully."""
        ob = OrderBook(yes_bids=[], no_bids=[])

        market_svc = MagicMock()
        market_svc.get_orderbook = AsyncMock(return_value=ob)

        result = await fetch_orderbook_snapshot(market_svc, "KXHIGHNY-26MAY18-T84")

        assert result["best_yes_bid"] is None
        assert result["best_no_bid"] is None
        assert result["implied_prob"] is None


# ---------------------------------------------------------------------------
# Test 5: save_to_db writes to all 4 tables
# ---------------------------------------------------------------------------


class TestSaveToDb:
    def test_writes_to_all_four_tables(self):
        """save_to_db inserts into markets, market_prices, settlement_results, orderbook_snapshots."""
        conn = sqlite3.connect(":memory:")
        create_tables(conn)

        market = {
            "ticker": "KXHIGHNY-26MAY18-T84",
            "city": "New York",
            "strike_type": "greater",
            "floor_strike": None,
            "ceiling_strike": None,
            "threshold": 84.0,
            "resolution_date": "2026-05-18",
            "settlement_result": "yes",
            "actual_value": 88.0,
            "event_ticker": "KXHIGHNY-26MAY18",
            "series_ticker": "KXHIGHNY",
        }
        prices = [
            {"timestep": 1, "yes_price": 0.85, "no_price": 0.15, "trade_count": 8},
            {"timestep": 2, "yes_price": 0.90, "no_price": 0.10, "trade_count": 12},
        ]
        orderbook = {
            "yes_bids_json": '[{"price": 90, "size": 50}]',
            "no_bids_json": '[{"price": 15, "size": 200}]',
            "best_yes_bid": 0.90,
            "best_no_bid": 0.15,
            "implied_prob": 0.90,
        }

        save_to_db(conn, market, prices, orderbook)

        # Verify markets table
        rows = conn.execute("SELECT * FROM markets WHERE ticker = ?", ("KXHIGHNY-26MAY18-T84",)).fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "New York"
        assert rows[0][2] == "greater"

        # Verify market_prices table
        rows = conn.execute("SELECT * FROM market_prices WHERE ticker = ?", ("KXHIGHNY-26MAY18-T84",)).fetchall()
        assert len(rows) == 2
        assert rows[0][3] == 0.85  # yes_price

        # Verify settlement_results table
        rows = conn.execute("SELECT * FROM settlement_results WHERE ticker = ?", ("KXHIGHNY-26MAY18-T84",)).fetchall()
        assert len(rows) == 1
        assert rows[0][1] == 88.0  # actual_temp_f
        assert rows[0][2] == "yes"  # settlement_result

        # Verify orderbook_snapshots table
        rows = conn.execute("SELECT * FROM orderbook_snapshots WHERE ticker = ?", ("KXHIGHNY-26MAY18-T84",)).fetchall()
        assert len(rows) == 1
        assert rows[0][3] == '[{"price": 90, "size": 50}]'  # yes_bids_json

        conn.close()

    def test_idempotent_market_upsert(self):
        """Re-inserting the same market ticker does not crash (upsert)."""
        conn = sqlite3.connect(":memory:")
        create_tables(conn)

        market = {
            "ticker": "KXHIGHNY-26MAY18-T84",
            "city": "New York",
            "strike_type": "greater",
            "floor_strike": None,
            "ceiling_strike": None,
            "threshold": 84.0,
            "resolution_date": "2026-05-18",
            "settlement_result": "yes",
            "actual_value": 88.0,
            "event_ticker": "KXHIGHNY-26MAY18",
            "series_ticker": "KXHIGHNY",
        }

        save_to_db(conn, market, [], {})
        save_to_db(conn, market, [], {})

        rows = conn.execute("SELECT * FROM markets").fetchall()
        assert len(rows) == 1

        conn.close()


# ---------------------------------------------------------------------------
# fetch_trade_history
# ---------------------------------------------------------------------------


class TestFetchTradeHistory:
    @pytest.mark.asyncio
    async def test_returns_trade_dicts(self):
        """fetch_trade_history returns list of dicts with required keys."""
        history_svc = MagicMock()
        history_svc.get_historical_trades = AsyncMock(
            return_value=TradeListResponse(
                trades=[
                    _make_trade("KXHIGHNY-26MAY18-T84", 85, datetime(2026, 5, 15, 12, 0, tzinfo=UTC)),
                    _make_trade("KXHIGHNY-26MAY18-T84", 90, datetime(2026, 5, 16, 14, 0, tzinfo=UTC)),
                ],
                cursor=None,
            )
        )

        result = await fetch_trade_history(
            history_svc,
            "KXHIGHNY-26MAY18-T84",
            start_ts=1747267200,
            end_ts=1747440000,
        )

        assert len(result) == 2
        assert result[0]["yes_price"] == 0.85
        assert result[0]["no_price"] == 0.15
        assert result[1]["yes_price"] == 0.90


# ---------------------------------------------------------------------------
# fetch_market_details
# ---------------------------------------------------------------------------


class TestFetchMarketDetails:
    @pytest.mark.asyncio
    async def test_extracts_market_fields(self):
        """fetch_market_details extracts strike fields from raw API response."""
        client = MagicMock()
        raw_resp = MagicMock()
        raw_resp.json.return_value = {
            "market": {
                "ticker": "KXHIGHNY-26MAY18-T84",
                "floor_strike": None,
                "ceiling_strike": None,
                "settlement_result": True,
                "settlement_value": 88.0,
                "event_ticker": "KXHIGHNY-26MAY18",
                "series_ticker": "KXHIGHNY",
                "close_time": 1747526400,
                "question": "NYC high > 84F?",
                "volume_fp": "1000",
                "open_interest_fp": "500",
                "outcome_prices": ["85", "15"],
                "state": "settled",
            }
        }
        raw_resp.raise_for_status = MagicMock()
        client.get = AsyncMock(return_value=raw_resp)
        market_svc = MagicMock()
        market_svc.get_market = AsyncMock(
            return_value=_make_market(),
        )

        result = await fetch_market_details(client, market_svc, "KXHIGHNY-26MAY18-T84")

        assert result["ticker"] == "KXHIGHNY-26MAY18-T84"
        assert result["event_ticker"] == "KXHIGHNY-26MAY18"
        assert result["series_ticker"] == "KXHIGHNY"
