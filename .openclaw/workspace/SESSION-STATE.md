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

### WAL-06F96D33
- Timestamp: 2026-06-01T01:25:28.978024+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-82F503AC
- Timestamp: 2026-06-01T01:25:29.150234+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-157884A2
- Timestamp: 2026-06-01T01:25:29.252714+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-667A2509
- Timestamp: 2026-06-01T01:26:25.121591+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-610F7415
- Timestamp: 2026-06-01T01:26:25.223661+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-81999D80
- Timestamp: 2026-06-01T01:26:25.323807+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-B1A2AB92
- Timestamp: 2026-06-01T01:26:25.422726+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-B1E92E17
- Timestamp: 2026-06-01T01:26:25.501089+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-92545296
- Timestamp: 2026-06-01T01:28:25.156207+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-0D6BE624
- Timestamp: 2026-06-01T01:28:25.254432+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-625FEC6A
- Timestamp: 2026-06-01T01:28:25.350824+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-0D65DFD8
- Timestamp: 2026-06-01T01:28:25.443544+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-B7CB53E9
- Timestamp: 2026-06-01T01:28:25.521619+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-B13E2833
- Timestamp: 2026-06-01T01:28:40.902045+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-05F179B6
- Timestamp: 2026-06-01T01:28:41.079503+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-587265FD
- Timestamp: 2026-06-01T01:28:41.177383+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-56E31500
- Timestamp: 2026-06-01T01:28:41.272443+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-83CE74E5
- Timestamp: 2026-06-01T01:28:41.352430+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-BECF9A9E
- Timestamp: 2026-06-01T01:28:58.346228+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-EC8304FE
- Timestamp: 2026-06-01T01:34:49.126009+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-0C4440E3
- Timestamp: 2026-06-01T01:34:49.279458+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-B22C59FD
- Timestamp: 2026-06-01T01:34:49.375106+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-61DAD8FA
- Timestamp: 2026-06-01T01:34:49.478576+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-70DAE087
- Timestamp: 2026-06-01T01:34:49.562286+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-25B0FCF6
- Timestamp: 2026-06-01T01:35:15.660634+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-99B7CC62
- Timestamp: 2026-06-01T01:38:51.977611+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-1C5845CD
- Timestamp: 2026-06-01T01:38:52.063876+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-F5682F2D
- Timestamp: 2026-06-01T01:38:52.141621+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-DF90C130
- Timestamp: 2026-06-01T01:38:52.215947+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-4FCA9C8F
- Timestamp: 2026-06-01T01:38:52.290505+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-527FD3EC
- Timestamp: 2026-06-01T01:39:03.389121+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-E760CB5C
- Timestamp: 2026-06-01T01:42:14.143034+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-CAE45995
- Timestamp: 2026-06-01T01:42:14.225653+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-F1CE8B00
- Timestamp: 2026-06-01T01:42:14.298842+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-068DE4F5
- Timestamp: 2026-06-01T01:42:14.372783+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-B8A93F94
- Timestamp: 2026-06-01T01:42:14.446231+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-330C62B3
- Timestamp: 2026-06-01T01:42:20.373936+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-55D0B2B0
- Timestamp: 2026-06-01T01:45:09.342393+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-AA791398
- Timestamp: 2026-06-01T01:45:09.425862+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-952B4A2B
- Timestamp: 2026-06-01T01:45:09.501503+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-3314E7A4
- Timestamp: 2026-06-01T01:45:09.578618+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-91E0692A
- Timestamp: 2026-06-01T01:45:09.651556+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-AAFA9483
- Timestamp: 2026-06-01T01:45:20.218425+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-E11B9C93
- Timestamp: 2026-06-01T01:46:34.210960+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-3060BC1A
- Timestamp: 2026-06-01T01:46:34.289618+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-89BD9EF4
- Timestamp: 2026-06-01T01:46:34.375910+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-B8CEA23E
- Timestamp: 2026-06-01T01:46:34.453187+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-680DB90F
- Timestamp: 2026-06-01T01:46:34.525905+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-32BA9215
- Timestamp: 2026-06-01T01:46:39.483701+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-68953ACD
- Timestamp: 2026-06-01T01:47:10.828637+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-DD2DFD8B
- Timestamp: 2026-06-01T01:47:10.981822+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-082BA39E
- Timestamp: 2026-06-01T01:47:11.060863+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-0A409B8E
- Timestamp: 2026-06-01T01:47:11.136019+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-7324948A
- Timestamp: 2026-06-01T01:47:11.215346+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-0B14EAF0
- Timestamp: 2026-06-01T01:47:22.823395+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-473F701D
- Timestamp: 2026-06-01T01:48:21.373249+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-B4D8E97C
- Timestamp: 2026-06-01T01:48:21.523279+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-4911423F
- Timestamp: 2026-06-01T01:48:21.599582+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-C658E626
- Timestamp: 2026-06-01T01:48:21.680134+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-A95F5853
- Timestamp: 2026-06-01T01:48:21.754537+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-E1E1128D
- Timestamp: 2026-06-01T01:48:31.821642+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-CAD59BC2
- Timestamp: 2026-06-01T01:49:21.466506+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-D76F1531
- Timestamp: 2026-06-01T01:49:21.566886+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-89C44B01
- Timestamp: 2026-06-01T01:49:21.663800+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-DE322690
- Timestamp: 2026-06-01T01:49:21.766973+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-D139B8E3
- Timestamp: 2026-06-01T01:49:21.956535+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-E188F267
- Timestamp: 2026-06-01T01:49:34.643346+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-E1AD6DE4
- Timestamp: 2026-06-01T01:49:51.537541+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-11BE7E4F
- Timestamp: 2026-06-01T01:50:18.614561+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-69B2F737
- Timestamp: 2026-06-01T01:51:09.642179+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-2D2B70D7
- Timestamp: 2026-06-01T01:51:09.725544+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-18BAEAB6
- Timestamp: 2026-06-01T01:51:09.798630+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-F24F5FF9
- Timestamp: 2026-06-01T01:51:09.872718+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-78D26096
- Timestamp: 2026-06-01T01:51:09.950035+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-278EFD2C
- Timestamp: 2026-06-01T01:51:13.945427+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-B0C9DCE5
- Timestamp: 2026-06-01T01:51:35.248333+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-D0230930
- Timestamp: 2026-06-01T01:51:35.486349+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-1E70A320
- Timestamp: 2026-06-01T01:51:35.612973+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-11D0EC3C
- Timestamp: 2026-06-01T01:51:35.735589+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-DD6F7552
- Timestamp: 2026-06-01T01:51:35.873881+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
Status: REJECTED
Status: REJECTED
Status: REJECTED
Status: REJECTED
Status: REJECTED
Status: REJECTED
Status: REJECTED
Status: REJECTED
Status: REJECTED
### WAL-B798201B
- Timestamp: 2026-06-01T01:52:36.274400+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-A75C9972
- Timestamp: 2026-06-01T01:52:36.347233+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
Status: REJECTED
### WAL-A0EDDBF6
- Timestamp: 2026-06-01T01:52:41.020629+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
Status: REJECTED
Status: REJECTED
Status: CANCELLED
Status: CANCELLED
Status: REJECTED
Status: REJECTED
Status: REJECTED
Status: EXECUTED
### WAL-963E39EA
- Timestamp: 2026-06-01T01:55:33.691044+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
Status: REJECTED
Status: REJECTED
### WAL-4FF5B96A
- Timestamp: 2026-06-01T01:55:56.726939+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
Status: REJECTED
Status: REJECTED
Status: EXECUTED
Status: EXECUTED
Status: REJECTED
Status: REJECTED
Status: REJECTED
Status: EXECUTED
Status: EXECUTED
Status: REJECTED
Status: REJECTED
Status: REJECTED
Status: EXECUTED
Status: EXECUTED
Status: REJECTED
Status: REJECTED
Status: REJECTED
Status: EXECUTED
Status: EXECUTED
Status: REJECTED
Status: REJECTED
Status: REJECTED
Status: EXECUTED
Status: EXECUTED
Status: REJECTED
Status: REJECTED
Status: REJECTED
Status: EXECUTED
Status: EXECUTED
Status: REJECTED
Status: REJECTED
Status: REJECTED
Status: EXECUTED
Status: EXECUTED
Status: REJECTED
Status: REJECTED
Status: REJECTED
Status: EXECUTED
Status: EXECUTED
Status: REJECTED
## Completed Actions

_No activity yet._

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