# Self-Learning & Adaptation

How TraderBot improves over time without human intervention — Bayesian parameter updating, learning logs, heartbeat reviews, and the WAL protocol.

## Design Philosophy

The agent improves through **math, not emotions**. When outcomes differ from predictions, we update the mathematical model. We don't "feel more confident" or "learn a lesson" — we adjust a probability distribution based on evidence.

This is the critical distinction from human traders who tilt, chase losses, or develop superstitions. The adaptation engine only changes parameters based on statistical evidence.

## Bayesian Parameter Adaptation

`simulation/adaptation.py` — the math layer that adjusts strategy parameters.

### How It Works

Strategy parameters are modeled as probability distributions (priors), not fixed values. As the agent observes outcomes, it updates these distributions using Bayes' theorem:

```
posterior ∝ prior × likelihood

where:
  prior      = current belief about the parameter
  likelihood = how likely the observed outcome is under different parameter values
  posterior   = updated belief
```

### Adapted Parameters

| Parameter | Prior Distribution | What It Controls |
|---|---|---|
| **Edge threshold** | Beta(2, 8) → starts at ~0.2 | Minimum edge required to enter a trade |
| **Signal weight: statistical** | Dirichlet(1,1,1) | How much weight to give statistical indicators |
| **Signal weight: sentiment** | Dirichlet(1,1,1) | How much weight to give sentiment signals |
| **Mean reversion strength** | Normal(0.5, 0.2) | How aggressively to fade price moves |
| **Momentum decay rate** | Exponential(1.0) | How quickly momentum signals decay |

These are not the strategy itself — they're tuning knobs that adjust how the strategy interprets signals. The agent still decides the overall approach.

### Update Cycle

The adaptation engine runs during the Heartbeat Loop (every 30 minutes):

1. Collect all decisions made since last heartbeat
2. For closed markets: compare predicted outcome vs. actual
3. Compute likelihood of observed outcomes under current priors
4. Update posterior distributions via conjugate prior updates (fast, no MCMC needed)
5. Write updated parameters to `SESSION-STATE.md`
6. Log what changed and why

### Parameter Change Logging

Every parameter update is recorded:

```markdown
## Adaptation: 2026-04-20T12:00:00Z

### Edge Threshold
- Prior: Beta(2, 8) → mean 0.20
- Observations: 14 trades, 9 profitable (64% win rate)
- Posterior: Beta(11, 13) → mean 0.46
- Action: Raised edge threshold from 0.20 to 0.25 (conservative shift)

### Signal Weight: Statistical vs Sentiment
- Prior: Dirichlet(1, 1) → equal weight
- Observations: Statistical signals outperform sentiment 3:1 on economic markets
- Posterior: Dirichlet(4, 2) → statistical given 0.67 weight
- Action: Increased statistical signal weight for economic category markets
```

### Guardrails on Adaptation

The adaptation engine has its own guards to prevent pathological behavior:

| Guard | Rule | Why |
|---|---|---|
| **Parameter bounds** | No parameter can move more than 20% in a single update | Prevents wild swings from small sample sizes |
| **Minimum sample** | At least 10 observations before any update | Statistical validity |
| **Cooldown** | No more than 4 updates per 24 hours | Prevents over-fitting to recent data |
| **Reset trigger** | If posterior distribution variance < 0.01, reset to weak prior | Prevents convergence to a false certainty |
| **Human review** | If any parameter moves >10% for 3 consecutive updates, flag for human review | Detects systematic drift |

## Learning Logs

Inspired by `peterskoett/self-improving-agent`. Structured markdown files that capture what the agent learns from experience.

### File Structure

```
.openclaw/workspace/.learnings/
├── LEARNINGS.md        # Corrections, insights, better approaches
├── ERRORS.md           # API errors, failed orders, unexpected states
└── FEATURE_REQUESTS.md # Capabilities the agent discovers it needs
```

### Learning Entry Format

```markdown
## Entry: EDGE-001
**Logged**: 2026-04-20T14:30:00Z
**Pattern-Key**: illiquid-market-slippage
**Recurrence-Count**: 4
**Priority**: high
**Status**: active
**Category**: risk
### Learning
Markets with open_interest < 500 experience significant slippage on orders > 5 contracts.
### Action
Added liquidity threshold to risk/limits.py. Pending verification in next heartbeat.
```

### Pattern Promotion

When a learning recurs enough, it gets promoted to permanent project memory:

**Promotion criteria** (from self-improving-agent):
- `Recurrence-Count >= 3`
- Seen across at least 2 distinct tasks
- Occurred within a 30-day window (`max_age_days=30`)
- Pattern is not stale (patterns older than 30 days from last recurrence are NOT eligible)

**Staleness constraint**: Patterns with `max_age_days > 30` are automatically excluded from promotion. This prevents promoting outdated observations that may no longer reflect current market conditions. The `max_age_days=30` limit is enforced in `db/learnings.py` and cannot be overridden at runtime.

**Promotion targets**:
- `AGENTS.md` — flagged for human review via PENDING_REVIEW status (never auto-committed)
- `SESSION-STATE.md` — active context for the current session
- Code changes — if the learning identifies a bug or improvement

**Promotion is notification-only**: The agent NEVER auto-edits `AGENTS.md`. Pattern promotion creates a `PENDING_REVIEW` entry in `FEATURE_REQUESTS.md` that surfaces during heartbeat review. Human approval is required before any operating rule change.

### FEATURE_REQUESTS.md Flow

The `.learnings/FEATURE_REQUESTS.md` file tracks capability gaps discovered during operation:

```markdown
## Entry: FEAT-001
**Logged**: 2026-04-20T14:30:00Z
**Category**: feature_request
**Pattern-Key**: missing-sports-data
**Recurrence-Count**: 5
**Priority**: high
**Status**: PENDING_REVIEW
### Request
The agent frequently encounters sports markets but lacks real-time sports data feeds.
Current keyword matching produces low-confidence classifications for sports events.
### Proposed Solution
Add sports data integration (e.g., ESPN API, sports scores) to improve sports market classification.
### Impact
Improved classification accuracy for ~15% of tracked markets.
```

**Capability gap logging** follows a recurrence-based promotion model:
1. When the agent encounters a capability it doesn't have (e.g., no data feed for a category, missing tool), it logs a `feature_request` category entry in `FEATURE_REQUESTS.md`
2. Each occurrence increments `Recurrence-Count` for that pattern
3. When `Recurrence-Count >= 3` across 2+ tasks within 30 days, the entry is promoted to `PENDING_REVIEW` status
4. `PENDING_REVIEW` entries surface in heartbeat reviews for human evaluation
5. Humans can approve (implement the feature), defer (lower priority), or reject (close the entry)

**Key constraint**: Feature requests are NOT auto-implemented. They require explicit human approval, consistent with the project principle that the toolkit never decides strategy or scope without human direction.

### Error Logging

Errors are logged immediately when they occur. Unlike learnings (which require pattern recognition), errors are always worth capturing:

```markdown
## Entry: ERR-001
**Logged**: 2026-04-20T09:15:00Z
**Priority**: critical
**Status**: pending
### Error
```
httpx.HTTPStatusError: 429 Too Many Requests
```
### Context
- Endpoint: GET /historical/trades
- Rate limit hit after 12 requests in 1 second
- Retry-after: 1 second
```

Resolved errors include the fix:

```markdown
**Resolved**: 2026-04-20T09:16:00Z
**Fix**: Added 100ms delay between paginated historical requests in data_loader.py
```

## Semantic Decision Search
> Model selection rationale and constraints: [ADR-001](decisions/voyage-ai-adoption.md)

Store decision embeddings in ChromaDB for natural language retrieval. Instead of filtering decisions by date or ticker with SQL, agents query with questions like "what happened last time the Fed raised rates?"

### Design

- **Embedding model**: `voyage-4-large` (general-purpose, 1024 dimensions default)
- **Why not finance-specific**: Decision context spans multiple categories (macro, sector, event) — a general-purpose model handles mixed-domain text better
- **Scope**: Last 90 days, max 1000 results per query
- **Embed on write**: Decisions are embedded when logged, not on read
- **Storage hierarchy**: ChromaDB stores embedding + `decision_id` (foreign key to SQLite); SQLite is authoritative; ChromaDB is the search index only

### Query Flow

1. Agent asks: "what happened to energy markets when the Fed raised rates?"
2. Query embedding generated with `voyage-4-large`
3. ChromaDB returns semantically similar decision IDs ranked by cosine similarity
4. Agent retrieves full decision records from SQLite via `decision_id`
5. Agent reviews historical decisions, forms hypothesis, decides action

### ChromaDB Collections

**`decision_embeddings`**
| Field | Type | Description |
|---|---|---|
| `embedding` | float[1024] | `voyage-4-large` output |
| `decision_id` | TEXT | FK to SQLite decisions table |
| `ticker` | TEXT | Market ticker |
| `category` | TEXT | Macro / sector / event |
| `timestamp` | ISO8601 | When decision was made |
| `outcome` | TEXT | closed / correct / incorrect / open |

**`cluster_results`**
| Field | Type | Description |
|---|---|---|
| `cluster_id` | TEXT | Unique cluster identifier |
| `decisions_count` | int | Number of decisions in cluster |
| `pattern_key` | TEXT | Human-readable pattern label |
| `created_at` | ISO8601 | When clustering was computed |

## WAL Protocol (Write-Ahead Log)

Borrowed from `halthelobster/proactive-agent`. Ensures no decision is lost to context overflow or crashes.

### The Problem

LLM agents have limited context windows. As a conversation grows, older context gets compacted or dropped. If the agent made a trade decision early in a session and context was subsequently lost, there's no record of why that trade was made.

### The Solution

**Before** executing any trade, the agent writes the intent to `SESSION-STATE.md`:

```markdown
## Pending Actions

### 2026-04-20T14:30:00Z
- Action: BUY YES 10 KXBTCD-26MAR31-T55000 @ 55¢
- Reason: Statistical edge 8.2% (model estimates 63.2% vs market 55%)
- Signal: momentum_reversal (strength 0.7), sentiment_positive (0.4)
- Risk: position would be 2.1% of portfolio (within 5% limit)
- Confidence: 0.72
- Status: APPROVED
```

If the agent crashes after writing but before executing, the Decision Loop on restart reads `SESSION-STATE.md`, finds the pending action, and either:
- Executes it (if market conditions still match)
- Cancels it (if market has moved significantly)
- Logs it as a missed opportunity (for heartbeat review)

### Scanning Rules

The WAL Protocol scans every outgoing action for these triggers:

| Trigger | Action |
|---|---|
| **Any trade order** | Write intent to SESSION-STATE.md before executing |
| **Human correction** | Log to LEARNINGS.md as "correction" category |
| **Proper noun mentioned** | Ensure entity is in market category mapping |
| **Decision with reasoning** | Write full reasoning to audit trail |
| **Risk limit check** | Log result (pass/fail) regardless of outcome |

## Heartbeat Pattern Clustering

During the heartbeat cycle, group closed-market decisions by semantic similarity of market conditions.

### Design

- **Embedding model**: `voyage-4-large` (general-purpose, same model as decision search)
- **Why not finance-specific**: Clusters span multiple market categories; a general-purpose model avoids category-specific bias
- **Timing**: Runs every 30 minutes during heartbeat, not on every decision
- **What is clustered**: Decision outcome sequences grouped by market condition similarity

### Clustering Flow

1. Heartbeat collects all closed-market decisions since last cycle
2. Each decision's market context text is embedded with `voyage-4-large`
3. Decisions are grouped by cosine similarity of their embeddings
4. Cluster labels and similarity scores are written to `cluster_results` collection
5. Agent reviews clusters and decides whether to act — no automatic strategy changes

### Clustering Input and Output

**Input**: Decision outcome sequences grouped by market semantic similarity

**Output**: Grouping labels + similarity scores stored in ChromaDB `cluster_results` collection

### Empty Clusters

If no significant clusters are found, log "no significant clusters found" and exit gracefully. This is not an error — it simply means recent decisions do not share enough semantic similarity to form meaningful groups.

## Degraded Mode (No Voyage API / ChromaDB)

When `VOYAGE_API_KEY` is unset or the Voyage API is unreachable, or when ChromaDB is unavailable:

1. **Semantic Decision Search**: Falls back to SQL queries filtered by date, ticker, and category. No semantic similarity — results are chronological and categorical rather than conceptually relevant.
2. **Heartbeat Pattern Clustering**: Skips the semantic clustering step entirely. Heartbeat completes with Bayesian adaptation and learning promotion only.
3. **Decision Embedding Queue**: Embedding generation is queued and retried on next heartbeat cycle. If the queue exceeds 24 hours, oldest embeddings are dropped.

The system continues operating without semantic search — it is a performance enhancement, not a dependency.

**Graceful degradation logging requirement**: All fallback paths MUST log at WARNING level when degrading. This includes:
- Voyage API unavailable → log WARNING with `"voyage_status": "unavailable"` and which component degraded
- ChromaDB unavailable → log WARNING with which semantic features are disabled
- NewsAPI unavailable → log WARNING and continue with available sources
- Twitter API key unset → log WARNING and return empty results (stub behavior)
- Any external API failure → log WARNING with error details and which fallback path was taken

This ensures that degraded operation is always visible in logs, enabling heartbeat reviews to detect persistent degradation patterns.

## Heartbeat System

The heartbeat is the periodic self-review mechanism. It combines Bayesian adaptation, learning promotion, and system health checks.

### Heartbeat Cycle (Every 6 Hours)

1. **Performance review**
   - Calculate win rate, Sharpe, drawdown since last heartbeat
   - Compare to expected performance based on strategy parameters
   - Flag significant deviations

2. **Decision review**
   - Review all decisions since last heartbeat
   - For closed markets: did we predict the right outcome?
   - For open markets: are current positions still justified?

3. **Bayesian adaptation**
   - Update parameter posteriors based on new observations
   - Log what changed and why
   - Check for parameter bounds violations

4. **Learning promotion**
   - Scan `.learnings/` for entries with Recurrence-Count >= 3
   - Promote qualifying entries to AGENTS.md
   - Mark promoted entries as `Status: promoted`

4b. **Semantic clustering**
   - Query ChromaDB for semantically similar past decisions
   - Group by `voyage-4-large` embedding similarity
   - Log clusters for agent review (agent decides, no automatic action)

5. **Circuit breaker check**
   - Is daily loss within limits?
   - Is drawdown within limits?
   - Are there any error patterns requiring attention?

6. **System health**
   - API connectivity: can we reach Kalshi?
   - WebSocket health: is the stream active?
   - Data freshness: when did we last receive market data?

7. **Update HEARTBEAT_DATA.md**
   - Write 7-step review results (performance, adaptation, circuit breaker, health, alerts)
   - Flag any items requiring human attention

### Heartbeat Output

```markdown
## Heartbeat: 2026-04-20T12:00:00Z

### Performance
- Win rate: 64% (expected: 60%) ✓
- Daily P&L: +$127 (+1.4%) ✓
- Open positions: 12 (limit: 20) ✓
- Max drawdown: 3.2% (limit: 10%) ✓

### Adaptation
- Edge threshold: 0.20 → 0.25 (conservative shift, 14 observations)
- Statistical weight: 0.50 → 0.55 (outperforming sentiment on economic markets)

### Learnings
- Promoted: ILLIQUID-SLIPPAGE → AGENTS.md (4 recurrences)
- New: FILL-DELAY on market KXBTCD... (1 occurrence, monitoring)

### Alerts
- ⚠️ WebSocket reconnected 3 times in last 6 hours (investigate stability)
```

## Self-Improvement Anti-Patterns

| Anti-Pattern | What It Looks Like | How TraderBot Prevents It |
|---|---|---|
| **Over-fitting** | Parameters adjusted to match recent history too closely | Minimum 10 observations; 20% max change per update |
| **Parameter drift** | Gradual shift away from sensible values without noticing | Guardrails on parameter bounds; reset trigger on low variance |
| **Confirmation-seeking** | Agent only sees evidence that supports its current approach | Audit trail includes rejected trades; heartbeat reviews all outcomes |
| **Superstition** | "This pattern worked once, so it always will" | Pattern promotion requires 3+ recurrences across 2+ tasks |
| **Circular improvement** | Agent rates itself based on its own criteria | Performance metrics are objective (P&L, Sharpe, Brier score) |