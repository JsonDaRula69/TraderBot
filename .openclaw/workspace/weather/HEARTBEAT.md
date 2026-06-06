# Heartbeat Collector

_All periodic checks run as isolated OpenClaw cron jobs. This file describes
each job for reference. The cron jobs fire independently — each in its own
session — so they never collide with trading or each other._

## Task Reference

| Task | Interval | What It Executes |
|---|---|---|
| circuit-breaker-check | 30m | `traderbot halt --json` |
| news-scan | 30m | `traderbot news-context weather --json` |
| decision-loop | 5m | Full 10-step trading decision cycle (scan, filter, forecast, model consensus, bias, analyze, news, trade, log) |
| data-forecast-check | 15,45 past hour | `traderbot data forecasts --cities NYC,CHI,LA,PHX,SEA --json` |
| position-health | 1h | `traderbot positions --json` |
| settlement-monitor | 1h | Check recently settled markets, update local positions with PnL |
| auth-check | 1h | `traderbot auth check --json` - verify Kalshi credentials resolvable |
| performance-review | 6h | `traderbot heartbeat --json` |
| learning-promotion | 6h | `.learnings/LEARNINGS.md` PENDING_REVIEW promotion + experiment design |
| pipeline-health | 6h | Pipeline timer status + data_points collection count |

## Setup

Register all tasks as isolated cron jobs (run once):

```bash
traderbot cron setup --agent weather --role trader --replace
```

Verify:
```bash
traderbot cron setup --agent weather --role trader --json
```

Remove:
```bash
traderbot cron setup --agent weather --role trader --replace
```
