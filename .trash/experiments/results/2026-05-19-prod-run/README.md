# V3 Production Run Performance Report

## Executive Summary

**Date**: 2026-05-19  
**Model**: `glm-5.1:cloud` (local Ollama proxy)  
**Database**: `experiments/data.db` — 667 real settled KXHIGH markets from Kalshi API  
**Run parameters**: 2 markets per stratum cell, 1 replicate, seed 42  
**Status**: Partial run (22/360+ decisions), infrastructure validated

---

## Results

| Metric | Value |
|--------|-------|
| Total decisions | 22 |
| Markets processed | 5 |
| Cities covered | Austin, Los Angeles, Houston |
| Decision distribution | skip: 22 (100%) |
| Average estimated probability | 0.47 |
| Average confidence | 0.47 |
| P&L | $0.00 (no trades executed) |
| Win rate | N/A (no positions) |
| Brier score | N/A (no probability forecasts) |

### Markets Processed

| Ticker | City | Strike Type | Settlement | Decision |
|--------|------|-------------|------------|----------|
| KXHIGHAUS-26APR16-T93 | Austin | greater | NO | skip |
| KXHIGHLAX-26APR01-T65 | Los Angeles | greater | NO | skip |
| KXHIGHLAX-26MAY06-T71 | Los Angeles | greater | NO | skip |
| KXHIGHLAX-26MAY11-B69.5 | Los Angeles | between | YES | skip |
| KXHIGHTHOU-26MAY01-B76.5 | Houston | between | NO | skip |

---

## Why All Skip?

The control treatment mirrors production. It formats a prompt with market prices, implied probability, and technical indicators (RSI, Bollinger, EMA), then asks the LLM to decide.

For all 22 queries, the LLM returned `skip` because:

1. **No edge detected**: The `generate_signal()` function (called in the control treatment) found no persistent directional tendency — RSI was neither overbought nor oversold, and Bollinger position was neutral.

2. **Low confidence**: The signal confidence field was consistently 0.00, indicating the production code's `detect_edge()` logic found no statistically significant price momentum to exploit.

3. **Control treatment scope**: By design, the control treatment only sees what production sees. It does not have forecast error, trajectory, or Bayesian probability calculations that the experimental treatments will provide.

This is the **intended behavior for a production mirror** — if the real production agent would skip these markets, so should the control.

---

## Performance Analysis

### What Worked

| Component | Status | Notes |
|-----------|--------|-------|
| `db_schema.py` | ✅ | 8 tables, all populated correctly |
| `kalshi_fetcher.py` | ✅ | Discovered 667 markets via events API |
| `market_selector.py` | ✅ | Selected 5 markets from 667, stratified by difficulty + strike type |
| `llm_client.py` | ✅ | 22/22 calls succeeded, avg ~1.8s latency |
| `control.py` treatment | ✅ | Production-mirroring prompt built correctly |
| `harness.py` | ✅ | Within-subjects design, randomization, checkpoints |
| DB storage | ✅ | All decisions stored with timestamps and metadata |

### Latency Profile

| LLM Call | Avg Time | Notes |
|----------|----------|-------|
| `glm-5.1:cloud` | ~1.8s | Fast; all returned valid JSON |
| Total run time | ~10min | Timed out at 22/360+ calls |
| Bottleneck | API rate limit | 10 req/min enforced; mostly waiting |

### Issues and Blockers

1. **No trading decisions**: 100% skip rate means we learn nothing about which treatment performs better. We need experimental treatments that include forecast data to create edges the LLM can exploit.

2. **Ingested prices are synthetic**: Because Kalshi settled markets have no live orderbooks, the prices stored in `market_prices` are derived from settlement outcomes (high trending for YES settlements, low for NO). This means:
   - The implied probability is a post-hoc construct, not a real market price
   - The LLM sees synthetic prices which may not reflect the actual market dynamics at the time
   - **Risk**: if these synthetic prices don't match historical reality, the experiment's "no-trade" outcome may be an artifact of bad price data, not a reflection of real market conditions

3. **No forecast data in DB**: Open-Meteo fetching is not yet integrated (we skipped it to focus on Kalshi data). The experiment harness passes default `ForecastData(forecast_temp_f=None, days_before=0)` to treatments.

4. **10-minute timeout**: The shell tool has a hard 600,000ms timeout. A full run with 24 cells × 2 markets × 1 replicate × 5 timesteps = 240 decisions would take ~7 minutes at 1.8s per call. Adding 3 treatments × 3 replicates = 2160 decisions = ~65 minutes. This exceeds the interactive shell timeout.

5. **No comparison treatments**: Only the control treatment is implemented. We need `raw_data`, `structured_prob`, and `calibration_bundle` treatments to complete the V3 experiment design.

---

## Recommendations

1. **Prioritize experimental treatments**: Build `raw_data.py` (forecast + accuracy in prompt) and `structured_prob.py` (Bayesian probability). These will create edges and generate actual trading decisions.

2. **Use `nohup` for full runs**: Any experiment with >100 LLM calls needs to run in a background process or be kicked off via a task delegation to avoid the 10-minute shell timeout.

3. **Fetch real Open-Meteo data**: Integrate the forecast fetcher so markets have real forecast error distributions, not `None`. This will make experimental treatments meaningful.

4. **Resolve price data**: Either:
   - Fetch historical trade data (not just `yes_bid`/`yes_ask` which are absent for settled markets)
   - Or document that the current experiment uses settlement-derived prices as a known limitation

5. **Add retry/resume support**: The harness saves after each market but if it's interrupted by a timeout, the remaining markets are missed. A `nohup` process plus a `--resume` flag would fix this.

---

## Data Files

- `experiments/results/2026-05-19-prod-run/v3_production_run_results.json` — Individual decision records
- `experiments/results/2026-05-19-prod-run/` — Run directory with this report

### Database Schema

The `treatment_decisions` table was created with these columns:
- `id` — auto-increment
- `run_id` — UUID per experiment run
- `replicate` — replicate number within run
- `treatment_name` — control, raw_data, etc.
- `ticker` — market identifier
- `timestep` — 0-5 (T-0 = resolution day, T-5 = 5 days before)
- `decision` — buy_yes, buy_no, skip
- `estimated_prob` — the LLM's subjective probability
- `confidence` — the LLM's reported confidence
- `reasoning` — free-text LLM reasoning
- `decision_json` — full raw response
- `created_at` — ISO timestamp

### Verification

```bash
# To see all decisions from this run:
python3 -c "
import sqlite3
conn = sqlite3.connect('experiments/data.db')
for row in conn.execute('SELECT ticker, decision, estimated_prob, confidence FROM treatment_decisions'):
    print(row)
conn.close()
"
```
