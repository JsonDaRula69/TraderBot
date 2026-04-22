---
name: traderbot
description: Autonomous prediction market investment toolkit for Kalshi
metadata:
  openclaw:
    requires:
      env: ["KALSHI_API_KEY", "KALSHI_PRIVATE_KEY"]
      bins: ["python3"]
    primaryEnv: KALSHI_API_KEY
---

# TraderBot — Kalshi Prediction Market Toolkit

## Commands

| Command | Args | Description |
|---|---|---|
| `traderbot scan` | `[--limit N] [--category STR] [--json]` | List open markets on Kalshi |
| `traderbot analyze` | `TICKER [--json]` | Market details, orderbook, indicators, edge estimate |
| `traderbot trade` | `TICKER --direction yes/no --quantity N --price CENTS [--json]` | Place trade through risk pipeline |
| `traderbot positions` | `[--json]` | List current positions from SQLite |
| `traderbot audit` | `[--ticker STR] [--start ISO] [--end ISO] [--outcome STR] [--json]` | Decision history with filters |
| `traderbot signals` | `[--json]` | Active signals across tracked markets |
| `traderbot heartbeat` | | System status summary |
| `traderbot halt` | `[--force]` | Circuit breaker status or forced halt |
| `traderbot news` | `[--source STR] [--json]` | Fetch recent news (Phase 7) |
| `traderbot sentiment` | `[--ticker STR] [--json]` | Sentiment analysis (Phase 7) |
| `traderbot backtest` | `STRATEGY [--json]` | Run backtest (Phase 5) |
| `traderbot paper` | `[--json]` | Paper trading mode (Phase 5) |
| `traderbot compare` | `STRATEGY_A STRATEGY_B [--json]` | Compare strategies (Phase 5) |
| `traderbot performance` | `[--period STR] [--json]` | Portfolio performance (Phase 5) |
| `traderbot learnings` | `[--json]` | Self-improvement log (Phase 6) |

## Trigger Phrases

| When the agent says/thinks... | Use command |
|---|---|
| "What markets look interesting?" / "Find opportunities" | `traderbot scan` |
| "Check KX* markets" / "Analyze this market" | `traderbot analyze <ticker>` |
| "Buy Yes on..." / "Place a trade" | `traderbot trade` |
| "Show my positions" / "What am I holding?" | `traderbot positions` |
| "Review decisions" / "Decision history" | `traderbot audit` |
| "Check signals" / "Active signals" | `traderbot signals` |
| "System status" / "Health check" | `traderbot heartbeat` |
| "Stop trading" / "Circuit breaker" | `traderbot halt` |
| "What's the latest news?" | `traderbot news` (Phase 7) |
| "Check sentiment" | `traderbot sentiment` (Phase 7) |
| "Test this strategy" | `traderbot backtest` (Phase 5) |
| "How did we do?" / "Performance" | `traderbot performance` (Phase 5) |

## Output Format

All commands support `--json` flag for machine-readable output. When `--json` is set, output is a single JSON object (or array) printed to stdout. Human-readable output uses Rich formatting.

### JSON Response Shape

```json
{
  "command": "scan",
  "timestamp": "2026-04-21T12:00:00Z",
  "data": { ... }
}
```

## Environment

| Variable | Required | Description |
|---|---|---|
| `KALSHI_API_KEY` | Yes | Kalshi API authentication key |
| `KALSHI_PRIVATE_KEY` | Yes | RSA private key for JWT auth |
| `KALSHI_DEMO` | No | Set to `true` to use demo API (`demo-api.kalshi.co`) |

## Cron Architecture

OpenClaw supports two cron execution modes. TraderBot uses both intentionally:

- **`isolated agentTurn`** — Autonomous background work (Decision Loop, Heartbeat Loop)
- **`systemEvent`** — Interactive alerts surfaced to main session (News Loop)

Defined programmatically in `src/traderbot/cron_loops.py`.

### Decision Loop (every 5 minutes, market hours)

- **Cron**: `*/5 9-15 * * 1-5` (9:30 AM–4:00 PM ET, Mon–Fri)
- **Mode**: `isolated agentTurn`
- **Impact threshold**: N/A (scheduled)

```json
{
  "sessionTarget": "isolated",
  "payload": {
    "kind": "agentTurn",
    "message": "AUTONOMOUS: Run traderbot decision loop. Read SESSION-STATE.md for tracked markets. Execute analysis, risk-check, and trades within guard rails. Log all decisions."
  }
}
```

### Heartbeat Loop (every 6 hours)

- **Cron**: `0 */6 * * *`
- **Mode**: `isolated agentTurn`
- **Impact threshold**: N/A (scheduled)
- Includes capability gap detection — scans `.learnings/FEATURE_REQUESTS.md` for entries with `Recurrence-Count >= 3`, promotes to `PENDING_REVIEW`

```json
{
  "sessionTarget": "isolated",
  "payload": {
    "kind": "agentTurn",
    "message": "HEARTBEAT: Run traderbot self-improvement cycle. Check circuit breaker, review recent decisions, update Bayesian parameters, promote learnings. Write HEARTBEAT.md."
  }
}
```

### News/Sentiment Loop (event-driven)

- **Cron**: None (event-driven, not scheduled)
- **Mode**: `systemEvent` (surfaces to main session for human intervention)
- **Impact threshold**: `0.7` (only triggers on high-impact events)

```json
{
  "sessionTarget": "main",
  "payload": {
    "kind": "systemEvent",
    "message": "ALERT: High-impact event detected. Run `traderbot sentiment <topic>` for analysis."
  }
}
```

## Risk Guard Rails

The agent MUST respect these immutable constraints enforced by the risk module:
- Maximum position size: 10% of portfolio per market
- Daily loss limit: 1% / 2% / 10% (SLOW / HALT / FULL_STOP circuit breaker)
- No short selling (binary markets only)
- All trades logged with full reasoning in audit trail