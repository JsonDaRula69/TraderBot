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

The adaptation engine runs during the Heartbeat Loop (every 6 hours):

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
- Occurred within a 30-day window

**Promotion targets**:
- `AGENTS.md` — becomes a permanent operating rule
- `SESSION-STATE.md` — active context for the current session
- Code changes — if the learning identifies a bug or improvement

### Error Logging

Errors are logged immediately when they occur. Unlike learnings (which require pattern recognition), errors are always worth capturing:

```markdown
## Entry: ERR-001
**Logged**: 2026-04-20T09:15:00Z
**Priority**: critical
**Status**: pending
### Error
```
kalshi_python_async.ApiException: 429 Too Many Requests
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

5. **Circuit breaker check**
   - Is daily loss within limits?
   - Is drawdown within limits?
   - Are there any error patterns requiring attention?

6. **System health**
   - API connectivity: can we reach Kalshi?
   - WebSocket health: is the stream active?
   - Data freshness: when did we last receive market data?

7. **Update HEARTBEAT.md**
   - Write checklist results
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

| Anti-Pattern | What It Looks Like | How BetBot Prevents It |
|---|---|---|
| **Over-fitting** | Parameters adjusted to match recent history too closely | Minimum 10 observations; 20% max change per update |
| **Parameter drift** | Gradual shift away from sensible values without noticing | Guardrails on parameter bounds; reset trigger on low variance |
| **Confirmation-seeking** | Agent only sees evidence that supports its current approach | Audit trail includes rejected trades; heartbeat reviews all outcomes |
| **Superstition** | "This pattern worked once, so it always will" | Pattern promotion requires 3+ recurrences across 2+ tasks |
| **Circular improvement** | Agent rates itself based on its own criteria | Performance metrics are objective (P&L, Sharpe, Brier score) |