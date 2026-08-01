# Future: Methodology Evaluation Framework

**Status**: Deferred — documented for future implementation
**Date**: 2026-05-18
**Context**: Cold-start fix discussion with user

## Concept

An ongoing evaluation framework where multiple prediction methodologies compete on a live scoreboard. Results feed back continuously, and the system self-selects the winner per category.

## Architecture

### Methodologies
Each methodology is a standalone module in `src/traderbot/methodologies/`:
- `bin_cal.py` — Forecast delta → accuracy bin → Beta posterior → point estimate (cold_start_fix.md Phase 1 approach)
- `logistic_reg.py` — Forecast features → learned logistic probability
- `llm_synthesis.py` — LLM reasoning over structured data → probability
- `ensemble.py` — Weighted combination of other methodologies

### Scoreboard (ChromaDB `methodology_scores`)
Per-prediction records: methodology, ticker, category, predicted_prob, actual_outcome, brier_score, timestamp

### Evaluation Flow
1. Settlement reconciliation (daily via heartbeat/cron): `traderbot calibrate --update`
2. Fetch newly settled markets from Kalshi
3. Re-run each methodology against pre-settlement data
4. Compare each output vs actual outcome
5. Record to scoreboard

### Methodology Rotation
- Current best methodology per category = lowest rolling Brier score with N≥30 samples
- Below 30 samples: runs in shadow mode (records but doesn't influence)
- Drift detection: 2σ degradation triggers human review + rotation to runner-up
- New methodologies enter in shadow mode until proven

### Key Metrics
- Brier score (primary)
- Calibration curve deviation
- Edge realization rate (what % of predicted edge actually materialized)
- Sample size per bin

### CLI Commands
- `traderbot prob-estimate --ticker X --all-methods` — returns all methodology outputs
- `traderbot calibrate --update` — daily reconciliation
- `traderbot methodology-scores --category weather` — view scoreboard

### Docker Test Harness
- One-time experiment: run each methodology against historical dataset
- Each in isolated Docker container
- Results written to same scoreboard format
- Comparison dashboard for winner selection

## Dependencies
- Phase 4 (decision storage) must exist first
- Phase 1 (calibration data infrastructure) must exist first
- HistoryService must support batch settlement queries
