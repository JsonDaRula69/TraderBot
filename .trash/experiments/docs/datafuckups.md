# Data & Decision Fuckups: Critical Audit of TraderBot Analysis Protocol

**Date**: 2026-05-18
**Scope**: Decision-making pipeline, signal generation, Bayesian adaptation, backtesting, and data flow
**Status**: No code changes made — this is a diagnosis document only

---

## Executive Summary

The TraderBot analysis and decision-making protocol is a **theater of functioning components surrounding a hollow core**. Every layer — signal generation, risk evaluation, Bayesian adaptation, backtesting, and decision storage — has a sophisticated implementation that is either fundamentally circular, disconnected from reality, or wired to fake data. The weather agent (Kestrel) ran **64 decision evaluations with zero trades executed** not because of bad luck, but because the system is architecturally incapable of forming a non-market-derived probability estimate. This document catalogs every weakness, pathetic assumption, and broken wire in the current protocol.

---

## 1. The Cold-Start Paradox (Fundamental Failure)

### Observation

The system cannot trade profitably on day one because it cannot form an `estimated_prob` that differs from the market-implied probability.

### Root Cause Chain

1. **`generate_signal()` takes `estimated_prob` as a parameter** (`analysis/signals.py:73`). It does not compute it. It merely uses it for edge detection against the orderbook.
2. **`traderbot signals` CLI defaults `estimated_prob` to market-implied probability** (`cli.py:304`: `estimated_prob=prob.yes_prob`). When the agent calls `traderbot signals`, it receives a signal whose `estimated_prob` is literally the market price it is trying to beat.
3. **`traderbot trade` accepts `--estimated-prob` but the agent has no principled source for it** (`cli.py:363`). The weather agent has forecast data (88°F for NYC) but no code path converts "forecast delta" into "probability of YES."
4. **Edge is always ~0**. `detect_edge(estimated_prob, orderbook)` computes `edge = estimated_prob - market_prob`. If `estimated_prob == market_prob`, edge ≈ 0. The Kelly sizing formula multiplies by edge, so position size ≈ 0. Risk rejects.
5. **Result**: 64 evaluations, 0 trades, every audit entry shows `edge_estimate: 0.0`.

### Why This Is Pathetic

The entire signal generation system is a self-fulfilling prophecy. The "signal" tells the agent what the market already believes. A `$1,000/hr` infrastructure computing `|market_price - market_price|` and calling it analysis.

---

## 2. Signal Generation is Financial Astrology

### RSI and Bollinger Bands on Binary Contract Prices

The `indicators` source in `generate_signal()` (`analysis/signals.py:81`) computes RSI and Bollinger bands on the contract price history. This is **nonsense** for binary prediction markets:

- **RSI was designed for continuous assets** (stocks, forex) where mean reversion is a real phenomenon. A binary contract at 85¢ is not "overbought" — it simply means the market thinks the event is 85% likely.
- **Bollinger bands depend on Gaussian price distributions**. Binary prices are bounded [0, 1] and their variance shrinks as they approach certainty. The standard deviation of a price near 0.95 is mathematically constrained, not a signal of volatility.
- **EMA crossover on binary prices** (`analysis/signals.py:134`) is equally meaningless. A 5-period vs 20-period EMA on a bounded discrete-time series tells you nothing about the "trend" of a probability.

### The Indicator Source Logic is Broken

```python
if rsi_val < 30:
    ind_direction = "yes"  # "oversold" → buy YES
elif rsi_val > 70:
    ind_direction = "no"   # "overbought" → buy NO
```

**Problem**: In binary markets, a low RSI means the price has been falling. A falling price means the market thinks the event is LESS likely. Buying YES because the price fell is **buying into deteriorating sentiment without understanding why**. This is the opposite of edge detection. It is noise-following.

### The Combine Signals Math is Bizarre

`combine_signals()` (`analysis/signals.py:36`) computes:

```python
signed_sum = sum(s.strength * s.weight * direction_sign for s in sources)
confidence = abs(signed_sum) / total_weight
```

**Problem**: This is a weighted vote of directional guesses. It does NOT compute a probability. The `CombinedSignal.estimated_prob` field is simply **echoing the input `estimated_prob`** (`analysis/signals.py:187`). The signal combination does zero probability estimation. It just votes on direction and confidence while blindly passing through whatever probability the caller provided.

### Sentiment Threshold is Arbitrary

```python
if news_sentiment > 0.1:
    sent_direction = "yes"
elif news_sentiment < -0.1:
    sent_direction = "no"
```

**Problem**: `0.1` is a magic number with no calibration. News sentiment scores are unnormalized. The classifier in `news/classifier.py` uses cosine similarity against topic vectors — the scale of these scores is arbitrary, not calibrated to predict binary outcomes.

---

## 3. The Bayesian Theater (The Grand Illusion)

### The Adapter is a Ghost Town

`BayesianAdapter` (`simulation/adaptation.py`) is one of the most sophisticated pieces of code in the repo:
- Beta-Binomial for edge threshold adaptation
- Dirichlet-Multinomial for signal weight rebalancing
- Normal-Normal for mean reversion level
- Gamma-Exponential for momentum decay rate
- Guardrails: 20% max change per update, min 10 observations, max 4 updates/24h, variance reset, drift detection

**BUT IT HAS ZERO OBSERVATIONS** because the data pipeline is severed at four points.

### Sever Point 1: No Settlement Outcomes in the DB

`step_bayesian_adaptation()` in `heartbeat.py:242` filters decisions:

```python
executed = [d for d in decisions if d.outcome == "executed"]
successes = sum(1 for d in executed if d.actual_result is not None and ...)
```

**Problem**: `DbDecision.actual_result` is almost always `None`. The `db/decisions.py` schema has:
```sql
actual_result INTEGER  -- nullable
```

But `cli.py` creates the `Decision` object without ever setting `actual_result`:
```python
decision = Decision(
    ...,
    actual_result=None,  -- Never populated
)
```

Result: `successes + failures < 1` → adaptation skipped with reason `"insufficient resolved decisions"`.

### Sever Point 2: Category is HARDCODED to ECONOMICS

In `heartbeat.py:283`:
```python
engine.update_beta(
    prior=WEAK_BETA,
    observations=observations,
    category=MarketCategory.ECONOMICS,  # <-- HARDCODED
)
```

**Problem**: A weather agent running on `Climate and Weather` markets is updating parameters under the `ECONOMICS` category. The adaptation state is keyed by category. This means:
- Weather outcomes update Economics priors
- Economics outcomes (when they exist) corrupt weather parameters
- The `AdapterStateStore` persists category-specific distributions, but the heartbeat always writes to the wrong key

### Sever Point 3: Prior is Reset Every Time

```python
engine = adapter or BayesianAdapter()  # Creates a NEW adapter with default priors
```

**Problem**: When `state_path` is not provided (common case in `heartbeat.py:457`), a brand-new `BayesianAdapter()` is instantiated. It loads no prior state. The Beta prior defaults to `WEAK_BETA = BetaParams(alpha=2, beta=8)` every single heartbeat. The 20% guardrail prevents change, but since the prior is always reset, the adapter never accumulates learning.

### Sever Point 4: The Adapter Never Adapts What Matters

Even if data flowed correctly, the `BayesianAdapter` only updates:
- Edge threshold (Beta-Binomial on win/loss)
- Signal weights (Dirichlet-Multinomial)

It does NOT adapt:
- How to compute `estimated_prob` from weather data
- City-specific bias corrections
- Lead-time accuracy adjustments
- Category-specific signal validity

The adapter tunes knobs on a broken machine. It never questions whether the machine should exist.

---

## 4. Decision Storage is a Cemetery

### SQLite vs ChromaDB: Two Worlds, Zero Bridge

The system has TWO decision storage systems:

**SQLite** (`db/decisions.py`):
- Schema: `decisions(id, timestamp, ticker, direction, quantity, price, signal_strength, confidence, edge_estimate, risk_checks, outcome, rejection_reason, actual_result)`
- Written by: `cli.py` after `traderbot trade`
- Read by: `heartbeat.py` for performance review and Bayesian adaptation

**ChromaDB** (`db/vectors.py`):
- Collections: `decisions`, `news`, `market_patterns`, `news_signals`, `market_conditions`, `data_points`
- Implementation: `VectorStore.store_document()`, `.query_similar()`, `.delete_document()`
- Written by: **NO ONE**

**Problem**: The ChromaDB `decisions` collection is initialized but never populated. The `cold_start_fix.md` explicitly states: "Audit trail writes to JSON files but NOT to ChromaDB `decisions` collection." The `decisions` collection has 0 entries.

### The Audit Logger Writes to JSONL Files

```python
class AuditLogger:
    def log_decision(self, decision: Decision) -> None:
        log_file = self._log_dir / f"{date_str}.jsonl"
        # Append JSON line to file
```

**Problem**: The audit trail is a write-only log in `~/.traderbot/audit/`. Nothing reads it. Not the heartbeat. Not the adapter. Not the backtester. It is a black hole for decision data.

### The `db/decisions.py` Table Exists But Has No Updates

The schema field `actual_result INTEGER` is nullable. Nothing ever updates it after settlement. There is no reconciliation loop that reads settled markets and writes outcomes back to the decisions table.

---

## 5. The Backtest Mirage

### Sophisticated Engine, Toy Strategies

`BacktestEngine` (`simulation/engine.py`) is genuinely well-designed:
- Event-driven replay
- Slippage model
- P&L tracking, Sharpe ratio, max drawdown, Brier score, edge capture
- Signal → Fill → P&L pipeline

**BUT THE STRATEGIES ARE JOKE CODE** (`simulation/strategies/__init__.py`):

```python
class MomentumStrategy:
    def on_market_open(self, market, context):
        yes_price = float(prices[0]) if prices else 0.5
        edge = abs(yes_price - 0.5)
        direction = "yes" if yes_price > 0.5 else "no"
        prob = yes_price if direction == "yes" else 1.0 - yes_price
        return [Signal(ticker=..., direction=..., quantity=1, price_cents=..., estimated_prob=prob, confidence=...)]
```

**Problem**: Every strategy derives `estimated_prob` from the market price itself. `prob = yes_price`. This means edge = 0 by definition. The backtester is testing strategies that cannot possibly have edge.

### No WeatherStrategy Exists

The V1 `cold_start_fix.md` proposed a `WeatherStrategy`. It does not exist. The `strategies/` directory has three toy strategies and nothing else.

### The CLI Has No Strategy Wiring

`traderbot backtest` accepts `--strategy NAME` (`api.md:86`), but the CLI implementation in `cli.py` only handles `"momentum"`, `"mean_reversion"`, and `"conservative"`. There is no `--category weather` option. There is no way to backtest weather-specific probability models against historical settled markets.

### `compile_data.py` Uses Synthesized Data

The experiment data in `experiments/compile_data.py` creates forecasts by adding Gaussian noise to actual temperatures:

```python
error = rng.gauss(bias * (1 - timestep / 10), std)
forecast_temp = actual_temp_f + error
```

**Problem**: This is synthesized data, not real Open-Meteo Previous Runs. The V3.md design explicitly calls for real archived forecasts. The experiment is running on fake data, making its conclusions unreliable for production.

---

## 6. Risk Pipeline Structural Flaws

### Fake Portfolio on Every Trade

In `cli.py:433`:
```python
portfolio = PortfolioState(
    portfolio_value_cents=100_000_00,  # $100,000 hardcoded
    peak_value_cents=100_000_00,
    current_positions_value_cents=0,
    today_realized_loss_cents=0,
    today_unrealized_loss_cents=0,
    open_positions_count=0,
)
```

**Problem**: Every `traderbot trade` call evaluates risk against the SAME dummy portfolio. No real position tracking. No accumulation of daily losses. No drawdown calculation. The circuit breaker checks a portfolio that resets to $100k with zero positions every single trade.

### Circuit Breaker is Fresh Every Time

```python
breaker = CircuitBreaker()  # New instance with no state
```

**Problem**: The circuit breaker has no memory. It cannot accumulate daily loss or track peak-to-trough drawdown because it is instantiated fresh for each trade evaluation.

### Position Sizing is Not Kelly

`risk/sizing.py` implements `compute_kelly_inputs()` which calculates the Kelly fraction:
```python
kelly = (estimated_prob * odds - (1 - estimated_prob)) / odds
```

**BUT**: `evaluate_trade()` calls `sized_position_for_trade()`, but the CLI path just sets `quantity=1` and passes it through. The Kelly formula is computed but the result is not used to set the position size. The `TradeRequest` model includes `estimated_prob` and `confidence`, but the sizing function does not use them for Kelly-optimal sizing.

---

## 7. The V3 Experiment is an Orphan

### Beautiful Design, Zero Implementation

V3.md contains a mathematically rigorous treatment design with:
- `prob_less`, `prob_greater`, `prob_between` using `scipy.stats.norm.cdf` with city-specific bias/MAE
- Proper band market probability (integrating over [floor, floor+1))
- Forecast trajectory and trend slope
- Historical settlement rates per delta bin
- Control treatment mirroring production `traderbot analyze` + `traderbot signals`

**BUT**:
- `experiments/simulation/treatment_harness.py` still uses V2 prompts and sigmoid computation
- `experiments/compile_data.py` still synthesizes forecasts from actual temps + noise
- `v2_experiment_data.db` has 25 markets (all band type) not the V3 10-market mixed-strike design
- The probability computation code in V3.md exists only in the document, not in any `.py` file

### The `experiments/docs/testfuckups.md` File is Empty

It exists but contains nothing. A fitting metaphor.

---

## 8. Documentation vs Reality Gap

### `docs/self-learning.md` Fantasy

Claims the adaptation engine:
- "Runs during the Heartbeat Loop (every 6 hours)"
- "Collects all decisions made since last heartbeat"
- "Compares predicted outcome vs actual"
- "Updates posterior distributions via conjugate prior updates"

**Reality**:
- Heartbeat runs every 30 minutes (`HEARTBEAT_LOOP_CRON = "*/30 * * * *"`)
- It reads from SQLite, but `actual_result` is almost always NULL
- The Bayesian update hardcodes the category to ECONOMICS
- No outcomes are ever compared because settlements aren't reconciled

### `docs/simulation.md` Fantasy

Claims the backtester:
- "Tests strategies before risking real money"
- Has a `Strategy` protocol with `on_market_open`, `on_trade`, `on_settle`
- "Replays historical events through the strategy"

**Reality**:
- Only 3 toy strategies exist, all deriving `estimated_prob` from market price
- No `WeatherStrategy`, no category-specific strategies
- The `traderbot backtest` CLI accepts a strategy name but it's not wired to real data

### `docs/architecture.md` Fantasy

Shows a "Three-Loop Autonomous System":
- Decision Loop: every 5 minutes
- Heartbeat Loop: every 30 minutes
- News Ingestion: every 30 minutes

**Reality**:
- Decision Loop requires a human to run `traderbot trade` manually
- There is no autonomous 5-minute loop that fetches markets and evaluates trades
- The cron loops in `cron_loops.py` define Pydantic payloads but there is no evidence they are scheduled or run by OpenClaw in production
- `cron_loops.py` defines the payload but the actual scheduling mechanism is never shown

---

## 9. Why the Weather Agent Can Never Win

### No Category-Specific Analysis Exists

The `AnalysisRegistry` (`analysis/registry.py`) has a protocol for `CategoryAnalyzer` but:
```python
def analyze(self, market_data: dict, category: MarketCategory) -> CategorySignals:
    analyzer = self.get(category)
    return analyzer.analyze(market_data, category)

@property
def _default(self) -> CategoryAnalyzer:
    return GenericAnalyzer()  # RSI, Bollinger, EMA on binary prices
```

**No analyzers are registered for any category**. Every market, including weather, gets the `GenericAnalyzer` which applies stock-market technical indicators to binary contracts.

### The Forecast Data Is Invisible to the Toolkit

The weather agent has access to Open-Meteo forecasts (88°F for NYC). But:
- `traderbot signals` does not accept forecast data as input
- `traderbot trade` does not accept forecast data as input
- `generate_signal()` does not know what weather is
- The Kalshi `Market` model has no forecast fields
- There is no `WeatherAnalyzer` or `WeatherProbabilityModel` in the toolkit

The agent must compute `estimated_prob` externally and pass it via `--estimated-prob`. But the agent is an LLM with no statistical training. It cannot integrate a normal distribution over a temperature threshold in its head. The toolkit gives it RSI and Bollinger bands instead of `scipy.stats.norm.cdf`.

---

## 10. The Fundamental Design Contradiction

The architecture document states: **"The toolkit never decides strategy — it computes, enforces, and executes, but the agent decides"** (`AGENTS.md`).

**But the agent cannot decide without a probability estimate. And the toolkit provides no principled way to compute one.**

This creates a paradox:
- The agent must provide `--estimated-prob` to trade
- The agent has raw forecast data but no statistical model
- The toolkit refuses to provide category-specific models ("never decides strategy")
- The agent cannot trade without a model
- The Bayesian adapter cannot learn without trades
- **Circular deadlock**

The V3 experiment exists to answer: "What should the toolkit provide so the agent can form a defensible probability estimate?" But the experiment itself is stalled on V2 code with synthesized data. The question is being asked in a document, not in code.

---

## Inventory of Broken Contracts

| Document Claim | Code Reality | Severity |
|---|---|---|
| "Heartbeat loop updates Bayesian parameters every 30 min" | Actual results are NULL; category hardcoded to ECONOMICS | P0 |
| "Signal generation combines indicators, odds, momentum, sentiment" | Estimated_prob is pass-through; indicators are astrology for binary markets | P0 |
| "Risk module enforces immutable hard limits" | Evaluated against fake portfolio with no position tracking | P0 |
| "Backtest engine tests strategies before risking money" | Only toy strategies exist, all with zero edge | P0 |
| "Decision storage feeds the learning loop" | ChromaDB decisions collection has 0 entries; SQLite actual_result is NULL | P0 |
| "Three-loop autonomous system" | No autonomous loop exists; all commands are manual CLI invocations | P1 |
| "Category-based analysis registry" | No analyzers registered; GenericAnalyzer used for all | P1 |
| "V3 experiment tests treatment levels" | Harness still uses V2 sigmoid; data is synthesized | P1 |
| "Audit trail enables traceability" | Write-only JSONL files; nothing reads them | P2 |
| "Kelly criterion for position sizing" | Formula exists but result is not used | P2 |

---

*This document is a diagnosis. The cure is a separate design decision.*
