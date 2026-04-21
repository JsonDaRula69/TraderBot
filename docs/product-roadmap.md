# Product Roadmap

Implementation phases, dependencies between them, success criteria, and future expansion plans.

## Phase 1: Kalshi Data Foundation

**Goal**: Connect to Kalshi, authenticate, fetch market data, normalize into our models.

| Component | Files | Description |
|---|---|---|
| Pydantic models | `kalshi/models.py` | Market, OrderBook, Trade, Order, Position, Fill |
| SDK wrapper | `kalshi/client.py` | Auth, retry, rate limiting, type normalization |
| Market data | `kalshi/markets.py` | List markets, get detail, orderbook, recent trades |
| Historical data | `kalshi/history.py` | Cutoff queries, historical trades, settled markets |
| WebSocket | `kalshi/websocket.py` | Real-time price/streaming data |
| Demo adapter | `kalshi/demo.py` | Demo API for paper trading |

**Dependencies**: None — this is the foundation.
**Version target**: v0.01.00

**Success criteria**:
- `traderbot scan` returns a list of open markets from production API
- `traderbot analyze KXBTCD-26MAR31-T55000` returns market details + orderbook
- WebSocket maintains persistent connection and receives real-time updates
- Demo mode works against `demo-api.kalshi.co`
- All API responses parsed into validated Pydantic models

## Phase 2: Risk Module

**Goal**: Build the immutable guardrail layer. Must exist before any trading happens.

| Component | Files | Description |
|---|---|---|
| Hard limits | `risk/limits.py` | Per-market cap, daily loss, max drawdown, liquidity, edge |
| Position sizing | `risk/sizing.py` | Kelly criterion, fractional Kelly, confidence scaling |
| Circuit breaker | `risk/circuit_breaker.py` | Three-tier slow/halt/full-stop system |
| Audit trail | `risk/audit.py` | Decision logging with full context |

**Dependencies**: Phase 1 (needs Pydantic models from `kalshi/models`).
**Version target**: v0.02.00

**Success criteria**:
- Risk module rejects trades that violate any hard limit
- Circuit breaker activates at correct thresholds
- Kelly sizing produces mathematically correct results
- Every decision (executed or rejected) is logged with full context
- Risk module cannot be bypassed by passing different config

## Phase 3: CLI & OpenClaw Skill

**Goal**: Make the toolkit callable from the command line and define the OpenClaw skill.

| Component | Files | Description |
|---|---|---|
| CLI entry point | `cli.py` | argparse/typer CLI for all commands |
| Skill definition | `skills/traderbot/SKILL.md` | OpenClaw skill with commands, triggers, env |
| Workspace setup | `.openclaw/workspace/` | AGENTS.md, SESSION-STATE.md, HEARTBEAT.md templates |
| DB layer | `db/positions.py`, `db/decisions.py` | SQLite for position tracking and decision audit |

**Dependencies**: Phase 1, Phase 2.
**Version target**: v0.03.00

**Success criteria**:
- `traderbot scan`, `traderbot analyze`, `traderbot positions` work from CLI
- `traderbot trade` places orders (through risk checks)
- OpenClaw can load the skill and execute commands
- Position state persists across CLI invocations (SQLite)
- `traderbot audit` shows full decision history

## Phase 4: Analysis Engine

**Goal**: Statistical computation and signal generation for binary outcome instruments.

| Component | Files | Description |
|---|---|---|
| Indicators | `analysis/indicators.py` | Technical indicators adapted for binary markets |
| Probability/edge | `analysis/odds.py` | Implied probability, edge detection, Kelly inputs |
| Portfolio analytics | `analysis/portfolio.py` | Sharpe, drawdown, correlation, Brier score |
| Signal combining | `analysis/signals.py` | Merge statistical + sentiment signals |

**Dependencies**: Phase 1 (market data models).
**Version target**: v0.04.00

**Success criteria**:
- `traderbot analyze <ticker>` returns statistical indicators and edge estimate
- `traderbot signals` shows active signals across tracked markets
- Brier score computed for historical prediction accuracy
- Indicators work correctly for binary/fixed-expiry instruments

## Phase 5: Simulation Engine

**Goal**: Backtesting and paper trading to validate strategies before live trading.

| Component | Files | Description |
|---|---|---|
| Backtest engine | `simulation/engine.py` | Event-driven replay for binary outcomes |
| Data loader | `simulation/data_loader.py` | Historical data fetch + cache |
| Paper trader | `simulation/paper_trader.py` | Demo API execution |
| Performance | `simulation/performance.py` | Strategy metrics and comparison |

**Dependencies**: Phase 1 (historical data), Phase 2 (risk checks), Phase 4 (signals).
**Version target**: v0.05.00

**Success criteria**:
- `traderbot backtest <strategy> 2026-01-01 2026-03-01` produces valid performance metrics
- Paper trading executes against demo API with realistic fills
- Slippage modeled in backtests (worst-case fill within spread)
- `traderbot compare strategy_a strategy_b` produces side-by-side metrics
- Historical data cached locally to avoid re-fetching

## Phase 6: Decision Logging & Self-Learning Foundation

**Goal**: Full audit trail, WAL protocol, and learning log infrastructure.

| Component | Files | Description |
|---|---|---|
| Decision DB | `db/decisions.py` | Every trade decision with reasoning, signals, risk params |
| Learnings | `db/learnings.py` | Pattern tracking with recurrence counts, semantic search, clustering |
| Vector store | `db/vectors.py` | ChromaDB interface for embedding storage and retrieval |
| WAL protocol | (in Decision Loop) | Write-to-SESSION-STATE before executing |
| Workspace files | `.openclaw/workspace/` | LEARNINGS.md, ERRORS.md, FEATURE_REQUESTS.md |

**Dependencies**: Phase 2 (audit trail), Phase 3 (CLI, DB).
**Version target**: v0.06.00

**Success criteria**:
- Every trade decision logged with full reasoning
- WAL: pending actions written to SESSION-STATE before execution
- Learning entries support Pattern-Key and Recurrence-Count
- Pattern promotion works (3+ recurrences → AGENTS.md)
- Decision log supports semantic search via natural language queries
- Heartbeat clusters semantically similar decision patterns

## Phase 7: News & Sentiment Pipeline

**Goal**: Real-time news ingestion, classification, and sentiment scoring.

| Component | Files | Description |
|---|---|---|
| Sources | `news/sources.py` | Unified interface for NewsAPI, Twitter, Reddit |
| Classifier | `news/classifier.py` | Map news to Kalshi categories (Voyage-enhanced semantic classification) |
| Sentiment | `news/sentiment_scorer.py` | VADER + TextBlob scoring with Voyage semantic enrichment |
| Impact | `news/impact_assessor.py` | Filter noise from signal (Voyage-boosted relevance scoring) |
| Embedding client | `news/embeddings.py` | Voyage API client (`voyage-finance-2` embeddings) |
| ChromaDB integration | `db/vectors.py` | Vector storage and similarity search for news embeddings |
| Semantic classification | (in `news/classifier.py`) | Embedding-based category matching with `voyage-finance-2` |
| Reranker fallback | `news/embeddings.py` | `rerank-2.5` for ambiguous classifications |

**Dependencies**: Phase 1 (market category mapping).
**Version target**: v0.07.00

**Success criteria**:
- `traderbot news` returns recent news relevant to tracked markets
- `traderbot sentiment <ticker>` returns sentiment score with confidence
- News classified to correct Kalshi category >90% of the time (with Voyage semantic classification)
- Sentiment scoring completes in <10ms per item (VADER)
- Impact assessor filters out >70% of irrelevant news
- Voyage-enhanced classification degrades gracefully when API unavailable

> **Note**: Voyage AI integration requires `VOYAGE_API_KEY` environment variable. Pipeline degrades to VADER/TextBlob/keyword-only mode without it.
> For model selection rationale and constraints, see [ADR-001](decisions/voyage-ai-adoption.md).

## Phase 8: Adaptation Engine & Full Autonomy

**Goal**: Bayesian parameter updating, heartbeat system, three-loop autonomous operation.

| Component | Files | Description |
|---|---|---|
| Bayesian adapter | `simulation/adaptation.py` | Conjugate prior updates for strategy parameters |
| Heartbeat | (in Decision Loop) | 6-hour self-review cycle |
| Three-loop | (OpenClaw crons) | Decision + Heartbeat + News loops via agentTurn/systemEvent |

**Dependencies**: Phases 5-7.
**Version target**: v0.08.00

**Success criteria**:
- Bayesian updates produce mathematically correct posteriors
- Parameter bounds enforced (no >20% change per update)
- Heartbeat runs every 6 hours autonomously
- Full three-loop system operates without human intervention
- Agent recovers from crash by reading SESSION-STATE.md

## Future Expansion

### Post-Kalshi Markets

| Market | Integration Approach | Key Differences |
|---|---|---|
| **Polymarket** | New adapter in `polymarket/` | CLOB-based, different auth, AMM + orderbook |
| **PredictIt** | New adapter in `predictit/` | Smaller market, simpler API, academic focus |
| **Stocks** | New adapter in `stocks/` | Continuous prices, shorting, no expiry — fundamentally different risk model |
| **Crypto** | New adapter in `crypto/` | 24/7 markets, DEX integration, on-chain data |

Each new market type follows the same adapter pattern: `client.py`, `models.py`, `markets.py`, `trading.py`. The `risk/` and `analysis/` modules extend to support new instrument characteristics.

### Advanced Capabilities

| Capability | Description | Phase |
|---|---|---|
| **Cross-exchange arbitrage** | Detect price discrepancies between Kalshi and Polymarket for the same event | Post-8 |
| **Portfolio optimization** | Correlation-aware position sizing across markets | Post-8 |
| **Voyage AI semantic pipeline** | `voyage-finance-2` embeddings + `rerank-2.5` for classification and sentiment | 7 |
| **Market chart analysis** | `voyage-multimodal-3.5` for visual chart pattern recognition | 7 |
| **Decision log semantic search** | Natural language queries over decision history via `voyage-4-large` + ChromaDB | 6 |
| **Multi-agent trading** | Multiple specialized agents (one per category) coordinating portfolio | Post-8 |
| **Market making** | Provide liquidity for edge on bid-ask spread | Post-8 |

## Implementation Principles

1. **Phase at a time**: No parallel phase development. Each phase builds on the previous.
2. **Test before trade**: Paper trading required before any live execution.
3. **Risk first**: Risk module (Phase 2) must be complete and tested before trading (Phase 3).
4. **Audit everything**: If it can't be audited, it shouldn't be in the system.
5. **Fail safe**: On any error, default to inaction (hold positions, don't trade).