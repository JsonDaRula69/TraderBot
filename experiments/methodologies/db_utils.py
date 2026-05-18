import sqlite3
from pathlib import Path


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with row factory and foreign keys enabled."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_market(db: sqlite3.Connection, ticker: str) -> dict | None:
    """Fetch all columns from the markets table for a given ticker."""
    row = db.execute("SELECT * FROM markets WHERE ticker = ?", (ticker,)).fetchone()
    return dict(row) if row else None


def get_market_prices(db: sqlite3.Connection, ticker: str, timestep: int) -> dict | None:
    """Fetch price data for a specific market and timestep."""
    row = db.execute(
        "SELECT * FROM market_prices WHERE ticker = ? AND timestep = ?",
        (ticker, timestep),
    ).fetchone()
    return dict(row) if row else None


def get_calibration_bins(db: sqlite3.Connection, bin_label: str) -> dict | None:
    """Fetch calibration bin data by bin label."""
    row = db.execute(
        "SELECT bin_label, bin_lower, bin_upper, count, actual_rate FROM calibration_bins WHERE bin_label = ?",
        (bin_label,),
    ).fetchone()
    return dict(row) if row else None


def record_methodology_output(
    db: sqlite3.Connection,
    ticker: str,
    timestep: int,
    methodology: str,
    result: dict,
) -> None:
    """Insert or replace a methodology output record."""
    db.execute(
        """
        INSERT OR REPLACE INTO methodology_outputs
        (ticker, timestep, methodology, estimated_prob, confidence, reasoning_data)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            ticker,
            timestep,
            methodology,
            result["estimated_prob"],
            result["confidence"],
            result.get("reasoning_data"),
        ),
    )
    db.commit()


def record_agent_decision(
    db: sqlite3.Connection,
    ticker: str,
    timestep: int,
    methodology: str,
    decision: dict,
) -> None:
    """Insert or replace an agent decision record."""
    db.execute(
        """
        INSERT OR REPLACE INTO agent_decisions
        (ticker, timestep, methodology, decision, estimated_prob, confidence, edge_estimate, position_size_cents, reasoning)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticker,
            timestep,
            methodology,
            decision["decision"],
            decision.get("estimated_prob"),
            decision.get("confidence"),
            decision.get("edge_estimate"),
            decision.get("position_size_cents"),
            decision.get("reasoning"),
        ),
    )
    db.commit()
