# Draft: V3 Experiment Test Environment

## Objective
Build a rigorous, treatment-agnostic test environment that accurately simulates real-world Kalshi trading conditions and measures agent performance by delta profit (treatment P&L minus control P&L).

## Folder Structure Refactoring

Current `experiments/experiments/` mixes test infrastructure with treatment content. Proposed reorganization:

```
experiments/
├── docs/                          # Design docs and history (not code)
│   ├── EXPERIMENT_EVOLUTION.md    # V1→V2→V3 history
│   ├── V3.md                      # V3 design spec (current)
│   ├── cold_start_fix.md          # V1 doc (historical)
│   ├── seed_format.md             # DB schema reference (moved from db/)
│   └── README.md                  # Experiment overview
│
├── v2/                            # V2 code (archived, not modified)
│   ├── compile_data.py            # Synthesized data compiler (DEPRECATED)
│   ├── v2_experiment_data.db      # Empty DB (keep as reference)
│   ├── methodologies/              # V2 methodology implementations
│   │   ├── __init__.py
│   │   ├── base.py                 # MethodologyInterface ABC
│   │   ├── bin_cal.py              # Bin calibration (DEPRECATED - uses sigmoid)
│   │   ├── logistic_reg.py         # Logistic regression
│   │   ├── llm_synthesis.py        # LLM-based estimation
│   │   ├── ensemble.py             # Weighted ensemble
│   │   ├── db_utils.py             # DB utilities (REFERENCE ONLY)
│   │   ├── forecast_loader.py      # Forecast loading (REFERENCE ONLY)
│   │   └── ticker_parser.py         # Parser (needs extension for less/greater)
│   ├── simulation/                 # V2 harness (archived)
│   │   ├── harness.py              # V1 methodology harness
│   │   ├── treatment_harness.py    # V2 treatment harness (REWRITE for v3)
│   │   └── scoring.py              # V2 scoring (EXTEND for delta profit)
│   ├── docker/                     # V1 Docker configs (archived)
│   │   ├── docker-compose.yml
│   │   ├── Dockerfile
│   │   └── run.sh
│   └── results/                    # V2 comparison (archived)
│       ├── __init__.py
│       └── compare.py
│
├── v3/                             # NEW: V3 test environment (treatment-agnostic)
│   ├── __init__.py
│   ├── db_schema.py                # SQLite schema for real data
│   ├── harness.py                  # Within-subjects experiment harness
│   ├── scoring.py                  # P&L + weighted Brier + delta profit
│   ├── statistics.py               # Paired t-tests, Cohen's d, CIs
│   ├── market_selector.py          # Stratified sampling (2×3×2 grid)
│   ├── probability.py              # Bayesian CDF computation (scipy)
│   ├── ticker_parser.py            # All strike types (less/greater/between)
│   ├── treatment_interface.py      # ABC for treatment plug-ins
│   ├── cli.py                      # CLI entry point
│   ├── data_sources/               # Real data pipeline
│   │   ├── __init__.py
│   │   ├── kalshi_fetcher.py        # Kalshi API data fetcher
│   │   ├── openmeto_fetcher.py      # Open-Meteo Previous Runs fetcher
│   │   └── accuracy_calculator.py   # Per-city per-lead-time accuracy
│   └── tests/                      # V3 test suite
│       ├── test_db_schema.py
│       ├── test_kalshi_fetcher.py
│       ├── test_openmeto_fetcher.py
│       ├── test_accuracy_calculator.py
│       ├── test_ticker_parser_v3.py
│       ├── test_treatment_interface.py
│       ├── test_probability.py
│       ├── test_market_selector.py
│       ├── test_harness.py
│       ├── test_scoring.py
│       ├── test_statistics.py
│       ├── test_cli.py
│       └── test_integration.py
│
└── treatments/                      # Treatment implementations (separate from infrastructure)
    ├── __init__.py
    └── (treatment plug-ins go here when designed)
```

**Key design principle**: `v3/` is treatment-agnostic test infrastructure. `treatments/` is where specific treatments (control, raw_data, etc.) are implemented as plug-ins. They are NOT mixed.

## Research Findings

### What V3 Design Proposes (from V3.md)
- 4 treatments: control (mirrors production), raw_data (+forecast+accuracy), structured_prob (+Bayesian prob), calibration_bundle (+trajectory+settlement rates)
- Fixes V2 band delta bug: uses `scipy.stats.norm.cdf` integration instead of broken `center - |forecast - center|`
- Adds forecast accuracy data (per-city, per-lead-time MAE/bias) computed from Kalshi settlement results
- 10 markets (7 contested, 3 blowouts)
- 5 timesteps per market
- Metrics: Brier score, P&L, win rate, with emphasis on contested markets

### What V2 Code Actually Implements

#### treatment_harness.py (647 lines) — CRITICAL GAPS vs V3
1. **Control treatment does NOT mirror production TraderBot**: Control only shows "YES/NO price" — no technical indicators (RSI, Bollinger, EMA crossover, signal direction, signal confidence), no implied probability from mid-price, no trade volume, no open interest. V3 explicitly requires `traderbot analyze` + `traderbot signals` output.
2. **Band delta uses the BROKEN formula**: `_compute_delta()` for `between` markets returns `forecast - threshold - 0.5` (signed distance from band center). V3 requires signed distance to nearest BOUNDARY, not band center.
3. **structured_prob uses sigmoid(delta)**: `_compute_bincal()` falls back to `sigmoid(delta)` with hardcoded confidence and CI calculations. V3 requires proper Bayesian probability using `norm.cdf` with city-specific error distributions. The current code has no city-specific error data.
4. **calibration_bundle uses BinCal data**: Falls back to synthesized statistics when `calibration_bins` table is empty (it is empty — DB is 0 bytes). No trajectory data, no historical settlement rates.
5. **Database is EMPTY**: `v2_experiment_data.db` is 0 bytes. The `compile_data.py` synthesizes forecasts from actual temps + Gaussian noise, which V3 explicitly identifies as a problem.
6. **API key hardcoded**: Line 313 has `_OLLAMA_API_KEY = "a805f58ea5514f149e59bf61c3d4945a.ZASFClNBFdSaMsi3XNgYoNAI"` — security issue.
7. **No forecast accuracy data**: V3 requires per-city, per-lead-time MAE/bias computed from Kalshi settlements. The current DB has no such data, and `compile_data.py` uses synthetic bias values that aren't grounded in real settlement results.
8. **No market type support for `less` and `greater`**: `ticker_parser.py` only parses `between` (band) markets. The V3 market list includes `less`, `greater`, and `between` types (e.g., KXHIGHNY-26MAY08-T64 is `less`, KXHIGHTSEA-26MAY07-T66 is `less`).

#### compile_data.py — SYNTHESIZED DATA (the root problem)
- Forecasts are synthesized: `actual_temp + gauss(bias * (1 - timestep/10), std)` 
- Market prices are synthesized from forecast-implied probabilities + noise
- City biases are generic values (Austin +0.5, NYC -0.2, etc.) — NOT computed from Kalshi settlements
- V3 requires real Open-Meteo Previous Runs API data + real Kalshi settlement results

#### Scoring — P&L model is simplified
- P&L calculated as: `position_size * (1 - yes_price)` for correct YES, `-position_size * yes_price` for incorrect YES
- No position sizing logic — `position_size_cents` comes from the agent's response but there's no risk framework enforcing limits
- No contested-vs-blowout market weighting (V3 requires emphasis on contested markets)

### What's Missing Entirely (Needed for V3)

1. **Real data pipeline**: Open-Meteo Previous Runs API integration to fetch historical forecasts at each lead time
2. **Real forecast accuracy computation**: Per-city, per-lead-time MAE and bias from Kalshi settlement vs Open-Meteo forecasts
3. **Production TraderBot control prompt**: Market analysis with RSI, Bollinger bands, EMA crossover, signal direction, confidence, implied probability
4. **Probability computation module**: `prob_less()`, `prob_greater()`, `prob_between()` using `scipy.stats.norm.cdf` with city-specific error distributions
5. **10-market dataset**: V3 specifies 10 specific markets — current DB has none (0 bytes)
6. **Contested market weighting**: V3 scoring emphasizes contested markets over blowouts
7. **`less` and `greater` market type support**: Parser, prompts, delta computation all need strike type handling
8. **Historical settlement rate computation**: "In N prior markets with delta within ±X°F of D, YES settled P%" — requires querying past settlement results

### Architecture Alignment Issues

1. **Single-table DB approach**: V2 uses a flat SQLite DB with disjoint tables. V3 needs relational data connecting markets → forecasts at multiple lead times → settlement results → accuracy stats.
2. **No Kalshi API integration for real prices**: V2 synthesizes prices. V3 requires real trade history (last trade before each timestep window end, no future peeking).
3. **LLM agent call via Ollama cloud**: Current harness calls `ollama.com/api/generate` with an API key. This works but needs error handling for rate limits and retries.
4. **No warm-up/context windowing**: The LLM gets one-shot prompts per timestep with no conversation history across timesteps — it only gets "your prior decisions" as text. This may not mirror how a real agent processes information.

## Clarifying Questions — ANSWERED

1. **Open-Meteo Previous Runs API**: Free, no credentials needed. Proceed as V3 specifies.
2. **Kalshi historical data**: We have API access via TraderBot's existing Kalshi adapter. Need to verify 10 specific markets still queryable.
3. **LLM agent**: glm-5.1:cloud only. Single model, controls for model effects.
4. **Agent pattern**: Prompt-and-respond (one-shot per timestep, prior decisions as text). Isolates the effect of what TraderBot provides.
5. **Scoring**: Weighted Brier + dual reporting.
6. **DB status**: v2_experiment_data.db is 0 bytes (empty). Need full data pipeline.
7. **Market selection**: User wants rigorous statistical design — not ad-hoc.

## Oracle Consultation — Experimental Design Recommendations

### Critical Design Changes from V3

1. **Stratified Sampling** (replaces ad-hoc 10 markets):
   - 2×3×2 factor grid: difficulty × strike_type × lead_time
   - 2 markets per cell → 24 markets minimum (36 preferred for power)
   - Ensures every treatment level tested across full diversity of Kalshi markets

2. **Within-Subjects Design** (replaces between-subjects):
   - Each market evaluated under ALL 4 treatment levels
   - Eliminates between-market variance from error term
   - 4 independent sessions, different random order per treatment
   - Agent never sees same market twice in same session

3. **Power Analysis** (minimum 20+ markets):
   - Detect medium effect size (Cohen's d ≈ 0.5)
   - α = 0.05, power = 0.80
   - 3+ replicates per market per treatment for LLM stochasticity

4. **Confounding Controls**:
   - Randomize market order per treatment
   - Multiple replicates per market for LLM stochasticity
   - Report metrics stratified by difficulty, strike_type, lead_time

5. **Scoring**: Weighted Brier (2× contested, 0.5× blowouts) + separate metrics per group
   - Also report: effect size (Cohen's d), confidence intervals, paired t-tests between treatments

## REVISED SCOPE (after user clarification)

**Core Mission**: Build a rigorous test environment that accurately simulates real-world Kalshi trading conditions. NOT designing treatments.

- INCLUDE:
  - Real data pipeline (Kalshi API + Open-Meteo Previous Runs)
  - Treatment-agnostic harness that accepts any treatment as a plug-in
  - Rigorous market selection (stratified sampling)
  - Within-subjects design infrastructure
  - P&L calculation with position sizing
  - Statistical analysis (paired comparisons, effect sizes, CIs)
  - Replication support (multiple LLM runs per market per treatment)
  - No-future-peeking price extraction
  - All three strike types (less, greater, between)

- EXCLUDE:
  - Treatment content design (what goes in control, raw_data, structured_prob, calibration_bundle)
  - Changes to production TraderBot code
  - Deployment infrastructure
  - The specific prompts or data injection for any specific treatment