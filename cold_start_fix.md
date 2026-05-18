# Cold-Start Fix: Agent Probability Calibration Pipeline

**Date**: 2026-05-18  
**Status**: Proposed  
**Priority**: P0 — blocks all profitable trading  
**Scope**: Weather agent (Kestrel/weather2) and future category agents

---

## Problem Statement

### The Cold-Start Paradox

A TraderBot agent cannot trade profitably on day one because:

1. **`edge_estimate` is always 0.0** — The agent must provide `--estimated-prob` and `--confidence` to `traderbot trade`, but has no principled way to compute these values from raw data. Without `estimated_prob`, the risk pipeline uses market-implied probability, guaranteeing ~0% edge (you can't beat the market by agreeing with it).

2. **No calibration data exists** — The `BayesianAdapter` is designed to update priors from trade outcomes, but ChromaDB `decisions` collection has 0 entries. There's no feedback loop: the agent can't learn because it can't trade, and it can't trade because it hasn't learned.

3. **Signal generation is circular** — `generate_signal()` in `src/traderbot/analysis/signals.py` receives `estimated_prob` as a parameter. When called from `traderbot signals`, it defaults to market-implied probability (`prob.yes_prob`). Computing `|market_prob - market_price|` ≈ 0 by definition — the signal confirms the market, not the agent's edge.

### Evidence from Production

The weather2 agent (Kestrel) ran **64 decision evaluations across 5 days** with **zero trades executed**. Every single audit entry has:

```
edge_estimate: 0.0
confidence: 0.70-0.95
signal_strength: 0.38-0.97
outcome: rejected
```

Meanwhile, the weather thesis is sound — Kestrel correctly identified:
- NYC >84°F YES (88°F forecast, 61¢ market) → settled YES ✓
- NYC <68°F low (66°F forecast, 55¢ NO market) → settled NO ✓
- Chicago <82°F YES (78°F forecast, 61¢ YES market) → settled YES ✓

The agent has the right data but no way to convert "forecast delta" into "estimated probability."

### Root Cause Analysis

| Layer | Problem | Code Location |
|---|---|---|
| **Signal** | `generate_signal()` takes `estimated_prob` as parameter but callers pass market-implied prob | `analysis/signals.py:69` |
| **CLI** | `traderbot trade` accepts `--estimated-prob` but the agent doesn't know how to derive it from weather data | `cli.py:363-430` |
| **Tooling** | `traderbot signals` uses market-implied prob → edge ≈ 0 | `cli.py:288-349` |
| **Storage** | Audit trail writes to JSON files but NOT to ChromaDB `decisions` collection | `cli.py`, `wal.py` |
| **Learning** | `BayesianAdapter` exists but has 0 observations; no code triggers updates | `simulation/adaptation.py` |
| **Backtest** | `BacktestEngine` complete but `strategies/` directory is empty — no strategy implementations | `simulation/engine.py`, `simulation/strategies/__init__.py` |

---

## Solution Architecture

### Phase 1: Weather Probability Model

**Goal**: Give the agent a principled `estimated_prob` derived from forecast data, not market price.

**Approach**: For weather markets (temperature thresholds, precipitation, etc.), compute probability from historical forecast accuracy:

```
P(market settles YES) = f(forecast_value, threshold, historical_accuracy_for_category)
```

Where `historical_accuracy_for_category` comes from analyzing settled weather markets:

```
For category "Climate and Weather":
  - Load last N settled markets (e.g., KXHIGHNY-*)
  - For each: get forecast_temp, threshold, settlement_result
  - Compute: accuracy = count(correct_predictions) / count(total_markets)
  - Bin by forecast_delta: [-∞, -4), [-4, -2), [-2, 0), [0, 2), [2, 4), [4, ∞)
  - Each bin has a Beta(α, β) prior: α = correct + 1, β = total - correct + 1
```

With this, when the agent sees "NYC forecast 88°F, market >84°F":
- `forecast_delta = 88 - 84 = +4°F`
- Bin: [2, 4) or [4, ∞)
- Historical accuracy for that bin: ~85-90% (forecast +4°F above threshold almost always settles YES)
- `estimated_prob = Beta(α, β).mean ≈ 0.85`
- `edge = |0.85 - 0.61| = 0.24` → passes 3% min_edge → trade executes

**Implementation**:

1. New module: `src/traderbot/analysis/weather_prob.py`
   - `compute_weather_probability(forecast_temp, threshold_temp, category, delta_bins)` → float
   - `load_historical_accuracy(category)` → dict of bins with Beta parameters
   - `update_accuracy_from_settlements(category, days_back=90)` → dict

2. CLI command: `traderbot calibrate --category weather`
   - Fetches settled markets from Kalshi via `HistoryService`
   - For each settled market, fetches forecast data from Open-Meteo historical API
   - Computes per-bin accuracy and updates `adapter_state.json`
   - Stores results in ChromaDB `market_patterns` collection

3. Wire into `generate_signal()`:
   - When market category is weather, call `compute_weather_probability()` instead of using market-implied prob
   - The function uses Open-Meteo current forecast + historical accuracy bins
   - Output: `estimated_prob` with genuine edge

**Data Flow**:

```
traderbot calibrate --category weather
  → HistoryService.get_settled_markets(category="weather", days_back=90)
  → DataLoader.fetch_forecast_data(dates, cities)
  → Compute per-bin accuracy → Store in adapter_state.json + ChromaDB
  → Output calibration curve

traderbot signals --category weather
  → Generate signal per market
  → For weather markets: compute_weather_probability(forecast, threshold, category)
  → estimated_prob = genuine probability (not market-implied)
  → edge = |estimated_prob - market_price| > 0
  → Signal passes min_edge filter
```

**Effort**: 2-3 sessions. Core logic is straightforward; the heavy lift is fetching and normalizing historical forecast data.

---

### Phase 2: Backtest with Settled Markets

**Goal**: Validate the weather probability model against historical data before live deployment.

**Existing Infrastructure**:
- `BacktestEngine` (`simulation/engine.py`) — complete, event-driven backtester
- `DataLoader` (`simulation/data_loader.py`) — fetches historical markets + trades from Kalshi, caches SQLite
- `HistoryService` (`kalshi/history.py`) — fetches settled markets, historical trades, cutoff timestamps
- `SettlementVerifier` (`simulation/settlement.py`) — reconciles settled markets, checks actual outcomes

**What's Missing**:
- A `WeatherStrategy` class in `simulation/strategies/` that implements the probability model from Phase 1
- A wiring from `traderbot backtest --category weather` → loads settled markets → runs strategy → produces P&L report
- Historical forecast data integration (Open-Meteo historical API or cached ingested data)

**Implementation**:

1. `src/traderbot/simulation/strategies/weather.py`:
   ```python
   class WeatherStrategy:
       """Strategy that uses forecast-derived probability estimates."""
       def generate_signal(self, context: Context) -> list[Signal]:
           # For each market in context:
           # 1. Parse threshold from ticker (e.g., KXHIGHNY → >84°F)
           # 2. Look up forecast for city/date
           # 3. Compute estimated_prob from Phase 1 model
           # 4. Return Signal with genuine edge
   ```

2. Extend `traderbot backtest`:
   ```python
   @app.command()
   def backtest(
       strategy: str,       # "momentum" or "weather"
       category: str,       # "Climate and Weather"
       from_date: str,
       to_date: str,
       json_output: bool = False,
   ):
       # Load settled markets for date range
       # For each settlement date:
       #   - Create Context with portfolio, market, sentiment
       #   - Run strategy.generate_signal(context)
       #   - Process through BacktestEngine
       #   - Track P&L, win rate, calibration curve
   ```

3. Output metrics:
   - Win rate by category
   - Calibration curve (predicted prob vs actual settlement rate)
   - P&L curve over time
   - Kelly fraction utilization
   - Edge distribution (how often edge > 3%, 5%, 10%)

**Effort**: 2-3 sessions. The engine exists; we need the strategy implementation and wiring.

---

### Phase 3: Bayesian Update Cycle

**Goal**: Continuous learning from trade outcomes.

**Existing Infrastructure**:
- `BayesianAdapter` (`simulation/adaptation.py`) — complete implementation:
  - Beta-Binomial for edge threshold adaptation
  - Dirichlet-Multinomial for signal weight rebalancing
  - Normal-Normal for mean reversion level
  - Gamma-Exponential for momentum decay rate
  - Safety guardrails: 20% max change per update, min 10 observations, max 4 updates/24h
  - Persistent state via `AdapterStateStore` (`adapter_state.py`)

**What's Missing**:
- No code path triggers `BayesianAdapter.update()` after trade settlement
- Decisions aren't written to ChromaDB (only to JSON audit files)
- No heartbeat integration that reads adapter state and uses it for signal generation

**Implementation**:

1. Write audit decisions to ChromaDB `decisions` collection:
   - After each `traderbot trade` call (whether executed or rejected)
   - Fields: ticker, category, estimated_prob, market_price, edge, direction, outcome (pending), settlement_result (later)
   - This unblocks the learning loop

2. Add settlement reconciliation to heartbeat loop:
   - `traderbot heartbeat` → fetch settled markets since last heartbeat
   - For each settled market with a pending decision:
     - Compare `estimated_prob` vs actual settlement
     - Call `BayesianAdapter.update()` with observation
     - Mark decision as resolved in ChromaDB

3. Wire adapter state into signal generation:
   - `generate_signal()` reads current `AdapterState` for category
   - Uses adapted edge thresholds and signal weights
   - Over time, the agent learns "my weather edge threshold should be 15%, not 3%" or "momentum signals are noise for weather markets, weight them lower"

**Effort**: 2-3 sessions. The adapter is complete; we need the data pipeline and heartbeat integration.

---

### Phase 4: Decision Storage Pipeline

**Goal**: Every trade evaluation (including rejections) feeds the learning loop.

**Current State**: Audit trail writes to `~/.traderbot/audit/YYYY-MM-DD.jsonl` but NOT to ChromaDB. The `decisions` collection exists but has 0 entries.

**Implementation**:

1. New module: `src/traderbot/db/decisions.py`
   - `store_decision(decision: TradeEvaluation)` → writes to ChromaDB `decisions` collection
   - `update_decision(ticker: str, settlement_result: str)` → updates outcome field
   - `get_pending_decisions(category: str)` → returns decisions awaiting settlement

2. Wire into `traderbot trade` CLI:
   - After `evaluate_trade()` call, store the full evaluation (including rejection reason) to ChromaDB
   - Fields: ticker, category, direction, estimated_prob, market_price, edge_estimate, confidence, signal_strength, outcome, rejection_reason, timestamp

3. Wire into heartbeat:
   - After settlement reconciliation, update decision outcome in ChromaDB
   - This enables: "how many of our last 50 weather predictions were correct?"

**Effort**: 1 session. Straightforward ChromaDB writes.

---

## Priority & Effort Matrix

| Phase | Goal | Effort | Unblocks | Dependencies |
|---|---|---|---|---|
| **Phase 1** | Weather probability model | 2-3 sessions | Agent can compute real `estimated_prob` → trades execute | None — can start immediately |
| **Phase 2** | Backtest with settled markets | 2-3 sessions | Validates Phase 1 model before live deployment | Phase 1 |
| **Phase 3** | Bayesian update cycle | 2-3 sessions | Continuous learning from outcomes | Phase 1, Phase 4 |
| **Phase 4** | Decision storage pipeline | 1 session | Enables Phase 3 (BayesianAdapter needs data) | None — can start in parallel with Phase 1 |

**Recommended execution order**: Phase 4 (quick win) → Phase 1 (the core fix) → Phase 2 (validate) → Phase 3 (learning loop)

---

## Existing Code Inventory

### Complete and Usable (No Changes Needed)

| Component | File | What It Does |
|---|---|---|
| `BacktestEngine` | `simulation/engine.py` | Event-driven backtester with position tracking, P&L, circuit breaker |
| `DataLoader` | `simulation/data_loader.py` | Fetches historical Kalshi data, caches to SQLite |
| `HistoryService` | `kalshi/history.py` | API client for settled markets, historical trades, cutoffs |
| `SettlementVerifier` | `simulation/settlement.py` | Lazy reconciliation of settled markets |
| `BayesianAdapter` | `simulation/adaptation.py` | Conjugate prior updates with guardrails (20% max change, min 10 obs) |
| `AdapterStateStore` | `simulation/adapter_state.py` | Versioned JSON persistence with atomic writes |
| `StrategyProfile` | `simulation/profiles.py` | Risk scaling within HARD_LIMITS |
| `PerformanceMetrics` | `simulation/performance.py` | Sharpe, max drawdown, win rate, calibration |
| `PaperTrader` | `simulation/paper_trader.py` | Paper trading with real market data |
| `generate_signal()` | `analysis/signals.py` | Weighted combination of indicators, odds, momentum, sentiment |
| `detect_edge()` | `analysis/odds.py` | Edge detection from orderbook |
| `compute_kelly_inputs()` | `analysis/odds.py` | Kelly criterion for position sizing |
| `evaluate_trade()` | `risk/__init__.py` | Full risk pipeline with position limits, circuit breaker |

### Exists but Empty (Needs Implementation)

| Component | File | What's Missing |
|---|---|---|
| `strategies/` | `simulation/strategies/__init__.py` | Empty — no strategy classes. Need `WeatherStrategy` |
| `decisions` ChromaDB | ChromaDB | 0 entries. Need write path from audit trail |

### Needs Modification

| Component | File | Change |
|---|---|---|
| `generate_signal()` | `analysis/signals.py:69` | Add weather probability override when category is weather |
| `traderbot signals` CLI | `cli.py:237-349` | Wire weather probability model into signal output |
| `traderbot trade` CLI | `cli.py:363-500` | Default `estimated_prob` from signal model when not provided |
| `traderbot backtest` CLI | `cli.py` | Add `--strategy weather` and `--category` options |
| Heartbeat loop | `cron_loops.py` | Add settlement reconciliation + Bayesian update step |
| Audit trail | `cli.py` / `wal.py` | Write decisions to ChromaDB after each evaluation |

---

## Expected Outcome

After Phase 1, the weather agent's first trade cycle would look like:

```
1. Agent runs traderbot scan --category weather --json
2. Sees: KXHIGHNY-26MAY19-T84 (NYC high >84°F on May 19)
3. Market price: 61¢ YES
4. Open-Meteo forecast: 88°F for NYC on May 19
5. Weather probability model: forecast_delta = +4°F → Bin [2°F, 4°F)
6. Historical accuracy for +4°F bin: ~85% → estimated_prob = 0.85
7. Edge = |0.85 - 0.61| = 0.24 (24%) → PASSES min_edge (3%)
8. Kelly sizing: edge × confidence → position_size = $XX
9. Trade executes
```

After Phase 3, after 50+ settled trades:

```
- BayesianAdapter tightens: edge threshold from 15% → 18% (learned: smaller deltas are noise)
- Signal weights shift: momentum weight down (noise for weather), forecast weight up
- Win rate converges: predicted 82% → actual 79% (well-calibrated)
- Agent adapts automatically via heartbeat loop
```

---

## Risk Considerations

1. **Historical data availability**: Kalshi's historical API may have gaps or limited coverage for weather markets. The `DataLoader` caches to SQLite but needs sufficient data (50+ settled markets per category).

2. **Forecast accuracy drift**: Weather forecast accuracy varies by season and lead time. The Beta-Binomial priors will adapt, but initial priors should be conservative (wide uncertainty bands).

3. **Overfitting**: Backtesting on the same data used to compute priors is circular. Use walk-forward validation: train on months 1-2, validate on month 3. The `BacktestEngine` supports date ranges for this purpose.

4. **Non-weather categories**: Phase 1 only solves the cold-start for weather markets. Politics, sports, and economics need separate probability models (news sentiment for politics, statistical models for sports, macro indicators for economics). These can follow the same architecture but need different data sources.

5. **API rate limits**: `HistoryService` and `DataLoader` make many API calls per category. Respect Kalshi's 20 RPS limit with semaphore (already handled by `Semaphore(3)` in series discovery).

---

*Proposed by Sisyphus. Data from macpro-linux deployment, weather agent audit trail, and TraderBot source code analysis.*
