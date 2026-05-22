"""Tests for accuracy_calculator — TDD: tests written before implementation."""

import math
import sqlite3

from experiments.v3.data_sources.accuracy_calculator import (
    compute_accuracy,
    compute_city_accuracy,
    save_accuracy,
)
from experiments.v3.db_schema import create_tables

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_market(conn: sqlite3.Connection, ticker: str, city: str) -> None:
    conn.execute(
        "INSERT INTO markets (ticker, city) VALUES (?, ?)",
        (ticker, city),
    )


def _insert_forecast(
    conn: sqlite3.Connection,
    ticker: str,
    days_before: int,
    forecast_temp_f: float,
    timestep: int = 1,
) -> None:
    conn.execute(
        "INSERT INTO forecast_snapshots (ticker, timestep, days_before, forecast_temp_f) "
        "VALUES (?, ?, ?, ?)",
        (ticker, timestep, days_before, forecast_temp_f),
    )


def _insert_settlement(
    conn: sqlite3.Connection,
    ticker: str,
    actual_temp_f: float,
) -> None:
    conn.execute(
        "INSERT INTO settlement_results (ticker, actual_temp_f) VALUES (?, ?)",
        (ticker, actual_temp_f),
    )


def _setup_db(conn: sqlite3.Connection) -> None:
    create_tables(conn)


# ---------------------------------------------------------------------------
# Test 1: 5 Austin markets — verify MAE, bias, sample_count, low_confidence
# ---------------------------------------------------------------------------


class TestComputeAccuracyAustin:
    """Hand-computed values:
    Forecasts: [90.1, 88.5, 91.2, 89.3, 87.8]
    Actuals:   [88.8, 87.0, 90.0, 88.5, 87.2]
    Errors:    [1.3, 1.5, 1.2, 0.8, 0.6]  → bias = 1.08
    Abs errors: [1.3, 1.5, 1.2, 0.8, 0.6] → mae = 1.08
    """

    def test_five_austin_markets_same_lead_time(self):
        conn = sqlite3.connect(":memory:")
        _setup_db(conn)

        forecasts = [90.1, 88.5, 91.2, 89.3, 87.8]
        actuals = [88.8, 87.0, 90.0, 88.5, 87.2]

        for i, (fc, act) in enumerate(zip(forecasts, actuals, strict=True)):
            ticker = f"KXHIGHAUS-26MAY{i+18}-T84"
            _insert_market(conn, ticker, "Austin")
            _insert_forecast(conn, ticker, days_before=3, forecast_temp_f=fc)
            _insert_settlement(conn, ticker, actual_temp_f=act)

        conn.commit()
        results = compute_city_accuracy(conn, "Austin")

        assert len(results) == 1
        row = results[0]
        assert row["city"] == "Austin"
        assert row["lead_time"] == 3
        assert row["sample_count"] == 5
        assert row["low_confidence"] == 0
        assert math.isclose(row["bias"], 1.08, rel_tol=1e-6)
        assert math.isclose(row["mae"], 1.08, rel_tol=1e-6)
        conn.close()


# ---------------------------------------------------------------------------
# Test 2: 2 Seattle markets — low_confidence = True
# ---------------------------------------------------------------------------


class TestLowConfidence:
    def test_two_seattle_markets_low_confidence(self):
        conn = sqlite3.connect(":memory:")
        _setup_db(conn)

        for i, (fc, act) in enumerate([(75.0, 74.0), (76.0, 77.0)]):
            ticker = f"KXHIGHSEA-26MAY{i+18}-T70"
            _insert_market(conn, ticker, "Seattle")
            _insert_forecast(conn, ticker, days_before=2, forecast_temp_f=fc)
            _insert_settlement(conn, ticker, actual_temp_f=act)

        conn.commit()
        results = compute_accuracy(conn)

        seattle_rows = [r for r in results if r["city"] == "Seattle"]
        assert len(seattle_rows) == 1
        row = seattle_rows[0]
        assert row["sample_count"] == 2
        assert row["low_confidence"] == 1
        conn.close()


# ---------------------------------------------------------------------------
# Test 3: 0 markets for a city — returns empty list gracefully
# ---------------------------------------------------------------------------


class TestEmptyCity:
    def test_city_with_no_markets(self):
        conn = sqlite3.connect(":memory:")
        _setup_db(conn)

        results = compute_city_accuracy(conn, "Nowhere")
        assert results == []
        conn.close()


# ---------------------------------------------------------------------------
# Test 4: save_accuracy writes to forecast_accuracy table
# ---------------------------------------------------------------------------


class TestSaveAccuracy:
    def test_save_writes_rows(self):
        conn = sqlite3.connect(":memory:")
        _setup_db(conn)

        rows = [
            {
                "city": "Austin",
                "lead_time": 3,
                "bias": 1.08,
                "mae": 1.08,
                "sample_count": 5,
                "low_confidence": 0,
            },
            {
                "city": "Seattle",
                "lead_time": 2,
                "bias": -0.5,
                "mae": 1.5,
                "sample_count": 2,
                "low_confidence": 1,
            },
        ]

        save_accuracy(conn, rows)

        cursor = conn.execute(
            "SELECT city, lead_time, mae, bias, sample_count, low_confidence "
            "FROM forecast_accuracy ORDER BY city"
        )
        saved = cursor.fetchall()

        assert len(saved) == 2

        austin = next(r for r in saved if r[0] == "Austin")
        assert austin[1] == 3
        assert math.isclose(austin[2], 1.08, rel_tol=1e-6)
        assert math.isclose(austin[3], 1.08, rel_tol=1e-6)
        assert austin[4] == 5
        assert austin[5] == 0

        seattle = next(r for r in saved if r[0] == "Seattle")
        assert seattle[1] == 2
        assert math.isclose(seattle[2], 1.5, rel_tol=1e-6)
        assert math.isclose(seattle[3], -0.5, rel_tol=1e-6)
        assert seattle[4] == 2
        assert seattle[5] == 1

        conn.close()

    def test_save_insert_or_replace(self):
        """Second save with same (city, lead_time) overwrites first."""
        conn = sqlite3.connect(":memory:")
        _setup_db(conn)

        rows_v1 = [
            {"city": "Austin", "lead_time": 1, "bias": 2.0, "mae": 2.0, "sample_count": 3, "low_confidence": 1},
        ]
        save_accuracy(conn, rows_v1)

        rows_v2 = [
            {"city": "Austin", "lead_time": 1, "bias": 3.0, "mae": 3.0, "sample_count": 10, "low_confidence": 0},
        ]
        save_accuracy(conn, rows_v2)

        cursor = conn.execute(
            "SELECT bias, mae, sample_count, low_confidence "
            "FROM forecast_accuracy WHERE city = 'Austin' AND lead_time = 1"
        )
        row = cursor.fetchone()
        assert row is not None
        assert math.isclose(row[0], 3.0, rel_tol=1e-6)
        assert math.isclose(row[1], 3.0, rel_tol=1e-6)
        assert row[2] == 10
        assert row[3] == 0
        conn.close()


# ---------------------------------------------------------------------------
# Test 5: Multiple cities with multiple lead times
# ---------------------------------------------------------------------------


class TestMultipleCitiesLeadTimes:
    def test_per_city_per_lead_time_grouping(self):
        conn = sqlite3.connect(":memory:")
        _setup_db(conn)

        # Austin: 2 forecasts at lead_time=5, 3 at lead_time=2
        austin_data = [
            ("AUS1", 5, 92.0, 90.0),
            ("AUS2", 5, 94.0, 93.0),
            ("AUS3", 2, 91.0, 89.0),
            ("AUS4", 2, 88.0, 87.0),
            ("AUS5", 2, 89.0, 90.0),
        ]
        for ticker, days_before, fc, act in austin_data:
            _insert_market(conn, ticker, "Austin")
            _insert_forecast(conn, ticker, days_before=days_before, forecast_temp_f=fc)
            _insert_settlement(conn, ticker, actual_temp_f=act)

        # Seattle: 4 forecasts at lead_time=2
        seattle_data = [
            ("SEA1", 2, 72.0, 71.0),
            ("SEA2", 2, 70.0, 72.0),
            ("SEA3", 2, 73.0, 71.0),
            ("SEA4", 2, 74.0, 73.0),
        ]
        for ticker, days_before, fc, act in seattle_data:
            _insert_market(conn, ticker, "Seattle")
            _insert_forecast(conn, ticker, days_before=days_before, forecast_temp_f=fc)
            _insert_settlement(conn, ticker, actual_temp_f=act)

        conn.commit()
        results = compute_accuracy(conn)

        # Should have 3 groups: (Austin, 5), (Austin, 2), (Seattle, 2)
        assert len(results) == 3

        austin_5 = [r for r in results if r["city"] == "Austin" and r["lead_time"] == 5]
        assert len(austin_5) == 1
        assert austin_5[0]["sample_count"] == 2
        # Errors: [2.0, 1.0] → bias=1.5, mae=1.5
        assert math.isclose(austin_5[0]["bias"], 1.5, rel_tol=1e-6)
        assert math.isclose(austin_5[0]["mae"], 1.5, rel_tol=1e-6)
        assert austin_5[0]["low_confidence"] == 1  # sample_count < 3

        austin_2 = [r for r in results if r["city"] == "Austin" and r["lead_time"] == 2]
        assert len(austin_2) == 1
        assert austin_2[0]["sample_count"] == 3
        # Errors: [2.0, 1.0, -1.0] → bias=0.666..., mae=1.333...
        assert math.isclose(austin_2[0]["bias"], 2.0 / 3.0, rel_tol=1e-6)
        assert math.isclose(austin_2[0]["mae"], 4.0 / 3.0, rel_tol=1e-6)
        assert austin_2[0]["low_confidence"] == 0

        seattle_2 = [r for r in results if r["city"] == "Seattle" and r["lead_time"] == 2]
        assert len(seattle_2) == 1
        assert seattle_2[0]["sample_count"] == 4
        # Errors: [1.0, -2.0, 2.0, 1.0] → bias=0.5, mae=1.5
        assert math.isclose(seattle_2[0]["bias"], 0.5, rel_tol=1e-6)
        assert math.isclose(seattle_2[0]["mae"], 1.5, rel_tol=1e-6)
        assert seattle_2[0]["low_confidence"] == 0

        conn.close()
