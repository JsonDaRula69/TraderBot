# TraderBot v2 — Database Schema

> This document covers the per-agent per-mode database isolation architecture, unified schema, ChromaDB collections, forecast snapshots, and database efficiency improvements. Grounded in DD-021, DD-027, DD-032.

---

## Directory Layout

```
~/.traderbot/
├── traderbot.db                    # Global DB (schema version, config, profile registry)
├── secrets/secrets.json            # Local encrypted fallback (if no Infisical)
├── secrets/secrets.json.sha256     # Integrity hash
├── secrets/secrets.json.meta       # Audit timestamps
├── tokens.enc                      # Agent token registry (Fernet-encrypted)
├── profiles.enc                    # Profile registry (Fernet-encrypted)
├── chromadb/                       # SHARED: all agents read, category filtering via metadata
│   ├── news/                       # News embeddings (category metadata on each doc)
│   ├── data_points/                # Quantitative data (category metadata)
│   ├── market_patterns/            # Pattern signatures (category metadata)
│   ├── news_signals/               # Processed signals (category metadata)
│   └── market_conditions/          # Market resolution conditions
├── sysadmin/
│   └── db/decisions.db             # SysAdmin decisions (oversight, not trading)
├── paper-weather/
│   └── db/decisions.db             # Weather agent paper trade history
├── paper-economics/
│   └── db/decisions.db             # Economics agent paper trade history
├── paper-politics/
│   └── db/decisions.db             # Politics agent paper trade history
├── paper-crypto/
│   └── db/decisions.db             # Crypto agent paper trade history
├── live-weather/                   # Created only when agent switches to live mode
│   └── db/decisions.db             # Live trade history
└── ...
```

**Key design choices**:
- Directory name `paper-{category}` is used even for backtesting mode — the directory doesn't change when mode changes
- Live databases (`live-{category}/`) are created only when an agent is promoted to live trading
- An agent in live mode has read access to its own backtest and paper databases for reference, but the MCP tool logs data to the corresponding database based on mode

---

## Per-Agent Per-Mode Isolation (DD-032)

### Database Isolation Rules

1. Each agent has separate databases for each mode: `backtest`, `paper`, `live`
2. An agent can only write to the database corresponding to its current mode
3. An agent in live mode can read its own backtest and paper databases for reference
4. Category agents CANNOT access other category agents' databases
5. SysAdmin can read all databases (enabled_categories: [])

### Isolation Enforcement

| Level | Mechanism | What It Enforces |
|---|---|---|
| Directory structure | Per-agent per-mode directories | Physical isolation of SQLite files |
| Profile token | MCP server resolves token → profile → categories + mode | Logical isolation of data access |
| OpenClaw tool filter | Per-agent `alsoAllow` lists | Tool-level isolation |
| Docker bind mount | Only agent's own data dir mounted RW | Container-level isolation |

### Access Matrix

| Agent | Own backtest DB | Own paper DB | Own live DB | Other agent DBs | ChromaDB |
|---|---|---|---|---|---|
| Weather (paper) | Read | Read/Write | N/A | No | Read (weather filter) |
| Weather (live) | Read | Read | Read/Write | No | Read (weather filter) |
| SysAdmin | Read all | Read all | Read all | Read all | Read all |

---

## Unified Schema

### Global Database (`traderbot.db`)

```sql
-- Schema version tracking (migration system)
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT
);

-- Trading profiles
CREATE TABLE profiles (
    name TEXT PRIMARY KEY,
    mode TEXT NOT NULL CHECK (mode IN ('backtest', 'paper', 'live')),
    description TEXT,
    enabled_categories TEXT,  -- JSON array, empty array = all categories
    permissions TEXT,  -- JSON array
    risk_multiplier REAL NOT NULL CHECK (risk_multiplier > 0 AND risk_multiplier <= 1.0),
    max_position_per_market_pct REAL NOT NULL CHECK (max_position_per_market_pct > 0),
    max_daily_loss_pct REAL NOT NULL CHECK (max_daily_loss_pct > 0),
    max_drawdown_pct REAL NOT NULL CHECK (max_drawdown_pct > 0),
    max_open_positions INTEGER NOT NULL CHECK (max_open_positions > 0),
    min_liquidity_threshold INTEGER NOT NULL CHECK (min_liquidity_threshold > 0),
    min_edge_pct REAL NOT NULL CHECK (min_edge_pct > 0),
    initial_balance_cents INTEGER DEFAULT 10000,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Configuration key-value store
CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### Per-Agent Database (`decisions.db`)

```sql
-- Trading decisions with full reasoning audit trail
CREATE TABLE decisions (
    id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    category TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('yes', 'no')),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    estimated_prob REAL CHECK (estimated_prob IS NULL OR (estimated_prob >= 0 AND estimated_prob <= 1)),
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    reasoning TEXT,  -- Full reasoning audit trail
    mode TEXT NOT NULL CHECK (mode IN ('backtest', 'paper', 'live')),
    profile TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),

    -- Indexes
    FOREIGN KEY (ticker) REFERENCES positions(ticker) ON DELETE CASCADE
);

CREATE INDEX idx_decisions_ticker ON decisions(ticker);
CREATE INDEX idx_decisions_category ON decisions(category);
CREATE INDEX idx_decisions_mode ON decisions(mode);
CREATE INDEX idx_decisions_created ON decisions(created_at);

-- Positions (open and closed)
CREATE TABLE positions (
    ticker TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('yes', 'no')),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    avg_entry_price_cents INTEGER NOT NULL CHECK (avg_entry_price_cents >= 0),
    current_price_cents INTEGER,
    mode TEXT NOT NULL CHECK (mode IN ('backtest', 'paper', 'live')),
    profile TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed', 'settled')),
    opened_at TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at TEXT,
    settled_at TEXT,

    -- P&L
    pnl_cents INTEGER,
    settlement_outcome INTEGER  -- 1 = yes won, 0 = no won
);

CREATE INDEX idx_positions_status ON positions(status);
CREATE INDEX idx_positions_category ON positions(category);
CREATE INDEX idx_positions_mode ON positions(mode);

-- Forecast snapshots (for backtesting accuracy tracking)
CREATE TABLE forecast_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    category TEXT NOT NULL,
    source TEXT NOT NULL,  -- 'nws', 'gfs', 'ecmwf', 'open-meteo', 'consensus'
    metric TEXT NOT NULL,  -- 'temp_high', 'temp_low', 'precip', 'wind_speed', etc.
    predicted_value REAL NOT NULL,
    predicted_for_date TEXT NOT NULL,  -- The date being forecasted
    snapshot_date TEXT NOT NULL,  -- When the forecast was made
    lead_time_days INTEGER NOT NULL,  -- Days between snapshot and target
    confidence REAL,
    model_consensus_score REAL,
    metadata TEXT,  -- JSON for additional model-specific data
    created_at TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE(ticker, source, metric, snapshot_date, predicted_for_date)
);

CREATE INDEX idx_forecast_ticker ON forecast_snapshots(ticker);
CREATE INDEX idx_forecast_snapshot ON forecast_snapshots(snapshot_date);
CREATE INDEX idx_forecast_lead ON forecast_snapshots(lead_time_days);
CREATE INDEX idx_forecast_source ON forecast_snapshots(source);

-- Generalized bias tracking (replaces weather-specific forecast_bias)
CREATE TABLE bias_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    source TEXT NOT NULL,
    metric TEXT NOT NULL,
    predicted_value REAL NOT NULL,
    actual_value REAL NOT NULL,
    predicted_for_date TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    lead_time_days INTEGER NOT NULL DEFAULT 0,
    error REAL NOT NULL,  -- predicted - actual
    abs_error REAL NOT NULL,  -- |predicted - actual|
    pct_error REAL,  -- (predicted - actual) / actual * 100
    created_at TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE(category, source, metric, snapshot_date, predicted_for_date)
);

CREATE INDEX idx_bias_category ON bias_tracking(category);
CREATE INDEX idx_bias_source ON bias_tracking(source);
CREATE INDEX idx_bias_lead ON bias_tracking(lead_time_days);

-- Settlement cache (consolidated from separate DB)
CREATE TABLE settlement_cache (
    ticker TEXT PRIMARY KEY,
    outcome INTEGER NOT NULL,
    settled_at TEXT NOT NULL
);

-- Learnings
CREATE TABLE learnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    pattern_key TEXT NOT NULL,
    description TEXT NOT NULL,
    recurrence_count INTEGER DEFAULT 1,
    justification TEXT,
    impact TEXT,
    priority TEXT CHECK (priority IN ('low', 'medium', 'high')),
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'promoted', 'resolved', 'dismissed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_learnings_category ON learnings(category);
CREATE INDEX idx_learnings_status ON learnings(status);
CREATE INDEX idx_learnings_priority ON learnings(priority);

-- Circuit breaker state (per-agent per-mode)
CREATE TABLE circuit_breaker (
    profile TEXT NOT NULL,
    mode TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'green' CHECK (state IN ('green', 'yellow', 'red', 'full_stop')),
    trigger_reason TEXT,
    triggered_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (profile, mode)
);

-- Portfolio summary (for fast balance queries)
CREATE TABLE portfolio_summary (
    profile TEXT NOT NULL,
    mode TEXT NOT NULL,
    initial_balance_cents INTEGER NOT NULL,
    current_balance_cents INTEGER NOT NULL,
    total_realized_pnl_cents INTEGER NOT NULL DEFAULT 0,
    open_position_count INTEGER NOT NULL DEFAULT 0,
    last_updated TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (profile, mode)
);
```

---

## ChromaDB Collections (Shared)

ChromaDB collections use category metadata filtering instead of per-category collections:

| Collection | Documents | Category Filter |
|---|---|---|
| `news` | News articles with embeddings | `where={"category": "weather"}` |
| `data_points` | Quantitative data points | `where={"category": "weather"}` |
| `market_patterns` | Pattern signatures | `where={"category": "weather"}` |
| `news_signals` | Processed news signals | `where={"category": "weather"}` |
| `market_conditions` | Market resolution conditions | Shared (no category filter) |

**Note**: `decisions` collection in ChromaDB is per-agent (not shared) — each agent has its own ChromaDB collection for decision embeddings. The `learnings` collection is also per-agent.

---

## Database Efficiency Improvements

### SQLite PRAGMA Optimization

```sql
PRAGMA journal_mode=WAL;          -- Already set
PRAGMA synchronous=NORMAL;        -- Faster writes, safe with WAL
PRAGMA busy_timeout=5000;          -- Wait up to 5s for locks
PRAGMA cache_size=-64000;          -- 64MB cache
PRAGMA temp_store=MEMORY;          -- In-memory temp tables
PRAGMA mmap_size=268435456;        -- 256MB memory-mapped I/O
PRAGMA foreign_keys=ON;            -- Already set
```

### Other Improvements

1. **Migration system**: Track schema version in `schema_version` table. Apply migrations in order, skip already-applied ones. Support rollback for development.

2. **Circuit breaker in DB**: Move from `circuit_breaker_state.json` to per-agent per-mode `circuit_breaker` table. Queryable via MCP for SysAdmin oversight.

3. **ChromaDB embedding dimension**: Store as collection metadata. Provide migration utility for re-embedding when the model changes.

4. **Data retention policy**:
   - News articles: retain 6 months (matching backfill window), archive older
   - Positions: retain all for active modes, archive after settlement + 90 days
   - Decisions: retain all (audit trail)
   - Forecast snapshots: retain 6 months for backtesting, archive older
   - ChromaDB vectors: retain per collection policy

5. **Settlement cache consolidation**: Move from separate `settlement_cache.db` per profile to a table in the main `decisions.db`.

6. **Portfolio summary table**: Maintain running `portfolio_summary` for fast balance queries without loading all positions. Updated on each trade.

7. **`learnings` in `init_schema()`**: Ensure the `learnings` table is created by `init_schema()`, not on-demand.

8. **Connection pooling**: Use a connection pool for the MCP server to handle concurrent agent requests.

9. **WAL checkpoint**: Run `PRAGMA wal_checkpoint(TRUNCATE)` periodically to keep WAL size bounded.

10. **DB file size monitoring**: Alert when databases exceed size thresholds. VACUUM on promotion from backtesting to paper.

---

## GRIB2 Processing Pipeline (DD-033)

For true multi-day lead time forecasts, a GRIB2 processing pipeline will be built in two phases:

### Phase 1 (Ship with v2)
- Use Open-Meteo Archive API + NWS forecasts + Kalshi historical data (day-0 only)
- Document the approximation: initial backtests use day-0 forecasts which inflate certainty

### Phase 2 (After v2 Core)
- Provider modules: `data/providers/gfs.py` and `data/providers/ecmwf.py`
- Optional dependency: `cfgrib` via `pip install traderbot[weather-backtest]`
- Process: Download grid points for 15 Kalshi cities → Extract temp/precip/wind → Store in `forecast_snapshots` with `lead_time_days`
- Deploy integration: Offer optional 6-month backfill (5-10 GB compressed, skip by default)
- Ongoing collection: GFS every 6 hours, ECMWF every 12 hours
