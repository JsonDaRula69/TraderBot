# Test Lab Results

_Archived results of completed experiments. One file per experiment: `<experiment-id>.md`._

## Archive

| ID | Status | Date | Summary |
|---|---|---|---|
| _(none)_ | — | — | — |

## Result File Format

Each result file documents the full cycle from pattern discovery to deployment decision:

```markdown
# EXP-003: Short description

## Source
LEARNINGS.md entry <date>: "<pattern>" (Recurrence-Count: N)

## Hypothesis
What we expected to happen and why.

## Experiment
- Type: backtest / backtest+paper
- Target: <agent> / <category>
- Parameters: <strategy variant, date range, risk settings>
- Control: <current config>

## Results
- Sharpe: X.XX (control: X.XX)
- Win rate: X.X% (control: X.X%)
- Samples: N (control: N)
- Edge improvement: X.XX

## Evaluation
Checks against deployment bar (SESSION-STATE.md):
- Sharpe >= X.XX: ✓ / ✗
- Win rate improvement >= Xpp: ✓ / ✗
- Samples >= N: ✓ / ✗

## Decision
DEPLOYED / REJECTED (<reason>)

## Deployment
- Command: traderbot profile update <profile> --field <key> --value <val>
- Timestamp: YYYY-MM-DDTHH:MM:SSZ
- Result: Success / Failure
```
