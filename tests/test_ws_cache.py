"""Unit tests for MarketCache (in-memory market cache with SQLite persistence)."""

from __future__ import annotations

import sqlite3
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


def _market_data_tickers(db: Path) -> list[str]:
    """All tickers in the persisted ``market_data`` table ([] if there are none)."""
    if not db.exists():
        return []
    conn = sqlite3.connect(db)
    try:
        return [str(row[0]) for row in conn.execute("SELECT ticker FROM market_data")]
    except sqlite3.OperationalError:
        return []  # table never created — no rows by definition
    finally:
        conn.close()


def _count_inserts(statements: list[str], table: str) -> int:
    return sum(1 for stmt in statements if stmt.startswith(f"INSERT OR REPLACE INTO {table}"))


class TestLifecycleKeepsPriceCacheClean:
    """Issue #251 slice 1: lifecycle state must not pollute the price cache."""

    def test_lifecycle_only_event_records_state_without_market_data_row(self):
        mc, db = _mk_cache()
        mc.update_lifecycle("LIFECYCLEONLY", {"category": "weather", "status": "open"})

        event = mc.get_lifecycle("LIFECYCLEONLY")
        assert event is not None
        assert event["category"] == "weather"
        assert event["status"] == "open"
        assert mc.get_event_category("LIFECYCLEONLY") == "weather"

        # No zero-valued placeholder was written into the price cache.
        assert mc.get_ticker("LIFECYCLEONLY") is None
        assert mc.get_tickers() == {}

        # Lifecycle is not persisted in slice 1: the cycle must not write a row.
        mc.persist_to_db()
        assert _market_data_tickers(db) == []


class TestPerEntryDirtyPersistence:
    """Issue #251 slice 1: persistence is O(changed), not O(cache size)."""

    def test_persist_cycle_writes_only_changed_tickers(self, monkeypatch):
        db = Path(tempfile.mkdtemp()) / "test.db"
        real_connect = sqlite3.connect
        statements: list[str] = []
        opens: list[int] = []

        def tracing_connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            connection.set_trace_callback(statements.append)
            opens.append(1)
            return connection

        monkeypatch.setattr(sqlite3, "connect", tracing_connect)

        mc = MarketCache(db_path=db)
        mc.update_ticker("A", last_price=1.0, updated_at=1.0)
        mc.update_ticker("B", last_price=2.0, updated_at=1.0)
        assert mc.get_stats()["dirty"] is True

        mc.persist_to_db()  # first cycle: both rows are dirty
        assert _count_inserts(statements, "market_data") == 2
        assert mc.get_stats()["dirty"] is False

        statements.clear()
        mc.update_ticker("A", last_price=1.5, updated_at=2.0)  # only A changed
        assert mc.get_stats()["dirty"] is True
        mc.persist_to_db()
        assert _count_inserts(statements, "market_data") == 1
        assert _count_inserts(statements, "orderbook") == 0
        assert mc.get_stats()["dirty"] is False

        # A quiet cycle (nothing dirty) runs no SQL and opens no new handle.
        statements.clear()
        mc.persist_to_db()
        assert statements == []
        assert len(opens) == 1  # only the first persist opened a connection

        conn = real_connect(db)
        try:
            assert conn.execute(
                "SELECT last_price FROM market_data WHERE ticker = ?", ("A",)
            ).fetchone() == (1.5,)
            assert conn.execute(
                "SELECT last_price FROM market_data WHERE ticker = ?", ("B",)
            ).fetchone() == (2.0,)
            assert conn.execute("SELECT COUNT(*) FROM market_data").fetchone() == (2,)
        finally:
            conn.close()

    def test_persist_cycle_writes_only_changed_orderbooks(self, monkeypatch):
        db = Path(tempfile.mkdtemp()) / "test.db"
        real_connect = sqlite3.connect
        statements: list[str] = []

        def tracing_connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            connection.set_trace_callback(statements.append)
            return connection

        monkeypatch.setattr(sqlite3, "connect", tracing_connect)

        mc = MarketCache(db_path=db)
        mc.update_orderbook("A", bids=[{"price_dollars": 49, "count_fp": 2}])
        mc.update_orderbook("B", asks=[{"price_dollars": 51, "count_fp": 3}])
        mc.persist_to_db()  # first cycle: both rows are dirty
        assert _count_inserts(statements, "orderbook") == 2

        statements.clear()
        mc.update_orderbook("B", asks=[{"price_dollars": 52, "count_fp": 4}])
        mc.persist_to_db()  # only B changed
        assert _count_inserts(statements, "orderbook") == 1
        assert _count_inserts(statements, "market_data") == 0
