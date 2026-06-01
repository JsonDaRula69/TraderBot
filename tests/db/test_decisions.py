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


class TestInitTable:
    def test_creates_decisions_table(self) -> None:
        conn = sqlite3.connect(":memory:")
        init_table(conn)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='decisions'"
        )
        assert cursor.fetchone() is not None
        conn.close()
