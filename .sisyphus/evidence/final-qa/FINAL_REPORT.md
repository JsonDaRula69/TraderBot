# V3 Experiment — Final QA Report

Date: 2026-05-18
Test Suite: experiments/v3/tests/
Total Tests: 209

## Results by Scenario

| # | Scenario | Tests | Status | Notes |
|---|----------|-------|--------|-------|
| 1 | DB Schema (Task 0c) | 6 | PASS | 8 tables, schema verification, idempotent |
| 2 | TreatmentInterface (Task 0d) | 21 | PASS | ABC enforcement, all 7 dataclasses frozen |
| 3 | Ticker Parser (Task 4) | 18 | PASS | All 10 V3 tickers, 5 error cases |
| 4 | Probability (Task 5) | 12 | PASS | prob_less/greater/between, CI, bug fix verified |
| 5 | LLM Client (Task 6) | 14 | PASS | Token bucket, retry, fallback, rate limiting |
| 6 | Market Selector (Task 7) | 14 | PASS | 12 strata, reproducibility, contested/blowout |
| 7 | Control Treatment (Task 8) | 25 | PASS | Production mirror, fallback, excludes weather* |
| 8 | Harness (Task 9) | 7 | PASS | Within-subjects, randomization, checkpoint resume |
| 9 | Scoring (Task 10) | 25 | PASS | P&L, Brier, weighted Brier, delta profit, skip rate |
| 10 | Statistics (Task 11) | 24 | PASS | Paired t-test, Cohen's d, CI, compare_treatments |
| 11 | CLI (Task 12) | 8 | PASS | Argparse, dry-run, verify-data |
| 12 | Integration (Task 13) | 1 | PASS | Full pipeline: DB→select→harness→score→stats |
| **Extra** | Accuracy Calculator | 6 | PASS | Per-city, per-lead-time MAE/bias |
| **Extra** | Kalshi Fetcher | 14 | PASS | Mock API, no future peeking |
| **Extra** | Open-Meteo Fetcher | 14 | PASS | Forecast fetching, caching |

*Control treatment tests require PYTHONPATH=.:src

## Edge Cases

| Case | Result |
|------|--------|
| Empty DB (verify-data) | PASS — reports 0 markets cleanly |
| Invalid ticker ("INVALID-TICKER") | PASS — ParseError |
| LLM timeout (0.001s) | PASS — fallback to "skip" |
| Malformed JSON ("this is not JSON") | PASS — fallback to "skip" |
| Empty decisions (skip_rate) | PASS — returns 0.0 |
| Empty decisions (weighted_brier) | PASS — returns 0.0 |
| Empty score_run | PASS — returns empty dict (bug fixed) |
| Single market stratum | PASS — returns min(n, requested) |

## Bug Found & Fixed

**scoring.py:130 — UnboundLocalError on empty decisions**
- `by_ticker` defined inside for-loop but accessed outside
- Fixed: added guard `if by_treatment:` before accessing
- Empty score_run now returns `{"treatments": {}, "delta_profit": 0.0, "per_market": {}}`
- All 25 scoring tests still pass after fix

## Test Environment

```
Python 3.14.5 | pytest 9.0.3 | scipy + numpy for stats
uv run pytest experiments/v3/tests/ --tb=no -q
→ 209 passed in 5.16s
```
