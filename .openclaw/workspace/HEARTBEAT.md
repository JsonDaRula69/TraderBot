# Heartbeat Checklist

_The Gateway wakes the agent on a cadence. Follow this checklist each time._

tasks:

- name: circuit-breaker-check
  interval: 30m
  prompt: "Run `traderbot halt` to check circuit breaker status. If SLOW or worse, report immediately."
- name: performance-review
  interval: 6h
  prompt: "Run `traderbot heartbeat --json` to run the 7-step self-review cycle (performance → decision review → Bayesian adaptation → learning promotion → circuit breaker check → system health → update HEARTBEAT_DATA.md)."
- name: learning-promotion
  interval: 6h
  prompt: "Review `.learnings/LEARNINGS.md` for entries with Recurrence-Count >= 3. Promote to PENDING_REVIEW status if not already. Never auto-commit to AGENTS.md."
- name: news-scan
  interval: 2h
  prompt: "Run `traderbot news --json` to check for high-impact news. If any impact score > 0.7, surface alert to main session."
- name: position-health
  interval: 1h
  prompt: "Run `traderbot positions --json` to check open positions. Flag any with drawdown > 5%."

## General Instructions

- If circuit breaker is HALT or FULL_STOP, do NOT place new trades.
- If Bayesian adaptation flags a drift (human_review: true), surface it.
- Keep alerts short and actionable.
- If nothing needs attention after all due tasks, reply HEARTBEAT_OK.

## Output Handling

After running `traderbot heartbeat --json`:
1. Read `HEARTBEAT_DATA.md` to see the results
2. If `circuit_breaker.level` != "OK", surface alert immediately with level and daily loss %
3. If `alerts` array has items, forward each to main session
4. If adaptation has `human_review: true`, flag it for human approval
5. If nothing needs attention after all checks, reply HEARTBEAT_OK

## Data Output

The 7-step review data is written to `HEARTBEAT_DATA.md` by `traderbot heartbeat` (not this file).