# V3 Experiment Harness

Treatment-agnostic test environment for evaluating what TraderBot should provide to a freshly deployed agent.

---

## What this is

V3 is a pluggable experiment framework. It runs the same LLM agent against multiple treatments, where each treatment decides what information to show the agent. The harness is blind to treatment internals: it assembles the full context, calls the treatment's `format_prompt()`, sends the prompt to the LLM, records the decision, and scores the results.

This README covers how the system works, how to run experiments, and how to add new treatments.

---

## Architecture Overview

### Module Diagram

```
experiments/
├── v3/                          Testing lab (treatment-agnostic)
│   ├── cli.py                   --entrypoint: parse args, load treatments, run harness
│   ├── harness.py               --execution loop: select markets, build context, call LLM, record decisions
│   ├── scoring.py               --P&L, delta profit, Brier, skip rate
│   ├── statistics.py              --paired t-tests, Cohen's d, confidence intervals
│   ├── market_selector.py       --stratified pool selection (2x3x2 grid)
│   ├── treatment_interface.py   --shared ABC + TreatmentContext dataclass
│   ├── db_schema.py             --SQLite schema for markets, forecasts, prices, decisions
│   ├── llm_client.py            --thin wrapper around LLM calls
│   ├── probability.py             --norm.cdf band/less/greater probability helpers
│   ├── data_sources/
│   │   ├── kalshi_fetcher.py    --Kalshi API: markets, orderbook, settlements
│   │   ├── openmeto_fetcher.py  --Open-Meteo Previous Runs: archived forecasts
│   │   └── accuracy_calculator.py--per-city MAE/bias from resolved markets
│   └── tests/
└── treatments/                    Plug-in treatments
    ├── __init__.py                Registry (one-line import per treatment)
    └── control.py                 ControlTreatment: mirrors production TraderBot
```

### Data Flow

```
Kalshi API         Open-Meteo API
     |                   |
     v                   v
kalshi_fetcher     openmeto_fetcher
     |                   |
     +----+         +----+
          |         |
          v         v
      SQLite DB (experiment_data.db)
           |
           v
    market_selector (stratified pool)
           |
           v
    harness (builds TreatmentContext)
           |
           v
    treatment.format_prompt(ctx)
           |
           v
    llm_client (glm-5.1:cloud)
           |
           v
    treatment.validate_response()
           |
           v
    scoring (P&L, Brier, delta profit)
           |
           v
    statistics (t-tests, CI, Cohen's d)
           |
           v
    DB + JSON reports
```

The harness never reads treatment code directly. The only interface between the lab and a treatment is `TreatmentInterface`.

### Boundary Rule

`v3/` code never imports from `treatments/`. `treatments/` code never modifies infrastructure. The only connection is the `TreatmentInterface` contract. This means you can add, remove, or rewrite treatments without changing a single line in the lab.

---

## Quick Start

### Install

```bash
cd experiments/
pip install -r requirements.txt
```

This installs the project dependencies including `httpx`, `numpy`, `scipy`, and the local `traderbot` package.

### Run the harness (one-liner)

```bash
python -m experiments.v3.cli \
  --db experiment_data.db \
  --control experiments.treatments.control \
  --treatments experiments.treatments.raw_data,experiments.treatments.calibration_bundle \
  --markets 2 \
  --replicates 3 \
  --seed 42 \
  --model glm-5.1:cloud \
  --output results/v3_run_001.json
```

Arguments:

| Flag | Default | Meaning |
|------|---------|---------|
| `--db` | required | Path to SQLite database |
| `--control` | required | Module path for control treatment |
| `--treatments` | none | Comma-separated list of up to 3 extra treatments |
| `--markets` | 2 | Markets per stratified cell |
| `--replicates` | 3 | Number of replicates per market |
| `--seed` | 42 | Random seed for market selection and ordering |
| `--model` | glm-5.1:cloud | LLM model identifier |
| `--output` | none | JSON path for experiment summary |
| `--dry-run` | false | Validate treatments and print market preview without calling the LLM |
| `--verify-data` | false | Count DB records and print coverage summary |

---

## How to Add a Treatment

Treatments are self-contained plug-ins that live in `experiments/treatments/`. To build one, implement `TreatmentInterface` and register it.

### Step 1: Read the spec

`experiments/docs/treatment_spec.md` defines the full contract, field descriptions, scaffold template, and checklist. Read it before writing any treatment code.

### Step 2: Implement the interface

```python
# experiments/treatments/my_treatment.py
from experiments.v3.treatment_interface import TreatmentInterface, TreatmentContext

class MyTreatment(TreatmentInterface):
    @property
    def name(self) -> str:
        return "my_treatment"

    def format_prompt(self, ctx: TreatmentContext) -> str:
        # Choose which fields to include. The harness always provides the full context.
        return f"""
Market: {ctx.market.ticker}
Forecast: {ctx.forecast.forecast_temp_f}F (source: {ctx.forecast.source})
Accuracy: MAE {ctx.accuracy.mae:.1f}F, bias {ctx.accuracy.bias:+.1f}F
YES price: {ctx.prices.yes_price:.2f}
Decide: buy_yes, buy_no, or skip.
Respond with JSON: {{"decision": "...", "estimated_prob": 0.0-1.0, "confidence": 0.0-1.0, "reasoning": "..."}}
"""

    def validate_response(self, response: dict) -> bool:
        if response.get("decision") not in ("buy_yes", "buy_no", "skip"):
            return False
        prob = response.get("estimated_prob")
        if not isinstance(prob, (int, float)) or not 0.0 <= prob <= 1.0:
            return False
        conf = response.get("confidence")
        return isinstance(conf, (int, float))
```

### Step 3: Register

Add one line to `experiments/treatments/__init__.py`:

```python
from .my_treatment import MyTreatment
```

### Step 4: Run

```bash
python -m experiments.v3.cli \
  --db experiment_data.db \
  --control experiments.treatments.control \
  --treatments experiments.treatments.my_treatment \
  --dry-run
```

Dry-run validates the treatment loads and prints the market pool. Remove `--dry-run` to run the real experiment.

---

## Data Pipeline Overview

### Kalshi API to SQLite (`kalshi_fetcher.py`)

`kalshi_fetcher.py` uses the existing TraderBot `KalshiClient` to fetch:

- Market metadata (ticker, city, strike type, threshold, resolution date)
- Orderbook snapshots (YES/NO midprice, trade count, open interest)
- Settlement results from resolved markets

It maps Kalshi tickers to cities via `KXHIGH_` prefix lookup and parses strike types from the ticker suffix (`T`=greater, `B`=between, `L`=less). All data is cached in the `markets`, `market_prices`, and `settlement_results` tables.

### Open-Meteo Previous Runs (`openmeto_fetcher.py`)

`openmeto_fetcher.py` queries `previous-runs-api.open-meteo.com` for archived forecast temperatures at lead times T-4 through T-0. It fetches per-city latitude/longitude, hits the API with a courtesy delay between requests, converts Celsius to Fahrenheit, and stores results in `forecast_snapshots`.

### Accuracy Calculator (`accuracy_calculator.py`)

The accuracy calculator joins `forecast_snapshots` with `settlement_results` and groups by city and `lead_time` to compute:

- `mae`: mean absolute error
- `bias`: mean forecast minus actual (signed)
- `sample_count`: number of resolved markets in the group
- `low_confidence`: true when `sample_count < 3`

Results are written to `forecast_accuracy` and passed into each `TreatmentContext` as `AccuracyData`.

---

## Running an Experiment

### Dry-run (no LLM calls)

```bash
python -m experiments.v3.cli \
  --db experiment_data.db \
  --control experiments.treatments.control \
  --treatments experiments.treatments.raw_data \
  --dry-run
```

This validates that:
- All treatments load without import errors
- All treatments expose `name`, `format_prompt`, and `validate_response`
- The stratified market pool can be built from the DB

### Verify data coverage

```bash
python -m experiments.v3.cli --db experiment_data.db --verify-data
```

Example output:

```
Data verification: 10 markets, 10 with forecasts, 10 with prices.
```

If forecast or price coverage is low, re-run the fetchers before the experiment.

### Full run

```bash
python -m experiments.v3.cli \
  --db experiment_data.db \
  --control experiments.treatments.control \
  --treatments experiments.treatments.raw_data,experiments.treatments.structured_prob \
  --markets 2 \
  --replicates 3 \
  --seed 42 \
  --model glm-5.1:cloud \
  --output results/run_$(date +%Y%m%d_%H%M%S).json
```

The harness selects a stratified pool (`2x3x2` grid, 24+ cells), runs each treatment on each market for each replicate, writes decisions to `treatment_decisions`, and prints a run ID you can pass to the scoring pipeline.

---

## Statistical Methodology

### Within-Subjects Design

Every treatment sees the exact same markets, timesteps, and replicate assignments. Because each market is its own control, we avoid between-subjects variance. Differences in performance come from the treatment itself, not from market selection or random ordering.

### Delta Profit

For each market, the harness computes P&L in cents using a fixed $1.00 position size:

- `buy_yes`: profit = `100 * (1 - yes_price)` if market settles YES, else `-100 * yes_price`
- `buy_no`: profit = `100 * yes_price` if market settles NO, else `-100 * (1 - yes_price)`
- `skip`: 0

Delta profit for a treatment is the per-market difference between the treatment P&L and the control P&L. This isolates the incremental value of the extra information.

### Paired t-test

We run a paired one-sample t-test on delta profits (treatment minus control) across all markets. The null hypothesis is that the mean delta profit is zero.

```python
from scipy import stats
result = stats.ttest_rel(treatment_pnl, control_pnl)
```

Output includes `t_statistic`, `p_value`, mean delta, and sample size.

### Cohen's d (Effect Size)

Cohen's d measures standardized effect size for paired samples:

```python
diffs = np.array(treatment_pnl) - np.array(control_pnl)
cohens_d = np.mean(diffs) / np.std(diffs, ddof=1)
```

Interpretation (Loose heuristic):

| | d | |
|---|---|---|
| Small | 0.2 |
| Medium | 0.5 |
| Large | 0.8 |

### Confidence Intervals

A 95% confidence interval is computed for the mean delta profit using the standard error of the mean and the t-distribution:

```python
mean = np.mean(deltas)
sem = stats.sem(deltas)
lower, upper = stats.t.interval(0.95, df=len(deltas)-1, loc=mean, scale=sem)
```

If the interval does not include zero, the treatment has a statistically reliable effect at the 5% level. The width of the interval tells you how precisely the effect is estimated.

### Reporting

After a run, call `score_run()` from `scoring.py` and `compare_treatments()` from `statistics.py` to produce a JSON report containing per-treatment mean P&L, p-values, Cohen's d, and CIs. A treatment is considered promising when it shows positive mean delta profit, p < 0.05, and a narrow CI.
