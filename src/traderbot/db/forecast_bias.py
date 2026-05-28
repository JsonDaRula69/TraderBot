"""SQLite persistence for NWS forecast bias tracking.

Records what was forecast vs. what actually happened, and provides
aggregate bias statistics per city/model.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import sqlite3


def init_table(conn: sqlite3.Connection) -> None:
    """Create the forecast_bias table if it does not exist."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS forecast_bias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT NOT NULL,
            model TEXT NOT NULL DEFAULT 'nws',
            forecast_date TEXT NOT NULL,
            forecast_high_f REAL NOT NULL,
            actual_high_f REAL NOT NULL,
            error_f REAL NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    conn.commit()


def record_forecast(
    conn: sqlite3.Connection,
    city: str,
    forecast_high_f: float,
    actual_high_f: float,
    model: str = "nws",
) -> None:
    """Record a forecast and its actual outcome.

    Computes error_f = actual_high_f - forecast_high_f automatically.
    """
    error_f = actual_high_f - forecast_high_f
    now = datetime.now(UTC)
    conn.execute(
        """INSERT INTO forecast_bias
           (city, model, forecast_date, forecast_high_f, actual_high_f, error_f, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            city,
            model,
            now.date().isoformat(),
            forecast_high_f,
            actual_high_f,
            error_f,
            now.isoformat(),
        ),
    )
    conn.commit()
    logger.info("Recorded forecast: city=%s model=%s error=%.1f°F", city, model, error_f)


def query_bias(
    conn: sqlite3.Connection,
    city: str,
    model: str = "nws",
    days: int = 90,
) -> dict:
    """Return bias statistics for a city/model over the last N days.

    Returns:
        dict with keys: mean_error, mean_abs_error, std_error, count, last_n_days
    """
    cutoff = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()
    rows = conn.execute(
        """SELECT error_f FROM forecast_bias
           WHERE city = ? AND model = ? AND forecast_date >= ?
           ORDER BY forecast_date DESC""",
        (city, model, cutoff),
    ).fetchall()

    errors = [r[0] for r in rows]
    if not errors:
        logger.debug("Bias query for city=%s model=%s days=%d: no data found", city, model, days)
        return {
            "mean_error": 0.0,
            "mean_abs_error": 0.0,
            "std_error": 0.0,
            "count": 0,
            "last_n_days": days,
        }

    n = len(errors)
    mean = sum(errors) / n
    mean_abs = sum(abs(e) for e in errors) / n
    variance = sum((e - mean) ** 2 for e in errors) / n
    std = variance ** 0.5
    return {
        "mean_error": round(mean, 2),
        "mean_abs_error": round(mean_abs, 2),
        "std_error": round(std, 2),
        "count": n,
        "last_n_days": days,
    }


def query_all_cities(
    conn: sqlite3.Connection,
    model: str = "nws",
    days: int = 90,
) -> list[dict]:
    """Return bias statistics grouped by city for the given model.

    Each dict contains city plus the same keys as query_bias.
    """
    cutoff = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()
    rows = conn.execute(
        """SELECT DISTINCT city FROM forecast_bias
           WHERE model = ? AND forecast_date >= ?""",
        (model, cutoff),
    ).fetchall()

    results: list[dict] = []
    for (city,) in rows:
        stats = query_bias(conn, city, model, days)
        results.append({"city": city, **stats})

    logger.debug("Bias query for all cities model=%s days=%d: %d cities found", model, days, len(results))
    return sorted(results, key=lambda r: r["city"])
