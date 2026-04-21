# Architecture

BetBot's architecture is built around one principle: **the toolkit is a dumb pipe with smart guards.** It handles execution correctness and risk enforcement, but the agent decides strategy.

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
| **Frequency** | Every 6 hours |
| **OpenClaw mechanism** | `isolated agentTurn` (autonomous background work) |
| **Responsibility** | Performance review → adapt parameters → log learnings |

**Cycle:**
1. Review all decisions since last heartbeat
2. Compare expected vs. actual outcomes for closed markets
3. Identify patterns (wins, losses, near-misses)
4. Adjust strategy parameters via Bayesian updating (`simulation/adaptation`)
5. Promote recurring learnings to `.learnings/LEARNINGS.md`
6. Check circuit breaker conditions
7. Update `HEARTBEAT.md` with status

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
│  betbot scan | analyze | trade | positions | backtest | ...  │
└──────┬───────┬───────────┬───────────┬───────────┬───────────┘
       │       │           │           │           │
       ▼       ▼           ▼           ▼           ▼
  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
  │ kalshi │ │analysis│ │  risk  │ │ sim    │ │  news  │
  │        │ │        │ │        │ │        │ │        │
  │ client │ │indic.  │ │limits  │ │engine  │ │sources │
  │ models │ │odds    │ │sizing  │ │paper   │ │classif.│
  │ markets│ │signals │ │breaker │ │adapt.  │ │scorer  │
  │ trading│ │portf.  │ │audit   │ │perf.   │ │impact  │
  │ history│ │sentim. │ │        │ │        │ │        │
  │ ws     │ │        │ │        │ │        │ │        │
  └───┬────┘ └────────┘ └────┬───┘ └────────┘ └────────┘
      │                      │
      ▼                      ▼
  ┌────────┐            ┌────────┐
  │ Kalshi │            │  db    │
  │   API  │            │positions│
  │        │            │decisions│
  └────────┘            │learnings│
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
| **Strategy selection** (what approach to use) | | ✅ |
| **Market interpretation** (why this market is attractive) | | ✅ |
| **Position sizing** (how much to risk) | | ✅ (within guard rails) |
| **Risk appetite** (acceptable overall loss level) | | ✅ |
| **Entry/exit timing** | | ✅ |

The toolkit computes, enforces, and executes. The agent decides, interprets, and sizes. Risk guards sit between them — the agent can request any trade, but the toolkit has veto power.

## Data Flow

### Trade Execution Flow

```
Agent → "betbot trade KXBTCD-26MAR31-T55000 yes 10"
  → cli.py parses command
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
Agent → "betbot analyze KXBTCD-26MAR31-T55000"
  → kalshi/markets fetches market details + orderbook
  → kalshi/history fetches historical trades for this ticker
  → analysis/indicators computes technical indicators
  → analysis/odds computes implied probability + edge estimate
  → news/sentiment_scorer fetches related news sentiment
  → analysis/signals combines all signals into unified view
  → returns structured analysis to agent
```

### Heartbeat Flow

```
Cron trigger → "betbot heartbeat"
  → simulation/adaptation reviews recent decisions
  → For each closed market: compare predicted outcome vs. actual
  → Bayesian update: adjust prior distributions based on evidence
  → If Recurrence-Count >= 3 for any pattern → promote to .learnings/
  → Check circuit breaker conditions
  → Update HEARTBEAT.md
```

## Module Dependencies

Internal dependency rules prevent circularity and maintain the enforcement boundary:

- `kalshi/` depends on: nothing (pure I/O)
- `analysis/` depends on: `kalshi/models` (Pydantic types only)
- `risk/` depends on: `kalshi/models`, `db/positions` (to check current exposure)
- `simulation/` depends on: `kalshi/history`, `analysis/`, `risk/`
- `news/` depends on: `kalshi/models` (for market category mapping)
- `db/` depends on: `kalshi/models`
- `cli.py` depends on: all modules (orchestration layer)

**Strict rule**: `risk/` never depends on `analysis/` or `news/`. Risk guards must be enforceable without understanding strategy signals. A signal can suggest "buy everything" — the risk module checks exposure regardless of signal quality.