"""Load forecast snapshots from the SQLite database."""

import sqlite3


def load_forecast(db: sqlite3.Connection, ticker: str, timestep: int) -> dict:
    """Return a single forecast snapshot for *ticker* and *timestep*."""
    db.row_factory = sqlite3.Row
    cursor = db.execute(
        """
        SELECT ticker, timestep, forecast_date, target_date,
               temp_max_f, temp_min_f, precip_mm,
               wind_speed_max_kmh, humidity_max_pct,
               weather_code, source
        FROM forecast_snapshots
        WHERE ticker = ? AND timestep = ?
        """,
        (ticker, timestep),
    )
    row = cursor.fetchone()
    return dict(row) if row is not None else {}


def load_all_forecasts(db: sqlite3.Connection, ticker: str) -> list[dict]:
    """Return all forecast snapshots for *ticker*."""
    db.row_factory = sqlite3.Row
    cursor = db.execute(
        """
        SELECT ticker, timestep, forecast_date, target_date,
               temp_max_f, temp_min_f, precip_mm,
               wind_speed_max_kmh, humidity_max_pct,
               weather_code, source
        FROM forecast_snapshots
        WHERE ticker = ?
        ORDER BY timestep
        """,
        (ticker,),
    )
    return [dict(row) for row in cursor.fetchall()]
