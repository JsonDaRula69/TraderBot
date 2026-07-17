# TraderBot v2 — Agents and Lifecycle

> This document covers agent types, lifecycle states, SysAdmin role, Dev-Liaison, category agents, and the deploy-to-live progression. Grounded in DD-008, DD-010, DD-017, DD-023, DD-034, DD-036, DD-038.

---

## Agent Types

### SysAdmin Agent

**Role**: Fleet orchestrator. Does NOT trade.

**Key responsibilities** (DD-017):
1. **Oversight** — Monitor fleet health, circuit breakers, data freshness, auth credentials
2. **Coordination** — Route information between agents, manage experiment proposals, deploy improvements
3. **Self-improvement orchestration** — Drive the improvement cycle (Layer 2), evaluate daily performance, investigate losses, design experiments

**Sandbox status**: Unsandboxed (DD-036). Runs on the host, not in a Docker container. Has `sandbox.mode: off`.

**Principled restrictions** (DD-036):
- **No trading tools**: `traderbot__trade`, `traderbot__scan`, `traderbot__analyze`, and all category-specific tools (`traderbot__weather_*`, etc.) are in its `deny` list
- **Workspace file immutability**: Core workspace files (AGENTS.md, TOOLS.md, SOUL.md, IDENTITY.md) are marked as not allowed to edit
- **Lifecycle confirmation required**: Promoting an agent from paper to live requires explicit confirmation. Suspending an agent can be done immediately but must log the reason and trigger investigation
- **Read access to everything**: `enabled_categories: []` gives access to all categories and all data sources

**MCP tool allowlist** (DD-036):
```
traderbot__health, traderbot__auth_check, traderbot__profile_list,
traderbot__profile_update, traderbot__performance, traderbot__audit,
traderbot__learnings, traderbot__cron_setup, traderbot__session_send,
traderbot__experiment, traderbot__data_status, traderbot__ws_status,
traderbot__backfill, traderbot__reference,
sessions_spawn, sessions_send, sessions_yield, sessions_list, sessions_history, subagents
```

**Denied tools**: `traderbot__trade`, `traderbot__scan`, `traderbot__analyze`, `traderbot__weather_*`, `traderbot__market_edge`, `traderbot__market_prices`

### Dev-Liaison

**Role**: Subject matter expert on TraderBot architecture, design, and implementation. Liaison between the TraderBot agent team and the AutoDev team (OpenCode + OmO), which is responsible for all engineering and development of TraderBot going forward, including v2 implementation. Provides feasibility perspective during debate cycles (DD-034).

**Key responsibilities**:
- Provide expert perspective on TraderBot architecture during improvement debates
- Assess feasibility of proposed changes (top-line feasibility check on Round 3 proposals)
- Partner with SysAdmin to coordinate diagnostics and issue investigations
- Bridge between Layer 2 (pipeline improvement) and Layer 3 (dev team)
- **Interface with AutoDev**: Receive webhook notifications when AutoDev completes work, is blocked, or deploys changes; send wake signals to AutoDev when TraderBot agents file GitHub issues that need engineering work
- **Update verification**: When AutoDev deploys changes, coordinate with TraderBot agents to validate health and confirm no regressions

**AutoDev Webhook Communication** (DD-034 §10):

The Dev-Liaison communicates with the AutoDev team via a low-latency webhook layer with GitHub as the shared source of truth:

| Channel | Direction | Mechanism | Latency |
|---|---|---|---|
| Wake signal | Either direction | OpenClaw webhooks / Discord bot | Seconds |
| GitHub | Both directions | Issues, PRs, labels, comments | 30 min (heartbeat) |

- **AutoDev → Dev-Liaison**: Webhook POST to `/hooks/autodev-completed`, `/hooks/autodev-blocked`, `/hooks/autodev-deployed` on the OpenClaw gateway
- **Dev-Liaison → AutoDev**: Posts `autodev:wake`, `autodev:cancel`, `autodev:priority` messages on shared Discord channel
- **Fallback**: If any channel fails, the heartbeat eventually catches everything. GitHub is always the source of truth.

**Agent configuration**:
- Agent ID: `dev-liaison`
- Sandbox mode: `off` (runs on host, like SysAdmin — needs access to source and logs)
- OpenClaw tool allowlist: `read`, `write`, `exec`, `github`, `traderbot__reference`, `traderbot__experiment`, `traderbot__auth_check`, `traderbot__health`, `sessions_spawn`, `sessions_send`, `sessions_yield`, `sessions_list`, `sessions_history`, `subagents`
- Denied: `traderbot__trade`, `traderbot__scan`, `traderbot__analyze`, `traderbot__weather_*`, `traderbot__market_edge`, `traderbot__market_prices`

**Workspace files**: Four bootstrap files — AGENTS.md, IDENTITY.md, TOOLS.md, HEARTBEAT.md — providing enough context to know what to search for, without exhaustive detail in context.

**This agent is not an autonomous developer.** It is a specialist consultant and communication bridge that participates in debate cycles, provides architecture guidance, and coordinates engineering work with the AutoDev team. It does not write or deploy production code autonomously.

### Category Agents

**Role**: Domain-specific traders. Each agent trades exclusively within its assigned category.

**Current categories**: Weather (first implementation), with Economics, Politics, Sports, Crypto, Entertainment, Science & Technology, Health, Social to follow.

**Key constraints** (DD-008, DD-010, DD-011):
- Prebuilt workspace files — no user customization
- Docker sandbox mandatory — `sandbox.mode: all`
- Per-agent data source and tool access via MCP filtering
- Only interact with TraderBot through MCP tools (CLI interface)
- Cannot access API tokens directly
- Cannot modify their own profile, risk limits, or workspace files
- Report to SysAdmin via heartbeat and SESSION-STATE.md

---

## Lifecycle States

Each category agent progresses through four states (DD-017):

```
BACKTESTING → PAPER TRADING → LIVE TRADING → (SUSPENDED)
     ↑              │               │               │
     └──────────────┘               │               │
     (demoted if metrics             │               │
      fall below threshold)          │               │
                                      └───────────────┘
                                       (demoted if risk
                                        limits breached)
```

### State 1: BACKTESTING (initial)

- Freshly deployed agents begin by backtesting on already-settled markets
- Time-lapse behavioral simulation (not just statistical replay) — DD-019
- The 6-month backfill provides historical data
- Agent runs `traderbot__trade(token, ticker, direction, quantity, price)` — MCP server returns historical fill at sim-time price
- Daily evaluation: SysAdmin reviews Sharpe, win rate, sample size
- **Promotion criteria (deployment bar)**: Sharpe ≥ 1.0, win rate ≥ 55%, sample size ≥ 30 trades
- If backtest fails: SysAdmin and agent investigate together via `sessions_send`

### State 2: PAPER TRADING

- Agent trades on live markets with simulated money
- Paper positions tracked in per-agent SQLite DB
- All trade decisions logged with full reasoning
- MCP server simulates fills using `PaperSlippageModel` (walks live orderbook)
- **Promotion criteria to live**: Sharpe ≥ 1.0, win rate ≥ 55%, 30+ paper trades, minimum 14 days of paper trading, breakeven or better for 2+ consecutive days
- Demotion back to backtesting if metrics fall below threshold

### State 3: LIVE TRADING

- Agent trades on live markets with real money via Kalshi API
- All risk limits enforced by TraderBot's risk module (immutable hard limits)
- Circuit breaker monitors for runaway losses
- Demotion to paper trading if drawdown exceeds threshold or circuit breaker triggers
- SysAdmin monitors live agents more frequently (heartbeat every 30 min)

### State 4: SUSPENDED

- Agent is suspended from all trading (circuit breaker FULL_STOP)
- SysAdmin investigates root cause
- Agent must re-validate through backtesting before resuming

---

## SysAdmin Activation Protocol

SysAdmin is deployed with exactly one cron job: a one-shot activation prompt that fires 5 minutes after deploy (DD-023). This triggers SysAdmin's startup protocol:

1. Remove the bootstrap job (confirms removal)
2. Verify TraderBot service is running: `traderbot health --json`
3. Verify data streams are fresh: `traderbot data-points weather --count --json`
4. Register essential self-jobs: `traderbot cron activate --role sysadmin --phase essential`
5. Enable own heartbeat
6. For each enabled category (one at a time):
   a. Verify category data is available
   b. Activate category agent: `traderbot profile update <agent> --mode backtest`
   c. Register backtesting jobs: `traderbot cron activate --agent <agent> --role trader --phase backtest`
   d. Register self oversight jobs: `traderbot cron activate --role sysadmin --phase oversight-backtest`
   e. Monitor backtesting progress via heartbeat
   f. When backtesting passes deployment bar:
      - Deactivate backtest cron jobs
      - Activate paper trading jobs
      - Update profile: `traderbot profile update <agent> --mode paper`
   g. When paper trading meets breakeven threshold for 2+ days:
      - Deactivate paper cron jobs
      - Activate live trading jobs (requires explicit confirmation)
      - Update profile: `traderbot profile update <agent> --mode live`
   h. Proceed to next category

---

## Cron/Heartbeat Architecture

Cron and heartbeat jobs are **not registered at deploy time**. They are designed as templates and deployed along with SysAdmin, but remain dormant until SysAdmin activates them (DD-023).

### SysAdmin Job Definitions

| Job | Phase | Interval | Session | Description |
|---|---|---|---|---|
| `health-check` | Always | 1h | Isolated | Combined health: service, WS, data, auth, circuit breakers |
| `error-logger` | Always | 15m | Isolated | Read agent ERRORS.md, investigate, file GitHub issues |
| `backtest-oversight` | Oversight-backtest | 1h | Isolated | Monitor progress, review results, evaluate promotion |
| `paper-oversight` | Oversight-paper | 6h | Isolated | Deep performance review: P&L, Sharpe, drawdown |
| `live-oversight` | Oversight-live | 6h | Isolated | Same as paper + live risk monitoring |
| `self-improvement` | Active during improvement cycle | 6h | Isolated | Learning promotion, experiment design, deployment validation |

### Category Agent Job Definitions

| Job | Phase | Interval | Session | Description |
|---|---|---|---|---|
| `decision-loop` | Paper, Live | 5m | Isolated | Full trading decision cycle via MCP tools |
| `circuit-breaker-check` | Paper, Live | 30m | Isolated | `traderbot halt --json` risk check |
| `position-review` | Paper, Live | 1h | Isolated | Position health, settlement sync, drawdown check |

**Note**: Backtesting phase has no category agent cron jobs — the backtesting engine drives the simulation, not the agent's decision loop. The agent participates via `sessions_send` prompts from SysAdmin or the test harness.

### Custom Jobs

SysAdmin can create ad-hoc jobs using `openclaw cron add` directly. Examples:
- Borderline agent performance → add a more frequent `performance-review` job (every 2h instead of 6h)
- New deployment → add temporary `high-frequency-health-check` (every 10min for 1 hour)
- Market volatility event → add temporary `volatility-monitor` job

Custom jobs follow naming convention `sysadmin-custom-*` for easy identification and cleanup.

---

## Self-Improvement Architecture

### Layer 1: Reactive Agent Learnings

- **Scope**: Category-specific operational quirks and recurring patterns
- **Trigger**: Discovered by category agents during normal operations
- **Mechanism**: Category agents document findings in `.learnings/` folder. After 3+ recurrences, the finding is flagged for promotion
- **Resolution**: SysAdmin investigates, verifies root cause, files GitHub issue

### Layer 2: Proactive Pipeline Improvement (Agent-Debate)

- **Scope**: Strictly limited to the data–analysis–decision pipeline
- **Trigger**: Continuous and proactive. Runs indefinitely. Required outcome: incremental improvement every cycle
- **Framework**: gumbel-ai/agent-debate integrated via OpenClaw's `sessions_spawn`/`sessions_send`/`sessions_yield`
- **Participants**: SysAdmin (orchestrator), Dev-Liaison (watcher), 2× Category Agent subs, 2× SysAdmin subs (adversarial debaters)
- **One concept per cycle**: Each improvement targets exactly one concept to modify, replace, or add
- **Statistical rigor**: Every claim must be grounded in verifiable evidence modeling how agent performance will be affected under Kalshi market conditions

**5-round improvement cycle** (DD-038):
1. **Identify Suboptimal Outcomes**: Each agent analyzes the entire pipeline, traces 10 root causes per agent (40 total, no duplicates)
2. **White Paper Development & Cross-Examination**: Each agent produces a white paper for each suggestion; cross-examined by other 3 agents sequentially
3. **Blind Vote**: All 6 participants cast one vote. Top 5 proposals advance
4. **In-Depth White Paper & Experiment Design**: Current code review, deep research, statistical experimental design
5. **Final Selection & Implementation**: SysAdmin selects top proposal; implementation path determined by root cause classification (TraderBot code issue → GitHub issue; Agent behavior issue → workspace update; Both → coordinated)

### Layer 3: Autonomous Development Team

- **Scope**: Full system architecture — any GitHub issue
- **Trigger**: GitHub issues filed by SysAdmin, agents, or humans
- **Mechanism**: Isolated team of autonomous dev agents picks up issues, investigates, deploys fixes, updates CHANGELOG.md
- **Status**: In development (future)
