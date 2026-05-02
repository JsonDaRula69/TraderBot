# TOOLS.md - Local Notes

_Skills define how tools work. This file is for our setup specifics._

> **⚠️ STRICTLY FORBIDDEN: Modifying this file, AGENTS.md, or SOUL.md requires explicit human approval. These are immutable operating constraints. Never edit them without being asked.**

## TraderBot CLI

- **Binary**: `traderbot` (installed via `uv` or `pip install -e .`)
- **Python**: 3.12+
- **Config**: `.env` file (never committed) with `KALSHI_API_KEY`, `KALSHI_PRIVATE_KEY`
- **Demo mode**: `KALSHI_DEMO=true` routes to `demo-api.kalshi.co` (fake money)

## Environment

- **DB**: SQLite at `traderbot.db` (in workspace)
- **ChromaDB**: Local instance for vector embeddings (graceful fallback if unavailable)
- **Voyage AI**: Embedding API (graceful fallback to VADER/TextBlob if unavailable)

## Key Commands

### Market Analysis
| What | Command |
|---|---|
| List open markets | `traderbot scan --json` |
| List open markets (filtered) | `traderbot scan --category crypto --limit 50 --json` |
| Analyze a market | `traderbot analyze TICKER --json` |
| Show active signals | `traderbot signals --json` |

### Trading
| What | Command |
|---|---|
| Place trade | `traderbot trade TICKER --direction yes --quantity N --price CENTS --json` |
| Check positions | `traderbot positions --json` |
| Cancel order | `traderbot cancel ORDER_ID --json` |
| Check circuit breaker | `traderbot halt` |
| Force halt | `traderbot halt --force` |

### News & Sentiment
| What | Command |
|---|---|
| Fetch news | `traderbot news --json` |
| Market sentiment | `traderbot sentiment --ticker TICKER --json` |

### Simulation & Backtesting
| What | Command |
|---|---|
| Run backtest | `traderbot backtest --strategy momentum --from 2025-01-01 --to 2025-03-01 --json` |
| Paper trade | `traderbot paper --strategy momentum --json` |
| Compare strategies | `traderbot compare --json` |
| Performance metrics | `traderbot performance --json` |

### Self-Improvement
| What | Command |
|---|---|
| Self-review (7-step) | `traderbot heartbeat --json` |
| List learnings | `traderbot learnings --json` |
| List learnings (filtered) | `traderbot learnings --status pending_review --category Strategy --json` |
| Promote a learning | `traderbot learnings --promote PATTERN_KEY` |

### Profile Management (Multi-Agent)
| What | Command |
|---|---|
| List profiles | `traderbot profile list` |
| Show profile | `traderbot profile show PROFILE_NAME` |
| Create profile | `traderbot profile create PROFILE_NAME --risk-multiplier 0.8` |
| Assign token to agent | `traderbot profile assign PROFILE_NAME --token TOKEN` |
| Discover agents | `traderbot profile discover-agents --json` |
| Set profile auth | `traderbot profile set-auth PROFILE_NAME --provider kalshi` |

### Utilities
| What | Command |
|---|---|
| Audit trail | `traderbot audit --json` |
| Check/apply updates | `traderbot update` |
| Manage API credentials | `traderbot auth --help` |
| One-time setup wizard | `traderbot bootstrap` |

## Skill Location

The TraderBot skill definition is at `skills/traderbot/SKILL.md` in the project root. OpenClaw loads this at the **project level** (highest precedence). Read it to understand:
- When to trigger each command (trigger phrases)
- Expected output format (JSON schema)
- Environment requirements (KALSHI_API_KEY, etc.)

## WAL Protocol (SESSION-STATE.md Writes)

Before executing any trade, write intent to `SESSION-STATE.md`:
```markdown
## Pending Actions
Status: PENDING
Action: trade KXBTC-25JUN
Direction: yes
Quantity: 5
Price: 45 (cents)
Reasoning: Statistical signal 0.72, news sentiment positive
```

After execution, update:
```markdown
Status: COMPLETED
Result: filled at 43 cents
```

If crash occurs mid-trade, `SESSION-STATE.md` preserves intent for reconciliation.

## Cron & Autonomous Loops

TraderBot uses two OpenClaw cron modes:

**`isolated agentTurn`** — for Decision Loop and Heartbeat:
```json
{
  "sessionTarget": "isolated",
  "payload": {
    "kind": "agentTurn",
    "message": "AUTONOMOUS: Run traderbot decision loop. Read SESSION-STATE.md for tracked markets."
  }
}
```

**`systemEvent`** — for high-impact news alerts (surfaces to main session):
```json
{
  "sessionTarget": "main",
  "payload": {
    "kind": "systemEvent",
    "message": "ALERT: High-impact news detected. Run `traderbot sentiment TICKER --json`."
  }
}
```

## Strategy Note

Default strategy is `momentum`. Available strategies are defined in `src/traderbot/simulation/strategies/`.
A dedicated `STRATEGY.md` document is coming — it will detail each strategy's logic, parameters, and when to use which.

## Gotchas

- `traderbot trade` requires price in **cents** (int), not dollars
- Circuit breaker at HALT/FULL_STOP blocks all new trades
- `--json` flag is required for machine-readable output
- Bayesian adaptation has a 4-update/day cooldown — don't expect updates every heartbeat
- Backtest `--strategy` flag accepts: `momentum`, `contrarian`, etc. (see `src/traderbot/simulation/strategies/`)
- `traderbot profile discover-agents` scans OpenClaw workspace to map agents ↔ profiles
- Portfolio is divided equally across enabled markets (not max 10% per market)