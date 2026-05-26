# Heartbeat Checklist

_The Gateway wakes Vane on a cadence. Follow this checklist each time._

tasks:

- name: circuit-breaker-check
  interval: 30m
  prompt: "Run `traderbot halt --json`. If circuit breaker is SLOW or worse, report to sysadmin immediately. If HALT or FULL_STOP, stop all trading."

- name: model-data-check
  interval: 30m
  prompt: "Run `traderbot data-points weather --json` to verify GFS/ECMWF/CMC data is available. If empty or errors: check whether the data pipeline timers are installed via `systemctl list-timers --all 2>/dev/null | grep traderbot || echo 'no timers'`. The data_points ChromaDB collection is populated by `traderbot-backfill-data@.timer` (daily) and `traderbot-news-ingest@.timer` (every 30m). If timers are running but data_points is still empty (< 24h since install), the initial backfill is in progress — note this in SESSION-STATE.md and proceed with live NWS web fetch data only. If timers are NOT running, surface to sysadmin: need to run `install-data-pipeline.sh`."

- name: pipeline-health
  interval: 6h
  prompt: "Run `systemctl is-active traderbot-backfill-data@*.timer traderbot-news-ingest@*.timer 2>/dev/null || launchctl list | grep traderbot 2>/dev/null || echo 'pipeline check unavailable'`. Verify both timers are active. If either is inactive, surface to sysadmin with the timer name. Also check data_points collection count: `traderbot data-points weather --json` should return >= 1 item. If count hasn't increased in 48h, surface stale-pipeline alert."

- name: news-scan
  interval: 30m
  prompt: "Run `traderbot news-context weather --json`. Check for: NHC advisories, NWS warnings, emergency declarations. If any active, switch to high-impact event cadence. If no active events, log standard context."

- name: performance-review
  interval: 6h
  prompt: "Run `traderbot heartbeat --json` to run the 7-step self-review cycle. Then manually check: drawdown > 3% in session → flag. Win rate < 40% over 30+ trades → escalate to sysadmin. Learning recurrence >= 3 → promote to PENDING_REVIEW."

- name: position-health
  interval: 1h
  prompt: "Run `traderbot positions --json`. Check each position: settlement < 48h away → assess exit. Model challenges position → recalculate conviction. Any position with drawdown > 5% → escalate to sysadmin."

- name: learning-promotion
  interval: 6h
  prompt: "Review `.learnings/LEARNINGS.md` for entries with Recurrence-Count >= 3. Promote to PENDING_REVIEW status via `traderbot learnings --promote <pattern-key>` if not already. For each newly promoted pattern, follow the Experiment Design Flow in AGENTS.md: spawn a sub-agent via `sessions_spawn`, call `sessions_yield`, collect the experiment design, review it, and record in SESSION-STATE.md under Pending Actions."

## General Instructions

- If circuit breaker is HALT or FULL_STOP, do NOT place new trades. Do NOT hold waiting for reversal — exit positions if exit conditions are favorable per SOUL.md.
- If model data is unavailable for more than 2 consecutive cycles, halt and surface.
- During high-impact weather events (hurricane, blizzard, heat wave), the agent will automatically shorten decision loop to 1 minute.
- Keep alerts to sysadmin short and actionable: "Vane: Data source GFS unavailable for 3 cycles. Trading halted."
- If nothing needs attention after all due tasks, reply HEARTBEAT_OK.

## Output Handling

After running `traderbot heartbeat --json`:
1. Read `HEARTBEAT_DATA.md` to see the 7-step review output
2. If `circuit_breaker.level` != "NORMAL", surface alert to sysadmin with level and daily loss %
3. If `alerts` array has items, forward each to sysadmin
4. If adaptation has `human_review: true`, flag it (note: this field exists but in practice the sysadmin handles it)
5. If nothing needs attention after all checks, reply HEARTBEAT_OK

## Data Output

The 7-step review data is written to `HEARTBEAT_DATA.md` by `traderbot heartbeat --json` (not this file).
