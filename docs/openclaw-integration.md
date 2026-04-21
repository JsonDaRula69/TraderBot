# OpenClaw Integration

How BetBot integrates with the OpenClaw agent framework — skill definition, workspace files, cron architectures, and proactive agent patterns.

## OpenClaw Overview

[OpenClaw](https://github.com/openclaw/openclaw) is a self-hosted personal AI assistant with a skill system. Skills are defined by `SKILL.md` files that tell the agent what tools are available, how to call them, and when to use them.

The agent consumes BetBot via **exec** calls — it shells out to our CLI commands and interprets the structured output.

## Skill Definition

The `skills/betbot/SKILL.md` file is the integration contract. It defines:

- **Available commands** and their arguments
- **When the agent should use each command** (trigger phrases)
- **Expected output format** (JSON structured responses)
- **Environment requirements** (API keys, Python version)

```yaml
---
name: betbot
description: Autonomous prediction market investment toolkit for Kalshi
metadata:
  openclaw:
    requires:
      env: ["KALSHI_API_KEY", "KALSHI_PRIVATE_KEY"]
      bins: ["python3"]
    primaryEnv: KALSHI_API_KEY
---
```

### Command Categories

| Category | Commands | Agent Trigger |
|---|---|---|
| **Market Analysis** | `scan`, `analyze`, `signals` | "What markets look interesting?", "Check KXBTCD markets" |
| **Trading** | `trade`, `positions`, `cancel` | "Buy Yes on BTC touch", "Show my positions" |
| **Simulation** | `backtest`, `paper`, `compare`, `performance` | "Test this strategy", "How did we do last week?" |
| **Self-Improvement** | `heartbeat`, `learnings`, `audit` | Periodic (cron), "Review our performance", "What have we learned?" |
| **News/Sentiment** | `news`, `sentiment` | "What's the latest news?", "Check BTC sentiment" |

## Three-Loop Cron Architecture

OpenClaw supports two cron execution modes. BetBot uses both intentionally:

### `isolated agentTurn` — Autonomous Background Work

Used for: **Decision Loop** and **Heartbeat Loop**

The agent spawns a sub-agent that executes independently. No human attention is needed. The sub-agent reads `SESSION-STATE.md` for context and writes results back.

```json
{
  "sessionTarget": "isolated",
  "payload": {
    "kind": "agentTurn",
    "message": "AUTONOMOUS: Run betbot decision loop. Read SESSION-STATE.md for tracked markets. Execute analysis, risk-check, and trades within guard rails. Log all decisions."
  }
}
```

**Decision Loop cron**: Runs every 5 minutes during market hours.
**Heartbeat Loop cron**: Runs every 6 hours.

### `systemEvent` — Interactive Alerts

Used for: **News/Sentiment Loop** (actionable events only)

When the news pipeline detects a high-impact event, it surfaces to the main session so the human can intervene if desired.

```json
{
  "sessionTarget": "main",
  "payload": {
    "kind": "systemEvent",
    "message": "ALERT: Fed emergency rate cut detected. This may affect 8 tracked markets. Run `betbot sentiment rate-cut` for analysis."
  }
}
```

## Workspace Files

OpenClaw uses a file-based memory system. BetBot's workspace mirrors the proactive-agent pattern (inspired by `halthelobster/proactive-agent`):

### AGENTS.md

Operating rules and constraints for the BetBot agent. Includes:
- Risk guard rails (immutable limits)
- Trading constraints (no shorting, binary outcomes)
- Market categories to track
- Preferred analysis approaches
- What requires human approval vs. what's autonomous

### SESSION-STATE.md (WAL Protocol target)

Active working memory — the Write-Ahead Log. The agent writes critical state here **before** taking action, ensuring context survives crashes or context loss.

Updated by the Decision Loop with:
- Currently tracked markets
- Active positions and pending orders
- Recent signal summary
- Last heartbeat timestamp

### HEARTBEAT.md

Periodic self-improvement checklist. Updated every 6 hours by the Heartbeat Loop:

```markdown
## Last Heartbeat: 2026-04-20T12:00:00Z
## Markets Tracked: 47
## Open Positions: 12
## Daily P&L: +2.3%

### Proactive Behaviors
- [x] Check circuit breaker conditions
- [x] Review recent decisions for pattern detection
- [x] Bayesian parameter updates applied (3 parameters adjusted)
- [x] Promoted 1 learning to permanent memory

### Self-Healing
- [x] No errors since last heartbeat

### Pending Actions
- [ ] Review low-liquidity position in KXBTCD-26MAR31-T55000
```

### USER.md

Human preferences — risk tolerance, market interests, notification preferences. This is where the human encodes their strategy appetite without the agent having to guess.

### .learnings/ Directory

Self-improvement logs, following the pattern from `peterskoett/self-improving-agent`:

- **LEARNINGS.md**: Corrections, insights, better approaches discovered
- **ERRORS.md**: API errors, failed orders, unexpected states
- **FEATURE_REQUESTS.md**: Capabilities the agent discovers it needs

Entries use structured metadata:
```markdown
## Entry: KALSHI-001
**Logged**: 2026-04-20T14:30:00Z
**Pattern-Key**: illiquid-market-slippage
**Recurrence-Count**: 4
**Priority**: high
**Status**: active
### Learning
Markets with open_interest < 500 experience significant slippage on orders > 5 contracts.
### Action
Added liquidity threshold to risk/limits.py
```

When Recurrence-Count >= 3 across 2+ tasks within 30 days, the agent promotes the learning to `AGENTS.md` as a permanent rule.

## WAL Protocol (Write-Ahead Log)

Borrowed from `proactive-agent`. Before the agent executes any trade:

1. **STOP** — do not place the order yet
2. **WRITE** — log the intended action to `SESSION-STATE.md` with reasoning
3. **THEN** — execute the order

This ensures every action is recoverable. If the agent crashes mid-trade, `SESSION-STATE.md` contains the intent and can be reconciled with actual positions on restart.

## Skill Loading Precedence

OpenClaw loads skills in this order (later overrides earlier):
1. Built-in / plugin skills
2. OpenClaw-shipped skills
3. User-installed skills (ClawHub or manual)
4. Project-level skills (in workspace)

BetBot is installed at the project level: `skills/betbot/SKILL.md`. This means it takes highest precedence and can override generic financial skills if any exist.

## Demo Mode for Development

During development, the agent uses the Kalshi demo API — `demo-api.kalshi.co` — which mirrors the production API but with fake money. This is controlled via environment variable:

```bash
KALSHI_DEMO=true  # routes all calls to demo API
```