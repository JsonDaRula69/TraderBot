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
### WAL-D22307EF
- Timestamp: 2026-06-02T23:59:07.632462+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-BE30A78F
- Timestamp: 2026-06-03T00:00:01.104717+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-2BCC34BE
- Timestamp: 2026-06-03T00:09:21.250253+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-CFD94490
- Timestamp: 2026-06-03T00:09:21.450693+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-2A31FD83
- Timestamp: 2026-06-03T00:09:21.552576+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-3A1F51DD
- Timestamp: 2026-06-03T00:09:21.653445+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-91849C8F
- Timestamp: 2026-06-03T00:11:28.118878+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-7DBE71EA
- Timestamp: 2026-06-03T00:14:51.239728+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-5A04B0BE
- Timestamp: 2026-06-03T00:16:54.897223+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-3EA7040C
- Timestamp: 2026-06-03T00:19:08.147794+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-526716E8
- Timestamp: 2026-06-03T02:05:00.599354+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-3E33E8D0
- Timestamp: 2026-06-03T02:05:00.786049+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-ED95DF78
- Timestamp: 2026-06-03T02:05:00.889278+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-E87C49FD
- Timestamp: 2026-06-03T02:05:00.989762+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-BCE77850
- Timestamp: 2026-06-03T02:05:01.106851+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-34AF90ED
- Timestamp: 2026-06-03T02:05:59.024025+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-95C93604
- Timestamp: 2026-06-03T02:05:59.213180+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-0E0A8D95
- Timestamp: 2026-06-03T02:05:59.318229+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-3E732BD6
- Timestamp: 2026-06-03T02:05:59.423049+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-227F5D92
- Timestamp: 2026-06-03T02:05:59.524060+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-D382801C
- Timestamp: 2026-06-03T02:08:21.584519+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-42D661E8
- Timestamp: 2026-06-03T02:08:21.759796+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-9DBBF649
- Timestamp: 2026-06-03T02:08:21.858053+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-FE596B0B
- Timestamp: 2026-06-03T02:08:21.962574+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-278A41C0
- Timestamp: 2026-06-03T02:20:05.604444+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-184A9D8A
- Timestamp: 2026-06-03T02:46:14.369005+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-164DDC48
- Timestamp: 2026-06-03T02:46:14.601695+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-BF699092
- Timestamp: 2026-06-03T02:46:14.722754+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-103B9474
- Timestamp: 2026-06-03T02:46:14.856223+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-3286AE29
- Timestamp: 2026-06-03T02:46:14.979567+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-D51FB0DF
- Timestamp: 2026-06-03T03:56:34.360004+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-9C3753E9
- Timestamp: 2026-06-03T03:56:34.698315+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-8CE39C10
- Timestamp: 2026-06-03T03:56:34.800634+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-F6736F54
- Timestamp: 2026-06-03T03:56:46.758720+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-78E63432
- Timestamp: 2026-06-03T03:56:47.073624+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-25D09334
- Timestamp: 2026-06-03T03:56:47.182535+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-712447AE
- Timestamp: 2026-06-03T03:57:11.616200+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-BB8BAA87
- Timestamp: 2026-06-03T03:57:11.630262+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-04EA7F65
- Timestamp: 2026-06-03T03:57:38.848200+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-29544CBB
- Timestamp: 2026-06-03T03:57:45.341190+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-D4AF53C8
- Timestamp: 2026-06-03T03:57:45.679436+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-39B4D59F
- Timestamp: 2026-06-03T03:57:45.799037+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-3C13FE3D
- Timestamp: 2026-06-03T03:59:12.283147+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-C6082868
- Timestamp: 2026-06-03T03:59:12.610034+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-85C1D4B4
- Timestamp: 2026-06-03T03:59:12.725998+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-6DB99860
- Timestamp: 2026-06-03T03:59:12.838965+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-843DBEDA
- Timestamp: 2026-06-03T03:59:12.945111+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-AD3C284E
- Timestamp: 2026-06-03T04:00:30.950828+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-4A54D8D6
- Timestamp: 2026-06-03T04:00:31.265610+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-9E18E11D
- Timestamp: 2026-06-03T04:00:31.370160+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-592E3E1A
- Timestamp: 2026-06-03T04:00:31.478346+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-434377C4
- Timestamp: 2026-06-03T04:00:31.581378+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-D6E6F9FE
- Timestamp: 2026-06-03T04:01:32.340286+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-2DCD485C
- Timestamp: 2026-06-03T04:01:32.518328+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-30DCCC07
- Timestamp: 2026-06-03T04:11:11.470663+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-E11AFC4F
- Timestamp: 2026-06-03T04:11:11.798998+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-52E7FDEA
- Timestamp: 2026-06-03T04:11:11.904659+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-CE685632
- Timestamp: 2026-06-03T04:31:00.366021+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-94359AB3
- Timestamp: 2026-06-03T04:31:00.485737+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-73E1E75A
- Timestamp: 2026-06-03T04:31:50.202705+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-76EEAC2A
- Timestamp: 2026-06-03T04:31:50.510288+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-0D5F6D33
- Timestamp: 2026-06-03T04:31:50.699401+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-B2C34126
- Timestamp: 2026-06-03T04:32:07.579772+00:00
- Action: BUY YES 1 KXBTCD-26MAR31-T55000 @ 60¢
- Reason: trade yes KXBTCD-26MAR31-T55000 @ 60¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-120F8854
- Timestamp: 2026-06-03T04:32:07.584697+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
Status: REJECTED
Status: EXECUTED
Status: REJECTED
Status: EXECUTED
Status: REJECTED
Status: EXECUTED
Status: EXECUTED
Status: REJECTED
Status: EXECUTED
Status: EXECUTED
Status: REJECTED
Status: REJECTED
Status: REJECTED
Status: EXECUTED
Status: EXECUTED
Status: REJECTED
### WAL-43615148
- Timestamp: 2026-06-03T04:54:12.360576+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
### WAL-52A5F5BB
- Timestamp: 2026-06-03T04:54:12.665488+00:00
- Action: BUY YES 1 TEST-TICKER @ 50¢
- Reason: trade yes TEST-TICKER @ 50¢
- Signal: (none)
- Risk: (none)
- Confidence: 0.50
- Status: PENDING
Status: EXECUTED
Status: EXECUTED
Status: REJECTED
Status: EXECUTED
Status: EXECUTED
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