"""Per-agent SQLite decisions database migrations."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from traderbot.db.migrations import Migration, apply_migrations

_DECISIONS_V1_SQL: Final = (
    """CREATE TABLE decisions (
        id TEXT PRIMARY KEY NOT NULL,
        timestamp TEXT NOT NULL,
        ticker TEXT NOT NULL,
        direction TEXT NOT NULL CHECK (direction IN ('yes', 'no', 'neutral')),
        quantity INTEGER NOT NULL CHECK (quantity > 0),
        price INTEGER NOT NULL,
        signal_strength REAL NOT NULL,
        confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
        edge_estimate REAL NOT NULL,
        risk_checks TEXT NOT NULL,
        outcome TEXT NOT NULL CHECK (outcome IN ('executed', 'rejected', 'held')),
        rejection_reason TEXT,
        actual_result INTEGER,
        mode TEXT NOT NULL CHECK (mode IN ('backtest', 'paper', 'live')),
        category TEXT NOT NULL,
        profile TEXT NOT NULL
    )""",
    "CREATE INDEX idx_decisions_ticker ON decisions(ticker)",
    "CREATE INDEX idx_decisions_timestamp ON decisions(timestamp)",
    "CREATE INDEX idx_decisions_ticker_timestamp ON decisions(ticker, timestamp)",
    "CREATE INDEX idx_decisions_category ON decisions(category)",
    "CREATE INDEX idx_decisions_mode ON decisions(mode)",
    "CREATE INDEX idx_decisions_profile ON decisions(profile)",
    "CREATE INDEX idx_decisions_profile_mode ON decisions(profile, mode)",
    """CREATE TABLE positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
        ticker TEXT UNIQUE NOT NULL,
        side TEXT NOT NULL DEFAULT 'yes' CHECK (side IN ('yes', 'no')),
        quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
        avg_price_cents INTEGER NOT NULL DEFAULT 0 CHECK (avg_price_cents >= 0),
        settlement_result INTEGER,
        pnl_cents INTEGER DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed', 'settled')),
        mode TEXT NOT NULL CHECK (mode IN ('backtest', 'paper', 'live')),
        category TEXT NOT NULL,
        profile TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    "CREATE INDEX idx_positions_status ON positions(status)",
    "CREATE INDEX idx_positions_category ON positions(category)",
    "CREATE INDEX idx_positions_mode ON positions(mode)",
    "CREATE INDEX idx_positions_profile ON positions(profile)",
    "CREATE INDEX idx_positions_profile_mode ON positions(profile, mode)",
    """CREATE TABLE forecast_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
        ticker TEXT NOT NULL,
        category TEXT NOT NULL,
        source TEXT NOT NULL,
        metric TEXT NOT NULL,
        predicted_value REAL NOT NULL,
        predicted_for_date TEXT NOT NULL,
        snapshot_date TEXT NOT NULL,
        lead_time_days INTEGER NOT NULL,
        confidence REAL,
        model_consensus_score REAL,
        metadata TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(ticker, source, metric, snapshot_date, predicted_for_date)
    )""",
    """CREATE INDEX idx_forecast_snapshots_lookup
        ON forecast_snapshots(ticker, predicted_for_date, snapshot_date)""",
    """CREATE INDEX idx_forecast_snapshots_source_lead
        ON forecast_snapshots(source, lead_time_days)""",
    """CREATE INDEX idx_forecast_snapshots_category
        ON forecast_snapshots(category, predicted_for_date)""",
    """CREATE TABLE bias_tracking (
        id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
        category TEXT NOT NULL,
        source TEXT NOT NULL,
        metric TEXT NOT NULL,
        predicted_value REAL NOT NULL,
        actual_value REAL,
        predicted_at TEXT NOT NULL,
        actual_at TEXT,
        lead_time_hours INTEGER,
        error REAL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(category, source, metric, predicted_at)
    )""",
    """CREATE INDEX idx_bias_tracking_category_source
        ON bias_tracking(category, source)""",
    """CREATE INDEX idx_bias_tracking_metric
        ON bias_tracking(category, metric, predicted_at)""",
    """CREATE TABLE learnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
        category TEXT NOT NULL,
        pattern_key TEXT NOT NULL,
        description TEXT NOT NULL,
        recurrence_count INTEGER DEFAULT 1,
        justification TEXT,
        impact TEXT,
        priority TEXT CHECK (priority IN ('low', 'medium', 'high')),
        status TEXT DEFAULT 'active'
            CHECK (status IN ('active', 'promoted', 'resolved', 'dismissed')),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX idx_learnings_category ON learnings(category)",
    "CREATE INDEX idx_learnings_status ON learnings(status)",
    "CREATE INDEX idx_learnings_priority ON learnings(priority)",
    """CREATE TABLE circuit_breaker (
        profile TEXT NOT NULL,
        mode TEXT NOT NULL CHECK (mode IN ('backtest', 'paper', 'live')),
        state TEXT NOT NULL DEFAULT 'green'
            CHECK (state IN ('green', 'yellow', 'red', 'full_stop')),
        trigger_reason TEXT,
        triggered_at TEXT,
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (profile, mode)
    )""",
    """CREATE TABLE portfolio_summary (
        profile TEXT NOT NULL,
        mode TEXT NOT NULL CHECK (mode IN ('backtest', 'paper', 'live')),
        initial_balance_cents INTEGER NOT NULL,
        current_balance_cents INTEGER NOT NULL,
        total_realized_pnl_cents INTEGER NOT NULL DEFAULT 0,
        open_position_count INTEGER NOT NULL DEFAULT 0,
        last_updated TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (profile, mode)
    )""",
)

DECISIONS_MIGRATIONS: Final[tuple[Migration, ...]] = (
    Migration(1, "Create per-agent decisions schema", _DECISIONS_V1_SQL, None),
)


def init_decisions_db(db_path: str | Path) -> None:
    """Initialize or migrate one per-agent decisions database."""
    _ = apply_migrations(db_path, DECISIONS_MIGRATIONS)
