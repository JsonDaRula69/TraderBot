# Test Lab Backlog

_A central registry for all experiments in the autonomous improvement lifecycle. Experiments are designed, queued, executed, and deployed without human intervention._

---

## Queue

_New experiments go here. Auto-created by the sysadmin when a pattern promotes to PENDING_REVIEW._

| ID | Hypothesis | Target Agent | Strategy Variant | Status |
|---|---|---|---|---|
| _(none)_ | — | — | — | — |

---

## Experiment Lifecycle

```
DISCOVERED → QUEUED → RUNNING → VALIDATED → DEPLOYED
                                    ↘ REJECTED
```

### 1. DISCOVERED (Sysadmin Formulates Hypothesis)

Pattern promoted to PENDING_REVIEW. The sysadmin designs an experiment:

- **Hypothesis**: "If we adjust min_edge from 0.03 to 0.025 for econ agent, we capture more valid signals without increasing loss rate"
- **Target**: Which agent/category this applies to
- **Experiment Type**: backtest or backtest+paper (per deployment bar)
- **Success Criteria**: Sharpe >= min_sharpe, win rate improvement >= min threshold, sample size >= min_samples

### 2. QUEUED → RUNNING

Sysadmin adds to queue, sets status to RUNNING, executes:

```bash
# Backtest the variant
traderbot backtest --strategy momentum --category economics --from 2026-01-01 --to 2026-05-24 --json

# Compare against current
traderbot compare --profiles econ-test-v2,econ-current --json
```

### 3. VALIDATED or REJECTED

Results checked against deployment bar in `SESSION-STATE.md`:

| Check | Pass/Fail | Threshold |
|---|---|---|
| Sharpe >= min_sharpe | ✓ / ✗ | 1.0 (backtest mode) |
| Win rate improvement >= min | ✓ / ✗ | 5pp |
| Sample size >= min | ✓ / ✗ | 30 trades |

**If VALIDATED** → DEPLOYED:
```bash
traderbot profile update econ-agent --field min_edge --value 0.025
```

**If REJECTED** → log reason, archive result, remove from queue.

### 4. DEPLOYED

Profile parameter updated. Log in SESSION-STATE.md Completed Actions. Archive result file in `results/<experiment-id>.md`.

---

## Results Archive

Completed experiments go in `results/<experiment-id>.md`:

```markdown
# EXP-003: econ-agent min_edge 0.03→0.025

## Source Pattern
LEARNINGS.md entry 2026-05-22: "Markets with open_interest > 2000 can
tolerate tighter edges" (Recurrence-Count: 3)

## Hypothesis
Lowering min_edge from 0.03 to 0.025 for economics agent will capture
more valid signals while maintaining win rate above 55%.

## Experiment
- Type: backtest
- Strategy: momentum
- Period: 2026-01-01 → 2026-05-24
- Variant: min_edge=0.025
- Control: min_edge=0.03 (current)

## Results
- Sharpe: 1.34 (control: 1.12)
- Win rate: 58.3% (control: 56.1%)
- Sample: 87 trades (control: 72)

## Evaluation
All checks pass (sharpe 1.34 >= 1.0, win rate +2.2pp, samples 87 >= 30)

## Deployment
- Executed: traderbot profile update econ-agent --field min_edge --value 0.025
- Timestamp: 2026-05-24T18:30:00Z
- Result: Success
```
