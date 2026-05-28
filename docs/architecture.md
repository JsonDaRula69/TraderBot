# Architecture

TraderBot's architecture is built around one principle: **the toolkit is a dumb pipe with smart guards.** It handles execution correctness and risk enforcement, but the agent decides strategy.

## Isolated Cron Jobs

The agent operates via independent isolated cron jobs registered via `openclaw cron add --session isolated`, each with a distinct responsibility. This replaces the old monolithic "three-loop" design (Decision/Heartbeat/News) with isolated, collision-free execution.

### Agent Cron Jobs (8 jobs)

Registered via `traderbot cron setup-heartbeat-tasks`:

| Job Name | Schedule | Command | Purpose |
|---|---|---|---|
| `circuit-breaker-check` | `*/30 * * * *` | `traderbot halt --json` | Check circuit breaker state; surface SLOW/CRITICAL alerts |
| `data-forecast-check` | `*/30 * * * *` | `traderbot data forecasts --cities NYC,CHI,LA,PHX,SEA --json` | Verify NWS and ensemble data availability |
| `news-scan` | `*/30 * * * *` | `traderbot news-context weather --json` | Scan for NHC advisories, NWS warnings, emergency declarations |
| `position-health` | `0 * * * *` | `traderbot positions --json` | Check positions with settlement < 48h, drawdown > 5% |
| `settlement-monitor` | `0 * * * *` | `traderbot check-settlements --json` | Check for recently settled markets and update positions DB |
| `performance-review` | `0 */6 * * *` | `traderbot heartbeat --json` | Review drawdown, win rate, learning promotions |
| `learning-promotion` | `0 */6 * * *` | `traderbot learnings --promote` | Promote recurring learnings (Recurrence-Count >= 3) |
| `pipeline-health` | `0 */6 * * *` | `systemctl list-timers --all \| grep traderbot` | Verify data pipeline timers are active and data is fresh |

All agent cron jobs use `--session isolated` for collision-free execution. The `settlement-monitor` job is explicitly marked isolated in its job definition.

### Sysadmin Cron Setup (3 jobs)

The `traderbot cron setup` command registers legacy-format loops as isolated cron jobs:

| Job Name | Schedule | Session | Purpose |
|---|---|---|---|
| `decision_loop` | `*/5 * * * *` | isolated | Agent trading decision cycle |
| `heartbeat_loop` | `0 */6 * * *` | isolated | Performance review and adaptation |
| `news_ingest` | `*/30 * * * *` | isolated | News and data point ingestion |

### Offline Data Pipelines (systemd timers)

| Timer | Frequency | Command | Purpose |
|---|---|---|---|
| `traderbot-news-ingest@.timer` | Every 30 min | `traderbot news-ingest` | Fetch, classify, embed news + data points to ChromaDB |
| `traderbot-backfill-data@.timer` | Daily (midnight) | `traderbot backfill --months 1` | Incremental historical data enrichment (Open-Meteo, FRED, CoinGecko) |

## Component Map

```
┌───────────────────────────────────────────────────────────────┐
│                     OpenClaw Agent                             │
│  (strategy decisions, market interpretation, sizing)          │
└───────────────┬───────────────────────────────────────────────┘
                │ calls via exec
                ▼
┌───────────────────────────────────────────────────────────────┐
│  cli/ — CLI package (9 modules + 2 infrastructure)            │
│                                                                │
│  Sub-apps (app.add_typer):                                     │
│    auth/ • cron/ • sandbox/ • profile/ • data/                 │
│  Flat commands (register_commands):                            │
│    trade • market • news • admin                               │
│  Plus: experiment/ (separate Typer sub-app)                    │
│  Root: update, update-configure, uninstall                     │
└──────┬────────┬──────────┬──────────┬──────────┬──────────────┘
       │        │          │          │          │
       ▼        ▼          ▼          ▼          ▼
  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────────┐
  │ kalshi │ │analysis │ │  risk  │ │  news  │ │experiment   │
  │        │ │        │ │        │ │        │ │             │
  │ client │ │indic.  │ │limits  │ │sources │ │shared       │
  │ models │ │odds    │ │sizing  │ │classif.│ │registry     │
  │ markets│ │signals │ │breaker │ │sentim. │ │harness      │
  │ trading│ │        │ │audit   │ │impact  │ │results      │
  │ history│ │        │ │        │ │embed.  │ │populate     │
  │ portf. │ │        │ │        │ │vectors │ │treatments   │
  │ ws     │ │        │ │        │ │ingest  │ │methodologies│
  └───┬────┘ └────────┘ └────┬───┘ └────────┘ └──────┬─────┘
      │                      │                           │
      ▼                      ▼                           ▼
  ┌────────┐            ┌────────┐              ┌──────────────┐
  │ Kalshi │            │  db    │              │ experiment db│
  │   API  │            │positions│              │  (5 tables)  │
  │        │            │decisions│              │    + LLM     │
  └────────┘            │learnings│              └──────────────┘
                        │ chroma  │
                        │ vectors │     ┌──────────────────┐
                        │forecast │     │ data/ package    │
                        │  _bias  │     │                  │
                        │reconcil │     │ base_provider ABC│
                        └────────┘     │ base_signals  ABC│
                                       │ registry         │
  ┌──────────────────────┐             │ models           │
  │ data/weather/        │             │ weather/          │
  │                      │             └──────────────────┘
  │ nws_client.py        │
  │ provider.py          │    ┌──────────────────────────┐
  │ signals.py           │    │ db/reconciliation.py     │
  │                      │    │                          │
  │ NWS + Open-Meteo     │    │ reconcile_positions()    │
  │ ensemble (GFS/ECMWF/ │    │ reconcile_settlements()  │
  │ GEM)                 │    │ reconcile_all()          │
  └──────────────────────┘    └──────────────────────────┘
```

## Toolkit vs. Agent Boundary

The critical design boundary. Crossing it means the toolkit is making decisions it shouldn't.

| Concern | Toolkit Owns | Agent Owns |
|---|---|---|
| API authentication & request signing | ✅ | |
| Data normalization into Pydantic models | ✅ | |
| Rate limiting & retry logic | ✅ | |
| Order lifecycle (place, cancel, track fills) | ✅ | |
| Risk guard enforcement (position limits, circuit breakers) | ✅ | |
| Statistical computation (indicators, probability) | ✅ | |
| Position tracking & PnL sync | ✅ | |
| Settlement monitoring & reconciliation | ✅ | |
| Audit trail (logging decisions with context) | ✅ | |
| Semantic embedding & similarity computation | ✅ | |
| **Strategy selection** (what approach to use) | | ✅ |
| **Market interpretation** (why this market is attractive) | | ✅ |
| **Position sizing** (how much to risk) | | ✅ (within guard rails) |
| **Risk appetite** (acceptable overall loss level) | | ✅ |
| **Entry/exit timing** | | ✅ |

The toolkit computes, enforces, and executes. The agent decides, interprets, and sizes. Risk guards sit between them — the agent can request any trade, but the toolkit has veto power.

## CLI Package Architecture

The CLI is organized as a Typer package at `cli/` with 9 command modules and 2 infrastructure files:

### Sub-App Registration Pattern

Two registration patterns are used:

1. **Sub-apps** (`app.add_typer`): `auth`, `cron`, `sandbox`, `profile`, `data` — each creates its own `typer.Typer()` instance and is mounted as a named sub-group.

2. **Flat commands** (`register_commands(parent_app)`): `trade`, `market`, `news`, `admin` — each module defines a `register_commands()` function that attaches `@parent_app.command()` handlers directly to the parent app.

3. **External sub-app**: `experiment/` is imported from outside `cli/` and mounted as `app.add_typer(experiment_app, name="experiment")`.

### Module Inventory

| Module | Pattern | Commands |
|---|---|---|
| `__init__.py` | Root wiring | `update`, `update-configure`, `uninstall` |
| `helpers.py` | Infrastructure | Defines root `app`, `_resolve_db_path`, `_with_db`, `_python_version_ok` |
| `auth/` | Sub-app | `list-keys`, `rotate`, `check`, `setup-master-password`, `change-master-password`, `check-master-password`, `set-kalshi`, `migrate`, `delete-key`, `clear-session` |
| `cron/` | Sub-app | `setup`, `setup-heartbeat-tasks`, `remove`, `remove-heartbeat-tasks`, `heartbeat-configure` |
| `sandbox/` | Sub-app | `shell`, `eval` |
| `profile/` | Sub-app | `create`, `list`, `select`, `show`, `delete` |
| `data/` | Sub-app | `forecasts`, `signals`, `bias` |
| `trade/` | Flat | `trade`, `positions`, `audit`, `backtest`, `paper`, `compare`, `analyze`, `performance`, `reconcile`, `check-settlements` |
| `market/` | Flat | `scan`, `signals`, `sentiment` |
| `news/` | Flat | `news`, `news-ingest`, `news-context`, `backfill`, `data-points`, `news-summary` |
| `admin/` | Flat | `bootstrap`, `heartbeat`, `halt`, `resume`, `learnings`, `backfill`, `cache-warm` |

### Experiment CLI

The `experiment/` package provides its own Typer sub-app with commands:

| Command | Purpose |
|---|---|
| `populate` | Fetch market data from Kalshi + forecasts from Open-Meteo into experiment DB |
| `verify` | Validate experiment DB integrity |
| `run` | Execute a within-subjects experiment |
| `results` | Score a completed experiment run |
| `list-treatments` | List available treatment classes |

## Experiment Infrastructure

The experiment system runs A/B tests of trading treatments against prediction-market data, measuring whether LLM-driven decision strategies outperform market-implied probability baselines.

### Database Schema

`db/experiment_schema.py` — `create_tables(conn)` creates 5 SQLite tables:

| Table | Purpose |
|---|---|
| `markets` | Market metadata: ticker, question, city, strike_type, strike_value, resolution_date, settlement_result, prices, volume |
| `forecast_snapshots` | Temperature forecasts from Open-Meteo per ticker, with `days_before` and `source` |
| `market_prices` | Price time series per ticker: timestep, yes_price_cents, no_price_cents |
| `settlement_actuals` | Resolved outcomes: actual_temp_f, settlement_date |
| `agent_decisions` | Experiment decisions: run_id, treatment, ticker, timestep, decision, estimated_prob, confidence, reasoning, timestamp |

### Shared Interface

`experiment/shared.py` — the contract every treatment must follow:

```python
class TreatmentInterface(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def bypass_llm(self) -> bool:  # Default False; True for control treatments

    @abstractmethod
    def format_prompt(self, ctx: TreatmentContext) -> str: ...

    @abstractmethod
    def validate_response(self, response: dict) -> ValidatedDecision: ...
```

`TreatmentContext` bundles market data, forecast, accuracy metrics, prices, technical indicators, and prior decisions into a single frozen dataclass passed to every treatment.

`ValidatedDecision` enforces valid `decision` values (`buy_yes`, `buy_no`, `skip`), bounded `estimated_prob` and `confidence` in [0.0, 1.0], and non-empty `reasoning`.

### Treatment Registry

`experiment/registry.py` — auto-discovery and lookup:

| Function | Signature | Purpose |
|---|---|---|
| `discover_treatments` | `() -> dict[str, type]` | Scan `treatments/` package for TreatmentInterface subclasses |
| `register_treatment` | `(name: str, cls: type) -> None` | Register a treatment class by name |
| `get_treatment` | `(name: str) -> type | None` | Look up a registered treatment |
| `list_treatments` | `() -> list[str]` | Return sorted list of treatment names |

Treatments are declared in `experiment/treatments/__init__.py` via `TREATMENT_REGISTRY`, which lists all treatment classes. `discover_treatments()` iterates this list and validates each against `TreatmentInterface`.

### Harness (Within-Subjects Design)

`experiment/harness.py` — `Harness(conn, llm_client, seed)` runs within-subjects experiments:

1. `select_markets(conn, markets_per_cell, seed)` (from `experiment/methodologies/db_utils`) stratifies markets by `(city_prefix, days_to_expiry_bucket)` for balanced sampling
2. For each replicate and each market, the harness iterates over all treatment instances
3. At each timestep, `TreatmentContext` is assembled from DB data (market row, forecasts, prices, technical indicators, prior decisions)
4. Control treatments (`bypass_llm=True`) use market-implied probability directly; experimental treatments call `format_prompt` then `llm_client.query` then `validate_response`
5. Every decision is recorded to `agent_decisions` with run_id, treatment, ticker, timestep, and full reasoning

### Scoring Engine

`experiment/results.py` — `score_run(db_path, run_id)` compares treatments vs control:

- Groups final-timestep decisions by `(treatment, ticker)`
- Computes P&L per decision based on settlement and entry prices
- Runs paired t-test (manual implementation, no scipy dependency)
- Computes Cohen's d with Hedges' g small-sample correction
- Returns `ExperimentResults` per treatment with delta_profit, t_stat, p_value, effect_size, 95% CI, and an `improvement` flag (p < 0.05 and d > 0)

### Treatments

| Treatment | Module | `bypass_llm` | Description |
|---|---|---|---|
| `ControlTreatment` | `experiment/treatments/control` | `True` | Uses market-implied probability; no LLM call |
| `CalibrationBundleTreatment` | `experiment/treatments/calibration_bundle` | `False` | Full calibration-rich prompt with forecast data, accuracy metrics, technical indicators, and prior decisions |

### Populate (Data Fetcher)

`experiment/populate.py` fetches market data from Kalshi and weather forecasts from Open-Meteo/NWS, populating the experiment DB's `markets`, `forecast_snapshots`, and `market_prices` tables. City mapping follows the KXHIGHT/KXHIGH naming convention for 15 US cities.

## Data Provider & Signal Engine Architecture

The data layer uses a category-agnostic provider/signal framework at `src/traderbot/data/` designed for scalable multi-category support. Each category (weather, economics, sports, crypto) implements its own data provider and signal engine by subclassing the base ABCs.

### Module Structure

```
src/traderbot/data/
├── __init__.py              # Package exports
├── base_provider.py          # BaseDataProvider ABC
├── base_signals.py           # BaseSignalEngine ABC
├── models.py                 # CityForecast, EnsembleRun, ModelConsensus, BiasReport, TradingSignal
├── registry.py               # ProviderRegistry — register/discover providers by category
└── weather/                  # Weather category implementation
    ├── __init__.py
    ├── nws_client.py         # NWS API gridpoint resolution + structured forecast fetch
    ├── provider.py           # WeatherDataProvider — NWS + Open-Meteo ensemble (GFS/ECMWF/GEM)
    └── signals.py            # WeatherSignalEngine — forecast-vs-market edge + bias adjustment
```

### Base Classes

| Class | File | Methods |
|---|---|---|
| **BaseDataProvider** | `data/base_provider.py` | `get_forecasts(cities)`, `get_model_consensus(city)`, `get_historical_bias(city, model, days)` |
| **BaseSignalEngine** | `data/base_signals.py` | `compute_signals(forecasts, markets)` → `list[TradingSignal]` |
| **ProviderRegistry** | `data/registry.py` | `register_provider(name, cls)`, `get_provider(name)`, `list_providers()` |

### Data Models

| Model | Purpose | Key Fields |
|---|---|---|
| **CityForecast** | Single-city forecast from a provider | `ticker`, `city`, `date`, `high_temp_f`, `low_temp_f`, `precip_prob`, `source` |
| **EnsembleRun** | One model in a multi-model ensemble | `model_name`, `forecast_temp_f`, `valid_time` |
| **ModelConsensus** | Aggregate across GFS/ECMWF/GEM | `mean_temp`, `std_dev`, `spread`, `agreement_score` (0-1) |
| **BiasReport** | Historical accuracy for city/model | `city`, `model`, `mean_error`, `mean_abs_error`, `std_error`, `total_comparisons` |
| **TradingSignal** | Trading recommendation | `ticker`, `direction`, `estimated_prob`, `market_prob`, `edge`, `confidence`, `model_consensus`, `bias_adjustment`, `reasoning` |

### Weather Data Sources

| Source | Endpoint | Provided By | Data |
|---|---|---|---|
| NWS API | `api.weather.gov` | `NwsClient` | Structured forecast: high/low temp, precip prob, wind, detailed text. Gridpoints resolved via `/points/{lat},{lon}` and cached to `~/.traderbot/nws_gridpoints.json`. |
| Open-Meteo Models | `api.open-meteo.com/v1/forecast` | `WeatherDataProvider` | Ensemble data for GFS (`gfs_seamless`), ECMWF (`ecmwf_ifens`), GEM (`gem_global`). Returns `daily.temperature_2m_max` per model. |
| Forecast Bias | `traderbot.db` | `ForecastBias` | SQLite table tracking forecast vs actual per city. Queried via `query_bias(conn, city, model, days)`. |

### Signal Generation Pipeline

The `WeatherSignalEngine.compute_signals()` processes each market:

1. **Match**: Map market ticker to city forecast via `_TICKER_TO_CITY` table
2. **Estimate probability**: Logistic function comparing forecast temp to market threshold (σ=5°F), handling greater/less/between strike types
3. **Get market probability**: Extract from order book `implied_probability().yes_prob` (falls back to 0.50)
4. **Compute edge**: `estimated_prob - market_prob`
5. **Model consensus**: `_compute_agreement_penalty()` — tiers 0.3/0.5/0.7/0.8/0.95 based on GFS/ECMWF/GEM agreement
6. **Bias adjustment**: Query `forecast_bias` SQLite table, normalize `mean_error` to [-1, 1]
7. **Final confidence**: `base × agreement_mult × (1 − |bias|)`

### Adding a New Category

1. Create `data/<category>/provider.py` subclassing `BaseDataProvider`
2. Create `data/<category>/signals.py` subclassing `BaseSignalEngine`
3. Register: `ProviderRegistry.register_provider("<category>", MyDataProvider)`
4. CLI available: `traderbot data signals --category <category> --json`

### CLI Commands

All commands live under `traderbot data` sub-app in `cli/data.py`:

| Command | Example | Output |
|---|---|---|
| `forecasts` | `traderbot data forecasts --cities NYC,CHI,LA --json` | NWS high, GFS/ECMWF/GEM highs, spread |
| `signals` | `traderbot data signals --category weather --json` | Ticker, direction, est. prob, market prob, edge, confidence |
| `bias` | `traderbot data bias NYC --days 90 --json` | Mean error, MAE, bias direction, sample size |

## NWS Alerts Pipeline

National Weather Service alerts are integrated as a news source alongside existing sources (NewsAPI, Reddit, Open-Meteo, etc.).

### Source Configuration

- **NewsSource enum**: `NWS_ALERTS = "nws_alerts"` in `news/models.py`
- **Category mapping**: `NWS_ALERTS → [WEATHER]` — alerts are always weather-category
- **No API key required**: NWS alerts are publicly accessible
- **Auto-discovery**: `_fetch_nws_alerts()` is called via the `_SOURCE_PRIORITY` dispatch in `ingest_news()`

### Alert Fetching

`_fetch_nws_alerts()` in `news/sources.py`:

1. Queries 13 states: `NY, PA, AZ, MN, WA, IL, TX, CA, FL, CO, GA, MA, MI`
2. For each state, fetches `https://api.weather.gov/alerts/active/area/{state}`
3. Parallelized with `asyncio.Semaphore(5)` for concurrency control
4. Deduplicates by alert ID across states
5. Maps each alert to a `NewsItem` with `source=NewsSource.NWS_ALERTS`
6. Falls back gracefully on HTTP errors

### Source Priority

NWS alerts appear in `_SOURCE_PRIORITY` alongside all other sources:

```python
_SOURCE_PRIORITY: ClassVar[list[NewsSource]] = [
    NewsSource.NEWSAPI,      # 1st
    NewsSource.REDDIT,       # 2nd
    NewsSource.OPEN_METEO,   # 3rd
    NewsSource.COINGECKO,    # 4th
    NewsSource.THESPORTSDB,  # 5th
    NewsSource.OPENWEATHERMAP,# 6th
    NewsSource.NWS_ALERTS,   # 7th
    NewsSource.FRED,         # 8th
    NewsSource.GOOGLE_TRENDS,# 9th
]
```

## WebSocket Real-Time Market Data

The `--realtime` flag on `traderbot analyze` enables live orderbook and ticker streaming via WebSocket.

### Architecture

- **`KalshiWebSocket`** (`kalshi/websocket.py`): Async WebSocket client connecting to `wss://api.elections.kalshi.com/trade-api/ws/v2`
- **Authentication**: RSA-PSS signed headers via `kalshi/signing.py` + TLS cert pinning via `kalshi/pinning.py`
- **Channels**: `orderbook_delta`, `ticker`, `market_lifecycle_v2`, `fill`, `user_orders`, `market_positions`
- **30-second timeout**: `asyncio.wait_for(ws.receive(), timeout=30.0)` — graceful disconnect if no data received
- **Graceful cleanup**: WebSocket connection closed on timeout or error; resources released in `finally` block

### Usage Flow

```
traderbot analyze <TICKER> --realtime
    → KalshiWebSocket.connect()
    → subscribe(channels=["orderbook_delta", "ticker"], market_ticker=<TICKER>)
    → loop: await ws.receive() with 30s timeout
        → orderbook_snapshot  → print full book (first only)
        → orderbook_delta    → print incremental changes
        → ticker             → print price/volume updates
    → on timeout: print warning, close connection
```

## Reconciliation & Settlement

### Position Reconciliation

`db/reconciliation.py` provides three async functions for syncing local DB with Kalshi API:

| Function | Purpose |
|---|---|
| `reconcile_positions(db_path, kalshi_client)` | Fetch open positions from Kalshi, sync local DB. Close missing positions, update quantities/prices, add new positions. Returns `{updated, closed, added}`. |
| `reconcile_settlements(db_path, kalshi_client)` | Fetch recent settlements from Kalshi, update local `settlement_result` and `pnl_cents`. Returns `{settled, skipped}`. |
| `reconcile_all(db_path, kalshi_client)` | Run both reconciliations. Returns `{positions: {...}, settlements: {...}}`. |

### Position DB Schema

`db/positions.py` — `DbPosition` model with `pnl_cents` column:

```python
class DbPosition(BaseModel):
    id: int
    ticker: str
    quantity: int  # >= 0
    avg_price: int  # in cents
    settlement_result: bool | None = None
    pnl_cents: int = 0
    updated_at: datetime
```

Key operations: `upsert()` (preserves existing `pnl_cents`), `update_settlement()`, `mark_closed()`, `get()`, `list_all()`, `delete()`.

### Admin Commands

| Command | Purpose |
|---|---|
| `traderbot reconcile` | Run `reconcile_all()` — sync positions and settlements with Kalshi |
| `traderbot check-settlements` | Run `reconcile_settlements()` — check for recently settled markets |

### Settlement-Monitor Cron

The `settlement-monitor` job (`0 * * * *`, hourly) is registered as an isolated cron session that runs `traderbot check-settlements --json` to detect and process market settlements automatically.

## Data Flow

### Trade Execution Flow

```
Agent → "traderbot trade KXBTCD-26MAR31-T55000 yes 10"
   → cli/trade parses command
   → risk/limits checks: position size, exposure cap, daily loss, market liquidity
   → risk/sizing validates: does this quantity make sense given edge and bankroll?
   → IF REJECTED → return rejection reason to agent (with audit log entry)
   → IF APPROVED → kalshi/trading places order via official SDK
   → db/decisions logs: ticker, direction, quantity, signal, risk params, timestamp
   → kalshi/websocket listens for fill notification
   → db/positions updates on fill
```

### Analysis Flow

```
Agent → "traderbot analyze KXBTCD-26MAR31-T55000"
   → kalshi/markets fetches market details + orderbook
   → kalshi/history fetches historical trades for this ticker
   → analysis/indicators computes technical indicators
   → analysis/odds computes implied probability + edge estimate
   → news/sentiment_scorer fetches related news sentiment
   → AnalysisRegistry dispatches to CategoryAnalyzer for market category
   → Voyage semantic enrichment (slow path, optional)
   → analysis/signals combines all signals into unified view
   → returns structured analysis to agent
```

### Reconciliation Flow

```
Cron trigger (hourly) → "traderbot check-settlements --json"
   → reconcile_settlements() fetches settlements from Kalshi
   → For each settlement:
     → Look up local position by ticker
     → If found: update settlement_result, compute pnl_cents
     → If not found: log and skip
   → Returns {settled, skipped} counts

Agent trigger → "traderbot reconcile --json"
   → reconcile_positions() + reconcile_settlements()
   → Full sync of both positions and settlements
```

## Semantic Layer (Voyage AI + ChromaDB)

The semantic layer provides search-optimized index capabilities. It is NOT the authoritative store — that role belongs to SQLite.

### Role

- Search-optimized index layer for semantic similarity and retrieval
- Enables pattern matching across decision logs, news, and heartbeat histories
- ChromaDB stores embeddings; Voyage AI generates them

### Models

| Model | Purpose | Dimensions | Use Case |
|---|---|---|---|
| `voyage-4-large` | General-purpose embeddings (MoE) | 256/512/1024/2048 | News articles, market commentary, decision logs, heartbeat patterns, strategy fingerprints |
| `voyage-multimodal-3.5` | Text + image embeddings | 1024 (256/512/2048 configurable) | Chart analysis, visual market patterns |
| `rerank-2.5` | Reranking ambiguous classification results | N/A | Disambiguating borderline sentiment or category assignments |

### Architecture Constraint

**SQLite remains the authoritative write store.** ChromaDB is read-optimized index only. Every write goes to SQLite first; ChromaDB is updated asynchronously from the SQLite audit trail. If ChromaDB is unavailable, the system continues operating without semantic search — it is a performance enhancement, not a dependency.

### Slow-Path Constraint

Voyage API calls take ~200–500ms and must never appear on the hot path.

| Path | Mechanism |
|---|---|
| Fast path | VADER/TextBlob/keywords (<10ms response) |
| Slow path | Voyage API calls (~200–500ms), triggered asynchronously after primary response is returned |

## Data Models

### MarketCategory Enum

The `MarketCategory` enum is defined in `kalshi/models.py` and used across the analysis, news, and classification layers:

```python
class MarketCategory(StrEnum):
    ECONOMICS = "economics"
    POLITICS = "politics"
    WEATHER = "weather"
    SPORTS = "sports"
    SCIENCE_AND_TECHNOLOGY = "science_and_technology"
    CRYPTO = "crypto"
    COMMODITIES = "commodities"
    COMPANIES = "companies"
    ELECTIONS = "elections"
    ENTERTAINMENT = "entertainment"
    FINANCIALS = "financials"
    HEALTH = "health"
    SOCIAL = "social"
    MENTIONS = "mentions"
```

### NewsSource Enum

```python
class NewsSource(StrEnum):
    NEWSAPI = "newsapi"
    TWITTER = "twitter"
    REDDIT = "reddit"
    OPEN_METEO = "open_meteo"
    COINGECKO = "coingecko"
    THESPORTSDB = "thesportsdb"
    OPENWEATHERMAP = "openweathermap"
    FRED = "fred"
    GOOGLE_TRENDS = "google_trends"
    NWS_ALERTS = "nws_alerts"
```

Sources requiring API keys: `OPENWEATHERMAP`, `FRED`. All others use public endpoints or don't require keys.

### StrategyProfile Model

Defined in `profiles/injection.py`:

```python
class StrategyProfile(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    name: str
    risk_multiplier: float  # Scales within HARD_LIMITS, never overrides
    signal_weights: dict[str, float]
    category_focus: list[str]
    description: str
```

The `risk_multiplier` scales risk limits proportionally but NEVER exceeds `HARD_LIMITS`: `effective_limit = risk_multiplier * HARD_LIMITS[key]`.

## Security: Credential Management

### Dual-Layer Credential Management

TraderBot uses OS-native keyring as the primary credential store, with `.env` file fallback when keyring is unavailable.

- **Primary**: OS keyring (macOS Keychain, Windows Credential Locker, Linux Secret Service)
  - Per-profile isolation via `traderbot.profiles.{name}.{service}` namespace
- **Fallback**: `~/.traderbot/.env` with mode 0600
  - All profiles share the same `.env` file; per-profile isolation requires keyring

- **API keys**: Stored in keyring on `traderbot auth set-kalshi`, retrieved at runtime. Never logged, never written to stdout.
- **Private keys**: RSA-PSS signing keys for Kalshi WebSocket auth, stored in keyring, never on disk in plaintext.
- **Master password**: Optional keyring encryption key, set via `traderbot auth setup-master-password`.