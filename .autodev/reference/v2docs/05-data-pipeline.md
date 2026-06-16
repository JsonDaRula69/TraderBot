# TraderBot v2 — Data Pipeline

> This document covers the unified data collection, processing, and storage architecture. Grounded in DD-016, DD-020, DD-027, DD-028, DD-029, DD-033, DD-035.

---

## Architecture: TraderBot Fetches, Agents Query

The TraderBot service is a single always-on process that combines the data pipeline, MCP server, and token rotation. It starts at boot and runs continuously (DD-016).

**Key principle**: TraderBot proactively fetches and organizes data on a schedule. Agents request information via MCP tools, which query local databases. This eliminates per-request API latency and reduces redundant API calls.

```
TraderBot Service (always-on)
│
├── Kalshi WebSocket (continuous)
│   ├── Market lifecycle events (market_lifecycle_v2)
│   ├── Ticker updates (real-time prices)
│   ├── Orderbook snapshots
│   ├── Order fills and status
│   └── Cached locally, sub-millisecond access for MCP queries
│
├── Data Collection Workers (scheduled)
│   ├── News ingest: fetches NewsAPI + Reddit + Twitter → embed → ChromaDB (30 min)
│   ├── Weather data: fetches NWS forecasts + Open-Meteo historical → SQLite + ChromaDB (1h)
│   ├── Economic indicators: fetches FRED → SQLite (daily)
│   ├── Crypto prices: fetches CoinGecko → SQLite (15 min, if crypto enabled)
│   ├── Sports data: fetches TheSportsDB → SQLite (daily, if sports enabled)
│   └── Settlement monitor: checks recently settled markets → settlement_cache (1h)
│
├── MCP Server (stdio, responds to agent tool calls)
│   ├── Reads from local databases, NOT external APIs
│   ├── Returns WebSocket-cached data for real-time requests
│   ├── Returns SQLite/ChromaDB data for historical queries
│   ├── Validates agent identity and category permissions
│   └── Sub-millisecond response for cached data
│
├── Token Rotation (every 4 hours)
│   └── Rotates all agent profile tokens via Infisical
│
└── Local Databases
    ├── SQLite: per-agent per-mode databases
    ├── ChromaDB: shared collections with category metadata
    └── WebSocket cache: real-time Kalshi prices, orderbooks, fills
```

---

## WebSocket-First Kalshi Data (DD-016)

The Kalshi WebSocket is the **sole source for all real-time Kalshi data**. REST API is used only for:

1. Seeding the cache on startup when WebSocket is not yet connected
2. Recovering from WebSocket disconnections
3. Fetching historical data (settled markets, candlesticks, historical trades)

No REST polling for current market data — the WebSocket provides a continuous stream, and any REST call for data that the WebSocket already provides is a bug.

**Channels subscribed**:
- `market_lifecycle_v2`: detects new markets as they appear — no REST scan needed
- Ticker updates: real-time price changes
- Orderbook snapshots: bid/ask depth
- Order fills and status: trade execution confirmations

---

## Unified Data Module (DD-028)

The `news/` package is retired. All data fetching and processing moves to a unified `data/` module:

```
src/traderbot/data/
├── __init__.py
├── pipeline.py              # DataCollectionService (always-on orchestrator)
├── scheduler.py             # Rate-limited scheduling (per-source rate limits)
├── base_provider.py          # BaseDataProvider ABC
├── base_signals.py           # BaseSignalEngine ABC
├── registry.py               # Provider registry
├── providers/                # One subpackage per source
│   ├── newsapi.py            # NewsAPI (articles only)
│   ├── reddit.py             # Reddit RSS (articles only)
│   ├── twitter.py            # Twitter/X stub
│   ├── kalshi.py             # Kalshi market data + candlesticks
│   ├── fred.py                # FRED economic data
│   ├── coingecko.py          # CoinGecko crypto data
│   ├── open_meteo.py          # Open-Meteo forecasts + archive
│   ├── openweathermap.py     # OpenWeatherMap current weather
│   ├── nws.py                 # NWS forecasts
│   ├── thesportsdb.py        # Sports data
│   ├── google_trends.py      # Google Trends
│   └── voyage.py              # VoyageAI embeddings
├── weather/                  # Weather-specific logic
│   ├── signals.py             # WeatherSignalEngine
│   ├── geo.py                 # City/coordinate mapping
│   └── bias.py                # Forecast bias tracking
├── processing/                # Post-fetch enrichment
│   ├── classifier.py          # Category classification
│   ├── sentiment.py           # Sentiment scoring
│   ├── impact.py              # Impact assessment
│   └── embed.py               # VoyageAI embedding
└── models.py                  # Shared data models
```

**What gets retired**: The entire `news/` package is deprecated and eventually removed.

---

## All Data Sources Collect at Install Time (DD-027)

All data sources begin collection at install, not just enabled categories. This ensures:
- Backtesting data is available for any category the user might enable later
- The 6-month backfill populates data for all categories
- The user doesn't need to wait for data collection before enabling a new category

The `--categories` flag for backfill becomes less critical since all categories are always backfilled, but may still be useful for re-backfilling a single category.

---

## Historical Data Sources for Backtesting (DD-020, DD-033)

### Tier 1: Available Now (Ship with Initial v2)

| Data | Source | Format | Status |
|---|---|---|---|
| Historical NWS forecasts | NWS API | JSON | Ready to use (day-0 only) |
| Open-Meteo Historical Forecast | Open-Meteo Archive API | JSON | Ready to use (day-0 only) |
| Kalshi historical market data | HistoryService | JSON | Ready to use |
| Kalshi historical orderbooks | Candlestick API (bid/ask OHLC + trade prices) | JSON | 1min/1hr/1day granularity |
| Kalshi forecast percentiles | `forecast_percentile_history` API | JSON | Up to 5-second granularity |
| Historical news with timestamps | ChromaDB with published_at | Vector | Verify metadata integrity |
| Historical bias data | forecast_bias SQLite (time-filtered) | SQLite | Ensure no look-ahead bias |

**Known limitation**: Tier 1 provides day-0 forecasts only. Backtesting results for weather agents will be slightly inflated because the agent always sees same-day forecast accuracy, not the degraded accuracy of multi-day lead times. This is acceptable for initial development.

### Tier 2: GRIB2 Processing Pipeline (Build After v2 Core)

True multi-day lead time forecasts from NOAA GFS and ECMWF, stored in GRIB2 format on AWS S3.

**Implementation plan** (DD-033):
1. Provider modules: `data/providers/gfs.py` and `data/providers/ecmwf.py`
2. Optional dependency: `cfgrib` via `pip install traderbot[weather-backtest]`
3. Processing flow: Download grid points for 15 Kalshi cities → Extract temperature, precipitation, wind → Store in `forecast_snapshots` table with `lead_time_days` column
4. Deploy integration: Offer optional 6-month backfill during `traderbot deploy` (5-10 GB compressed, skip by default)
5. Ongoing collection: Archive GFS runs every 6 hours, ECMWF every 12 hours

### Tier 3: Kalshi Market Data (Archiving)

Historical Kalshi orderbook data available via the API. Archiving should begin immediately as it's straightforward to collect and provides essential backtesting data.

---

## P&L and Settlement Consolidation (DD-029)

P&L calculation and settlement logic is consolidated into a single `trading.py` module:

- **Unified `compute_pnl(direction, entry_price, exit_price, quantity)`**: One function, called by all modules
- **Unified `settle_position(ticker, outcome)`**: Routes to correct settlement method based on mode
- **Mode-aware settlement**:
  - Backtest: historical data, MCP server checks at sim-time
  - Paper: `SettlementVerifier` checks settled markets, auto-settles weather bets
  - Live: `reconcile_settlements` syncs with Kalshi

**What moves where**:

| Current | v2 Location |
|---|---|
| `paper.py` (balance computation) | `traderbot/trading.py` |
| `simulation/paper_trader.py` (PaperTrader, PaperSlippageModel) | `traderbot/trading.py` |
| `simulation/settlement.py` (weather settlement) | `traderbot/trading.py` |
| `simulation/settlement.py` (Kalshi settlement) | `traderbot/kalshi/settlement.py` |
| `simulation/performance.py` (metrics) | `traderbot/analysis/portfolio.py` |
| `simulation/adaptation.py` (BayesianAdapter) | `traderbot/analysis/adaptation.py` |
| `simulation/engine.py` (BacktestEngine) | `traderbot/simulation/engine.py` (renamed to StatisticalBacktestEngine) |
| `cli/trade.py` (business logic) | `traderbot/trading.py` (service) + `cli/trade.py` (thin handler) |

---

## Category-Specific Analysis Toolkits (DD-035)

Each category agent receives a custom set of MCP tools designed for its domain. TraderBot provides *interpretive statistical outputs*, not directional trading calls.

### Weather Toolkit (First Implementation)

| Tool | Purpose | Key Output |
|---|---|---|
| `traderbot__weather_forecast_prob` | Calibrated probability estimate with confidence interval | estimated_prob, confidence_interval, calibration_score, sources, model_consensus |
| `traderbot__weather_accuracy` | Historical forecast accuracy by source, city, lead time | brier_score, mean_abs_error, by_lead_time, recent_trend |
| `traderbot__weather_seasonal_context` | Historical temperature distributions and recent anomalies | historical_distribution (percentiles), recent_anomaly, climate_patterns |
| `traderbot__weather_decision_brief` | Assembled analytical brief for a specific market/ticker | Combined output from all weather tools + market_edge |
| `traderbot__market_edge` (shared) | Market-implied probability, spread, liquidity | estimated_edge, market_implied_prob, spread, volume |
| `traderbot__market_prices` (shared) | Current and historical price data | prices, orderbook_depth, recent_trades |

**Key design decisions**:
- City-month-specific σ values (no more hardcoded sigma=5.0)
- Calibration curves from historical accuracy data
- Lead-time decay: probability estimates widen as lead time increases
- Interpretive notes help the agent understand the numbers, but the tool never says "buy yes" or "buy no"

### General-Purpose Tools (All Categories)

```
traderbot__market_edge      — Market-implied probability, spread, liquidity, edge assessment
traderbot__market_prices    — Current and historical price data from Kalshi WebSocket/cache
```

### Future Toolkits (Design Pending)

- Election toolkit: `traderbot__election_poll_aggregate`, `traderbot__election_demographic`, `traderbot__election_accuracy`, `traderbot__election_decision_brief`
- Crypto toolkit: `traderbot__crypto_volatility`, `traderbot__crypto_onchain`, `traderbot__crypto_accuracy`, `traderbot__crypto_decision_brief`
- Other categories follow the same pattern, designed from scratch for each domain

### What Gets Retired

| Current | Reason |
|---|---|
| `analysis/signals.py` (GenericAnalyzer) | Replaced by category-specific toolkits |
| `data/weather/signals.py` (WeatherSignalEngine) | Replaced by weather toolkit tools |
| `generate_signal()` (directional trading calls) | Agents make decisions, TraderBot provides analysis |
| `cli/news.py` | Eventually retired — all data access becomes MCP tools |
