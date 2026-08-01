# Treatment Specification

This document is the instruction sheet for building experimental treatments in the V3 test environment. It defines the interface contract, data shapes, and step-by-step process. Treatments are plug-in modules, they never modify the lab infrastructure.

---

## 1. TreatmentInterface (ABC)

Every treatment must inherit from `TreatmentInterface` and implement three members.

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

class TreatmentInterface(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier used by the CLI and reporting."""

    @abstractmethod
    def format_prompt(self, ctx: TreatmentContext) -> str:
        """Return a prompt string for the LLM given the full context."""

    @abstractmethod
    def validate_response(self, response: dict) -> ValidatedDecision:
        """Parse and validate the raw LLM response. Raise ValueError on bad format."""
```

**Type signatures**

| Member | Signature | Purpose |
|--------|-----------|---------|
| `name` | `str` (property) | Used in CLI args, DB rows, and report filenames. Must be unique across all treatments. |
| `format_prompt` | `(TreatmentContext) -> str` | Receives the full context object. Chooses what to show the LLM. Returns a single prompt string. |
| `validate_response` | `(dict) -> ValidatedDecision` | Guards against malformed LLM output. Raises `ValueError` so the harness can log and skip. |

---

## 2. TreatmentContext Dataclass

The harness builds one `TreatmentContext` per market per timestep and passes it to `format_prompt()`. The treatment cannot request extra data, it only chooses what to include from the fields below.

```python
@dataclass(frozen=True)
class TreatmentContext:
    market: MarketData
    forecast: ForecastData
    accuracy: AccuracyData
    prices: PriceData
    technical: TechnicalData
    prior: PriorDecisions
    system_context: str = ""  # OpenClaw workspace files (AGENTS.md, SOUL.md, TOOLS.md, etc.)
```

### Field descriptions

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `market` | `MarketData` | Ticker, strike type, threshold, expiration, category tags | Kalshi API (cached in SQLite) |
| `forecast` | `ForecastData` | Raw forecast temperature, source model, days before expiry | Open-Meteo Previous Runs API |
| `accuracy` | `AccuracyData` | Historical accuracy metrics for the source model on this ticker | Back-computed from resolved markets |
| `prices` | `PriceData` | YES/NO midprice history (cents), current spread, last trade | Kalshi market data snapshots |
| `technical` | `TechnicalData` | RSI, Bollinger bands, EMA crossover computed over `prices.history` | `traderbot.analysis.indicators` |
| `prior` | `PriorDecisions` | Decisions made by this treatment on earlier timesteps of the same market | In-memory during the experiment run |
| `system_context` | `str` | OpenClaw workspace files defining agent identity/rules/tools | Harness loads from `~/.openclaw/workspace/` |

### Sub-dataclass details

```python
@dataclass(frozen=True)
class MarketData:
    ticker: str
    strike_type: Literal["between", "less", "greater"]
    threshold: float
    expiration: datetime
    category: str

@dataclass(frozen=True)
class ForecastData:
    forecast_temp_f: float
    source: str          # e.g. "ecmwf", "gfs"
    days_before: int

@dataclass(frozen=True)
class AccuracyData:
    brier_score: float | None
    calibration_error: float | None
    sample_size: int

@dataclass(frozen=True)
class PriceData:
    current_yes_cents: int
    current_no_cents: int
    history: list[int]   # chronological mid-prices in cents
    spread_cents: int

@dataclass(frozen=True)
class TechnicalData:
    rsi: float | None
    bb_upper: float | None
    bb_lower: float | None
    ema_short: float | None
    ema_long: float | None

@dataclass(frozen=True)
class PriorDecisions:
    decisions: list[dict]  # each dict: {"timestep": int, "decision": str, "estimated_prob": float}
```

---

## 3. Expected LLM Response Format

The LLM must return a single JSON object. The harness parses it with `json.loads()` and passes the dict to `validate_response()`. Your `validate_response` must enforce this schema.

```json
{
  "decision": "buy_yes",
  "estimated_prob": 0.72,
  "confidence": 0.85,
  "reasoning": "Temperature forecast is 5°F above threshold with high model agreement."
}
```

### Field rules

| Field | Type | Constraints |
|-------|------|-------------|
| `decision` | `str` | Must be one of `"buy_yes"`, `"buy_no"`, `"skip"`. |
| `estimated_prob` | `float` | Range `[0.0, 1.0]`. The treatment's own probability estimate. |
| `confidence` | `float` | Range `[0.0, 1.0]`. Self-reported certainty in the decision. |
| `reasoning` | `str` | Free text. Stored in the audit trail, not used for scoring. |

If any field is missing or violates constraints, `validate_response` must raise `ValueError`. The harness will record the failure and move on.

---

## 4. How to Create a New Treatment

1. **Create a file** in `experiments/treatments/` named after your treatment, e.g. `my_treatment.py`.
2. **Import the ABC and dataclasses**:
   ```python
   from experiments.v3.harness import TreatmentInterface, TreatmentContext
   ```
3. **Implement the three required members** (`name`, `format_prompt`, `validate_response`).
4. **Register the class** in `experiments/treatments/__init__.py` by adding it to the `TREATMENT_REGISTRY` list:
   ```python
   from .my_treatment import MyTreatment
   TREATMENT_REGISTRY = [MyTreatment]
   ```
5. **Point the CLI to it**. The experiment runner discovers treatments from the registry automatically. Run with:
   ```bash
   python -m experiments.v3.runner --treatment my_treatment --markets markets.json
   ```

---

## 5. How the Harness Calls Your Treatment

At each timestep for each market, the harness performs the following operations in order:

1. **Load data** — Fetch `MarketData`, `ForecastData`, `AccuracyData`, `PriceData`, and compute `TechnicalData`.
2. **Build context** — Assemble a `TreatmentContext` with the data above plus `PriorDecisions` from earlier timesteps.
3. **Call `format_prompt(ctx)`** — Pass the context to your treatment. You decide what goes into the prompt string.
4. **Query the LLM** — Send the prompt to the configured model (default: `glm-5.1:cloud` via Ollama).
5. **Parse the response** — Run `json.loads()` on the LLM output.
6. **Call `validate_response(response)`** — Your method checks the dict and returns a `ValidatedDecision`.
7. **Record the decision** — Store the decision, estimated probability, and reasoning in the experiment DB.
8. **Update `PriorDecisions`** — Append this timestep's result to the context for the next timestep.

The harness repeats steps 1-8 for every market in the pool, then proceeds to the next timestep.

---

## 6. Delta Profit Computation

Delta profit is the core metric for comparing treatments. It answers: *How much more (or less) did this treatment earn than the control?*

### Per-market delta profit

For a single market, the harness tracks:

- **Control P&L** — Profit/loss from the control treatment's decisions on that market.
- **Treatment P&L** — Profit/loss from the experimental treatment's decisions on that market.

```
DeltaProfit = TreatmentP&L - ControlP&L
```

Both P&L values are computed in cents using the actual resolution outcome (`YES` or `NO`). A positive delta means the treatment outperformed the control on that market.

### Aggregation

After all markets and timesteps are complete, the harness aggregates:

- **Mean delta profit** across all markets.
- **Paired t-test** (treatment vs control on the same market set).
- **Effect size** (Cohen's d) and **95% confidence interval**.

Because the design is within-subjects (same markets for every treatment), the paired test isolates the treatment effect from market variation.

---

## 7. Data Contract

The harness guarantees that `TreatmentContext` will always contain the fields listed in section 2, but some values may be `None` when data is unavailable.

### Guarantees

| Field | Guarantee |
|-------|-----------|
| `market.ticker` | Always present, non-empty string. |
| `market.strike_type` | Always one of `between`, `less`, `greater`. |
| `forecast.forecast_temp_f` | Always a float. |
| `prices.history` | Chronological list. May be empty if no historical snapshots exist. |
| `technical.rsi` | `None` if fewer than 2 price points. Otherwise computed with period 14. |
| `technical.bb_upper` / `bb_lower` | `None` if fewer than 20 price points. |
| `prior.decisions` | Empty list on timestep 0. Grows by one entry per timestep. |

### What the treatment should NOT do

- Do not query external APIs. All data is pre-loaded by the harness.
- Do not assume `accuracy.brier_score` is present. It is `None` until enough historical data exists.
- Do not modify the context object. It is frozen (`frozen=True`).

---

## 8. Minimal Treatment Example

```python
"""Minimal treatment that mirrors how a human trader might reason."""

import json
from dataclasses import dataclass
from experiments.v3.harness import TreatmentInterface, TreatmentContext

class MinimalTreatment(TreatmentInterface):
    @property
    def name(self) -> str:
        return "minimal"

    def format_prompt(self, ctx: TreatmentContext) -> str:
        return (
            f"Market: {ctx.market.ticker}\n"
            f"Strike: {ctx.market.strike_type} {ctx.market.threshold}\n"
            f"Forecast: {ctx.forecast.forecast_temp_f}°F\n"
            f"Current YES price: {ctx.prices.current_yes_cents}c\n\n"
            "Decide: buy_yes, buy_no, or skip. "
            "Reply with JSON: {\"decision\": \"...\", \"estimated_prob\": 0.0-1.0, "
            "\"confidence\": 0.0-1.0, \"reasoning\": \"...\"}"
        )

    def validate_response(self, response: dict) -> "ValidatedDecision":
        decision = response.get("decision")
        if decision not in ("buy_yes", "buy_no", "skip"):
            raise ValueError(f"Invalid decision: {decision}")
        prob = float(response.get("estimated_prob", -1))
        if not 0.0 <= prob <= 1.0:
            raise ValueError(f"Invalid estimated_prob: {prob}")
        conf = float(response.get("confidence", -1))
        if not 0.0 <= conf <= 1.0:
            raise ValueError(f"Invalid confidence: {conf}")
        return ValidatedDecision(
            decision=decision,
            estimated_prob=prob,
            confidence=conf,
            reasoning=response.get("reasoning", ""),
        )


@dataclass(frozen=True)
class ValidatedDecision:
    decision: str
    estimated_prob: float
    confidence: float
    reasoning: str
```

---

## 9. Control Treatment (Reference)

The control treatment is special. It does not query an LLM. Instead, it calls the production `generate_signal()` function directly so the experiment measures the exact behavior of the deployed system.

```python
from traderbot.analysis.signals import generate_signal

class ControlTreatment(TreatmentInterface):
    @property
    def name(self) -> str:
        return "control"

    def format_prompt(self, ctx: TreatmentContext) -> str:
        """Not used. The control bypasses the LLM entirely."""
        return ""

    def validate_response(self, response: dict) -> "ValidatedDecision":
        """Not used. The control returns a ValidatedDecision directly."""
        raise NotImplementedError("Control treatment bypasses validate_response.")

    def decide(self, ctx: TreatmentContext) -> "ValidatedDecision":
        """Called by the harness instead of the LLM pipeline."""
        signal = generate_signal(
            ticker=ctx.market.ticker,
            prices=ctx.prices.history,
            orderbook=...,  # built from ctx.prices by the harness
            estimated_prob=...,  # computed by the harness from forecast data
            news_sentiment=None,
        )
        return ValidatedDecision(
            decision="buy_yes" if signal.direction == "yes" else "buy_no",
            estimated_prob=signal.estimated_prob,
            confidence=signal.confidence,
            reasoning=f"Production signal: {signal.direction} ({signal.confidence:.2f})",
        )
```

The harness detects the control treatment by name and routes it through `decide()` instead of the LLM pipeline. All other treatments go through `format_prompt()` → LLM → `validate_response()`.

---

## 10. Checklist Before Running

- [ ] Treatment file lives in `experiments/treatments/`
- [ ] Class inherits from `TreatmentInterface`
- [ ] `name` is unique across all treatments
- [ ] `format_prompt()` returns a string
- [ ] `validate_response()` raises `ValueError` on bad input
- [ ] LLM response schema matches section 3
- [ ] Treatment is added to `TREATMENT_REGISTRY`
- [ ] No DB, scoring, or harness logic is modified
