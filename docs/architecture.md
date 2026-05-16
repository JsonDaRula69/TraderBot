# Architecture

TraderBot's architecture is built around one principle: **the toolkit is a dumb pipe with smart guards.** It handles execution correctness and risk enforcement, but the agent decides strategy.

## Three-Loop Autonomous System

The agent operates via three independent loops, each with a distinct responsibility and OpenClaw execution mechanism.

### Decision Loop

| Attribute | Value |
|---|---|
| **Frequency** | Every 5 minutes (24/7) — Kalshi prediction markets never close |
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
|---|---|---|
| **Frequency** | Every 30 minutes |
| **OpenClaw mechanism** | `isolated agentTurn` (autonomous background work) |
| **Responsibility** | Performance review → adapt parameters → log learnings |

**Cycle:**
1. Review all decisions since last heartbeat
2. Compare expected vs. actual outcomes for closed markets
3. Identify patterns (wins, losses, near-misses)
4. Adjust strategy parameters via Bayesian updating (`simulation/adaptation`)
5. Promote recurring learnings to `.learnings/LEARNINGS.md`
6. Check circuit breaker conditions
7. Update `HEARTBEAT_DATA.md` with status

The Heartbeat Loop is the self-improvement mechanism. It doesn't change strategy emotionally — it adjusts mathematical parameters (prior distributions, confidence thresholds) based on observed evidence.

### News/Sentiment Loop

| Attribute | Value |
|---|---|
| **Frequency** | Event-driven (news webhook or polling) |
| **OpenClaw mechanism** | `systemEvent` (surfaces to main session when actionable) |
| **Responsibility** | Process news → classify events → update market outlook |

**Cycle:**
1. Poll news sources for new articles/posts
2. Classify each item by Kalshi market category
3. Score sentiment (positive/negative/neutral + magnitude)
4. Assess impact: "Does this materially change the probability of any tracked market?"
5. If actionable → emit `systemEvent` to main session
6. If not → update internal sentiment state silently

The News Loop is the only loop that uses `systemEvent` — because timely news sometimes requires human awareness (e.g., "The Fed just announced an emergency rate cut" is worth knowing about immediately).

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
│  traderbot scan | analyze | trade | positions | audit |       │
│  backtest | paper | compare | performance | news |            │
│  sentiment | signals | heartbeat | halt | resume | bootstrap  │
│  learnings | cron setup | profile | auth                       │
└──────┬───────┬───────────┬───────────┬───────────┬───────────┘
       │       │           │           │           │
       ▼       ▼           ▼           ▼           ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
    │ kalshi │ │analysis│ │  risk  │ │ sim    │ │  news  │
    │        │ │        │ │        │ │        │ │        │
    │ client │ │indic.  │ │limits  │ │engine  │ │sources │
    │ models │ │odds    │ │sizing  │ │paper   │ │classif.│
    │ markets│ │signals │ │breaker │ │adapt.  │ │sentim. │
    │ trading│ │portf.  │ │audit   │ │perf.   │ │impact  │
    │ events │ │registry│ │agent   │ │profiles│ │embed.  │
    │ history│ │        │ │limits  │ │data_ldr│ │models  │
    │ ws     │ │        │ │        │ │settle  │ │cache   │
    │ exchange│ │        │ │        │ │strateg.│ │paths   │
    │ signing│ │        │ │        │ │adapter │ │        │
    │ config │ │        │ │        │ │state   │ │        │
    │ cache  │ │        │ │        │ │        │ │        │
    │ provider│ │        │ │        │ │        │ │        │
    │ rate_lim│ │        │ │        │ │        │ │        │
    │ _norm. │ │        │ │        │ │        │ │        │
    └───┬────┘ └────────┘ └────┬───┘ └────────┘ └────────┘
       │                      │
       ▼                      ▼
   ┌────────┐            ┌────────┐
    │ Kalshi │            │  db    │
    │   API  │            │positions│
    │        │            │decisions│
    └────────┘            │learnings│
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
- TTL policy: embeddings auto-expire after configurable window (default 90 days)
- Async support: embedding generation and querying run without blocking the hot path
- Collections: `decisions`, `news`, `market_patterns`, `news_signals`, `market_conditions`

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

### Bootstrap Flow (Setup Wizard)

```
Agent → "traderbot bootstrap"
   → Checks Python version (3.12.x required for chromadb compatibility)
   → Creates default config directory (~/.traderbot/)
   → Launches interactive credential setup for all services
   → Writes credentials to .env file
   → Reports completion status
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

### .env-Based Credential Management

TraderBot uses a `.env` file for all credential and configuration storage. There is no separate credential backend.

- **Location**: `~/.traderbot/.env` with mode 0600
- **API keys**: `KALSHI_API_KEY`, `KALSHI_PRIVATE_KEY_PEM`, `KALSHI_RATE_LIMIT_RPS`
- **Profile resolution**: `TRADERBOT_PROFILE_TOKEN` set as an environment variable at agent startup

All profiles share the same `.env` file. There is no per-profile credential isolation.

### `traderbot auth` CLI

The `traderbot auth` command manages credentials in the `.env` file:

| Subcommand | Description |
|---|---|
| `traderbot auth check` | Verify that required env vars are set and valid |
| `traderbot auth set-key <name> <value>` | Store a credential in `.env` |
| `traderbot auth list-keys` | List configured credential names (values NOT shown) |
| `traderbot auth rotate <name>` | Rotate a credential — prompts for new value |

### Credential Resolution

1. **`.env` file** (primary) — located at `~/.traderbot/.env`
2. **Environment variables** (fallback) — for container deployments

All credential fields in Pydantic models use `SecretStr` to prevent accidental logging of secrets.

## Module Dependencies

Internal dependency rules prevent circularity and maintain the enforcement boundary:

- `kalshi/` depends on: nothing (pure I/O)
- `analysis/` depends on: `kalshi/models` (Pydantic types only)
- `risk/` depends on: `kalshi/models`, `db/positions` (to check current exposure)
- `simulation/` depends on: `kalshi/history`, `analysis/`, `risk/`
- `news/` depends on: `kalshi/models` (for market category mapping), `chromadb` (for storing/querying embeddings), `CategoryAnalyzer` Protocol and `AnalysisRegistry` pattern for category-specific analysis dispatch
- `db/` depends on: `kalshi/models`
- `db/chroma` depends on: `kalshi/models` (for metadata), `voyageai` (for embedding generation)
- `db/chroma` never depends on: `risk/` (search index has no enforcement role)
- `cli.py` depends on: all modules (orchestration layer)

**Strict rule**: `risk/` never depends on `analysis/` or `news/`. Risk guards must be enforceable without understanding strategy signals. A signal can suggest "buy everything" — the risk module checks exposure regardless of signal quality.