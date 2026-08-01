"""Tests for db/sync.py — settlement→decision bridging."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from traderbot.db import get_connection, init_schema
from traderbot.db.decisions import insert, list_by_ticker
from traderbot.db.positions import upsert
from traderbot.db.sync import sync_settlement_to_decisions
from traderbot.kalshi.models import Decision, Position

if TYPE_CHECKING:
    from pathlib import Path


def _settled_position(ticker: str, result: bool) -> Position:
    return Position(
        ticker=ticker,
        side="yes",
        quantity=10,
        avg_price=50,
        settlement_result=result,
    )


def _executed_decision(ticker: str, direction: str, ts: datetime) -> Decision:
    return Decision(
        timestamp=ts,
        ticker=ticker,
        direction=direction,
        quantity=5,
        price=50,
        signal_strength=0.7,
        confidence=0.8,
        edge_estimate=0.1,
        risk_checks={"max_position": True},
        outcome="executed",
        actual_result=None,
    )


class TestSyncSettlementToDecisions:
    """sync_settlement_to_decisions bridges positions.settlement_result → decisions.actual_result."""

    def test_settles_yes_correctly(self, tmp_path: Path) -> None:
        """Position settles YES → yes-direction decision gets actual_result=True."""
        db_file = tmp_path / "test.db"
        now = datetime.now(UTC)
        with get_connection(db_file) as conn:
            init_schema(conn)
            upsert(conn, _settled_position("KX-SYNC1", True))
            insert(conn, _executed_decision("KX-SYNC1", "yes", now))
            synced = sync_settlement_to_decisions(conn)

        assert synced == 1
        with get_connection(db_file) as conn:
            decisions = list_by_ticker(conn, "KX-SYNC1")
        assert len(decisions) == 1
        assert decisions[0].actual_result is True

    def test_settles_no_correctly(self, tmp_path: Path) -> None:
        """Position settles NO → no-direction decision gets actual_result=True (predicted loss correctly)."""
        db_file = tmp_path / "test.db"
        now = datetime.now(UTC)
        with get_connection(db_file) as conn:
            init_schema(conn)
            upsert(conn, _settled_position("KX-SYNC2", False))
            insert(conn, _executed_decision("KX-SYNC2", "no", now))
            synced = sync_settlement_to_decisions(conn)

        assert synced == 1
        with get_connection(db_file) as conn:
            decisions = list_by_ticker(conn, "KX-SYNC2")
        assert len(decisions) == 1
        assert decisions[0].actual_result is True

    def test_wrong_direction_flags_false(self, tmp_path: Path) -> None:
        """Position settles YES but decision was no → actual_result=False."""
        db_file = tmp_path / "test.db"
        now = datetime.now(UTC)
        with get_connection(db_file) as conn:
            init_schema(conn)
            upsert(conn, _settled_position("KX-SYNC3", True))
            insert(conn, _executed_decision("KX-SYNC3", "no", now))
            synced = sync_settlement_to_decisions(conn)

        assert synced == 1
        with get_connection(db_file) as conn:
            decisions = list_by_ticker(conn, "KX-SYNC3")
        assert decisions[0].actual_result is False

    def test_idempotent_no_re_sync(self, tmp_path: Path) -> None:
        """Already-synced decisions are not updated again."""
        db_file = tmp_path / "test.db"
        now = datetime.now(UTC)
        with get_connection(db_file) as conn:
            init_schema(conn)
            upsert(conn, _settled_position("KX-SYNC4", True))
            insert(conn, _executed_decision("KX-SYNC4", "yes", now))
            first = sync_settlement_to_decisions(conn)
            second = sync_settlement_to_decisions(conn)

        assert first == 1
        assert second == 0

    def test_multiple_decisions_same_ticker(self, tmp_path: Path) -> None:
        """All un-synced executed decisions on the same ticker get synced."""
        db_file = tmp_path / "test.db"
        now = datetime.now(UTC)
        with get_connection(db_file) as conn:
            init_schema(conn)
            upsert(conn, _settled_position("KX-SYNC5", True))
            insert(conn, _executed_decision("KX-SYNC5", "yes", now - timedelta(hours=1)))
            insert(conn, _executed_decision("KX-SYNC5", "yes", now))
            synced = sync_settlement_to_decisions(conn)

        assert synced == 2
        with get_connection(db_file) as conn:
            decisions = list_by_ticker(conn, "KX-SYNC5")
        assert all(d.actual_result is True for d in decisions)

    def test_skips_already_synced_but_syncs_new(self, tmp_path: Path) -> None:
        """One decision already synced, one not — only the unsynced gets updated."""
        db_file = tmp_path / "test.db"
        now = datetime.now(UTC)
        with get_connection(db_file) as conn:
            init_schema(conn)
            upsert(conn, _settled_position("KX-SYNC6", True))
            insert(conn, _executed_decision("KX-SYNC6", "yes", now - timedelta(hours=2)))
            second_id = insert(conn, _executed_decision("KX-SYNC6", "yes", now))
            # Manually mark first as already synced
            conn.execute(
                "UPDATE decisions SET actual_result = 1 WHERE id = ?", (second_id - 1,)
            )
            conn.commit()
            synced = sync_settlement_to_decisions(conn)

        assert synced == 1

    def test_out_of_window_decision_not_synced(self, tmp_path: Path) -> None:
        """Decision outside the ±24h window is NOT synced."""
        db_file = tmp_path / "test.db"
        now = datetime.now(UTC)
        with get_connection(db_file) as conn:
            init_schema(conn)
            upsert(conn, _settled_position("KX-SYNC7", True))
            # Decision timestamped 48 hours ago — outside the 24h window
            insert(
                conn,
                _executed_decision("KX-SYNC7", "yes", now - timedelta(hours=48)),
            )
            synced = sync_settlement_to_decisions(conn)

        assert synced == 0
        with get_connection(db_file) as conn:
            decisions = list_by_ticker(conn, "KX-SYNC7")
        assert decisions[0].actual_result is None

    def test_no_settled_positions_returns_zero(self, tmp_path: Path) -> None:
        """No settled positions → no sync, returns 0."""
        db_file = tmp_path / "test.db"
        with get_connection(db_file) as conn:
            init_schema(conn)
            synced = sync_settlement_to_decisions(conn)

        assert synced == 0

    def test_different_ticker_not_matched(self, tmp_path: Path) -> None:
        """Position settles for ticker A but decision is for ticker B → no sync."""
        db_file = tmp_path / "test.db"
        now = datetime.now(UTC)
        with get_connection(db_file) as conn:
            init_schema(conn)
            upsert(conn, _settled_position("KX-A", True))
            insert(conn, _executed_decision("KX-B", "yes", now))
            synced = sync_settlement_to_decisions(conn)

        assert synced == 0
