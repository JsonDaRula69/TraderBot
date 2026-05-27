# Heartbeat Collector — Sysadmin

_All periodic checks run as isolated OpenClaw cron jobs. This file describes
each job for reference. The cron jobs fire independently — each in its own
session — so they never collide with other agent work or each other._

## Task Reference

| Task | Interval | What It Executes |
|---|---|---|
| main-fleet-health | 30m | Check fleet circuit breakers, pipeline timer status |
| main-experiment-check | 30m | Read agent SESSION-STATE.md for experiment proposals, queue in backlog |
| main-experiment-execution | 30m | Execute queued experiments from test-lab/backlog.md |
| main-learning-review | 1h | Cross-reference PENDING_REVIEW learnings against backlog |
| main-news-scan | 2h | `traderbot news-summary --signals --json`, surface high-impact items |
| main-pipeline-health | 3h | Run backfill, verify ChromaDB data_points, check timers |
| main-performance-review | 6h | Review agent P&L, drawdown, win rate across fleet |

## Setup

These cron jobs are registered by `traderbot cron setup` or can be verified:

```bash
openclaw cron list | grep " main "
```

## Data Output

The 7-step self-review data from `traderbot heartbeat --json` is written to
`HEARTBEAT_DATA.md` (not this file).
