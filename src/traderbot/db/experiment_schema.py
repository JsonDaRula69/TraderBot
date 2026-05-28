"""SQLite schema for experiment database tables."""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)


def create_tables(conn: sqlite3.Connection) -> None:
    """Create the experiment tables if they do not exist."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS markets (
            ticker TEXT PRIMARY KEY,
            question TEXT NOT NULL,
            city TEXT NOT NULL,
            city_prefix TEXT NOT NULL,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            timezone TEXT NOT NULL,
            resolution_date TEXT NOT NULL,
            close_time TEXT NOT NULL,
            settlement_result TEXT,
            actual_value REAL,
            strike_value REAL,
            strike_type TEXT,
            market_type TEXT,
            yes_price_dollars REAL,
            volume REAL,
            open_interest REAL,
            event_ticker TEXT,
            series_ticker TEXT
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS forecast_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            forecast_temp_f REAL,
            source TEXT,
            days_before INTEGER,
            snapshot_date TEXT,
            FOREIGN KEY (ticker) REFERENCES markets (ticker)
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS market_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            timestep INTEGER,
            yes_price_cents INTEGER,
            no_price_cents INTEGER,
            FOREIGN KEY (ticker) REFERENCES markets (ticker)
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS settlement_actuals (
            ticker TEXT PRIMARY KEY,
            actual_temp_f REAL,
            settlement_date TEXT,
            FOREIGN KEY (ticker) REFERENCES markets (ticker)
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS agent_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            treatment TEXT NOT NULL,
            ticker TEXT NOT NULL,
            timestep INTEGER NOT NULL,
            decision TEXT NOT NULL,
            estimated_prob REAL,
            confidence REAL,
            reasoning TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (ticker) REFERENCES markets (ticker)
        )"""
    )

    conn.commit()
    logger.info("Created experiment database tables (markets, forecast_snapshots, market_prices, settlement_actuals, agent_decisions)")
