"""Unit tests for MarketCache (in-memory market cache with SQLite persistence)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from traderbot.kalshi.ws_cache import MarketCache


def _mk_cache() -> tuple[MarketCache, Path]:
    tmp = Path(tempfile.mkdtemp()) / "test.db"
    return MarketCache(db_path=tmp), tmp


class TestMarketCacheInMemory:
    def test_update_and_get_ticker(self):
        mc, _ = _mk_cache()
        mc.update_ticker("TEST", last_price=50.0, bid=49.0, ask=51.0)
        assert mc.get_ticker("TEST")["last_price"] == 50.0
        assert mc.get_ticker("TEST")["bid"] == 49.0
        assert mc.get_ticker("TEST")["ask"] == 51.0

    def test_get_unknown_ticker_returns_none(self):
        mc, _ = _mk_cache()
        assert mc.get_ticker("NOPE") is None

    def test_update_ticker_and_get_tickers(self):
        mc, _ = _mk_cache()
        mc.update_ticker("A", last_price=1.0)
        mc.update_ticker("B", last_price=2.0)
        assert set(mc.get_tickers().keys()) == {"A", "B"}

    def test_update_orderbook(self):
        mc, _ = _mk_cache()
        mc.update_orderbook(
            "TEST",
            bids=[{"price_dollars": 49, "count_fp": 2}],
            asks=[{"price_dollars": 51, "count_fp": 3}],
        )
        ob = mc.get_orderbook("TEST")
        assert ob is not None
        assert ob["bids"][0]["price_dollars"] == 49
        assert ob["asks"][0]["count_fp"] == 3

    def test_update_lifecycle_sets_category(self):
        mc, _ = _mk_cache()
        mc.update_lifecycle("TEST", {"category": "weather", "status": "open"})
        assert mc.get_event_category("TEST") == "weather"
        assert mc.get_lifecycle("TEST")["category"] == "weather"

    def test_record_fill_bounded(self):
        mc, _ = _mk_cache()
        for i in range(600):
            mc.record_fill({"i": i})
        # Bounded to _FILLS_LIMIT (500) — most recent first.
        assert len(mc.get_fills(limit=500)) == 500
        assert mc.get_fills(1)[0]["i"] == 599


class TestMarketCachePersistence:
    def test_round_trip(self):
        tmp = Path(tempfile.mkdtemp()) / "test.db"
        mc = MarketCache(db_path=tmp)
        mc.update_ticker("TEST", last_price=50.0, bid=49.0, ask=51.0)
        mc.update_orderbook(
            "TEST",
            bids=[{"price_dollars": 49, "count_fp": 2}],
            asks=[{"price_dollars": 51, "count_fp": 3}],
        )
        mc.persist_to_db()

        mc2 = MarketCache(db_path=tmp)
        mc2.load_from_db()
        assert mc2.get_ticker("TEST")["last_price"] == 50.0
        assert mc2.get_orderbook("TEST")["bids"][0]["price_dollars"] == 49
        assert mc2.get_orderbook("TEST")["asks"][0]["count_fp"] == 3

    def test_load_from_missing_db_is_noop(self):
        mc, _ = _mk_cache()
        mc.load_from_db()  # should not raise
        assert mc.get_tickers() == {}

    def test_persist_failure_keeps_in_memory(self, monkeypatch):
        mc, _ = _mk_cache()
        mc.update_ticker("TEST", last_price=50.0)

        import sqlite3

        def boom(*args, **kwargs):
            raise sqlite3.Error("boom")

        monkeypatch.setattr(sqlite3, "connect", boom)
        # persist fails but must not raise — in-memory still serves.
        mc.persist_to_db()
        assert mc.get_ticker("TEST")["last_price"] == 50.0
        assert mc.get_stats()["persist_errors"] >= 1


class TestMarketCacheOpenMarkets:
    def test_open_markets_most_recent_first(self):
        mc, _ = _mk_cache()
        mc.update_ticker("A", last_price=1.0, updated_at=100.0)
        mc.update_ticker("B", last_price=2.0, updated_at=200.0)
        mc.update_ticker("C", last_price=3.0, updated_at=300.0)
        markets = mc.get_open_markets()
        assert [m["ticker"] for m in markets][:3] == ["C", "B", "A"]
