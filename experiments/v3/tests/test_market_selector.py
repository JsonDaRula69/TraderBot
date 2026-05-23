import sqlite3
from dataclasses import FrozenInstanceError
from datetime import date
from itertools import product

import pytest

from experiments.v3.market_selector import (
    Stratum,
    compute_stratum,
    select_markets,
)

DIFFICULTIES = ["contested", "blowout"]
STRIKE_TYPES = ["less", "greater", "between"]
LEAD_BUCKETS = ["short", "long"]


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS markets (
            ticker TEXT PRIMARY KEY,
            city TEXT,
            strike_type TEXT,
            floor_strike REAL,
            ceiling_strike REAL,
            threshold REAL,
            resolution_date TEXT,
            settlement_result TEXT,
            actual_value REAL,
            event_ticker TEXT,
            series_ticker TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS market_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            timestep INTEGER,
            yes_price REAL,
            no_price REAL,
            trade_count INTEGER,
            open_interest INTEGER,
            extracted_at TEXT
        )
    """)
    conn.commit()


def _ticker(difficulty: str, strike: str, lead: str, idx: int) -> str:
    return f"KXTEST-{difficulty[:4]}-{strike[:3]}-{lead[:2]}-{idx:02d}"


def _insert_market(
    conn: sqlite3.Connection, ticker: str, strike_type: str, resolution_date: str
) -> None:
    conn.execute(
        "INSERT INTO markets (ticker, city, strike_type, resolution_date, settlement_result) VALUES (?, ?, ?, ?, ?)",
        (ticker, "TEST", strike_type, resolution_date, "YES"),
    )


def _insert_price(conn: sqlite3.Connection, ticker: str, yes_price: float) -> None:
    conn.execute(
        "INSERT INTO market_prices (ticker, timestep, yes_price, no_price) VALUES (?, 0, ?, ?)",
        (ticker, yes_price, 1.0 - yes_price),
    )


def _populate_full_grid(conn: sqlite3.Connection, n_per_cell: int = 2) -> None:
    _create_tables(conn)
    for _idx, (difficulty, strike, lead) in enumerate(
        product(DIFFICULTIES, STRIKE_TYPES, LEAD_BUCKETS)
    ):
        yes_price = 0.50 if difficulty == "contested" else 0.10
        resolution_date = "2025-01-01" if lead == "short" else "2025-02-01"
        for i in range(n_per_cell):
            ticker = _ticker(difficulty, strike, lead, i)
            _insert_market(conn, ticker, strike, resolution_date)
            _insert_price(conn, ticker, yes_price)
    conn.commit()


class TestStratumAndCompute:
    def test_stratum_is_frozen(self):
        s = Stratum(difficulty="contested", strike_type="less", lead_time_bucket="short")
        assert s.difficulty == "contested"
        assert s.strike_type == "less"
        assert s.lead_time_bucket == "short"
        with pytest.raises(FrozenInstanceError):
            s.difficulty = "blowout"  # type: ignore[misc]

    def test_compute_stratum_contested(self):
        market = {"strike_type": "between", "lead_time_bucket": "long"}
        t0 = {"yes_price": 0.50}
        result = compute_stratum(market, t0)
        assert result.difficulty == "contested"
        assert result.strike_type == "between"
        assert result.lead_time_bucket == "long"

    def test_compute_stratum_blowout_low(self):
        market = {"strike_type": "greater", "lead_time_bucket": "short"}
        t0 = {"yes_price": 0.05}
        result = compute_stratum(market, t0)
        assert result.difficulty == "blowout"

    def test_compute_stratum_blowout_high(self):
        market = {"strike_type": "less", "lead_time_bucket": "medium"}
        t0 = {"yes_price": 0.95}
        result = compute_stratum(market, t0)
        assert result.difficulty == "blowout"

    def test_compute_stratum_boundary(self):
        for price in (0.20, 0.80):
            result = compute_stratum({"strike_type": "less"}, {"yes_price": price})
            assert result.difficulty == "contested", f"price {price} should be contested"

    def test_compute_stratum_defaults(self):
        result = compute_stratum({}, {})
        assert result.difficulty == "contested"
        assert result.strike_type == "between"
        assert result.lead_time_bucket == "medium"


class TestSelectMarkets:
    def test_returns_12_strata_with_2_markets_each(self):
        conn = sqlite3.connect(":memory:")
        _populate_full_grid(conn, n_per_cell=2)
        selected = select_markets(
            conn, markets_per_cell=2, seed=42, reference_date=date(2024, 12, 31)
        )
        assert len(selected) == 12, (
            f"Expected 12 strata, got {len(selected)}: {sorted(selected.keys())}"
        )
        for key, tickers in selected.items():
            assert len(tickers) == 2, f"Stratum {key} has {len(tickers)} markets, expected 2"
        all_tickers = {t for tickers in selected.values() for t in tickers}
        assert len(all_tickers) == 24, "No ticker should appear in more than one stratum"
        conn.close()

    def test_same_seed_produces_identical_results(self):
        conn = sqlite3.connect(":memory:")
        _populate_full_grid(conn, n_per_cell=3)
        ref = date(2024, 12, 31)
        run1 = select_markets(conn, markets_per_cell=2, seed=42, reference_date=ref)
        run2 = select_markets(conn, markets_per_cell=2, seed=42, reference_date=ref)
        for key in run1:
            assert run1[key] == run2[key], f"Mismatch in stratum {key}"
        conn.close()

    def test_different_seed_produces_different_selection(self):
        conn = sqlite3.connect(":memory:")
        _populate_full_grid(conn, n_per_cell=5)
        ref = date(2024, 12, 31)
        run1 = select_markets(conn, markets_per_cell=2, seed=1, reference_date=ref)
        run2 = select_markets(conn, markets_per_cell=2, seed=99, reference_date=ref)
        all_tickers_1 = {t for tickers in run1.values() for t in tickers}
        all_tickers_2 = {t for tickers in run2.values() for t in tickers}
        assert all_tickers_1 != all_tickers_2, (
            "Different seeds should produce different market selections"
        )
        conn.close()

    def test_undersampled_stratum_returns_all_available(self):
        conn = sqlite3.connect(":memory:")
        _populate_full_grid(conn, n_per_cell=1)
        ref = date(2024, 12, 31)
        selected = select_markets(conn, markets_per_cell=2, seed=42, reference_date=ref)
        for key, tickers in selected.items():
            assert len(tickers) == 1, f"Stratum {key} should return all 1 available markets"
        conn.close()

    def test_empty_db_returns_empty_dict(self):
        conn = sqlite3.connect(":memory:")
        _create_tables(conn)
        selected = select_markets(conn, seed=42)
        assert selected == {}
        conn.close()

    def test_contested_vs_blowout_classification(self):
        conn = sqlite3.connect(":memory:")
        _create_tables(conn)
        _insert_market(conn, "TICK-A", "less", "2025-01-01")
        _insert_market(conn, "TICK-B", "less", "2025-01-01")
        _insert_price(conn, "TICK-A", 0.30)
        _insert_price(conn, "TICK-B", 0.10)
        conn.commit()
        selected = select_markets(
            conn, markets_per_cell=1, seed=42, reference_date=date(2024, 12, 31)
        )
        keys = set(selected.keys())
        assert "contested-less-short" in keys
        assert "blowout-less-short" in keys
        conn.close()

    def test_markets_without_settlement_are_excluded(self):
        conn = sqlite3.connect(":memory:")
        _create_tables(conn)
        _insert_market(conn, "TICK-A", "less", "2025-01-01")
        _insert_price(conn, "TICK-A", 0.50)
        conn.execute("UPDATE markets SET settlement_result = NULL WHERE ticker = 'TICK-A'")
        conn.commit()
        selected = select_markets(
            conn, markets_per_cell=2, seed=42, reference_date=date(2024, 12, 31)
        )
        assert selected == {}
        conn.close()

    def test_minimum_24_markets_across_all_strata(self):
        conn = sqlite3.connect(":memory:")
        _populate_full_grid(conn, n_per_cell=2)
        selected = select_markets(
            conn, markets_per_cell=2, seed=42, reference_date=date(2024, 12, 31)
        )
        total = sum(len(v) for v in selected.values())
        assert total >= 24, f"Expected >= 24 markets, got {total}"
        conn.close()
