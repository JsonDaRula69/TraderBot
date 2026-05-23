# Experiment Evolution History

Factual timeline of the cold-start experiment from V1 through V3.

---

## Phase 0: Discovery of the Cold-Start Problem

**Date**: 2026-05-18 (sessions starting ~10:39 UTC)

The weather2 agent (Kestrel) ran **64 decision evaluations across 5 days** with **zero trades executed**. Every audit entry showed `edge_estimate: 0.0` with confidence 0.70–0.95. The agent had correct weather theses (NYC >84°F settled YES, Chicago <82°F settled YES) but could not convert "forecast delta" into `estimated_prob` because `generate_signal()` defaults to market-implied probability, guaranteeing ~0% edge.

This paradox — can't trade because it hasn't learned, can't learn because it hasn't traded — was identified as the **cold-start problem** for prediction market agents.

Three exploration sessions investigated:
- `ses_1c554a913ffei3gZbTxx2rUsUU` — Research cold start solutions for prediction markets (librarian)
- `ses_1c554cfbdffe1YHXDUt7WMecm7` — Explore what agent sees at decision time (explore)
- `ses_1c5553697ffeA7Jj6ng6r9kHQu` — Explore agent decision pipeline (explore)

---

## Phase 1: Cold-Start Fix Document (V1 Approach)

**Date**: 2026-05-17 23:38 (commit `7db2a40`)

**Document**: `cold_start_fix.md` (340 lines)

**Approach**: Hardcode a weather probability model into TraderBot's `generate_signal()`. Four phases:

1. **Phase 1**: `weather_prob.py` — compute estimated_prob from forecast delta binned by historical accuracy, wire into `generate_signal()`
2. **Phase 2**: `WeatherStrategy` — backtest against settled Kalshi markets
3. **Phase 3**: `BayesianAdapter` update cycle — learn from trade outcomes via heartbeat
4. **Phase 4**: Decision storage pipeline — write audit decisions to ChromaDB

**Problems identified with V1 approach**:
- Couples `weather_prob.py` into the TraderBot toolkit — the toolkit decides strategy, not the agent
- Category-specific code inside the toolkit violates the architecture constraint ("the toolkit never decides strategy")
- Only solves weather — politics, sports, economics need separate models
- `BayesianAdapter` exists but has 0 observations (circular: can't learn without trading)

**Rejection**: The methodology experiment approach (V2) was chosen instead — compare multiple estimation methods rather than hardcode one.

---

## Phase 2: Methodology Experiment (V2)

### 2.1 Planning

**Date**: 2026-05-18 08:07 (session `ses_1c5df9fa2ffeDO8RFISr1LiqIE`)

**Document**: `.sisyphus/plans/methodology-experiment.md` (960 lines)

**Approach**: Compare 4 **methodologies** (bin_cal, logistic_reg, llm_synthesis, ensemble) against 25 historical Kalshi weather markets with 10 forecast timesteps each. Each methodology gets its own Docker container with an OpenClaw agent. The experiment evaluates methodology accuracy, not agent decision quality.

**Key design decisions**:
- `MethodologyInterface` ABC with `estimate()` method — each methodology implements only estimation logic
- Shared infrastructure: `ticker_parser.py`, `forecast_loader.py`, `db_utils.py`
- Simulation harness runs 25 markets × 10 timesteps per methodology
- Scoring pipeline: Brier score, calibration curve, edge realization, P&L, timing analysis, confidence-weighted accuracy
- No modifications to `src/traderbot/` — experiment is self-contained in `experiments/`
- LLM synthesis operates without artificial constraints (no token budget, no rate limit)

### 2.2 Implementation (Wave 1-4)

All committed on 2026-05-18, 02:26–04:12 UTC, on the `experiments` branch.

| Commit | Time | Files | What |
|--------|------|-------|------|
| `21a5e0b` | 02:26 | `compile_data.py` (344 lines) | V1 data compilation script (synthesized forecasts from actual temps + Gaussian noise) |
| `9eb02f0` | 02:57 | `compile_data.py` (350 lines, 267 added) | Synthesized forecast variation + market prices |
| `72a9403` | 02:38 | `DO_NOT_MERGE` marker | One-time experiment branch warning |
| `3478747` | 03:32 | 7 files, +1488 lines | **Wave 1**: seed_format.md, MethodologyInterface, ticker_parser, forecast_loader, db_utils |
| `ce28f6d` | 03:46 | 3 files, +685 lines | **Wave 2**: simulation harness (`harness.py`) + scoring pipeline (`scoring.py`) |
| `735acee` | 04:00 | 9 files, +1222 lines | **Wave 3-4**: 4 methodologies (bin_cal, logistic_reg, llm_synthesis, ensemble), Docker configs, comparison report |
| `e62b4d8` | 04:05 | 4 files, 11 lines changed | Fix 4 HIGH severity issues from code review |
| `391e59d` | 04:12 | 3 files, 25 lines changed | Fix 3 runtime bugs from QA testing |

### 2.3 V2 Data Issues

**Original V2 experiment data was synthesized** — forecasts were actual temperatures + Gaussian noise, market prices were forecast-implied probabilities + noise. This produced artificially high forecast accuracy, making results unreliable for drawing conclusions about real agent performance.

### 2.4 V2 Redesign (Treatment-Based)

**Date**: 2026-05-18 10:03 (commit `eae4728`)

The experiment was redesigned from methodology comparison to **treatment comparison** — testing what TraderBot should provide to an agent, not which methodology is most accurate.

**Document**: `.sisyphus/plans/fix-experiment-v2.md`

Key changes:
- Replaced 4 methodologies with 4 treatment levels (control, raw_data, structured_prob, calibration_bundle)
- Same LLM agent (glm-5.1:cloud) across all treatments — only context varies
- `treatment_harness.py` (647 lines) replaces methodology harness
- Real Open-Meteo Previous Runs archived forecasts + real Kalshi market prices
- Sequential treatment runs (not parallel) to avoid Ollama contention
- 10 markets (7 contested + 3 blowouts) instead of 25
- 5 timesteps per market (within ~40h trading window, not T-4 through T-0 days-before)

### 2.5 V2 Runtime Bugs

**Sessions**: Treatment runs on macpro-linux, PIDs 139848, 139851, 139854, 139857.

**Known V2 issues discovered**:
1. Band market delta computation (`center - |forecast - center|`) produces absurd values like +88.6 — not a meaningful distance to threshold
2. `structured_prob` treatment (BinCal sigmoid) is a deterministic monotonic transform of delta — zero incremental information over `raw_data`
3. `control` treatment provides only market price — doesn't mirror production TraderBot (`traderbot analyze` + `traderbot signals`)
4. 3 of 10 markets are blowouts (prices 0.01-0.02) — not informative for testing agent reasoning quality
5. `settlement_actuals` (Open-Meteo) disagrees with `markets.actual_value` (Kalshi/NOAA) for ~30% of markets — different measurement sources
6. BinCal cold-start: sigmoid heuristic confidence is anti-correlated with accuracy at early timesteps (larger deltas → higher confidence but less reliability)
7. 8 processes observed during parallel treatment runs (expected 4)

---

## Phase 3: V3 Experiment Design (Current)

**Date**: 2026-05-18 (written in OpenCode session `ses_1c3b331e1ffe5ygGAy7czAnaIT`, recovered from `opencode.db` after accidental deletion)

**Document**: `experiments/V3.md` (309 lines)

### Why V3 — Five Problems Fixed

| # | V2 Problem | V3 Fix |
|---|-----------|--------|
| 1 | Band delta `center - \|forecast - center\|` gives absurd values | `norm.cdf` integration with known error distributions P(temp ∈ [floor, floor+1)) |
| 2 | Point-estimate only — no forecast uncertainty | raw_data adds city-specific MAE/bias per lead time |
| 3 | structured_prob = `sigmoid(delta)` — monotonic transform of raw_data | structured_prob = `norm.cdf` probability the agent can't compute in its head |
| 4 | No forecast accuracy data in any treatment | raw_data includes per-city, per-lead-time MAE and bias (from Kalshi settlements) |
| 5 | Control = bare market price only | Control mirrors production: signal direction, confidence, RSI, Bollinger, implied probability |

### V3 Treatment Design

| Treatment | What agent receives | Incremental info over lower tier |
|-----------|--------------------|---------------------------------|
| **control** | Market prices, implied probability, technical indicators (RSI, Bollinger, momentum, signal direction/confidence) | Baseline — mirrors production `traderbot analyze` + `traderbot signals` |
| **raw_data** | + Forecast temp, forecast age, city-specific MAE/bias at each lead time, delta from threshold | Cannot derive "Austin is +1.3°F biased" from a single forecast |
| **structured_prob** | + P(YES) computed via norm.cdf with city error distributions, 95% CI, sample size | Cannot integrate normal distribution over band threshold in its head |
| **calibration_bundle** | + Forecast trajectory (T-4 through T-0), trend, range, historical settlement rates for similar deltas | Shows convergence/divergence and empirical calibration |

### Key Technical Changes

1. `prob_less`, `prob_greater`, `prob_between` use `scipy.stats.norm.cdf` with city-specific μ_adj and σ
2. Delta for band markets uses signed distance to nearest boundary
3. Forecast accuracy computed from Kalshi settlement (NWS CLI) vs Open-Meteo Previous Runs — NOT from Open-Meteo archive actuals
4. 10 markets (7 contested + 3 blowouts), including mixed strike types (less, greater, between)
5. 5 timesteps within ~40h trading window

### What Exists vs What Needs Building

| Component | V2 Status | V3 Action Needed |
|-----------|-----------|-------------------|
| `treatment_harness.py` | 647 lines, functional | Rewrite prompts and probability computation |
| `_compute_delta()` | Center-based band delta | Replace with boundary-based |
| `_sigmoid()` / `_compute_bincal()` | Sigmoid heuristic | Replace with norm.cdf probability |
| Control prompt | Market price only | Add RSI, Bollinger, signal direction |
| raw_data prompt | Forecast + delta only | Add city MAE/bias per lead time |
| structured_prob prompt | BinCal sigmoid output | Use norm.cdf output |
| calibration_bundle prompt | BinCal + evolution | Add trajectory, trend, settlement rates |
| DB (experiment_data.db) | 25 markets, all band type | Re-select 10 markets with mixed strike types |
| `compile_data.py` / `v2_compile_data.py` | Synthesized data | Need v3_compiler with real Previous Runs data |
| `forecast_loader` | Reads `forecasts` table | Need to read Previous Runs API data |

### Current State (as of 2026-05-18)

- `treatment_harness.py` runs 4 treatments but with V2 prompts and sigmoid computation
- `experiment_data.db` on macpro-linux has 25 markets, 250 snapshots, 250 prices, 1000 treatment decisions
- V3 redesign document exists but implementation has not started
- The cold_start_fix.md V1 approach (hardcode weather_prob.py) was rejected in favor of the experiment approach
- The methodology experiment plan (bin_cal, logistic_reg, llm_synthesis, ensemble) was superseded by the treatment-based design

---

## Phase 4: V3 — Treatment-Agnostic Test Environment

**Date**: 2026-05-18 (commit `tbd`, session `ses_1c5b2b2a0ffe...`)

**Document**: `experiments/v3/README.md`

### What V3 Is

V3 is a treatment-agnostic experiment lab. The harness assembles the full context for every market, hands it to a treatment, records the LLM decision, and scores the results. The lab never knows which treatments are loaded and never contains treatment-specific logic. A treatment is a plug-in module that implements `TreatmentInterface`.

### Key Improvements Over V2

| Area | V2 | V3 |
|------|-----|-----|
| Architecture | Treatment prompts hardcoded inside `treatment_harness.py` (647 lines, `if/elif` blocks) | `TreatmentInterface` ABC; treatments live in `experiments/treatments/` |
| Extensibility | Adding a treatment required editing the harness | Add a file + one-line registry entry |
| Control | Bare market price only | Mirrors production `traderbot analyze` + `traderbot signals` (RSI, Bollinger, EMA, signal direction, confidence) |
| Probability | Sigmoid(delta) heuristic | `scipy.stats.norm.cdf` with city-specific error distributions |
| Forecast data | Synthetic (actual temp + Gaussian noise) | Real archived forecasts from Open-Meteo Previous Runs |
| Accuracy data | None | Per-city, per-lead-time MAE and bias computed from Kalshi settlements |
| Experiment design | No formal pairing | Within-subjects: every treatment sees the exact same markets and timesteps |
| Scoring | Brier score, binary accuracy | P&L, delta profit, paired t-tests, Cohen's d, confidence intervals |

### Folder Reorganization

```
experiments/
├── v3/               Testing lab (treatment-agnostic)
│   ├── harness.py
│   ├── scoring.py
│   ├── statistics.py
│   ├── market_selector.py
│   ├── treatment_interface.py
│   ├── db_schema.py
│   ├── cli.py
│   └── data_sources/
│       ├── kalshi_fetcher.py
│       ├── openmeto_fetcher.py
│       └── accuracy_calculator.py
└── treatments/       Plug-in treatments
    ├── control.py
    └── ...
```

### TreatmentInterface Plug-In Architecture

Every treatment inherits from `TreatmentInterface` and implements three members:

- `name` — unique identifier used by CLI and reporting
- `format_prompt(ctx)` — receives the full `TreatmentContext` and returns a prompt string
- `validate_response(response)` — parses and guards against malformed LLM output

The harness only calls these methods. It never branches on treatment names, never knows what fields are included in the prompt, and never modifies scoring based on which treatment is running. This is the boundary rule: `v3/` code never imports from `treatments/`.

### Production-Mirroring Control

The control treatment (`ControlTreatment`) replicates what a real TraderBot agent receives today:

- Market details and orderbook
- Implied probability from mid-price
- RSI, Bollinger bands, EMA crossover
- Signal direction and confidence from `generate_signal()`

The control does not receive weather forecasts, forecast accuracy, or city-specific bias. This establishes a realistic baseline: any treatment that outperforms the control does so because the extra information is genuinely useful to the agent, not because the control is artificially weak.

### Within-Subjects Design

Every treatment is evaluated on the same stratified market pool. Markets are selected from a `2x3x2` grid (difficulty x strike_type x lead_time_bucket) to ensure coverage. Because the same market appears for every treatment, we compute **delta profit** (treatment P&L minus control P&L) per market and run paired t-tests. This removes between-market variance and isolates the effect of the treatment itself.

Statistical outputs include:
- Paired t-test (mean delta profit vs zero)
- Cohen's d (standardized effect size)
- 95% confidence interval for mean delta profit

A treatment is considered promising when it shows positive mean delta profit, p < 0.05, and a narrow confidence interval.

### Implementation Status

- [x] `TreatmentInterface` ABC and `TreatmentContext` dataclass
- [x] Control treatment with production-mirroring logic
- [x] Harness, scoring, statistics, and CLI
- [x] Market selector with stratified 2x3x2 grid
- [x] Kalshi fetcher, Open-Meteo fetcher, and accuracy calculator
- [x] SQLite schema for markets, forecasts, prices, settlements, decisions
- [ ] Full end-to-end run with all four treatments (in progress)

