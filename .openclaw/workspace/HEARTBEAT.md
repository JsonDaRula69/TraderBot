# Heartbeat Checklist

_The Gateway wakes the sysadmin on a cadence. Follow this checklist each time._

## Sysadmin Tasks

tasks:

- name: agent-health-check
  interval: 30m
  prompt: "Run `traderbot halt --json` and read `HEARTBEAT_DATA.md` for all category agents. If any circuit breaker is SLOW or worse, investigate. If HALT or FULL_STOP, surface alert to main session."

- name: agent-experiment-check
  interval: 30m
  prompt: "For each registered agent in SESSION-STATE.md, read `agents/<category>/SESSION-STATE.md` (via `sessions_list` and `sessions_history`) and check Pending Actions for experiment proposals. If a proposal exists, extract the full experiment design and queue it in `test-lab/backlog.md` as QUEUED. Acknowledge receipt to the agent by recording the experiment ID in their Pending Actions with status 'RECEIVED'."

- name: learning-review
  interval: 1h
  prompt: "Run `traderbot learnings list --json`. Cross-reference PENDING_REVIEW entries against open experiments in `test-lab/backlog.md`. Any promotions without a matching experiment → check that agent's workspace — the agent should be designing. If an agent has a pattern at recurrence >= 3 but no matching experiment proposal in their SESSION-STATE.md after 2+ heartbeats, surface alert."

- name: experiment-execution
  interval: 30m
  prompt: "Check `test-lab/backlog.md` for QUEUED or RUNNING experiments. If QUEUED and execution slot is free, set to RUNNING and execute. If RUNNING, check results against deployment bar in `SESSION-STATE.md`. If validated → DEPLOY (run profile update). If rejected → archive result, update experiment status."

- name: news-scan
  interval: 2h
  prompt: "Run `traderbot news-summary --signals --json`. If any impact score > 0.7, surface alert to main session."

- name: performance-review
  interval: 6h
  prompt: "Run `traderbot performance --json`. Check each agent against thresholds: drawdown > 5% → investigate. Win rate < 40% over 30+ trades → consider revoke. Log findings."

## Output Handling

After running `traderbot heartbeat --json`:
1. Read `HEARTBEAT_DATA.md` for the 7-step review output
2. Check the experiment pipeline (learning-review + experiment-check tasks)
3. If any agent circuit breaker is HALT or FULL_STOP, surface alert with level and daily loss %
4. If a deployment failed, retry once; if it fails again, surface alert
5. If nothing needs attention after all checks, reply HEARTBEAT_OK

## Data Output

The 7-step review data is written to `HEARTBEAT_DATA.md` by `traderbot heartbeat --json` (not this file).
