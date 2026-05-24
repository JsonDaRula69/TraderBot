# Heartbeat Checklist

_The Gateway wakes the sysadmin on a cadence. Follow this checklist each time._

## Sysadmin-only Tasks

tasks:

- name: agent-health-check
  interval: 30m
  prompt: "Review HEARTBEAT_DATA.md for all category agents. Check circuit breaker status. If any agent is SLOW or worse, report immediately."
- name: learning-promotion
  interval: 6h
  prompt: "Review `.learnings/LEARNINGS.md` for entries with Recurrence-Count >= 3. Promote to PENDING_REVIEW status if not already. Never auto-commit to AGENTS.md."
- name: test-lab-review
  interval: 6h
  prompt: "Check `test-lab/backlog.md` for pending tests. If any are approved by human, queue them for execution."
- name: news-scan
  interval: 2h
  prompt: "Run `traderbot news-summary --signalsonly --json` to check for high-impact news signals. If any impact score > 0.7, surface alert to main session."
- name: performance-review
  interval: 6h
  prompt: "Run `traderbot performance --json` to review agent P&L and win rate. Flag any agent with drawdown > 5% or win rate < 40%."

## General Instructions

- If any category agent circuit breaker is HALT or FULL_STOP, do NOT attempt to fix it yourself. Surface alert for human review.
- If test-lab results show promise, summarize and wait for human approval before suggesting deployment.
- Keep alerts short and actionable.
- If nothing needs attention after all due tasks, reply HEARTBEAT_OK.

## Output Handling

After running `traderbot heartbeat --json`:
1. Read `HEARTBEAT_DATA.md` to see the results
2. If `circuit_breaker.level` != "NORMAL" for any agent, surface alert immediately with level and daily loss %
3. If `alerts` array has items, forward each to main session
4. If adaptation has `human_review: true`, flag it for human approval
5. If nothing needs attention after all checks, reply HEARTBEAT_OK

## Data Output

The 7-step review data is written to `HEARTBEAT_DATA.md` by `traderbot heartbeat --json` (not this file).
