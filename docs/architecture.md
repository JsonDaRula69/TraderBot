# Architecture

TraderBot's architecture is built around one principle: **the toolkit is a dumb pipe with smart guards.** It handles execution correctness and risk enforcement, but the agent decides strategy.

## Three-Loop Autonomous System

The agent operates via three independent loops, each with a distinct responsibility and OpenClaw execution mechanism.

### Decision Loop

| Attribute | Value |
|---|---|
| **Frequency** | Continuous during market hours |
| **OpenClaw mechanism** | `isolated agentTurn` (autonomous, no human attention needed) |
| **Responsibility** | Analyze markets → generate signals → risk-check → execute |

**Cycle:**
1. Fetch market data (WebSocket stream + REST snapshot)
2. Run statistical analysis (`analysis/indicators`, `analysis/odds`)
3. Cross-reference with sentiment signals (`analysis/signals`)
4. Generate buy/sell/hold signals
5. **Risk gate**: Every signal passes through `risk/limits` before execution
6. Execute approved orders via `kalshi/trading`
7. Log decision with full reasoning to `db/decisions`

The Decision Loop runs as an OpenClaw `isolated agentTurn` — a background sub-agent that operates autonomously without requiring the main session's attention. This means trading continues even when the human isn't watching.

### Heartbeat Loop

| Attribute | Value |
|---|---|
| **Frequency** | Every 6 hours (configurable via `cron setup --heartbeat-every`) |
| **OpenClaw mechanism** | `isolated agentTurn` (autonomous background work) |
| **Responsibility** | Performance review → adapt parameters → log learnings |

**Cycle:**
1. Review all decisions since last heartbeat (every 6h automatically via cron)
2. Compare expected vs. actual outcomes for closed markets
3. Identify patterns (wins, losses, near-misses)
4. Adjust strategy parameters via Bayesian updating (`simulation/adaptation`)
5. Promote recurring learnings to `.learnings/LEARNINGS.md`
6. Check circuit breaker conditions
7. Update `HEARTBEAT_DATA.md` with status

The Heartbeat Loop is the self-improvement mechanism. It doesn't change strategy emotionally — it adjusts mathematical parameters (prior distributions, confidence thresholds) based on observed evidence.

### News Ingestion & Data Backfill (Offline Pipeline)

The pipeline consists of two independent systemd timers, both running outside any agent session:

| Timer | Frequency | Command | Purpose |
|---|---|---|---|
| `traderbot-news-ingest@.timer` | Every 30 min | `traderbot news-ingest` | Fetch, classify, embed news + data points to ChromaDB |
| `traderbot-backfill-data@.timer` | Daily (midnight) | `traderbot backfill --months 1` | Incremental historical data enrichment (Open-Meteo, FRED, CoinGecko) to ChromaDB `data_points` |

#### News Ingestion

| Attribute | Value |
|---|---|
| **Frequency** | Every 30 minutes (systemd timer) |
| **Mechanism** | Standalone CLI command (`traderbot news-ingest`), no LLM required |
| **Responsibility** | Fetch → classify → embed → store news and data points to ChromaDB |

The news ingestion timer (`traderbot-news-ingest@.timer`) runs independently and:

1. Fetches from 9 sources (NewsAPI, Reddit RSS, Open-Meteo, OpenWeatherMap, CoinGecko, TheSportsDB, FRED, Google Trends, Twitter/X stub)
2. Parallelizes all HTTP calls via `asyncio.gather` for maximum throughput
3. Classifies each item by Kalshi market category (keyword fast path → Voyage semantic slow path)
4. Scores sentiment via VADER + TextBlob with optional Voyage rerank uplift
5. Embeds articles with Voyage AI (`voyage-4-large`, 1024-dim) and stores to ChromaDB `news` collection
6. Stores DataPoints (weather, economic, sports, crypto) to ChromaDB `data_points` collection
7. Deduplicates by SHA-256 URL hash

#### Data Backfill

| Attribute | Value |
|---|---|
| **Frequency** | Daily (systemd timer) |
| **Mechanism** | Standalone CLI command (`traderbot backfill`), idempotent |
| **Responsibility** | Continuously enrich `data_points` with historical weather, economics, and crypto data |

The backfill timer (`traderbot-backfill-data@.timer`) runs once per day and:
1. Fetches Open-Meteo historical weather (past 92 days max per chunk, chunked for longer windows)
2. Fetches FRED economic indicator history
3. Fetches CoinGecko crypto price history
4. Stores all items to ChromaDB `data_points` collection
5. Skips already-stored items (idempotent by doc ID)

On first install, `install-data-pipeline.sh` runs a one-shot 6-month backfill to seed the collection. Daily runs thereafter add incremental data.

Agents query accumulated data via `traderbot data-points` and `traderbot news-context` — they do not receive pipeline data inline during trading sessions.

## Component Map

```
┌─────────────────────────────────────────────────────────────┐
│                      OpenClaw Agent                          │
│  (strategy decisions, market interpretation, sizing)        │
└──────────┬──────────────────────────────────────────────────┘
           │ calls via exec
           ▼
┌──────────────────────────────────────────────────────────────┐
│  cli.py — CLI entry point                                    │
│  traderbot scan | analyze | trade | positions | backtest |    │
│  paper | compare | performance | news | signals |             │
│  sentiment | heartbeat | learnings | audit | halt | resume |  │
│  bootstrap | auth | experiment | cron | cache                 │
└──────┬───────┬───────────┬───────────┬───────────┬───────────┬───────────┐
       │       │           │           │           │           │
       ▼       ▼           ▼           ▼           ▼           ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────────┐
   │ kalshi │ │analysis│ │  risk  │ │ sim    │ │  news  │ │experiment  │
   │        │ │        │ │        │ │        │ │        │ │            │
   │ client │ │indic.  │ │limits  │ │engine  │ │sources │ │shared      │
   │ models │ │odds    │ │sizing  │ │paper   │ │classif.│ │registry    │
   │ markets│ │signals │ │breaker │ │adapt.  │ │sentim. │ │harness     │
   │ trading│ │portf.  │ │audit   │ │perf.   │ │impact  │ │results     │
   │ history│ │        │ │        │ │profiles│ │embed.  │ │populate    │
   │ ws     │ │        │ │        │ │data_ldr│ │vectors │ │treatments  │
   └───┬────┘ └────────┘ └────┬───┘ └────────┘ └────────┘ │methodologies│
       │                      │                                └──────┬─────┘
       ▼                      ▼                                       │
   ┌────────┐            ┌────────┐                                   ▼
   │ Kalshi │            │  db    │                            ┌──────────────┐
   │   API  │            │positions│                            │ experiment db│
   │        │            │decisions│                            │  (5 tables)  │
   └────────┘            │learnings│                            │    + LLM     │
                         │ chroma  │                            └──────────────┘
                         │ vectors │
                         └────────┘
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
| Position tracking & P&L sync | ✅ | |
| Audit trail (logging decisions with context) | ✅ | |
| **Semantic embedding & similarity computation** | ✅ | |
| **Strategy selection** (what approach to use) | | ✅ |
| **Market interpretation** (why this market is attractive) | | ✅ |
| **Position sizing** (how much to risk) | | ✅ (within guard rails) |
| **Risk appetite** (acceptable overall loss level) | | ✅ |
| **Entry/exit timing** | | ✅ |

The toolkit computes, enforces, and executes. The agent decides, interprets, and sizes. Risk guards sit between them — the agent can request any trade, but the toolkit has veto power.

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

### LLM Client

`llm/client.py` — `LLMClient(provider, max_retries)` wraps any provider implementing `generate(prompt) -> str` with exponential-backoff retry (1s, 2s, 4s) on transient connection errors.

`llm/ollama.py` — `OllamaProvider(model, base_url, timeout)` implements the `LLMProvider` protocol against a local Ollama server. Raises `OllamaConnectionError` on connectivity, timeout, or HTTP errors, which the client retries.

### Market Stratification

`experiment/methodologies/db_utils.py` — `select_markets(conn, markets_per_cell, seed)` groups markets into strata by `city_prefix` and days-to-expiry bucket (`lt7d`, `7-14d`, `gt14d`). Within each stratum, it randomly samples up to `markets_per_cell` tickers using the provided seed for reproducibility.

## Semantic Layer (Voyage AI + ChromaDB)
> Model selection rationale and constraints: [ADR-001](decisions/voyage-ai-adoption.md)

The semantic layer provides search-optimized index capabilities. It is NOT the authoritative store — that role belongs to SQLite.

### Role

- Search-optimized index layer for semantic similarity and retrieval
- Enables pattern matching across decision logs, news, and heartbeat histories
- ChromaDB stores embeddings; Voyage AI generates them

### Models

| Model | Purpose | Dimensions | Use Case |
|---|---|---|---|
| `voyage-4-large` | General-purpose embeddings (MoE) | 256/512/1024/2048 | News articles, market commentary, decision logs, heartbeat patterns, strategy fingerprints |
| ~~`voyage-finance-2`~~ | ~~Financial text embeddings~~ | ~~1024~~ | ~~Retired — replaced by voyage-4-large~~ |
| `voyage-multimodal-3.5` | Text + image embeddings | 1024 (256/512/2048 configurable) | Chart analysis, visual market patterns |
| `rerank-2.5` | Reranking ambiguous classification results | N/A | Disambiguating borderline sentiment or category assignments |

### ChromaDB

- Persistent vector store with metadata filtering (ticker, category, date range)
- No built-in TTL: embeddings persist until manually purged or collection reset
- Async support: embedding generation and querying run without blocking the hot path
- Collections: `decisions`, `news`, `market_patterns`, `news_signals`, `market_conditions`, `data_points`

### Architecture Constraint

**SQLite remains the authoritative write store.** ChromaDB is read-optimized index only. Every write goes to SQLite first; ChromaDB is updated asynchronously from the SQLite audit trail. If ChromaDB is unavailable, the system continues operating without semantic search — it is a performance enhancement, not a dependency.

### Slow-Path Constraint

Voyage API calls take ~200–500ms and must never appear on the hot path.

| Path | Mechanism |
|---|---|
| Fast path | VADER/TextBlob/keywords (<10ms response) |
| Slow path | Voyage API calls (~200–500ms), triggered asynchronously after primary response is returned |

Slow-path embeddings are queued and processed in background tasks. The heartbeat loop uses the batch API (33% discount, 12h window) for population-scale pattern analysis.

## Data Flow

### Trade Execution Flow

```
Agent → "traderbot trade KXBTCD-26MAR31-T55000 yes 10"
   → cli.py parses command
   → risk/limits checks: position size, exposure cap, daily loss, market liquidity
   → risk/sizing validates: does this quantity make sense given edge and bankroll?
   → IF REJECTED → return rejection reason to agent (with audit log entry)
   → IF APPROVED → kalshi/trading places order via official SDK
   → db/decisions logs: ticker, direction, quantity, signal, risk params, timestamp
   → kalshi/websocket listens for fill notification
   → db/positions updates on fill
```

### Bootstrap Flow

```
Agent → "traderbot bootstrap"
   → cli.py: one-time setup wizard
   → Check Python version (3.12+)
   → Verify dependencies installed
   → Auth check: KALSHI_API_KEY configured
   → Database schema initialized
   → Profile creation prompt (interactive)
   → IF --dry-run → validate only, no writes
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

### Heartbeat Flow

```
Cron trigger → "traderbot heartbeat"
   → simulation/adaptation reviews recent decisions
   → For each closed market: compare predicted outcome vs. actual
   → Bayesian update: adjust prior distributions based on evidence
   → If Recurrence-Count >= 3 for any pattern → promote to .learnings/
   → Capability gap detection: scan for feature_request patterns
   → Promote recurring feature_request entries to PENDING_REVIEW status
   → Check circuit breaker conditions
   → Query ChromaDB for similar past patterns via `voyage-4-large` embeddings
   → Update HEARTBEAT_DATA.md
```

## Data Models

### MarketCategory Enum

The `MarketCategory` enum is defined in `news/` and used across the analysis, news, and classification layers:

```python
class MarketCategory(str, Enum):
    ECONOMICS = "economics"
    POLITICS = "politics"
    WEATHER = "weather"
    SPORTS = "sports"
    CULTURE = "culture"
    TECHNOLOGY = "technology"
    SCIENCE = "science"
```

This enum replaces the previous string-based category labels, providing type safety and ensuring consistent category names across the pipeline.

### StrategyProfile Model

Defined in `simulation/profiles.py`:

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

### AnalysisRegistry

The `AnalysisRegistry` in `news/` provides category-specific analysis dispatch:

```python
class AnalysisRegistry:
    def register(category: MarketCategory, analyzer: CategoryAnalyzer) -> None: ...
    def get(category: MarketCategory) -> CategoryAnalyzer | None: ...
    def analyze(text: str, source: SourceType) -> CategorySignals: ...
```

## Security: Credential Management

### Dual-Layer Credential Management

TraderBot uses OS-native keyring as the primary credential store, with `.env` file fallback when keyring is unavailable.

- **Primary**: OS keyring (macOS Keychain, Windows Credential Locker, Linux Secret Service)
  - Per-profile isolation via `traderbot.profiles.{name}.{service}` namespace
- **Fallback**: `~/.traderbot/.env` with mode 0600
  - All profiles share the same `.env` file; per-profile isolation requires keyring

- **API keys**: `KALSHI_API_KEY`, `KALSHI_PRIVATE_KEY_PEM`, `KALSHI_RATE_LIMIT_RPS`
- **Profile resolution**: `TRADERBOT_PROFILE_TOKEN` set as an environment variable at agent startup

See [security.md](security.md#credential-storage) for full details on resolution order, keyring namespaces, and per-profile auth.

### `traderbot auth` CLI

The `traderbot auth` command manages credentials via OS keyring with `.env` fallback:

| Subcommand | Description |
|---|---|
| `traderbot auth check` | Verify KALSHI_API_KEY is configured |
| `traderbot auth set-kalshi` | Store Kalshi credentials (keyring or .env) |
| `traderbot auth list-keys` | List configured credential names (values NOT shown) |
| `traderbot auth rotate <name>` | Rotate a credential — prompts for new value |
| `traderbot auth migrate [--service]` | Migrate credentials from .env to keyring |
| `traderbot auth delete-key <service>` | Delete a stored credential |
| `traderbot auth setup-master-password` | Set up master password for trade auth |
| `traderbot auth change-master-password` | Change the master password |
| `traderbot auth check-master-password` | Verify master password is configured |
| `traderbot auth clear-session` | Clear session credential cache |

### Credential Resolution

1. **OS keyring** (primary) — macOS Keychain / Windows Credential Locker / Linux Secret Service
2. **Environment variables** (fallback) — for container deployments
3. **.env file** (fallback) — `~/.traderbot/.env` when keyring unavailable

All credential fields in Pydantic models use `SecretStr` to prevent accidental logging of secrets.

## Module Dependencies

Internal dependency rules prevent circularity and maintain the enforcement boundary:

- `kalshi/` depends on: nothing (pure I/O)
- `analysis/` depends on: `kalshi/models` (Pydantic types only)
- `risk/` depends on: `kalshi/models`, `db/positions` (to check current exposure)
- `simulation/` depends on: `kalshi/history`, `analysis/`, `risk/`
- `news/` depends on: `kalshi/models` (for market category mapping), `chromadb` (for storing/querying embeddings), `CategoryAnalyzer` Protocol and `AnalysisRegistry` pattern for category-specific analysis dispatch
- `db/` depends on: `kalshi/models`
- `db/vectors` depends on: `kalshi/models` (for metadata), `voyageai` (for embedding generation)
- `db/vectors` never depends on: `risk/` (search index has no enforcement role)
- `cli.py` depends on: all modules (orchestration layer)

**Strict rule**: `risk/` never depends on `analysis/` or `news/`. Risk guards must be enforceable without understanding strategy signals. A signal can suggest "buy everything" — the risk module checks exposure regardless of signal quality.