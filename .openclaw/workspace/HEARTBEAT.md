# Heartbeat Collector — Sysadmin

_All periodic checks run as isolated OpenClaw cron jobs. This file describes
each job for reference. The cron jobs fire independently — each in its own
session — so they never collide with other agent work or each other._

## Task Reference

| Task | Interval | What It Executes |
|---|---|---|
| main-circuit-breaker-check | 30m | `traderbot halt --json` fleet-wide |
| main-experiment-check | 30m | Read agent SESSION-STATE.md for proposals, queue in backlog |
| main-experiment-execution | 15,45 past hour | Execute queued experiments from test-lab/backlog.md |
| main-auth-check | 1h | `traderbot auth check --json` - verify all API credentials |
| main-learning-review | 1h | Cross-reference PENDING_REVIEW against backlog |
| main-pipeline-health | 6h | Pipeline timers, ChromaDB data_points count, backfill if stale |
| main-performance-review | 6h | Fleet P&L, agent win rates, drawdown |

## Setup

These cron jobs are registered by `traderbot cron setup-heartbeat-tasks --role sysadmin` or can be verified:

```bash
openclaw cron list | grep " main "
```

## Data Output

The 7-step self-review data from `traderbot heartbeat --json` is written to
`HEARTBEAT_DATA.md` (not this file).
