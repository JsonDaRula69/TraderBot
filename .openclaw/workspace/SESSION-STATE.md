# Session State

## Deployment Bar

Controls when validated experiments are deployed to live agents. Switchable without downtime.

```
mode: backtest-only
params:
  min_sharpe: 1.0
  min_win_rate_improvement: 5             # percentage points
  min_samples: 30                         # minimum backtest trades
  min_edge_improvement: 0.005             # probability points
  
# Alternative mode (commented out):
# mode: backtest+paper
# params:
#   min_sharpe: 1.2
#   min_win_rate_improvement: 5
#   min_samples: 30
#   paper_days: 14                        # paper trade validation period
#   min_paper_edge: 0.005
```

To switch modes: update this block and the next experiment will use the new bar.

---

## Agent Fleet Registry

| Agent | Category | Profile | Status | Last Heartbeat | Positions | Daily P&L | Alerts |
|---|---|---|---|---|---|---|---|
| _(none)_ | — | — | UNASSIGNED | — | 0 | — | — |

**Status values:** UNASSIGNED, MONITORING, ALERT, HALTED, DECOMMISSIONED

When a new agent is created:
1. Run `traderbot profile assignments --json` to verify
2. Verify the agent's workspace exists at the agent's workspace path
3. Add to registry with MONITORING status
4. Log in Completed Actions

When a profile is revoked or agent decommissioned:
1. Verify with `traderbot profile assignments --json`
2. Set status to DECOMMISSIONED
3. Note the decommission date
4. Log in Completed Actions

---

## Experiment Tracker

_Each row is one run through the improvement lifecycle. Experiments are designed by category agents (via sub-agent instances), received by the sysadmin, executed in the test lab, validated against the deployment bar, and deployed or rejected._

| ID | Hypothesis | Agent (Source) | Status | Result | Deployed Change |
|---|---|---|---|---|---|
| _(none)_ | — | — | — | — | — |

**Status flow:** PROPOSED (by agent) → RECEIVED → QUEUED → RUNNING → VALIDATED → DEPLOYED
                                                                          ↘ REJECTED

**Status definitions:**
| Status | Meaning |
|---|---|
| PROPOSED | Agent submitted experiment design in their SESSION-STATE.md Pending Actions |
| RECEIVED | Sysadmin acknowledged receipt, added to this tracker |
| QUEUED | Experiment added to test-lab/backlog.md, awaiting execution slot |
| RUNNING | Backtest or paper trade in progress |
| VALIDATED | Results pass deployment bar — deploying now |
| DEPLOYED | Profile parameters updated. Result archived in test-lab/results/ |
| REJECTED | Failed validation bar. Reason documented. Result archived. |

### Experiment Intake Flow

1. **Detect** — At each heartbeat, read each agent's `SESSION-STATE.md` via `sessions_list` + `sessions_history`. Check Pending Actions for experiment proposals.
2. **Acknowledge** — Register the proposal in this tracker with status RECEIVED. Add experiment ID to the agent's SESSION-STATE.md Pending Actions: "EXP-001: RECEIVED by sysadmin."
3. **Queue** — Write the experiment to `test-lab/backlog.md` with status QUEUED.
4. **Execute** — On next heartbeat, move to RUNNING. Run `traderbot backtest` + `traderbot compare`.
5. **Validate** — Check results against deployment bar. DEPLOY or REJECT.
6. **Notify** — Use `sessions_send` to notify the originating agent of the outcome, or record the result in their SESSION-STATE.md.

---

## Pending Actions

- (no pending actions)

---

## Completed Actions

| Date | Action |
|---|---|---|
| 2026-05-28 | Workspace audit: fixed stale agent path references (agents/ → workspace/ layout), removed BOOTSTRAP.md/BOOT.md from tree, fixed weather HEARTBEAT.md agent name 'weatherman' → 'weather', removed stale 'profile set-auth' reference from weather TOOLS.md, fixed profile update flag name '--min-liquidity-threshold' → '--min-liquidity' in sysadmin TOOLS.md |
| 2026-05-24 | Sysadmin workspace fleshed out with autonomous improvement lifecycle. |
| 2026-05-24 | Deployment bar config added (backtest-only mode). |
| 2026-05-24 | Category agent workspaces created under weather/ |
| 2026-05-24 | Test lab scaffolded with full experiment lifecycle. |
| 2026-05-24 | Sysadmin workspace initialized. |

---

## Active Category Agents

_No category agents assigned yet._

---

## Learning Promotions

_None pending._

---

## Data Sources Used

- `traderbot profile assignments --json` — fleet inventory
- `traderbot profile list --json` — all profiles
- `traderbot profile show <name> --json` — profile details
- `traderbot profile update <name> --field <key> --value <val>` — deploy validated changes
- `traderbot profile create <name> --mode paper --categories ...` — create test profiles
- `traderbot heartbeat --json` — system health check
- `traderbot halt --json` — circuit breaker (fleet-wide)
- `traderbot performance --json` — agent performance review (per-agent)
- `traderbot backtest --strategy ... --category ... --from ... --to ... --json` — experiment execution
- `traderbot compare --profiles name1,name2 --json` — A/B experiment results
- `traderbot news-summary --signalsonly --json` — high-impact news
- `traderbot learnings list --json` — learning pattern promotions
