
## Experiment Infrastructure QA (2026-05-26)

### Bug Found: score_run raises OperationalError for nonexistent DB file
- File: `src/traderbot/experiment/results.py`, line 205 and 248
- `score_run(db_path, run_id)` calls `sqlite3.connect(db_path)` twice but only the second call (line 248) is wrapped in a try/except for OperationalError
- The first connection (line 205) will raise `sqlite3.OperationalError: unable to open database file` for nonexistent paths
- **Expected**: return `[]` like it does for empty results
- **Actual**: raises unhandled exception
- Severity: Low (CLI `experiment results` command catches this via its own error handling, but programmatic callers will crash)

### Issue Found: NaN in score_run when all paired P&L deltas are zero
- When both treatments make identical decisions for all markets, `_paired_ttest` returns (0.0, 1.0) but the upstream P&L computation produces identical values
- The `t_stat` and `p_value` become NaN in the output when `_cohen_d` returns 0.0 and the delta is 0.0
- The `ExperimentResults.to_json()` serializes NaN, which is not valid JSON (will fail strict JSON parsers)
- `improvement` correctly returns False in this case
- Severity: Low (edge case - identical decisions are unlikely in production; NaN not valid JSON)

### Verified Working: 24/24 unit tests pass
