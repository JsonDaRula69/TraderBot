# Test Environment Design Failures and Lessons Learned

## Executive Summary

This document catalogs every way our prior test environment designs failed to accurately simulate real-world Kalshi trading conditions. It focuses exclusively on the **testing infrastructure and methodology** — not treatment content design, not production code, not deployment.

The fundamental failure mode across all iterations (V1, V2): **the test environment was not treatment-agnostic.** Instead, the infrastructure was hardcoded around specific treatments, specific data pipelines, and specific scoring logic — making it impossible to test new treatment designs without rewriting the system.

---

## V1: The Methodology Experiment (Referred to as "V1")

### What It Was

V1 compared four methodologies (bin_cal, logistic_reg, llm_synthesis, ensemble) in a simulation harness. Each methodology was a Python class inheriting from `MethodologyInterface` that computed `estimated_prob` from market data.

### How It Failed

1. **Data source was synthesized in `compile_data.py`** — all forecasts were generated from actual temperatures plus Gaussian noise (`actual_temp + gauss(bias, std)`), not fetched from real historical forecast models. The noise parameters were hand-tuned (`CITY_BIAS_F`, `FORECAST_ERROR_STD`) with no basis in real-world Kalshi settlement data.

2. **Market prices were synthesized** — compute_price() in compile_data.py (line ~153+) used `sigmoid(delta) + random.gauss(0, 0.05)` instead of real Kalshi trade histories. The prices never reflected actual market dynamics (bid-ask spread, liquidity, trader behavior).

3. **Methodologies were hardcoded in harness.py** — `METHODOLOGY_REGISTRY` (lines 26-31) was a static dict mapping names to module paths. Adding a new methodology required editing `simulation/harness.py`, making the harness methodology-dependent rather than plug-in based.

4. **No treatment-agnostic interface** — the harness ran one methodology at a time with `python -m simulation.harness --methodology bin_cal`. There was no support for testing the same market under multiple treatments (within-subjects design).

5. **Between-subjects design only** — each market ran under exactly one methodology, which means methodology differences were confounded with market differences. You couldn't tell if Ensemble outperformed BinCal because Ensemble was better or because it got easier markets.

6. **Scoring was methodology-oriented, not treatment-oriented** — `scoring.py` compared methodologies across markets, but there was no concept of a "control" baseline, no delta profit, no paired comparisons.

7. **V1 was abandoned** when we realized the real problem wasn't "which methodology is better" but "what information should the agent receive." The V1 approach tried to solve a problem (cold start) by comparing existing tools, when the actual issue was that the agent had no principled way to convert forecasts into probabilities.

### Key Lesson
**Don't compare methodologies. Compare information environments.** The system design should provide the agent with different data, not different processing logic.

---

## V2: The Treatment Experiment (Current Implementation)

### What It Was

V2 redesigned the experiment to test "what TraderBot should provide to an agent" rather than "which methodology is better." It has four treatments (control, raw_data, structured_prob, calibration_bundle) with the same LLM agent seeing different context levels.

### How It Failed

#### 1. The Data Is Entirely Synthetic

**`compile_data.py`** (the entire file, ~500+ lines):
- Forecasts: `random.gauss(bias * (1 - timestep / 10), std)` — noise from actual temps, not real model forecasts
- Prices: `sigmoid(delta) + random.gauss(0, 0.05)` — synthetic, not from Kalshi trade history
- Accuracy stats: Hardcoded `CITY_BIAS_F` and `FORECAST_ERROR_STD` — no relation to real settlement results

**Result**: The test environment simulates a fictional market that doesn't exist. An agent trained on synthetic forecasts and synthetic prices with synthetic noise patterns will not generalize to real-world Kalshi conditions.

#### 2. The Control Treatment Is Not Production-Control

**`simulation/treatment_harness.py`** CONTROL_PROMPT (lines 102-114):
```
Current market prices: YES={yes_price}, NO={no_price}
Based ONLY on the market price, decide: buy_yes | buy_no | skip
```

This is NOT what TraderBot's production pipeline provides to an agent. The production pipeline (`traderbot analyze` + `traderbot signals`) outputs:
- RSI, Bollinger bands, EMA crossover
- Signal direction and confidence
- Implied probability from mid-price
- Trade volume and open interest

The control treatment in V2 is a **degraded version of production**, not a mirror of it.

#### 3. The Probability Computation Is Wrong

**`simulation/treatment_harness.py`** `_compute_bincal()` (around lines 247-255):
- Uses `sigmoid(delta)` for `structured_prob`
- This is a deterministic monotonic transform: `sigmoid(forecast - threshold)`
- **The LLM agent can compute this in its head** — it contains zero incremental information beyond raw_data

**Correct approach** (what V3.md calls for): Use `scipy.stats.norm.cdf` with city-specific MAE and bias, computing the integral of the error distribution over the YES region. This is computationally different and provides information the agent cannot derive from raw_data alone.

#### 4. The Band Market Delta Is Fundamentally Broken

**`simulation/treatment_harness.py`** `_compute_delta()` for `between` markets:
```python
if strike_type == "between":
    return forecast_temp - threshold - 0.5  # Distance from band center
```

This says: a forecast of 88.9°F for band [90,91) gives delta = 88.9 - 90 - 0.5 = -1.6°F. But the intuitive quantity should be "how far is the forecast from the nearest boundary of the band?"

The `calibration_bundle` prompt then says: "Forecast is -1.6°F below the center of the [90,91) band" — this is semantically meaningless to an agent.

**Correct approach**: Signed distance to nearest boundary: if forecast < floor, distance = forecast - floor (negative, below band); if forecast > ceiling, distance = forecast - ceiling (positive, above band). Only then can the agent reason "the forecast is 1.1°F below the band" and integrate that with uncertainty.

#### 5. No Treatment-Agility

**`simulation/treatment_harness.py`** (lines 52, 100-230):
```python
TREATMENTS = ("control", "raw_data", "structured_prob", "calibration_bundle")
```

These four treatments are hardcoded into the harness. To test a fifth treatment, you must:
- Modify `treatment_harness.py` to add a new prompt template
- Modify the treatment dispatch logic
- Modify scoring to handle the new treatment name

The harness is **treatment-aware** when it should be **treatment-agnostic.**

#### 6. No Within-Subjects Design

The V2 harness runs one treatment per invocation (`--treatment control`). To test all four treatments on the same market, you must run the harness four times, each with a different market selection. Markets are never exposed to multiple treatments, so between-market variance confounds treatment effects.

**Correct approach**: Each market is evaluated under ALL treatment conditions in a randomized order, with the same agent making decisions each time.

#### 7. No Replication for LLM Stochasticity

The V2 harness runs each market once per treatment. LLM agents are stochastic — a `temperature > 0` means the same prompt can yield different responses. With no replicates, a treatment that "won" may have just gotten lucky on the LLM's RNG.

#### 8. The DB Is Empty (0 Bytes)

**`v2_experiment_data.db`** — The file exists but has 0 bytes of content. The compile_data.py script has never been successfully run, or the data was deleted. Regardless, there is no existing database of real market data to work with.

#### 9. Future Peeking Is Possible

**`simulation/treatment_harness.py`** price extraction (around lines 200-240):
The prompt receives market prices as `YES={yes_price}, NO={no_price}` but there's no evidence the extraction logic enforces "only trades before the timestep window closes." If a timestep corresponds to a day range (e.g., T-0 = "day of resolution"), and there are trades AFTER the timestep cutoff that get included, the agent would see future price movements.

#### 10. Missing Data Types in Ticker Parser

**`experiments/methodologies/ticker_parser.py`** (lines 1-157):
The existing parser only handles the `KXHIGHAUS-26APR01-B90.5` format (between/band markets). But V3.md's market list includes:
- `KXHIGHTSEA-26MAY07-T66` — less than 66°F
- `KXHIGHTSEA-26MAY11-T75` — greater than 75°F

The parser needs to return `strike_type=less` for some `-T*` tickers and `strike_type=greater` for others. Currently it likely fails or misidentifies these.

#### 11. The Probability Computation for Band Markets Uses a Fixed Sigma

`compute_band_probability()` in compile_data.py (lines 153-174):
```python
forecast_std = 2.0  # Fixed for simplicity
prob = 0.5 * (erf(z_upper) - erf(z_lower))
```

It uses `forecast_std = 2.0` regardless of city, lead time, or actual historical accuracy. V3.md correctly requires city-specific MAE at each lead time. Austin at T-0 has MAE 1.6°F, so using 2.0°F systematically overestimates uncertainty for Austin markets.

#### 12. The V3 Design Document Contains a Copy-Paste Bug

**V3.md lines 198-203**:
```python
def prob_greater(forecast, threshold, city_bias, city_mae):
    mu_adj = forecast - city_bias
    sigma = city_mae
    return norm.cdf(floor + 1, loc=mu_adj, scale=sigma) - norm.cdf(floor, loc=mu_adj, scale=sigma)
```

This is `prob_between()` logic copy-pasted into `prob_greater()`. The correct code should be:
```python
def prob_greater(forecast, threshold, city_bias, city_mae):
    mu_adj = forecast - city_bias
    sigma = city_mae
    return 1 - norm.cdf(threshold, loc=mu_adj, scale=sigma)
```

This bug in the design spec would propagate into any code that uses the spec as reference.

#### 13. Architecture Boundary Violations

The `simulation/` directory contains both **test infrastructure** (harness.py, scoring.py) and **treatment content** (treatment_harness.py). The methodologies/ directory contains both data utilities (db_utils.py, forecast_loader.py, ticker_parser.py) and methodology implementations (bin_cal.py, logistic_reg.py). There is no clean separation between "how we test" and "what we test."

---

## Cross-Version Failures (V1 and V2 Both Suffered)

### A. Monolithic, Not Modular

Both versions use monolithic files that mix concerns:
- `compile_data.py` — fetches data, synthesizes forecasts, computes prices, creates DB
- `scoring.py` — loads JSON, queries DB, computes metrics, generates report
- `treatment_harness.py` — loads DB, formats prompts, calls LLM, stores results, all in one file

There is no clear separation between:
- Data pipeline (fetching real vs synthesizing)
- Experiment harness (running treatments)
- Scoring engine (computing metrics)
- Statistical analysis (t-tests, CIs, effect sizes)

### B. No Treatment Interface (ABC)

Neither version defines `TreatmentInterface` or similar abstraction. A treatment is either:
- A string name in a hardcoded tuple (V2)
- A class in a hardcoded registry dict (V1)

Adding a new treatment requires modifying the harness source code. This is the opposite of a treatment-agnostic design where a treatment is a drop-in module.

### C. No Delta Profit Metric

Both versions compute P&L absolutely (how much money did the methodology make?), not relatively (how much more did treatment A make than control?). The key metric for comparing treatments is **delta profit**: treatment P&L minus control P&L on the same market, which isolates the treatment effect from market difficulty.

### D. Scoring Is Too Simple

Both `simulation/scoring.py` and `simulation/treatment_harness.py` compute:
- Brier score (mean squared error)
- Win rate (direction accuracy)
- P&L (simple profit/loss)

Neither computes:
- Paired t-tests between treatments on the same markets
- Effect sizes (Cohen's d)
- Confidence intervals
- Stratified analysis by market type (less vs greater vs between)
- Weighted metrics (contested markets weighted more than blowouts)

### E. No Statistical Power Analysis

Neither version has any concept of "how many markets do I need to detect a meaningful effect?" The V2 design lists exactly 10 markets with no justification. The V1 design uses 25 markets with no power analysis. This means experiments may be underpowered (can't detect real effects) or overpowered (wasting LLM calls).

### F. API Key Hardcoded

**`simulation/treatment_harness.py`** line ~313:
```python
_OLLAMA_API_KEY = "a805f58ea5514f149e59bf61c3d4945a.ZASFClNBFdSaMsi3XNgYoNAI"
```

This is a live API key for the Ollama cloud service. It should be in an environment variable, never in source control.

---

## What We Learned About Test Environment Design

### Principle 1: Treatment-Agnostic Infrastructure

The test environment should be a **machine** that accepts any treatment as a plug-in module. Treatment content (prompts, data, probability formulas) lives in a separate namespace. The infrastructure handles:
- Market selection and randomization
- Data fetching and storage
- Running treatments in randomized order
- Extracting decisions from LLM responses
- Computing P&L, Brier, delta profit
- Statistical analysis

### Principle 2: Real Data Is Non-Negotiable

Synthesized data (forecasts from `random.gauss`, prices from `sigmoid(delta)`) is only useful for unit tests and dry-runs. For actual experiments:
- Forecasts must come from real historical model runs (Open-Meteo Previous Runs API)
- Prices must come from real Kalshi trade history (before timestep cutoff)
- Accuracy metrics must be computed from real settlement results

### Principle 3: Within-Subjects Design Is Required

For any comparison between treatments, each market must be exposed to ALL treatments. This eliminates between-market variance and makes paired comparisons valid. V1 and V2 between-subjects designs were statistically invalid for this purpose.

### Principle 4: Replication Is Not Optional

LLM responses are stochastic. A single run per market is noisy. Minimum 3 replicates per treatment per market is needed to average out LLM variance.

### Principle 5: The Control Must Mirror Production

If the experiment asks "does adding X to treatment improve decisions?", the control must receive exactly what production provides now. V2's control was a degraded version, not a production mirror.

### Principle 6: Probability Computations Must Be Correct

`sigmoid(delta)` is wrong. `center - |forecast - center|` is wrong. Both contain zero incremental information and mislead the agent. The correct computation uses `scipy.stats.norm.cdf` with city-specific error distributions and integrates over the YES region. This is computationally meaningful and the agent cannot derive it from raw_data alone.

### Principle 7: All Three Strike Types Must Work

Less, greater, and between are fundamentally different probability computations:
- `less`: P(temp < T) = CDF(threshold)
- `greater`: P(temp > T) = 1 - CDF(threshold)
- `between`: P(temp in [floor, floor+1)) = CDF(floor+1) - CDF(floor)

Each requires its own probability formula. The parser must distinguish all three.

---

## V3 Requirements (Based on Lessons Learned)

The V3 test environment must:

1. **Be treatment-agnostic** — plug-in architecture, no hardcoded treatments
2. **Use real data only** — Open-Meteo Previous Runs + Kalshi trade history + settlement results
3. **Implement within-subjects design** — each market under all treatments
4. **Support replication** — configurable replicate count (min 3)
5. **Mirror production control** — full TraderBot analyze + signals output
6. **Use correct probability computations** — norm.cdf with city-specific error distributions
7. **Handle all strike types** — less, greater, between
8. **Measure delta profit** — treatment P&L minus control P&L
9. **Include statistical rigor** — paired t-tests, effect sizes, CIs
10. **Support stratified sampling** — 2×3×2 grid for representative market selection
11. **No future peeking** — prices extracted only from trades before timestep window
12. **No hardcoded credentials** — API keys via environment variables
13. **No synthesized data** — everything from real APIs
14. **Be deployable** — CLI entry point, Docker support, clear README

---

## Files That Need Attention

### Must Be Rewritten (Not Salvageable)
- `experiments/compile_data.py` — Entirely synthetic data generation
- `experiments/simulation/treatment_harness.py` — Hardcoded treatments, wrong probability, wrong control
- `experiments/v2_experiment_data.db` — Empty (0 bytes), non-functional

### Must Be Extended (Partially Usable)
- `experiments/methodologies/ticker_parser.py` — Add less/greater strike type support
- `experiments/methodologies/db_utils.py` — Connection pooling, but schema is flat and incomplete
- `experiments/simulation/scoring.py` — Extend with delta profit, weighted Brier, paired stats
- `experiments/db/seed_format.md` — Schema reference, but needs expansion

### Already Correct (Keep As-Is)
- `experiments/V3.md` — Design document (despite the prob_greater copy-paste bug)
- `experiments/EXPERIMENT_EVOLUTION.md` — History document
- `experiments/cold_start_fix.md` — Problem statement (V1 proposal, now archival)
- `experiments/docker/docker-compose.yml` — Container orchestration (needs new config for v3)

---

## Summary of Core Failures

| Failure | V1 | V2 | Impact |
|---------|----|----|--------|
| Synthetic forecasts | ✅ | ✅ | Agent trained on synthesized weather — doesn't generalize |
| Synthetic prices | ✅ | ✅ | Market dynamics are fictional — can't test real edge |
| Monolithic harness | ✅ | ✅ | Can't add treatments without rewriting core code |
| Between-subjects design | ✅ | ✅ | Can't isolate treatment effects from market difficulty |
| No treatment ABC | ✅ | ✅ | No plug-in architecture |
| No replication | ✅ | ✅ | LLM stochasticity contaminates results |
| No delta profit | ✅ | ✅ | Can't measure treatment value-added |
| No statistical analysis | ✅ | ✅ | Can't compute significance, CIs, effect sizes |
| Wrong probability formula | ❌ | ✅ | sigmoid(delta) = zero incremental info |
| Wrong band delta | ❌ | ✅ | `center - |forecast - center|` is semantically meaningless |
| Empty database | ❌ | ✅ | No data to run experiments |
| Control != production | ❌ | ✅ | Control treatment is degraded, not a true baseline |
| Hardcoded API key | ❌ | ✅ | Security risk (treatment_harness.py line ~313) |
| No strike type diversity | ❌ | ✅ | Only between markets supported |
| Future peeking possible | ❌ | ✅ | No evidence price extraction is time-bounded |
| V3 prob_greater bug | ❌ | ❌ | Copy-paste in design doc — would propagate to implementation |

**Key Takeaway**: Every failure either renders tests non-generalizable (synthetic data), makes comparisons invalid (between-subjects), or makes the system unmaintainable (monolithic, no plug-in). The V3 system must address all of these from the ground up.
