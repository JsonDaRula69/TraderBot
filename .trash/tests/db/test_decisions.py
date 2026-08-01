from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from traderbot.db.decisions import DbDecision, init_table


class TestDbDecision:
    def test_minimal_executed(self) -> None:
        d = DbDecision(
            id=1,
            timestamp=datetime.now(UTC),
            ticker="KXBTCD-26MAR31-T55000",
            direction="yes",
            quantity=10,
            price=5000,
            signal_strength=0.8,
            confidence=0.75,
            edge_estimate=0.05,
            risk_checks={"min_liquidity": True, "max_risk": True},
            outcome="executed",
        )
        assert d.ticker == "KXBTCD-26MAR31-T55000"
        assert d.direction == "yes"
        assert d.outcome == "executed"
        assert d.rejection_reason is None
        assert d.actual_result is None

    def test_rejected_decision(self) -> None:
        d = DbDecision(
            id=2,
            timestamp=datetime.now(UTC),
            ticker="KXBTCD-26MAR31-T55000",
            direction="no",
            quantity=5,
            price=5000,
            signal_strength=0.3,
            confidence=0.2,
            edge_estimate=-0.02,
            risk_checks={"min_liquidity": False},
            outcome="rejected",
            rejection_reason="Below min liquidity threshold",
        )
        assert d.outcome == "rejected"
        assert d.rejection_reason == "Below min liquidity threshold"

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValueError):  # pydantic validation
            DbDecision(
                id=3,
                timestamp=datetime.now(UTC),
                ticker="TEST",
                direction="yes",
                quantity=1,
                price=50,
                signal_strength=0.5,
                confidence=0.5,
                edge_estimate=0.0,
                risk_checks={},
                outcome="executed",
                unknown_field="x",
            )


class TestRowToModel:
    def _insert_and_fetch(self, table_sql: str, insert_sql: str, insert_args: tuple, col_list: str) -> sqlite3.Row:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(table_sql)
        conn.execute(insert_sql, insert_args)
        row = conn.execute("SELECT * FROM decisions").fetchone()
        conn.close()
        return row

    def test_legacy_checks_column_renamed_to_risk_checks(self) -> None:
        from traderbot.db.decisions import _row_to_model

        row = self._insert_and_fetch(
            "CREATE TABLE decisions (id INTEGER PRIMARY KEY, timestamp TEXT, ticker TEXT, "
            "direction TEXT, quantity INTEGER, price INTEGER, signal_strength REAL, "
            "confidence REAL, edge_estimate REAL, checks TEXT, outcome TEXT, "
            "rejection_reason TEXT, actual_result INTEGER)",
            "INSERT INTO decisions (id, timestamp, ticker, direction, quantity, price, "
            "signal_strength, confidence, edge_estimate, checks, outcome, rejection_reason, "
            "actual_result) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (1, "2025-01-01T00:00:00+00:00", "KXBTCD-26MAR31-T55000", "yes", 10, 5000, 0.8,
             0.75, 0.05, '{"min_liquidity": true, "max_risk": true}', "executed", None, None),
            "",
        )
        result = _row_to_model(row)
        assert result.risk_checks == {"min_liquidity": True, "max_risk": True}
        assert result.outcome == "executed"

    def test_risk_checks_column_works(self) -> None:
        from traderbot.db.decisions import _row_to_model

        row = self._insert_and_fetch(
            "CREATE TABLE decisions (id INTEGER PRIMARY KEY, timestamp TEXT, ticker TEXT, "
            "direction TEXT, quantity INTEGER, price INTEGER, signal_strength REAL, "
            "confidence REAL, edge_estimate REAL, risk_checks TEXT, outcome TEXT, "
            "rejection_reason TEXT, actual_result INTEGER)",
            "INSERT INTO decisions (id, timestamp, ticker, direction, quantity, price, "
            "signal_strength, confidence, edge_estimate, risk_checks, outcome, rejection_reason, "
            "actual_result) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (2, "2025-01-01T00:00:00+00:00", "KXBTCD-26MAR31-T55000", "no", 5, 5000, 0.3,
             0.2, -0.02, '{"min_liquidity": false}', "rejected", "Below min liquidity threshold", None),
            "",
        )
        result = _row_to_model(row)
        assert result.risk_checks == {"min_liquidity": False}
        assert result.outcome == "rejected"

    def test_missing_risk_checks_defaults_to_empty(self) -> None:
        from traderbot.db.decisions import _row_to_model

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE decisions (id INTEGER PRIMARY KEY, timestamp TEXT, ticker TEXT, "
            "direction TEXT, quantity INTEGER, price INTEGER, signal_strength REAL, "
            "confidence REAL, edge_estimate REAL, outcome TEXT, rejection_reason TEXT, "
            "actual_result INTEGER)"
        )
        conn.execute(
            "INSERT INTO decisions (id, timestamp, ticker, direction, quantity, price, "
            "signal_strength, confidence, edge_estimate, outcome, rejection_reason, "
            "actual_result) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (3, "2025-01-01T00:00:00+00:00", "TEST", "neutral", 1, 50, 0.5, 0.5, 0.0, "held", None, None),
        )
        row = conn.execute("SELECT * FROM decisions").fetchone()
        conn.close()
        result = _row_to_model(row)
        assert result.risk_checks == {}


class TestInitTable:
    def test_creates_decisions_table(self) -> None:
        conn = sqlite3.connect(":memory:")
        init_table(conn)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='decisions'"
        )
        assert cursor.fetchone() is not None
        conn.close()
