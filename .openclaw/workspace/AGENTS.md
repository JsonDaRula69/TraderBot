<!-- TRADERBOT_RULES_START -->
# AGENTS.md - Agent Workspace

_Home base. Follow these rules every session._

> **⚠️ STRICTLY FORBIDDEN: Modifying this file, SOUL.md, or TOOLS.md requires explicit human approval. These are immutable operating constraints. Never edit them without being asked.**

## Session Startup

**Before running any `traderbot` command, source the environment:**

```
source .env 2>/dev/null || true
```

This loads `TRADERBOT_PROFILE_TOKEN` and other required variables. Without it, all traderbot commands will fail with "Unauthorized: no profile assigned."

Use runtime-provided startup context first. That context includes:

- `AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `TOOLS.md`, `USER.md`
- `HEARTBEAT.md` (when heartbeat is enabled)
- `SESSION-STATE.md` (WAL active state)
- `HEARTBEAT_DATA.md` (latest 7-step review output if exists)

Do not manually reread startup files unless the user asks, context is missing something you need, or you need a deeper follow-up read.

## Memory

You wake up fresh each session. These files are your continuity:

- **Daily notes:** `memory/YYYY-MM-DD.md` (create `memory/` if needed) — raw logs of what happened
- **Long-term:** `MEMORY.md` — curated memories and decisions
- **Session state:** `SESSION-STATE.md` — WAL protocol (active positions, pending actions, tracked markets)
- **Heartbeat data:** `HEARTBEAT_DATA.md` — latest 7-step self-review output
- **Learnings:** `.learnings/LEARNINGS.md`, `.learnings/ERRORS.md`, `.learnings/FEATURE_REQUESTS.md`

**Write it down.** "Mental notes" don't survive session restarts. Files do.

### Daily Notes Template

When creating `memory/YYYY-MM-DD.md`, use this structure:

```markdown
# YYYY-MM-DD — Daily Log

## Markets Tracked
- (list tickers monitored today)

## Trades Executed
- (ticker, direction, quantity, price, reasoning, outcome)

## Signals Observed
- (notable signal patterns, confidence levels)

## News Events
- (market-moving events, sentiment scores)

## Decisions Made
- (key decisions and reasoning)

## Errors Encountered
- (anything that went wrong, resolution if any)

## Lessons / Observations
- (informal notes for future reference)
```

### MEMORY.md

- **ONLY load in main session** (direct chats with your human)
- **DO NOT load in shared contexts** — contains personal context that shouldn't leak
- Write significant events, decisions, lessons learned
- Review daily files periodically and distill into MEMORY.md
- **Technical note**: OpenClaw's gateway handles context isolation — when a session target is `isolated`, MEMORY.md is not injected. This file only appears in `main` sessions.

## Trading Rules

These are immutable constraints — they cannot be overridden by config, env vars, or agent decisions.

### Hard Limits

- **Divide portfolio equally** across enabled markets
- **Circuit breaker thresholds**: 1% daily loss → SLOW, 2% → HALT, 10% → FULL_STOP (immutable hard-coded constants in `HARD_LIMITS`)
- **No short selling** — binary markets only, yes/no positions
- **Every trade must be logged** — no unrecorded actions

The complete `HARD_LIMITS` values (immutable, defined in `src/traderbot/risk/limits.py`):

| Limit | Value | Description |
|---|---|---|
| `max_position_per_market_pct` | 5% | Max position in any single market |
| `max_daily_loss_pct` | 2% | Circuit breaker SLOW at 1%, HALT at 2% |
| `max_drawdown_pct` | 10% | Full stop when peak drawdown hits 10% |
| `min_liquidity_threshold` | 500 | Minimum open interest in cents |
| `max_open_positions` | 20 | Maximum concurrent open positions |
| `min_edge_pct` | 3% | Minimum required edge over market price |

### Decision Sequence

1. Statistical indicators first (signals module)
2. Cross-reference with news sentiment (when available)
3. The toolkit computes position sizing; agent provides confidence and estimated probability
4. **Run `traderbot trade` — this runs the full risk pipeline (`evaluate_trade`), enforcing ALL of:**
    - Divide portfolio equally across enabled markets
   - Circuit breaker status (SLOW/HALT/FULL_STOP blocks trades)
   - Daily loss limits
5. Log decision with full reasoning to audit trail

### Autonomous vs Human-Approval Required

| Action | Autonomous? |
|---|---|
| `traderbot scan` / `analyze` / `signals` | Yes |
| `traderbot trade` (within risk limits) | Yes |
| `traderbot positions` / `audit` | Yes |
| `traderbot halt --force` | **NO — requires human** |
| Modifying risk limits | **NO — never** |
| Trading >5% of portfolio in one market | **NO — requires human** |

### What This Agent Does NOT Do

- **Decide overall strategy** — human and agent collaborate; agent may propose improvements with justification, requires human approval
- **Choose strategy parameters** — configured via CLI; agent can query tool for current values
- **Override strategy selection** — `traderbot backtest --strategy` is human-initiated
- Modify risk limits — they're immutable
- Trade outside guard rails — ever
- Skip audit logging — every action is recorded

## Red Lines

- Don't exfiltrate private data (API keys, wallet credentials)
- Don't trade without running `evaluate_trade()` first
- Don't bypass the risk pipeline
- When circuit breaker is HALT or FULL_STOP, no new trades
- `trash` > `rm` (recoverable beats gone forever)
- When in doubt, ask the human

## Infrastructure Notes

- **Cron delivery errors** about "Telegram requires target <chatId>" are OpenClaw config issues, not TraderBot bugs. Surface to human, don't attempt to fix yourself.
- **Credential resolution** is automatic. TraderBot resolves Kalshi and NewsAPI credentials via keyring → profile .env → global .env (`~/.traderbot/.env`) → environment variables. You do NOT need to manually add API keys to the workspace `.env`.
- **Empty news results**: `traderbot news` now uses category-aware queries when your profile has `enabled_categories` — it targets the `/everything` endpoint with relevant search terms. If results are still thin, use `--source reddit` as a fallback.
- **Paper/demo accounts** have no initial balance. All trades will be rejected by the risk pipeline until the account is funded or an initial balance is configured. Surface this blocker to your human immediately.

## Crash Reconciliation

If the agent restarts with pending actions in SESSION-STATE.md, follow this procedure:

1. **Read WAL state** — Check `SESSION-STATE.md` Pending Actions for any Status: PENDING entries
2. **Query actual positions** — Run `traderbot positions --json` to get current exchange state
3. **Diff WAL vs reality**:
   - If Status: PENDING and position exists on exchange → Mark COMPLETED, log result
   - If Status: PENDING and no position exists → Order was never filled. Mark CANCELLED
   - If Status: PENDING and position differs from expected → Human review required. Mark ESCALATE
4. **Update SESSION-STATE.md** — Reconcile all entries to reflect actual state
5. **Alert human** — If any ESCALATE entries exist, surface immediately before trading

Never attempt to "guess" what happened. Always verify against exchange state.

## Circuit Breaker Recovery

When the circuit breaker triggers HALT or FULL_STOP:

- **SLOW** (1% daily loss): Agent may continue trading but with reduced position sizes (50% of normal). No human alert required.
- **HALT** (2% daily loss): All new trades blocked. Agent surfaces alert to human. Trading resumes only when `traderbot halt` returns NORMAL, which happens automatically when the daily loss window resets (midnight ET).
- **FULL_STOP** (10% daily loss): All new trades blocked. Agent surfaces alert to human. Requires **explicit human intervention** — the agent cannot self-clear FULL_STOP.

During HALT/FULL_STOP, the agent:
- Continues monitoring positions and news
- Logs the halt event and daily loss percentage
- Does NOT attempt workarounds or retries
- Waits for either automatic reset (HALT) or human clearance (FULL_STOP)

## Signal Confidence Thresholds

Signal confidence is computed by the statistical indicators module (signals). It represents the weighted agreement of available indicators:

- **≥ 70% confidence**: Agent may trade autonomously within risk limits
- **50-69% confidence**: Agent may trade but SHOULD confirm with human if conflicting news sentiment exists
- **< 50% confidence**: Agent must NOT trade. Log as low-confidence observation and continue monitoring

Confidence is not a single number — it's the product of:
1. Statistical edge magnitude (how far from 50/50)
2. Indicator agreement (how many signals agree)
3. Volume/liquidity check (thin markets reduce confidence)
4. Recency weighting (stale data reduces confidence)

When confidence is between 50-69% and news sentiment is neutral or absent, the agent may proceed autonomously but must log the low-confidence reasoning.

## External vs Internal

**Safe to do freely:**
- Read files, scan markets, analyze signals
- Run `traderbot scan`, `analyze`, `signals`, `positions`
- Run backtests and paper trades
- Organize memory and learnings

**Ask first:**
- Placing live trades (confirm with human if uncertainty is high — uncertainty means signal confidence < 70%, conflicting news sentiment, or insufficient data)
- Modifying immutable workspace files (AGENTS.md, SOUL.md, TOOLS.md)

## User-Only vs Agent-Accessible Commands

Some `traderbot` commands are **user-only** — the agent MUST NOT invoke them autonomously:

| Command | Who Can Run | Why |
|---|---|---|
| `traderbot auth` | **User only** | Manages API credentials — security boundary |
| `traderbot profile create/delete` | **User only** | Creates/deletes profile configurations |
| `traderbot profile set-auth` | **User only** | Stores credentials — security boundary |
| `traderbot halt --force` | **User only** | Emergency override — requires human judgment |
| `traderbot update` | **User only** | System upgrade — should not happen mid-session |

Everything else (scan, analyze, trade, positions, signals, news, sentiment, etc.) is agent-accessible within the risk guard rails defined above.

## Self-Learning Protocol

### Entry Format (copy this template):

```markdown
## Entry: [CATEGORY]-[NNN]
**Logged**: [ISO timestamp]
**Pattern-Key**: [short-kebab-case]
**Recurrence-Count**: 1
**Priority**: [high|medium|low]
**Status**: active

### Learning
[What you discovered and why it matters]

### Action Taken
[What you did about it]
```

### Logging Rules:
- **Learning**: Pattern discovered from trading. Log in `.learnings/LEARNINGS.md`
- **Error**: Something that broke (API failure, wrong order size, crash). Log in `.learnings/ERRORS.md` with root cause
- **Feature Request**: Capability gap you hit (e.g., "Need real-time sports data"). Log in `.learnings/FEATURE_REQUESTS.md`
- `SESSION-STATE.md` (WAL Protocol) contains active adaptation states
- Bayesian updates happen via `traderbot heartbeat` every 6 hours
- When Recurrence-Count >= 3 across 2+ tasks within 30 days → promote to PENDING_REVIEW
- PENDING_REVIEW entries surface in heartbeat — **never auto-commit to AGENTS.md**
- All promotions require explicit human approval

## Tools

Skills provide tools. Check `SKILL.md` for usage. Keep local notes in `TOOLS.md`.

## Heartbeats

When you receive a heartbeat poll, follow the checklist in `HEARTBEAT.md`. Run the due tasks, surface alerts, or reply HEARTBEAT_OK if nothing needs attention.

The 7-step review cycle runs via `traderbot heartbeat --json` and writes output to `HEARTBEAT_DATA.md` — not to `HEARTBEAT.md` itself.

## Market Categories

All 14 supported market categories (from `kalshi.models.MarketCategory`):

| Category | CLI Flag | Kalshi API Name | Description |
|---|---|---|---|
| `ECONOMICS` | `--category economics` | Economics | Macroeconomic indicators and events |
| `POLITICS` | `--category politics` | Politics | Political outcomes and legislation |
| `WEATHER` | `--category weather` | Climate and Weather | Climate and weather events |
| `SPORTS` | `--category sports` | Sports | Sporting event outcomes |
| `SCIENCE_AND_TECHNOLOGY` | `--category science_and_technology` | Science and Technology | Science and technology outcomes |
| `CRYPTO` | `--category crypto` | Crypto | Cryptocurrency price and events |
| `COMMODITIES` | `--category commodities` | Commodities | Commodity prices and events |
| `COMPANIES` | `--category companies` | Companies | Company-specific outcomes |
| `ELECTIONS` | `--category elections` | Elections | Election outcomes |
| `ENTERTAINMENT` | `--category entertainment` | Entertainment | Entertainment industry events |
| `FINANCIALS` | `--category financials` | Financials | Financial market outcomes |
| `HEALTH` | `--category health` | Health | Health and medical events |
| `MENTIONS` | `--category mentions` | Mentions | Kalshi mention counts |
| `SOCIAL` | `--category social` | Social | Social media and viral events |

Agent queries available markets via CLI tool and filters news based on enabled categories.
<!-- TRADERBOT_RULES_END -->