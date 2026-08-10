# TraderBot v2 — Database Schema

> Authoritative database contract for Phase 3 (per-agent per-mode isolation). This document supersedes earlier prose in `v2roadmap.md` section 10 and any stale `v2docs` copies. When the running code disagrees with this doc, the code is the source of truth and this doc must be updated.

---

## File layout

```
~/.traderbot/
├── traderbot.db                    # Global DB: schema version, profiles, config, market data,
│                                   # weather forecasts, NWS forecasts, settlement cache
├── secrets/                        # Encrypted secrets (outside DB scope)
├── tokens.enc                      # Profile token registry (Fernet-encrypted)
├── chromadb/                       # Embedded PersistentClient root (daemon-owned, owner-only).
│                                   # Collections (news, data_points, market_patterns,
│                                   # news_signals, market_conditions) are logical objects
│                                   # inside this single ChromaDB directory, not guaranteed
│                                   # filesystem subdirectories.
├── backtest-{name}/                # Per-profile backtest mode
│   └── db/decisions.db             # decisions, positions, forecast_snapshots, bias_tracking,
│                                   # learnings, circuit_breaker, portfolio_summary
├── paper-{name}/                   # Per-profile paper mode (separate directory, not shared with backtest)
│   └── db/decisions.db             # Same seven-table schema as backtest
└── live-{name}/                    # Created when a profile is promoted to live
    └── db/decisions.db             # Same seven-table schema as backtest/paper
```

Key design choices:

- Directory names are explicit per-mode: `backtest-{name}`, `paper-{name}`, `live-{name}`. Backtest and paper never share a directory.
- A profile in `live` mode can read its own backtest and paper databases for reference, but MCP tools log new trading data to the database matching the active mode.
- Category agents cannot access other category agents' databases. SysAdmin reads across agents through MCP, not through direct filesystem access.
- The ChromaDB root is an embedded `PersistentClient` path owned by the daemon process; no HTTP server is started.

---

## Per-agent per-mode isolation (DD-032)

### Phase 3 implementation status

Phase 3 Tasks 0-9 are implemented on `feat/v2-database`; on-target macpro-linux QA (Task 10) remains pending. The implementation now provides:

- `src/traderbot/db/` as the central database module, including the typed migration runner, per-agent schema, bounded SQLite connection pool, embedded ChromaDB store, storage validation, and `DatabaseAccess` routing.
- Global migration v1 for `traderbot.db` and decisions migration v1 for all seven per-agent tables: `decisions`, `positions`, `forecast_snapshots`, `bias_tracking`, `learnings`, `circuit_breaker`, and `portfolio_summary`.
- Ordered, skip-applied migrations recorded in `schema_version`, atomic `BEGIN IMMEDIATE` application, fail-closed legacy signature validation with adjacent backups, and highest-applied-version rollback guards.
- A daemon-owned `SQLiteConnectionPool` with WAL and the PRAGMAs documented below. `DatabaseAccess` enforces resolved profile identity, active-mode writes, read-only access to authorized earlier modes, path containment, and SysAdmin-only enumeration.
- One embedded `chromadb.PersistentClient` with the Rust bindings backend pinned, telemetry disabled, explicit caller-supplied vectors, five shared logical collections, mode-qualified per-agent collections, category-prefixed IDs, and mandatory category filters.
- Daemon startup and shutdown integration with database, ChromaDB, and Chroma ownership-lock health reporting. Reads never create a per-agent database; explicit deployment/promotion or the first authorized write initializes it.

### ChromaDB accepted risk: GHSA-f4j7-r4q5-qw2c

TraderBot pins `chromadb==1.5.9`, which is affected by [GHSA-f4j7-r4q5-qw2c](https://github.com/advisories/GHSA-f4j7-r4q5-qw2c) / CVE-2026-45829. The advisory is a pre-authentication code-injection path in ChromaDB's Python HTTP collection endpoint: attacker-controlled embedding configuration could be deserialized before authentication. TraderBot accepts the package-level risk because that HTTP exploit path is unreachable under the enforced embedded-only design:

- TraderBot creates only an in-process `PersistentClient` configured with `chromadb.api.rust.RustBindingsAPI`, asserts that effective backend at runtime, and never imports or starts ChromaDB's HTTP server, FastAPI adapter, Uvicorn, `HttpClient`, `AsyncHttpClient`, or `CloudClient`.
- The application creates the Chroma root itself and rejects external, prebuilt, symlinked, wrong-owner, or permissive storage. On POSIX the root is owner-only mode `0700` and the ownership lock is mode `0600`; Windows requires the current user SID as owner, a protected DACL, and no broad or foreign allow ACEs.
- Collections use `embedding_function=None`; callers provide explicit vectors. TraderBot accepts no serialized remote embedding-function configuration and performs no default model download.

The CI waiver is deliberately exact and fails on every other advisory:

```bash
uv export --frozen --no-hashes --no-emit-project -o requirements-audit.txt
uvx pip-audit --strict --aliases -r requirements-audit.txt \
  --ignore-vuln GHSA-f4j7-r4q5-qw2c
```

Waiver owner: **TraderBot**. Removal condition: **upgrade ChromaDB and remove the waiver with the first official release containing merged upstream fix [chroma-core/chroma#7237](https://github.com/chroma-core/chroma/pull/7237)**. Until then, the accepted risk and independent review are tracked in [TraderBot #195](https://github.com/JsonDaRula69/TraderBot/issues/195) and [TraderBot #196](https://github.com/JsonDaRula69/TraderBot/issues/196); the vulnerable code remains present in the dependency even though TraderBot does not expose its HTTP path.

### Isolation rules

1. Each profile has separate `decisions.db` files for `backtest`, `paper`, and `live` modes.
2. A profile can only write to the database matching its current mode.
3. A profile in `live` mode can read its own backtest and paper databases for reference.
4. Category agents cannot access other category agents' databases.
5. SysAdmin can read all databases through MCP.

### Access matrix

| Profile | Own backtest DB | Own paper DB | Own live DB | Other profile DBs | ChromaDB |
|---|---|---|---|---|---|
| Weather (paper) | Read | Read/Write | N/A | No | Read (weather filter) |
| Weather (live) | Read | Read | Read/Write | No | Read (weather filter) |
| SysAdmin | Read all | Read all | Read all | Read all | Read all |

---

## Global database (`traderbot.db`)

### Schema version tracking

```sql
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT
);
```

### Profiles registry (Phase 4 compatibility, included in global migration v1)

The `profiles` and `config` tables are included in the global migration v1 so that the schema is ready for Phase 4 persistence. Runtime persistence is not yet wired: current production code still manages profile state through `TradingProfile` models and the profile factory functions in `src/traderbot/profiles/`.

```sql
CREATE TABLE profiles (
    name TEXT PRIMARY KEY,
    mode TEXT NOT NULL CHECK (mode IN ('backtest', 'paper', 'live')),
    description TEXT,
    enabled_categories TEXT,  -- JSON array; empty array means all categories
    permissions TEXT,         -- JSON array
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
```

### Configuration key/value store (Phase 4 compatibility, included in global migration v1)

```sql
CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

`config` is part of the global migration v1 schema for Phase 4 compatibility. Runtime persistence is not yet wired. The table is empty until a later phase populates it.

### Phase 2 global data tables

These tables are created by the running daemon and data pipeline. The signatures below are copied directly from the current production source files cited in the reconciliation checklist.

#### `market_data`

Source: `src/traderbot/kalshi/ws_cache.py`.

```sql
CREATE TABLE IF NOT EXISTS market_data (
    ticker TEXT PRIMARY KEY,
    last_price REAL,
    bid REAL,
    ask REAL,
    volume REAL,
    open_interest REAL,
    updated_at REAL NOT NULL
);
```

#### `orderbook`

Source: `src/traderbot/kalshi/ws_cache.py`.

The orderbook is stored as one row per ticker. `bids_json` and `asks_json` contain the full aggregated orderbook arrays as JSON text.

```sql
CREATE TABLE IF NOT EXISTS orderbook (
    ticker TEXT PRIMARY KEY,
    bids_json TEXT NOT NULL,
    asks_json TEXT NOT NULL,
    updated_at REAL NOT NULL
);
```

#### `weather_forecasts`

Source: `src/traderbot/data/providers/open_meteo.py`.

```sql
CREATE TABLE IF NOT EXISTS weather_forecasts (
    snapshot_ts TEXT NOT NULL,
    city TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    model TEXT NOT NULL,
    valid_date TEXT NOT NULL,
    variable TEXT NOT NULL,
    value REAL NOT NULL,
    PRIMARY KEY (snapshot_ts, city, model, valid_date, variable)
);
```

#### `nws_forecasts`

Source: `src/traderbot/data/providers/nws.py`.

```sql
CREATE TABLE IF NOT EXISTS nws_forecasts (
    snapshot_ts TEXT NOT NULL,
    city TEXT NOT NULL,
    forecast_date TEXT NOT NULL,
    high_temp_f REAL,
    low_temp_f REAL,
    precip_prob REAL,
    wind_speed REAL,
    detailed_forecast TEXT,
    PRIMARY KEY (snapshot_ts, city, forecast_date)
);
```

#### `settlement_cache`

Source: `src/traderbot/data/providers/settlement.py`.

Settlement outcomes are global and authoritative. They are not duplicated inside per-agent `decisions.db` files.

```sql
CREATE TABLE IF NOT EXISTS settlement_cache (
    ticker TEXT PRIMARY KEY,
    outcome INTEGER NOT NULL,
    settled_at TEXT NOT NULL
);
```

---

## Per-agent database (`decisions.db`)

Every per-agent `decisions.db` has the same seven tables. `init_decisions_db()` owns creation of all seven tables, including `learnings`. No table is created on demand.

Column naming rule: use `profile`, never `agent`. Only `decisions`, `positions`, `circuit_breaker`, and `portfolio_summary` carry both `profile` and `mode` columns. Other tables carry `category` where category grouping is needed.

### `decisions`

Trading decisions with a full reasoning audit trail. Decision IDs are caller-generated canonical UUID4 strings (`str(uuid.uuid4())`). There is no foreign key to `positions(ticker)`. Per-agent isolation makes cross-agent contamination impossible at the filesystem level, and the trading engine handles position correlation in code.

```sql
CREATE TABLE decisions (
    id TEXT PRIMARY KEY,               -- UUID4 canonical string, supplied by caller
    timestamp TEXT NOT NULL,
    ticker TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('yes', 'no', 'neutral')),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    price INTEGER NOT NULL,            -- cents
    signal_strength REAL NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    edge_estimate REAL NOT NULL,
    risk_checks TEXT NOT NULL,         -- JSON
    outcome TEXT NOT NULL CHECK (outcome IN ('executed', 'rejected', 'held')),
    rejection_reason TEXT,
    actual_result INTEGER,             -- 1 = yes won, 0 = no won, NULL until settled
    mode TEXT NOT NULL CHECK (mode IN ('backtest', 'paper', 'live')),
    category TEXT NOT NULL,
    profile TEXT NOT NULL
);

CREATE INDEX idx_decisions_ticker ON decisions(ticker);
CREATE INDEX idx_decisions_timestamp ON decisions(timestamp);
CREATE INDEX idx_decisions_ticker_timestamp ON decisions(ticker, timestamp);
CREATE INDEX idx_decisions_category ON decisions(category);
CREATE INDEX idx_decisions_mode ON decisions(mode);
CREATE INDEX idx_decisions_profile ON decisions(profile);
CREATE INDEX idx_decisions_profile_mode ON decisions(profile, mode);
```

### `positions`

Open and closed positions, unified from the retired `paper_positions` and `db/positions.py` schemas.

```sql
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT UNIQUE NOT NULL,
    side TEXT NOT NULL DEFAULT 'yes' CHECK (side IN ('yes', 'no')),
    quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    avg_price_cents INTEGER NOT NULL DEFAULT 0 CHECK (avg_price_cents >= 0),
    settlement_result INTEGER,         -- 1 = yes won, 0 = no won, NULL for open
    pnl_cents INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed', 'settled')),
    mode TEXT NOT NULL CHECK (mode IN ('backtest', 'paper', 'live')),
    category TEXT NOT NULL,
    profile TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_positions_status ON positions(status);
CREATE INDEX idx_positions_category ON positions(category);
CREATE INDEX idx_positions_mode ON positions(mode);
CREATE INDEX idx_positions_profile ON positions(profile);
CREATE INDEX idx_positions_profile_mode ON positions(profile, mode);
```

### `forecast_snapshots`

Time-series forecast snapshots for backtesting. Records what the forecast was on day X-N for day X.

```sql
CREATE TABLE forecast_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    category TEXT NOT NULL,
    source TEXT NOT NULL,              -- 'nws', 'gfs', 'ecmwf', 'gem', 'open-meteo'
    metric TEXT NOT NULL,              -- 'high_temp', 'low_temp', 'precip_prob', 'wind_speed'
    predicted_value REAL NOT NULL,
    predicted_for_date TEXT NOT NULL,  -- the date being forecast
    snapshot_date TEXT NOT NULL,       -- when this forecast was made
    lead_time_days INTEGER NOT NULL,
    confidence REAL,
    model_consensus_score REAL,
    metadata TEXT,                     -- JSON for source-specific data
    created_at TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE(ticker, source, metric, snapshot_date, predicted_for_date)
);

CREATE INDEX idx_forecast_snapshots_lookup
    ON forecast_snapshots(ticker, predicted_for_date, snapshot_date);
CREATE INDEX idx_forecast_snapshots_source_lead
    ON forecast_snapshots(source, lead_time_days);
CREATE INDEX idx_forecast_snapshots_category
    ON forecast_snapshots(category, predicted_for_date);
```

### `bias_tracking`

Generalized forecast bias tracking across all categories.

```sql
CREATE TABLE bias_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    source TEXT NOT NULL,
    metric TEXT NOT NULL,
    predicted_value REAL NOT NULL,
    actual_value REAL,
    predicted_at TEXT NOT NULL,
    actual_at TEXT,
    lead_time_hours INTEGER,
    error REAL,                        -- actual - predicted
    created_at TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE(category, source, metric, predicted_at)
);

CREATE INDEX idx_bias_tracking_category_source ON bias_tracking(category, source);
CREATE INDEX idx_bias_tracking_metric ON bias_tracking(category, metric, predicted_at);
```

### `learnings`

Agent learning records. Created by `init_decisions_db()`, not on demand.

```sql
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
```

### `circuit_breaker`

Per-profile per-mode risk state, moved from the retired `circuit_breaker_state.json`.

```sql
CREATE TABLE circuit_breaker (
    profile TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('backtest', 'paper', 'live')),
    state TEXT NOT NULL DEFAULT 'green' CHECK (state IN ('green', 'yellow', 'red', 'full_stop')),
    trigger_reason TEXT,
    triggered_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (profile, mode)
);
```

### `portfolio_summary`

Running balance summary for fast MCP balance queries without scanning all positions.

```sql
CREATE TABLE portfolio_summary (
    profile TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('backtest', 'paper', 'live')),
    initial_balance_cents INTEGER NOT NULL,
    current_balance_cents INTEGER NOT NULL,
    total_realized_pnl_cents INTEGER NOT NULL DEFAULT 0,
    open_position_count INTEGER NOT NULL DEFAULT 0,
    last_updated TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (profile, mode)
);
```

---

## Schema manifest

The block below is strict JSON that can be extracted and parsed by tooling. It contains the same table metadata in machine-readable form.

<!-- schema-manifest:start -->
{
  "version": "phase3-task0",
  "scopes": {
    "global": {
      "db_file": "traderbot.db",
      "created_by": "daemon and data pipeline",
      "tables": [
        "schema_version",
        "profiles",
        "config",
        "market_data",
        "orderbook",
        "weather_forecasts",
        "nws_forecasts",
        "settlement_cache"
      ]
    },
    "per_agent": {
      "db_file": "{mode}-{profile}/db/decisions.db",
      "created_by": "init_decisions_db()",
      "tables": [
        "decisions",
        "positions",
        "forecast_snapshots",
        "bias_tracking",
        "learnings",
        "circuit_breaker",
        "portfolio_summary"
      ]
    }
  },
  "tables": {
    "schema_version": {
      "scope": "global",
      "columns": [
        {
          "name": "version",
          "type": "INTEGER",
          "nullable": false,
          "pk_ordinal": 1
        },
        {
          "name": "applied_at",
          "type": "TEXT",
          "nullable": false,
          "default": "datetime('now')",
          "pk_ordinal": 0
        },
        {
          "name": "description",
          "type": "TEXT",
          "nullable": true,
          "pk_ordinal": 0
        }
      ],
      "primary_key": [
        "version"
      ],
      "foreign_keys": [],
      "indexes": []
    },
    "profiles": {
      "scope": "global",
      "columns": [
        {
          "name": "name",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 1
        },
        {
          "name": "mode",
          "type": "TEXT",
          "nullable": false,
          "check": "mode IN ('backtest', 'paper', 'live')",
          "pk_ordinal": 0
        },
        {
          "name": "description",
          "type": "TEXT",
          "nullable": true,
          "pk_ordinal": 0
        },
        {
          "name": "enabled_categories",
          "type": "TEXT",
          "nullable": true,
          "note": "JSON array",
          "pk_ordinal": 0
        },
        {
          "name": "permissions",
          "type": "TEXT",
          "nullable": true,
          "note": "JSON array",
          "pk_ordinal": 0
        },
        {
          "name": "risk_multiplier",
          "type": "REAL",
          "nullable": false,
          "check": "risk_multiplier > 0 AND risk_multiplier <= 1.0",
          "pk_ordinal": 0
        },
        {
          "name": "max_position_per_market_pct",
          "type": "REAL",
          "nullable": false,
          "check": "max_position_per_market_pct > 0",
          "pk_ordinal": 0
        },
        {
          "name": "max_daily_loss_pct",
          "type": "REAL",
          "nullable": false,
          "check": "max_daily_loss_pct > 0",
          "pk_ordinal": 0
        },
        {
          "name": "max_drawdown_pct",
          "type": "REAL",
          "nullable": false,
          "check": "max_drawdown_pct > 0",
          "pk_ordinal": 0
        },
        {
          "name": "max_open_positions",
          "type": "INTEGER",
          "nullable": false,
          "check": "max_open_positions > 0",
          "pk_ordinal": 0
        },
        {
          "name": "min_liquidity_threshold",
          "type": "INTEGER",
          "nullable": false,
          "check": "min_liquidity_threshold > 0",
          "pk_ordinal": 0
        },
        {
          "name": "min_edge_pct",
          "type": "REAL",
          "nullable": false,
          "check": "min_edge_pct > 0",
          "pk_ordinal": 0
        },
        {
          "name": "initial_balance_cents",
          "type": "INTEGER",
          "nullable": true,
          "default": 10000,
          "pk_ordinal": 0
        },
        {
          "name": "created_at",
          "type": "TEXT",
          "nullable": false,
          "default": "datetime('now')",
          "pk_ordinal": 0
        },
        {
          "name": "updated_at",
          "type": "TEXT",
          "nullable": false,
          "default": "datetime('now')",
          "pk_ordinal": 0
        }
      ],
      "primary_key": [
        "name"
      ],
      "foreign_keys": [],
      "indexes": [],
      "global_migration_v1": true,
      "note": "Included in global migration v1 for Phase 4 compatibility; runtime persistence is not yet wired."
    },
    "config": {
      "scope": "global",
      "columns": [
        {
          "name": "key",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 1
        },
        {
          "name": "value",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "updated_at",
          "type": "TEXT",
          "nullable": false,
          "default": "datetime('now')",
          "pk_ordinal": 0
        }
      ],
      "primary_key": [
        "key"
      ],
      "foreign_keys": [],
      "indexes": [],
      "global_migration_v1": true,
      "note": "Included in global migration v1 for Phase 4 compatibility; runtime persistence is not yet wired."
    },
    "market_data": {
      "scope": "global",
      "source": "src/traderbot/kalshi/ws_cache.py",
      "columns": [
        {
          "name": "ticker",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 1
        },
        {
          "name": "last_price",
          "type": "REAL",
          "nullable": true,
          "pk_ordinal": 0
        },
        {
          "name": "bid",
          "type": "REAL",
          "nullable": true,
          "pk_ordinal": 0
        },
        {
          "name": "ask",
          "type": "REAL",
          "nullable": true,
          "pk_ordinal": 0
        },
        {
          "name": "volume",
          "type": "REAL",
          "nullable": true,
          "pk_ordinal": 0
        },
        {
          "name": "open_interest",
          "type": "REAL",
          "nullable": true,
          "pk_ordinal": 0
        },
        {
          "name": "updated_at",
          "type": "REAL",
          "nullable": false,
          "pk_ordinal": 0
        }
      ],
      "primary_key": [
        "ticker"
      ],
      "foreign_keys": [],
      "indexes": []
    },
    "orderbook": {
      "scope": "global",
      "source": "src/traderbot/kalshi/ws_cache.py",
      "note": "one JSON-encoded orderbook per ticker",
      "columns": [
        {
          "name": "ticker",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 1
        },
        {
          "name": "bids_json",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "asks_json",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "updated_at",
          "type": "REAL",
          "nullable": false,
          "pk_ordinal": 0
        }
      ],
      "primary_key": [
        "ticker"
      ],
      "foreign_keys": [],
      "indexes": []
    },
    "weather_forecasts": {
      "scope": "global",
      "source": "src/traderbot/data/providers/open_meteo.py",
      "columns": [
        {
          "name": "snapshot_ts",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 1
        },
        {
          "name": "city",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 2
        },
        {
          "name": "latitude",
          "type": "REAL",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "longitude",
          "type": "REAL",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "model",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 3
        },
        {
          "name": "valid_date",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 4
        },
        {
          "name": "variable",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 5
        },
        {
          "name": "value",
          "type": "REAL",
          "nullable": false,
          "pk_ordinal": 0
        }
      ],
      "primary_key": [
        "snapshot_ts",
        "city",
        "model",
        "valid_date",
        "variable"
      ],
      "foreign_keys": [],
      "indexes": []
    },
    "nws_forecasts": {
      "scope": "global",
      "source": "src/traderbot/data/providers/nws.py",
      "columns": [
        {
          "name": "snapshot_ts",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 1
        },
        {
          "name": "city",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 2
        },
        {
          "name": "forecast_date",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 3
        },
        {
          "name": "high_temp_f",
          "type": "REAL",
          "nullable": true,
          "pk_ordinal": 0
        },
        {
          "name": "low_temp_f",
          "type": "REAL",
          "nullable": true,
          "pk_ordinal": 0
        },
        {
          "name": "precip_prob",
          "type": "REAL",
          "nullable": true,
          "pk_ordinal": 0
        },
        {
          "name": "wind_speed",
          "type": "REAL",
          "nullable": true,
          "pk_ordinal": 0
        },
        {
          "name": "detailed_forecast",
          "type": "TEXT",
          "nullable": true,
          "pk_ordinal": 0
        }
      ],
      "primary_key": [
        "snapshot_ts",
        "city",
        "forecast_date"
      ],
      "foreign_keys": [],
      "indexes": []
    },
    "settlement_cache": {
      "scope": "global",
      "source": "src/traderbot/data/providers/settlement.py",
      "note": "global and authoritative; not duplicated per-agent",
      "columns": [
        {
          "name": "ticker",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 1
        },
        {
          "name": "outcome",
          "type": "INTEGER",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "settled_at",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        }
      ],
      "primary_key": [
        "ticker"
      ],
      "foreign_keys": [],
      "indexes": []
    },
    "decisions": {
      "scope": "per_agent",
      "note": "caller-generated UUID4 id; no foreign key to positions",
      "columns": [
        {
          "name": "id",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 1,
          "note": "UUID4 canonical string"
        },
        {
          "name": "timestamp",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "ticker",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "direction",
          "type": "TEXT",
          "nullable": false,
          "check": "direction IN ('yes', 'no', 'neutral')",
          "pk_ordinal": 0
        },
        {
          "name": "quantity",
          "type": "INTEGER",
          "nullable": false,
          "check": "quantity > 0",
          "pk_ordinal": 0
        },
        {
          "name": "price",
          "type": "INTEGER",
          "nullable": false,
          "note": "cents",
          "pk_ordinal": 0
        },
        {
          "name": "signal_strength",
          "type": "REAL",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "confidence",
          "type": "REAL",
          "nullable": false,
          "check": "confidence >= 0 AND confidence <= 1",
          "pk_ordinal": 0
        },
        {
          "name": "edge_estimate",
          "type": "REAL",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "risk_checks",
          "type": "TEXT",
          "nullable": false,
          "note": "JSON",
          "pk_ordinal": 0
        },
        {
          "name": "outcome",
          "type": "TEXT",
          "nullable": false,
          "check": "outcome IN ('executed', 'rejected', 'held')",
          "pk_ordinal": 0
        },
        {
          "name": "rejection_reason",
          "type": "TEXT",
          "nullable": true,
          "pk_ordinal": 0
        },
        {
          "name": "actual_result",
          "type": "INTEGER",
          "nullable": true,
          "note": "1 = yes won, 0 = no won",
          "pk_ordinal": 0
        },
        {
          "name": "mode",
          "type": "TEXT",
          "nullable": false,
          "check": "mode IN ('backtest', 'paper', 'live')",
          "pk_ordinal": 0
        },
        {
          "name": "category",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "profile",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        }
      ],
      "primary_key": [
        "id"
      ],
      "foreign_keys": [],
      "indexes": [
        {
          "name": "idx_decisions_ticker",
          "columns": [
            "ticker"
          ],
          "unique": false
        },
        {
          "name": "idx_decisions_timestamp",
          "columns": [
            "timestamp"
          ],
          "unique": false
        },
        {
          "name": "idx_decisions_ticker_timestamp",
          "columns": [
            "ticker",
            "timestamp"
          ],
          "unique": false
        },
        {
          "name": "idx_decisions_category",
          "columns": [
            "category"
          ],
          "unique": false
        },
        {
          "name": "idx_decisions_mode",
          "columns": [
            "mode"
          ],
          "unique": false
        },
        {
          "name": "idx_decisions_profile",
          "columns": [
            "profile"
          ],
          "unique": false
        },
        {
          "name": "idx_decisions_profile_mode",
          "columns": [
            "profile",
            "mode"
          ],
          "unique": false
        }
      ]
    },
    "positions": {
      "scope": "per_agent",
      "columns": [
        {
          "name": "id",
          "type": "INTEGER",
          "nullable": false,
          "pk_ordinal": 1,
          "autoincrement": true
        },
        {
          "name": "ticker",
          "type": "TEXT",
          "nullable": false,
          "unique": true,
          "pk_ordinal": 0
        },
        {
          "name": "side",
          "type": "TEXT",
          "nullable": false,
          "default": "'yes'",
          "check": "side IN ('yes', 'no')",
          "pk_ordinal": 0
        },
        {
          "name": "quantity",
          "type": "INTEGER",
          "nullable": false,
          "default": 0,
          "check": "quantity >= 0",
          "pk_ordinal": 0
        },
        {
          "name": "avg_price_cents",
          "type": "INTEGER",
          "nullable": false,
          "default": 0,
          "check": "avg_price_cents >= 0",
          "pk_ordinal": 0
        },
        {
          "name": "settlement_result",
          "type": "INTEGER",
          "nullable": true,
          "note": "1 = yes won, 0 = no won",
          "pk_ordinal": 0
        },
        {
          "name": "pnl_cents",
          "type": "INTEGER",
          "nullable": true,
          "default": 0,
          "pk_ordinal": 0
        },
        {
          "name": "status",
          "type": "TEXT",
          "nullable": false,
          "default": "'open'",
          "check": "status IN ('open', 'closed', 'settled')",
          "pk_ordinal": 0
        },
        {
          "name": "mode",
          "type": "TEXT",
          "nullable": false,
          "check": "mode IN ('backtest', 'paper', 'live')",
          "pk_ordinal": 0
        },
        {
          "name": "category",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "profile",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "updated_at",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        }
      ],
      "primary_key": [
        "id"
      ],
      "foreign_keys": [],
      "indexes": [
        {
          "name": "idx_positions_status",
          "columns": [
            "status"
          ],
          "unique": false
        },
        {
          "name": "idx_positions_category",
          "columns": [
            "category"
          ],
          "unique": false
        },
        {
          "name": "idx_positions_mode",
          "columns": [
            "mode"
          ],
          "unique": false
        },
        {
          "name": "idx_positions_profile",
          "columns": [
            "profile"
          ],
          "unique": false
        },
        {
          "name": "idx_positions_profile_mode",
          "columns": [
            "profile",
            "mode"
          ],
          "unique": false
        }
      ]
    },
    "forecast_snapshots": {
      "scope": "per_agent",
      "columns": [
        {
          "name": "id",
          "type": "INTEGER",
          "nullable": false,
          "pk_ordinal": 1,
          "autoincrement": true
        },
        {
          "name": "ticker",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "category",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "source",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "metric",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "predicted_value",
          "type": "REAL",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "predicted_for_date",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "snapshot_date",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "lead_time_days",
          "type": "INTEGER",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "confidence",
          "type": "REAL",
          "nullable": true,
          "pk_ordinal": 0
        },
        {
          "name": "model_consensus_score",
          "type": "REAL",
          "nullable": true,
          "pk_ordinal": 0
        },
        {
          "name": "metadata",
          "type": "TEXT",
          "nullable": true,
          "note": "JSON",
          "pk_ordinal": 0
        },
        {
          "name": "created_at",
          "type": "TEXT",
          "nullable": false,
          "default": "datetime('now')",
          "pk_ordinal": 0
        }
      ],
      "primary_key": [
        "id"
      ],
      "unique": [
        {
          "name": "uq_forecast_snapshots",
          "columns": [
            "ticker",
            "source",
            "metric",
            "snapshot_date",
            "predicted_for_date"
          ]
        }
      ],
      "foreign_keys": [],
      "indexes": [
        {
          "name": "idx_forecast_snapshots_lookup",
          "columns": [
            "ticker",
            "predicted_for_date",
            "snapshot_date"
          ],
          "unique": false
        },
        {
          "name": "idx_forecast_snapshots_source_lead",
          "columns": [
            "source",
            "lead_time_days"
          ],
          "unique": false
        },
        {
          "name": "idx_forecast_snapshots_category",
          "columns": [
            "category",
            "predicted_for_date"
          ],
          "unique": false
        }
      ]
    },
    "bias_tracking": {
      "scope": "per_agent",
      "columns": [
        {
          "name": "id",
          "type": "INTEGER",
          "nullable": false,
          "pk_ordinal": 1,
          "autoincrement": true
        },
        {
          "name": "category",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "source",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "metric",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "predicted_value",
          "type": "REAL",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "actual_value",
          "type": "REAL",
          "nullable": true,
          "pk_ordinal": 0
        },
        {
          "name": "predicted_at",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "actual_at",
          "type": "TEXT",
          "nullable": true,
          "pk_ordinal": 0
        },
        {
          "name": "lead_time_hours",
          "type": "INTEGER",
          "nullable": true,
          "pk_ordinal": 0
        },
        {
          "name": "error",
          "type": "REAL",
          "nullable": true,
          "note": "actual - predicted",
          "pk_ordinal": 0
        },
        {
          "name": "created_at",
          "type": "TEXT",
          "nullable": false,
          "default": "datetime('now')",
          "pk_ordinal": 0
        }
      ],
      "primary_key": [
        "id"
      ],
      "unique": [
        {
          "name": "uq_bias_tracking",
          "columns": [
            "category",
            "source",
            "metric",
            "predicted_at"
          ]
        }
      ],
      "foreign_keys": [],
      "indexes": [
        {
          "name": "idx_bias_tracking_category_source",
          "columns": [
            "category",
            "source"
          ],
          "unique": false
        },
        {
          "name": "idx_bias_tracking_metric",
          "columns": [
            "category",
            "metric",
            "predicted_at"
          ],
          "unique": false
        }
      ]
    },
    "learnings": {
      "scope": "per_agent",
      "note": "created by init_decisions_db(), not on demand",
      "columns": [
        {
          "name": "id",
          "type": "INTEGER",
          "nullable": false,
          "pk_ordinal": 1,
          "autoincrement": true
        },
        {
          "name": "category",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "pattern_key",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "description",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "recurrence_count",
          "type": "INTEGER",
          "nullable": true,
          "default": 1,
          "pk_ordinal": 0
        },
        {
          "name": "justification",
          "type": "TEXT",
          "nullable": true,
          "pk_ordinal": 0
        },
        {
          "name": "impact",
          "type": "TEXT",
          "nullable": true,
          "pk_ordinal": 0
        },
        {
          "name": "priority",
          "type": "TEXT",
          "nullable": true,
          "check": "priority IN ('low', 'medium', 'high')",
          "pk_ordinal": 0
        },
        {
          "name": "status",
          "type": "TEXT",
          "nullable": true,
          "default": "'active'",
          "check": "status IN ('active', 'promoted', 'resolved', 'dismissed')",
          "pk_ordinal": 0
        },
        {
          "name": "created_at",
          "type": "TEXT",
          "nullable": false,
          "default": "datetime('now')",
          "pk_ordinal": 0
        },
        {
          "name": "updated_at",
          "type": "TEXT",
          "nullable": false,
          "default": "datetime('now')",
          "pk_ordinal": 0
        }
      ],
      "primary_key": [
        "id"
      ],
      "foreign_keys": [],
      "indexes": [
        {
          "name": "idx_learnings_category",
          "columns": [
            "category"
          ],
          "unique": false
        },
        {
          "name": "idx_learnings_status",
          "columns": [
            "status"
          ],
          "unique": false
        },
        {
          "name": "idx_learnings_priority",
          "columns": [
            "priority"
          ],
          "unique": false
        }
      ]
    },
    "circuit_breaker": {
      "scope": "per_agent",
      "columns": [
        {
          "name": "profile",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 1
        },
        {
          "name": "mode",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 2,
          "check": "mode IN ('backtest', 'paper', 'live')"
        },
        {
          "name": "state",
          "type": "TEXT",
          "nullable": false,
          "default": "'green'",
          "check": "state IN ('green', 'yellow', 'red', 'full_stop')",
          "pk_ordinal": 0
        },
        {
          "name": "trigger_reason",
          "type": "TEXT",
          "nullable": true,
          "pk_ordinal": 0
        },
        {
          "name": "triggered_at",
          "type": "TEXT",
          "nullable": true,
          "pk_ordinal": 0
        },
        {
          "name": "updated_at",
          "type": "TEXT",
          "nullable": false,
          "default": "datetime('now')",
          "pk_ordinal": 0
        }
      ],
      "primary_key": [
        "profile",
        "mode"
      ],
      "foreign_keys": [],
      "indexes": []
    },
    "portfolio_summary": {
      "scope": "per_agent",
      "columns": [
        {
          "name": "profile",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 1
        },
        {
          "name": "mode",
          "type": "TEXT",
          "nullable": false,
          "pk_ordinal": 2,
          "check": "mode IN ('backtest', 'paper', 'live')"
        },
        {
          "name": "initial_balance_cents",
          "type": "INTEGER",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "current_balance_cents",
          "type": "INTEGER",
          "nullable": false,
          "pk_ordinal": 0
        },
        {
          "name": "total_realized_pnl_cents",
          "type": "INTEGER",
          "nullable": false,
          "default": 0,
          "pk_ordinal": 0
        },
        {
          "name": "open_position_count",
          "type": "INTEGER",
          "nullable": false,
          "default": 0,
          "pk_ordinal": 0
        },
        {
          "name": "last_updated",
          "type": "TEXT",
          "nullable": false,
          "default": "datetime('now')",
          "pk_ordinal": 0
        }
      ],
      "primary_key": [
        "profile",
        "mode"
      ],
      "foreign_keys": [],
      "indexes": []
    }
  },
  "semantics": {
    "profile_not_agent": true,
    "profile_and_mode_tables": [
      "decisions",
      "positions",
      "circuit_breaker",
      "portfolio_summary"
    ],
    "no_decisions_to_positions_fk": true,
    "no_per_agent_settlement_cache": true,
    "settlement_authoritative_scope": "global",
    "init_decisions_db_creates_learnings": true,
    "phase4_profiles_config_not_yet_wired": true,
    "decision_id_uuid4": true
  }
}
<!-- schema-manifest:end -->

---

## Reconciliation checklist

Use this checklist when comparing this document to production code or when onboarding a new database module.

- [ ] `market_data` columns match `src/traderbot/kalshi/ws_cache.py` exactly: `ticker TEXT PRIMARY KEY`, `last_price REAL`, `bid REAL`, `ask REAL`, `volume REAL`, `open_interest REAL`, `updated_at REAL NOT NULL`.
- [ ] `orderbook` is one row per ticker: `bids_json TEXT NOT NULL`, `asks_json TEXT NOT NULL`, `updated_at REAL NOT NULL`. It is not a multi-row `(ticker, side, price_dollars)` table.
- [ ] `weather_forecasts` includes `snapshot_ts`, `latitude`, `longitude`, `model`, `valid_date`, `variable`, `value`, with PK `(snapshot_ts, city, model, valid_date, variable)`.
- [ ] `nws_forecasts` includes `snapshot_ts`, `forecast_date`, `high_temp_f`, `low_temp_f`, `precip_prob`, `wind_speed`, `detailed_forecast`, with PK `(snapshot_ts, city, forecast_date)`.
- [ ] `settlement_cache` is global only. It has exactly `ticker TEXT PRIMARY KEY`, `outcome INTEGER NOT NULL`, `settled_at TEXT NOT NULL`.
- [ ] `schema_version`, `profiles`, and `config` are present in the global schema. `profiles` and `config` are Phase 4 compatibility tables, not yet backed by runtime persistence code.
- [ ] Per-agent `decisions.db` has exactly seven tables: `decisions`, `positions`, `forecast_snapshots`, `bias_tracking`, `learnings`, `circuit_breaker`, `portfolio_summary`.
- [ ] `decisions.id` is `TEXT PRIMARY KEY` and stores a caller-generated canonical UUID4 string (`str(uuid.uuid4())`).
- [ ] `decisions` has no foreign key to `positions(ticker)`.
- [ ] `learnings` is created by `init_decisions_db()`, not on demand.
- [ ] No per-agent table uses an `agent` column. Use `profile` instead.
- [ ] Only `decisions`, `positions`, `circuit_breaker`, and `portfolio_summary` carry both `profile` and `mode` columns.
- [ ] Settlement outcomes remain authoritative in the global `settlement_cache`; per-agent queries read from `~/.traderbot/traderbot.db`.
- [ ] The JSON manifest between `<!-- schema-manifest:start -->` and `<!-- schema-manifest:end -->` parses with `json.loads`, lists every table, and includes `primary_key`, `foreign_keys`, and structured `indexes` entries.

---

## ChromaDB collections (embedded)

ChromaDB uses an embedded `PersistentClient` at `~/.traderbot/chromadb/` owned by the daemon. No HTTP server or external embedding-function configuration is used. Callers supply explicit vectors.

### Shared collections

| Collection | Documents | Category filter |
|---|---|---|
| `news` | News articles with embeddings | `where={"category": "weather"}` |
| `data_points` | Quantitative data points | `where={"category": "weather"}` |
| `market_patterns` | Pattern signatures | `where={"category": "weather"}` |
| `news_signals` | Processed news signals | `where={"category": "weather"}` |
| `market_conditions` | Market resolution conditions | Shared (no category filter) |

### Per-agent collection naming

Profile names in storage are lowercase hyphenated `[a-z0-9]+(?:-[a-z0-9]+)*`, max 44 characters, with no underscores and no reserved names such as `sysadmin` for non-SysAdmin identities. Collection names are built by replacing `-` with `_` (underscores are forbidden in source names, so this is collision-free) and appending `_{mode}_{kind}`. The canonical SysAdmin collections are the mode-less exception.

Examples:

- Weather paper decisions: `weather_paper_decisions`
- Weather paper learnings: `weather_paper_learnings`
- SysAdmin decisions: `sysadmin_decisions`
- SysAdmin learnings: `sysadmin_learnings`

The MCP server enforces category filtering on shared collections and restricts per-agent collections to their owning profile.

---

## SQLite tuning

Recommended PRAGMAs for the global and per-agent databases:

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=5000;
PRAGMA cache_size=-64000;
PRAGMA temp_store=MEMORY;
PRAGMA mmap_size=268435456;
PRAGMA foreign_keys=ON;
```

Additional operational notes:

- Run `PRAGMA wal_checkpoint(TRUNCATE)` periodically to keep WAL size bounded.
- VACUUM per-agent databases when promoting from backtest to paper.
- Monitor database file sizes and alert above thresholds.

---

## Data retention policy

| Data type | Retention |
|---|---|
| News articles | 6 months, then archive |
| Positions | Retain all for active modes; archive after settlement + 90 days |
| Decisions | Retain all (audit trail) |
| Forecast snapshots | 6 months for backtesting, then archive |
| ChromaDB vectors | Per collection policy |

---

## GRIB2 processing pipeline (DD-033)

Implementation is deferred from Phase 3 and tracked in [issue #194](https://github.com/JsonDaRula69/TraderBot/issues/194). Phase 3 implements the `forecast_snapshots` storage contract only; it does not add GRIB2 providers or `cfgrib`.

### Phase 1 (ships with v2 core)

Use Open-Meteo Archive API + NWS forecasts + Kalshi historical data (day-0 only). Backtests use same-day forecasts, which slightly inflates certainty. This is acceptable for initial development.

### Phase 2 (after core is stable)

Add `data/providers/gfs.py` and `data/providers/ecmwf.py` to process GRIB2 from AWS S3. Store true multi-day lead time forecasts in `forecast_snapshots` with `lead_time_days > 0`. Optional dependency: `pip install traderbot[weather-backtest]`.

---

## Appendix: Current deployed Phase 2 schema

These are the exact `CREATE TABLE` statements found in the current production source as of the Task 0 pass. They are the source of truth until implementation changes them.

### `src/traderbot/kalshi/ws_cache.py`

```sql
CREATE TABLE IF NOT EXISTS market_data (
    ticker TEXT PRIMARY KEY,
    last_price REAL,
    bid REAL,
    ask REAL,
    volume REAL,
    open_interest REAL,
    updated_at REAL NOT NULL
)

CREATE TABLE IF NOT EXISTS orderbook (
    ticker TEXT PRIMARY KEY,
    bids_json TEXT NOT NULL,
    asks_json TEXT NOT NULL,
    updated_at REAL NOT NULL
)
```

### `src/traderbot/data/providers/open_meteo.py`

```sql
CREATE TABLE IF NOT EXISTS weather_forecasts (
    snapshot_ts TEXT NOT NULL,
    city TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    model TEXT NOT NULL,
    valid_date TEXT NOT NULL,
    variable TEXT NOT NULL,
    value REAL NOT NULL,
    PRIMARY KEY (snapshot_ts, city, model, valid_date, variable)
)
```

### `src/traderbot/data/providers/nws.py`

```sql
CREATE TABLE IF NOT EXISTS nws_forecasts (
    snapshot_ts TEXT NOT NULL,
    city TEXT NOT NULL,
    forecast_date TEXT NOT NULL,
    high_temp_f REAL,
    low_temp_f REAL,
    precip_prob REAL,
    wind_speed REAL,
    detailed_forecast TEXT,
    PRIMARY KEY (snapshot_ts, city, forecast_date)
)
```

### `src/traderbot/data/providers/settlement.py`

```sql
CREATE TABLE IF NOT EXISTS settlement_cache (
    ticker TEXT PRIMARY KEY,
    outcome INTEGER NOT NULL,
    settled_at TEXT NOT NULL
)
```
