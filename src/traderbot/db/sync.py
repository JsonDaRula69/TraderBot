"""Bridge settlement data from positions to decisions for Bayesian adaptation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import sqlite3

#: Maximum hours between a decision's timestamp and a position's settlement
#: update for them to be considered the same trade event.
PROXIMITY_HOURS: int = 24


def sync_settlement_to_decisions(conn: sqlite3.Connection) -> int:
    """Propagate positions.settlement_result → decisions.actual_result.

    For every settled position (settlement_result IS NOT NULL), find
    un-synced executed decisions on the same ticker within
    PROXIMITY_HOURS of the settlement update.
    Returns the count of decisions updated.
    """
    settled = conn.execute(
        "SELECT ticker, settlement_result, updated_at FROM positions "
        "WHERE settlement_result IS NOT NULL"
    ).fetchall()

    if not settled:
        logger.debug("sync: no settled positions to propagate")
        return 0

    synced = 0
    for row in settled:
        ticker: str = row["ticker"]
        settled_result: bool = bool(row["settlement_result"])
        settled_at: str = row["updated_at"]

        try:
            settled_dt = datetime.fromisoformat(settled_at)
        except (ValueError, TypeError):
            logger.warning("sync: unparseable updated_at for %s: %s", ticker, settled_at)
            continue

        window_start = (settled_dt - timedelta(hours=PROXIMITY_HOURS)).isoformat()
        window_end = (settled_dt + timedelta(hours=PROXIMITY_HOURS)).isoformat()

        pending = conn.execute(
            "SELECT id, direction FROM decisions "
            "WHERE ticker = ? "
            "  AND outcome = 'executed' "
            "  AND actual_result IS NULL "
            "  AND timestamp >= ? "
            "  AND timestamp <= ? "
            "ORDER BY timestamp",
            (ticker, window_start, window_end),
        ).fetchall()

        for decision in pending:
            decision_id: int = decision["id"]
            direction: str = decision["direction"]

            # actual_result = True when direction predicted correctly
            actual = (
                (direction == "yes" and settled_result is True)
                or (direction == "no" and settled_result is False)
            )

            conn.execute(
                "UPDATE decisions SET actual_result = ? WHERE id = ?",
                (int(actual), decision_id),
            )
            logger.info(
                "sync: decision %d (%s/%s) → actual_result=%s (settlement=%s)",
                decision_id,
                ticker,
                direction,
                actual,
                settled_result,
            )
            synced += 1

    if synced:
        conn.commit()
        logger.info("sync: propagated %d settlement results to decisions", synced)
    else:
        logger.debug("sync: no pending decisions to sync")

    return synced
