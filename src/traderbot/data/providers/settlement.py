"""Settlement monitor worker (DD-028).

Runs hourly, queries recently settled Kalshi markets over REST (settled
markets are historical data — allowed via the WS-first policy, which reserves
REST for historical data and recovery), and records each market's outcome in
a ``settlement_cache`` table. Agents query local settlement data rather than
polling the exchange.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, override

from traderbot.data.base_provider import BaseDataProvider
from traderbot.kalshi.client import KalshiClient
from traderbot.paths import get_db_path

logger = logging.getLogger(__name__)

_HOURLY_INTERVAL_SECONDS: float = 60.0 * 60.0  # one hour
_SETTLED_LIMIT = 100
_TIME_WINDOW_SECONDS = 6 * 60 * 60  # look back 6h for newly settled markets

# Maps the Kalshi settlement cache outcome column to a boolean.
_YES_OUTCOME = 1
_NO_OUTCOME = 0


class SettlementMonitor(BaseDataProvider):
    """Hourly monitor that records settled Kalshi market outcomes.

    Args:
        client: A :class:`~traderbot.kalshi.client.KalshiClient` used to query
            settled markets (historical data; allowed under the WS-first
            policy). Injected so tests can mock it.
        db_path: SQLite database file. Defaults to
            ``~/.traderbot/traderbot.db`` (see :func:`traderbot.paths.get_db_path`).
    """

    def __init__(self, client: KalshiClient, db_path: Path | None = None) -> None:
        super().__init__()
        self._client: KalshiClient = client
        self._db_path: Path = db_path or get_db_path()

    @property
    @override
    def name(self) -> str:
        return "settlement-monitor"

    @property
    @override
    def interval_seconds(self) -> float:
        return _HOURLY_INTERVAL_SECONDS

    @override
    async def fetch(self) -> list[dict[str, Any]]:
        """Query recently settled markets and return their outcome records.

        Uses ``GET /markets`` with ``status=settled`` (historical data, so REST
        is the correct channel under the WS-first policy).

        Returns:
            A list of ``{"ticker", "outcome", "settled_at"}`` dicts for markets
            settled within the look-back window, or an empty list on error.
        """
        try:
            resp = await self._client.get(
                "/markets",
                status="settled",
                limit=_SETTLED_LIMIT,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception:  # noqa: BLE001 — monitor must not kill the loop
            logger.warning("settlement monitor query failed", exc_info=True)
            return []

        markets = payload.get("markets", []) if isinstance(payload, dict) else []
        now_ts = datetime.now(UTC).timestamp()
        records: list[dict[str, Any]] = []
        for m in markets:
            if not isinstance(m, dict):
                continue
            ticker = m.get("ticker")
            result = m.get("result")
            close_time = m.get("close_time") or m.get("settled_at")
            if not isinstance(ticker, str) or not isinstance(result, str):
                continue
            # Extract an epoch timestamp from an ISO string (with offset).
            settled_epoch = _iso_to_epoch(str(close_time)) if isinstance(close_time, str) else None
            if settled_epoch is not None and now_ts - settled_epoch > _TIME_WINDOW_SECONDS:
                continue
            records.append(
                {
                    "ticker": ticker,
                    "outcome": _YES_OUTCOME if result == "yes" else _NO_OUTCOME,
                    "settled_at": (
                        datetime.fromtimestamp(settled_epoch, tz=UTC).isoformat()
                        if settled_epoch is not None
                        else datetime.now(UTC).isoformat()
                    ),
                }
            )
        return records

    @override
    async def insert(self, data: list[dict[str, Any]]) -> int:
        """Persist settlement outcomes into the ``settlement_cache`` table."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        try:
            self._create_tables(conn)
            inserted = 0
            for row in data:
                cur = conn.execute(
                    """INSERT OR IGNORE INTO settlement_cache (ticker, outcome, settled_at)
                       VALUES (?, ?, ?)""",
                    (row["ticker"], int(row["outcome"]), str(row["settled_at"])),
                )
                inserted += cur.rowcount
            conn.commit()
            logger.info("settlement monitor recorded %d settled markets", inserted)
            return inserted
        finally:
            conn.close()

    @staticmethod
    def _create_tables(conn: sqlite3.Connection) -> None:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS settlement_cache (
                   ticker TEXT PRIMARY KEY,
                   outcome INTEGER NOT NULL,
                   settled_at TEXT NOT NULL
               )"""
        )
        conn.commit()


def _iso_to_epoch(value: str) -> float | None:
    """Parse an ISO-8601 timestamp to epoch seconds, or None if unparseable."""
    try:
        dt = datetime.fromisoformat(value)
        return dt.timestamp()
    except ValueError:
        return None


__all__ = ["SettlementMonitor"]
