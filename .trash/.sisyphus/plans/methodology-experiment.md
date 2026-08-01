# Methodology Experiment: Probability Estimation for Prediction Market Agents

## TL;DR

> **Quick Summary**: Build a lightweight experiment framework to compare 4 competing probability estimation methodologies for Kalshi weather markets. Shared infrastructure (schema, interface, parsers, harness, scoring) is built first, then 4 methodology implementations run in parallel, each only implementing `estimate()`. Framework only — deployment to macpro-linux is a separate effort.
> 
> **Deliverables**:
> - SQLite schema + seed format documentation for 25 markets x 10 timesteps
> - Shared methodology interface (`base.py`, `ticker_parser.py`, `forecast_loader.py`, `db_utils.py`)
> - Simulation harness that runs 25 markets x 10 timesteps per methodology
> - Scoring pipeline (Brier, calibration, edge realization, P&L, timing, confidence-weighted accuracy)
> - 4 methodology modules: bin_cal, logistic_reg, llm_synthesis, ensemble
> - Docker configs for isolated container runs
> - Comparison report generator
> 
> **Estimated Effort**: Medium (2-3 focused sessions)
> **Parallel Execution**: YES — Wave 1 (5 shared modules) -> Wave 2 (2 core modules) -> Wave 3 (4 methodologies in parallel) -> Wave 4 (Docker + report)
> **Critical Path**: Task 1 -> Task 6 -> Task 12

---

## Context

### Original Request
User wants to test 4 competing probability estimation methodologies against 25 historical Kalshi weather markets with 10 forecast timesteps each. Each methodology gets its own Docker container with an OpenClaw agent. The experiment evaluates not just prediction accuracy but how well each methodology helps agents make trading decisions under realistic temporal dynamics (evolving forecasts, shifting market prices).

### Interview Summary
**Key Discussions**:
- Rejected cold_start_fix.md's single-methodology approach (hardcoded weather_prob.py inside generate_signal())
- Rejected `traderbot signals`-path approach (market-implied prob -> edge = 0)
- Each Kalshi category needs its own analysis model; weather != elections != crypto
- The OpenClaw agent is the decision-maker; TraderBot is the toolkit
- Agent will be reset between experiments; priority is improving the package for future agents
- Agents apply data mechanically without reasoning about uncertainty — need stochasticity-aware architecture
- Evaluation framework (scoreboard, drift detection, rotation) DEFERRED to future plan
- Database creation handled separately by the user — this plan only builds the framework
- Deployment to macpro-linux is NOT included in this plan — framework only
- LLM synthesis should operate without artificial constraints (no token budget, no rate limit)

**Research Findings**:
- `_KALSHI_WEATHER_CITIES` in `src/traderbot/news/sources.py` maps 15 ticker prefixes to (city, lat, lon)
- Open-Meteo archive API provides historical daily/hourly temperature data
- Open-Meteo forecast API provides up to 10-day forecasts (for timestep reconstruction)
- `HistoryService.get_settled_markets()` fetches settled markets, no category filter — client-side filtering needed
- `AnalysisRegistry` already supports `register(category, analyzer)` pattern — production integration path exists
- Market tickers follow pattern: `KXHIGHNY-26MAY18-T84` (city prefix + date + threshold)

### Metis Review
**Identified Gaps** (addressed):
- LLM methodology needs clear prompt template
- Ensemble needs definition of "weighted combination" — configurable weights, default 0.4/0.4/0.2
- Shared infrastructure should be extracted before methodology implementations to maximize parallelism
- Settlement data must be completely isolated from agent-facing queries

---

## Work Objectives

### Core Objective
Build the experiment framework — shared infrastructure, simulation harness, scoring pipeline, and 4 methodology implementations. The framework is self-contained in `experiments/` with no production code changes.

### Concrete Deliverables
- `experiments/db/seed_format.md` — Documentation of actual database schema (DB already exists)
- `experiments/db/seed_format.md` — Seed data format and timestep documentation
- `experiments/methodologies/base.py` — Abstract MethodologyInterface with `estimate()` signature
- `experiments/methodologies/ticker_parser.py` — `parse_weather_ticker()` shared utility
- `experiments/methodologies/forecast_loader.py` — `load_forecast()` shared utility
- `experiments/methodologies/db_utils.py` — SQLite connection/query helpers
- `experiments/simulation/harness.py` — Simulation orchestrator (25 markets x 10 timesteps)
- `experiments/simulation/scoring.py` — Scoring pipeline (Brier, calibration, edge realization, P&L)
- `experiments/methodologies/bin_cal.py` — Bin calibration methodology
- `experiments/methodologies/logistic_reg.py` — Logistic regression methodology
- `experiments/methodologies/llm_synthesis.py` — LLM synthesis methodology
- `experiments/methodologies/ensemble.py` — Ensemble methodology
- `experiments/docker/Dockerfile.methodology` — Base Docker image
- `experiments/docker/docker-compose.yml` — 4 services + scoring
- `experiments/results/compare.py` — Comparison report generator

### Definition of Done
- [ ] All shared modules implement well-defined interfaces
- [ ] Each methodology module implements only `estimate()` against the shared interface
- [ ] Simulation harness runs against a prepopulated SQLite database
- [ ] Docker containers build successfully (framework verified, not deployed)
- [ ] Scoring pipeline produces all 6 metrics from simulation JSONL output
- [ ] No modifications to `src/traderbot/` code

### Must Have
- Common `MethodologyInterface` ABC that all 4 methodologies implement
- Shared ticker parser, forecast loader, and DB utilities (no duplication across methodologies)
- Each methodology module only contains its unique estimation logic
- Simulation harness is methodology-agnostic (same harness for all containers)
- All data from prepopulated SQLite — no live API calls

### Must NOT Have (Guardrails)
- NO deployment to macpro-linux (framework only)
- NO live API connections inside containers (prepopulated data only)
- NO production TraderBot code modifications (experiment is self-contained in `experiments/`)
- NO `traderbot calibrate`, `traderbot prob-estimate`, or `AnalysisRegistry` changes (deferred)
- NO decision storage pipeline (Phase 4 from original doc — deferred)
- NO Bayesian learning loop (Phase 3 from original doc — deferred)
- NO modifications to existing `src/traderbot/` code
- NO artificial constraints on LLM synthesis (no token budget, no rate limit)
- AI slop: no over-engineering, no premature abstraction beyond the shared interface

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: NO (experiment is self-contained)
- **Automated tests**: NO unit tests (experiment validates itself via scoring pipeline)
- **Primary verification**: Agent-executed QA scenarios running harness + scoring

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — shared infrastructure):
+-- Task 1: SQLite schema + seed format [quick]
+-- Task 2: MethodologyInterface ABC + estimate() signature [quick]
+-- Task 3: Ticker parser utility [quick]
+-- Task 4: Forecast loader utility [quick]
+-- Task 5: DB utilities [quick]

Wave 2 (After Wave 1 — core orchestration):
+-- Task 6: Simulation harness (depends: 1, 2, 3, 4, 5) [deep]
+-- Task 7: Scoring pipeline (depends: 1, 2) [unspecified-high]

Wave 3 (After Wave 2 — methodology implementations, MAX PARALLEL):
+-- Task 8: Bin calibration (depends: 2, 3, 4, 5) [deep]
+-- Task 9: Logistic regression (depends: 2, 3, 4, 5) [deep]
+-- Task 10: LLM synthesis (depends: 2, 3, 4, 5) [deep]
+-- Task 11: Ensemble (depends: 8, 9, 10) [quick]

Wave 4 (After Wave 3 — packaging + analysis):
+-- Task 12: Docker configs + compose (depends: 6, 11) [unspecified-high]
+-- Task 13: Comparison report generator (depends: 7) [quick]

Wave FINAL (After ALL tasks — 4 parallel reviews):
+-- Task F1: Plan compliance audit (oracle)
+-- Task F2: Code quality review (unspecified-high)
+-- Task F3: Real QA — run harness + scoring end-to-end (unspecified-high)
+-- Task F4: Scope fidelity check (deep)

Critical Path: Task 1 -> Task 6 -> Task 12
Parallel Speedup: ~65% faster than sequential
Max Concurrent: 5 (Wave 1), 4 (Wave 3)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1    | -         | 6, 7   | 1    |
| 2    | -         | 6, 7, 8, 9, 10, 11 | 1    |
| 3    | -         | 6, 8, 9, 10 | 1    |
| 4    | -         | 6, 8, 9, 10 | 1    |
| 5    | -         | 6, 8, 9, 10 | 1    |
| 6    | 1, 2, 3, 4, 5 | 12 | 2    |
| 7    | 1, 2       | 13   | 2    |
| 8    | 2, 3, 4, 5 | 11   | 3    |
| 9    | 2, 3, 4, 5 | 11   | 3    |
| 10   | 2, 3, 4, 5 | 11   | 3    |
| 11   | 8, 9, 10  | 12   | 3    |
| 12   | 6, 11      | -    | 4    |
| 13   | 7          | -    | 4    |

### Agent Dispatch Summary

- **Wave 1**: 5 — T1-T5 all `quick`
- **Wave 2**: 2 — T6 `deep`, T7 `unspecified-high`
- **Wave 3**: 4 — T8 `deep`, T9 `deep`, T10 `deep`, T11 `quick`
- **Wave 4**: 2 — T12 `unspecified-high`, T13 `quick`
- **FINAL**: 4 — F1 `oracle`, F2 `unspecified-high`, F3 `unspecified-high`, F4 `deep`

---

## TODOs

- [x] 1. SQLite Schema Alignment + Seed Format Documentation

  **What to do**:
  - Create `experiments/db/seed_format.md` documenting the actual database schema and data format:
    - **markets** table: ticker (PK), question, city, city_prefix, lat, lon, timezone, resolution_date, close_time, settlement_result (YES/NO/null), actual_value, strike_value, strike_type, market_type, yes_price_dollars, volume, open_interest, event_ticker, series_ticker
    - **forecast_snapshots** table: id (auto), ticker (FK→markets), timestep (1-10), forecast_date, target_date, temp_max_f, temp_min_f, precip_mm, wind_speed_max_kmh, humidity_max_pct, weather_code, source ('synthesized')
    - **market_prices** table: id (auto), ticker (FK), timestep, yes_price (0-1), no_price (0-1), volume, open_interest
    - **settlement_actuals** table: ticker (PK, FK), actual_temp_max_f, actual_temp_min_f, actual_precip_mm, actual_weather_code
    - **calibration_bins** table: id (auto), methodology, bin_label, bin_lower, bin_upper, count (default 0), actual_rate, created_at
    - **agent_decisions** table: id (auto), ticker, timestep, methodology, decision, estimated_prob, confidence, edge_estimate, position_size_cents, reasoning, created_at
    - **methodology_outputs** table: id (auto), ticker, timestep, methodology, estimated_prob, confidence, reasoning_data, created_at
  - Document the actual data characteristics:
    - 25 markets, all `strike_type=band` (e.g., KXHIGHNY-26MAY16-B82.5 means "Will NYC high temp be 82-83°F?")
    - 10 timesteps per market (T-9 through T-0), forecast dates advancing
    - 3 YES settlements, 22 NO settlements (imbalanced — tests calibration under class imbalance)
    - Forecast temps vary across timesteps (real temporal dynamics)
    - Market prices vary across timesteps (enables entry timing analysis)
    - calibration_bins is empty — bin_cal methodology falls back to uniform prior
    - source field in forecast_snapshots is 'synthesized' (not live API data)
  - Note: Schema already exists in `experiments/experiment_data.db` — this task documents it, doesn't create it
  - The `city_prefix` field in markets maps directly to `_KALSHI_WEATHER_CITIES` keys

  **Must NOT do**:
  - NO modifications to the existing database schema (it's already populated)
  - NO modifications to `src/traderbot/` code
  - NO settlement_result or settlement_actuals in agent-facing queries (evaluation-only data)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 6, 7
  - **Blocked By**: None

  **References**:
  - `experiments/experiment_data.db` — Actual populated database (inspect schema with `sqlite3 experiment_data.db ".schema"`)
  - `src/traderbot/news/sources.py:140-173` — `_KALSHI_WEATHER_CITIES` mapping (city_prefix ↔ city)

  **Acceptance Criteria**:

  ```
  Scenario: Seed format doc matches actual database schema
    Tool: Bash
    Steps:
      1. `cat experiments/db/seed_format.md | grep -c "string"`
      2. Verify doc lists all 7 tables: markets, forecast_snapshots, market_prices, settlement_actuals, calibration_bins, agent_decisions, methodology_outputs
      3. Verify doc documents the class imbalance (3 YES, 22 NO)
      4. Verify doc notes that schema already exists in experiment_data.db
    Expected Result: Complete documentation matching actual schema
    Failure Indicators: Missing tables, wrong column types, schema mismatch
    Evidence: .sisyphus/evidence/task-1-seed-format-check.txt
  ```

  **Commit**: YES — `feat(experiments): add seed format documentation for actual database schema`
- [x] 2. MethodologyInterface ABC + estimate() Signature

  **What to do**:
  - Create `experiments/methodologies/base.py` with:
    - `MethodologyInterface` abstract base class defining the `estimate()` contract:
      ```python
      class MethodologyInterface(ABC):
          def __init__(self, db_path: Path):
              self.db = db_utils.get_connection(db_path)
          
          @abstractmethod
          def estimate(self, ticker: str, forecast: dict, timestep: int, prior_decisions: list -> MethodologyResult:
              """Return estimated probability, confidence, and reasoning data."""
              ...
      ```
    - `MethodologyResult` dataclass: `estimated_prob: float`, `confidence: float`, `reasoning: dict`
    - Shared validation: `estimated_prob` clamped to [0.01, 0.99], `confidence` clamped to [0.1, 1.0]
    - `__init__.py` exports `MethodologyInterface`, `MethodologyResult`

  **Must NOT do**:
  - NO methodology-specific logic in the base class
  - NO assumptions about which methodology is running

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 6, 7, 8, 9, 10, 11
  - **Blocked By**: None

  **References**:
  - `src/traderbot/analysis/signals.py:62-66` — `default_weights()` pattern for interface design
  - `src/traderbot/simulation/adaptation.py:53-70` — `BetaParams` dataclass pattern

  **Acceptance Criteria**:

  ```
  Scenario: MethodologyInterface is importable and enforceable
    Tool: Bash
    Steps:
      1. `cd experiments && python -c "from methodologies.base import MethodologyInterface, MethodologyResult"`
      2. Verify MethodologyInterface cannot be instantiated directly
      3. Verify MethodologyResult accepts estimated_prob, confidence, reasoning
      4. Verify validation: estimated_prob=1.5 raises or clamps to [0.01, 0.99]
    Expected Result: Import succeeds, ABC enforced, validation works
    Failure Indicators: Import error, ABC not enforced, no validation
    Evidence: .sisyphus/evidence/task-2-interface.txt
  ```

  **Commit**: YES — `feat(experiments): add MethodologyInterface ABC and method signature`

- [x] 3. Ticker Parser Utility

  **What to do**:
  - Create `experiments/methodologies/ticker_parser.py`:
    - `parse_weather_ticker(ticker: str) -> dict` returning `{city_code, city_name, direction, threshold, close_date, lat, lon}`
    - Handles formats: `KXHIGHNY-26MAY18-T84`, `KXLOWCHI-26JUN01-T32`
    - Direction: `KXHIGH` -> `above`, `KXLOW` -> `below`
    - Maps ticker prefix to city using `_KALSHI_WEATHER_CITIES` data
    - Raises `ValueError` for unparseable tickers

  **Must NOT do**:
  - NO live API calls
  - NO hardcoded assumptions beyond the documented ticker format

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 6, 8, 9, 10
  - **Blocked By**: None

  **References**:
  - `src/traderbot/news/sources.py:140-154` — `_KALSHI_WEATHER_CITIES` mapping (copy data, don't import)
  - Weather ticker format: `KXHIGH{CITY}-{DDMMMYY}-T{THRESHOLD}`, `KXLOW{CITY}-{DDMMMYY}-T{THRESHOLD}`

  **Acceptance Criteria**:

  ```
  Scenario: Ticker parser handles all known city codes
    Tool: Bash
    Steps:
      1. `cd experiments && python -c "from methodologies.ticker_parser import parse_weather_ticker; print(parse_weather_ticker('KXHIGHNY-26MAY18-T84'))"`
      2. Verify output has: city_code="NY", city_name="New York", direction="above", threshold=84.0, close_date parsed
      3. Test KXLOW: `parse_weather_ticker('KXLOWCHI-26JUN01-T32')` -> direction="below"
      4. Test invalid: `parse_weather_ticker('INVALID')` raises ValueError
    Expected Result: Correct parsing of all formats, ValueError on invalid
    Failure Indicators: Wrong direction, missing fields, crash on valid input
    Evidence: .sisyphus/evidence/task-3-ticker-parser.txt
  ```

  **Commit**: YES — `feat(experiments): add ticker parser utility`

- [x] 4. Forecast Loader Utility

  **What to do**:
  - Create `experiments/methodologies/forecast_loader.py`:
    - `load_forecast(db: sqlite3.Connection, ticker: str, timestep: int) -> dict` returning forecast snapshot data
    - `load_all_forecasts(db: sqlite3.Connection, ticker: str) -> list[dict]` returning all 10 timesteps
    - Queries `forecast_snapshots` table in SQLite
    - Returns dict with: `temp_max_f, temp_min_f, humidity_max_pct, precip_mm, wind_speed_max_kmh, weather_code, source, forecast_date`

  **Must NOT do**:
  - NO live API calls — reads from prepopulated SQLite only
  - NO caching or memoization (keep it simple)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 6, 8, 9, 10
  - **Blocked By**: None

  **References**:
  - `experiments/experiment_data.db` — Actual `forecast_snapshots` table (inspect with sqlite3)

  **Acceptance Criteria**:

  ```
  Scenario: Forecast loader reads from SQLite correctly
    Tool: Bash
    Steps:
      1. Create test DB with schema and sample forecast data
      2. `cd experiments && python -c "from methodologies.forecast_loader import load_forecast; print(load_forecast(conn, 'market1', 5))"`
      3. Verify returned dict has all expected fields
      4. `load_all_forecasts(conn, 'market1')` returns list of 10 dicts
    Expected Result: Correct data retrieval from SQLite
    Failure Indicators: Missing fields, wrong timestep, empty results
    Evidence: .sisyphus/evidence/task-4-forecast-loader.txt
  ```

  **Commit**: YES — `feat(experiments): add forecast loader utility`

- [x] 5. DB Utilities

  **What to do**:
  - Create `experiments/methodologies/db_utils.py`:
    - `get_connection(db_path: Path) -> sqlite3.Connection` — opens DB with row factory
    - `get_market(db: sqlite3.Connection, ticker: str) -> dict` — fetches market metadata
    - `get_market_prices(db: sqlite3.Connection, ticker: str, timestep: int) -> dict` — fetches prices at timestep
    - `get_calibration_bins(db: sqlite3.Connection, bin_range: str, city: str, month: int) -> dict` — for bin calibration
    - `record_methodology_output(db: sqlite3.Connection, ticker, timestep, methodology, result: MethodologyResult)` — stores methodology output
    - `record_agent_decision(db: sqlite3.Connection, ticker, timestep, methodology, decision: dict)` — stores agent decision

  **Must NOT do**:
  - NO live API calls
  - NO business logic — pure data access functions

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 6, 8, 9, 10
  - **Blocked By**: None

  **References**:
  - `experiments/experiment_data.db` — Actual table structures (inspect with sqlite3 .schema)
  - `src/traderbot/db/decisions.py` — TraderBot's own DB patterns for reference

  **Acceptance Criteria**:

  ```
  Scenario: DB utilities read and write correctly
    Tool: Bash
    Steps:
      1. Create test DB with schema and sample data
      2. `cd experiments && python -c "from methodologies.db_utils import get_market; print(get_market(conn, 'market1'))"`
      3. `get_calibration_bins(conn, '[-2,0)', 'NY', 5)` returns bin data
      4. `record_methodology_output(conn, ...)` inserts without error
    Expected Result: All functions work against SQLite
    Failure Indicators: Connection errors, missing data, write failures
    Evidence: .sisyphus/evidence/task-5-db-utils.txt
  ```

  **Commit**: YES — `feat(experiments): add DB utilities`

- [ ] 6. Simulation Harness

  **What to do**:
  - Create `experiments/simulation/harness.py`
  - Orchestrates the experiment: loads DB, runs 25 markets x 10 timesteps per methodology
  - At each timestep:
    1. Load forecast snapshot via `forecast_loader`
    2. Load market prices via `db_utils`
    3. Call `methodology.estimate(ticker, forecast, timestep, prior_decisions)` — get probability
    4. Record methodology output via `db_utils.record_methodology_output()`
    5. Construct agent context: methodology output + forecast + prices (NO settlement data)
    6. Record agent decision via `db_utils.record_agent_decision()`
  - After all 10 timesteps: resolve market against `settlement_actuals`
  - Output: JSONL file per methodology with all decisions and outcomes
  - Must be methodology-agnostic: accepts any `MethodologyInterface` subclass

  **Must NOT do**:
  - NO live API calls — all data from prepopulated SQLite
  - NO exposure of settlement_actuals to agent during simulation
  - NO methodology-specific logic

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Tasks 1-5)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 12
  - **Blocked By**: Tasks 1, 2, 3, 4, 5

  **References**:
  - `src/traderbot/simulation/engine.py:91-215` — `BacktestEngine.run()` pattern for event-driven simulation
  - `experiments/methodologies/base.py` — `MethodologyInterface` and `MethodologyResult`
  - `experiments/methodologies/forecast_loader.py` — `load_forecast()`, `load_all_forecasts()`
  - `experiments/methodologies/db_utils.py` — `get_market()`, `record_methodology_output()`, etc.

  **Acceptance Criteria**:

  ```
  Scenario: Harness loads DB and iterates markets/timesteps
    Tool: Bash
    Steps:
      1. Create minimal test DB with 2 markets, 2 timesteps each
      2. Run harness with a mock methodology (returns 0.5 for everything)
      3. Verify output JSONL has 4 records (2 markets x 2 timesteps)
      4. Verify each record has: ticker, timestep, estimated_prob, confidence, action
    Expected Result: Correct number of decision records with all fields
    Failure Indicators: Missing records, wrong timestep count, missing fields
    Evidence: .sisyphus/evidence/task-6-harness-basic.txt

  Scenario: Harness isolates settlement data from agent context
    Tool: Bash
    Steps:
      1. Search harness.py for "settlement_result" or "settlement_actuals" — neither should appear in agent context
      2. Verify settlement data is ONLY accessed after all timesteps complete
      3. Verify agent context does NOT include settlement fields
    Expected Result: Settlement data never appears in agent-facing context
    Failure Indicators: Settlement data in timestep prompt/context
    Evidence: .sisyphus/evidence/task-6-settlement-isolation.txt
  ```

  **Commit**: YES — `feat(experiments): add simulation harness`

- [ ] 7. Scoring Pipeline

  **What to do**:
  - Create `experiments/simulation/scoring.py`
  - Reads JSONL output from harness (one file per methodology)
  - Computes per-methodology and per-market metrics:
    - **Brier Score**: mean of (predicted_prob - actual_outcome)^2
    - **Calibration Curve**: predictions bucketed into deciles, actual win rate vs predicted
    - **Edge Realization Rate**: % of trades where predicted edge materialized
    - **P&L**: cumulative profit/loss at market prices from timestep of trade
    - **Entry Timing Analysis**: P&L by timestep (did early entries outperform late?)
    - **Confidence-Weighted Accuracy**: correlation between confidence and accuracy
  - Output: JSON summary + markdown comparison table
  - Handles edge cases: no decisions, all-same-predictions, confidence extremes

  **Must NOT do**:
  - NO statistical overkill — simple, understandable metrics
  - NO changes to simulation harness

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (only depends on Tasks 1, 2 for type references)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 13
  - **Blocked By**: Tasks 1, 2

  **References**:
  - `src/traderbot/analysis/portfolio.py:41-46` — `calibration_curve()` for predicted vs actual bucketing
  - `src/traderbot/analysis/portfolio.py:27-38` — `win_rate()` pattern

  **Acceptance Criteria**:

  ```
  Scenario: Scoring pipeline produces all metrics from valid JSONL
    Tool: Bash
    Steps:
      1. Create sample JSONL with 10 decisions, 5 correct, various confidence levels
      2. Run scoring pipeline
      3. Verify output includes: brier_score, calibration_buckets, edge_realization_rate, pnl, timing_analysis
      4. Verify Brier score is between 0 and 1
    Expected Result: All core metrics present and numerically valid
    Failure Indicators: Missing metrics, Brier outside 0-1, division by zero
    Evidence: .sisyphus/evidence/task-7-scoring-metrics.txt

  Scenario: Graceful handling of empty input
    Tool: Bash
    Steps:
      1. Run scoring pipeline with empty JSONL
      2. Verify no crash, clear "no decisions" message
    Expected Result: No crash, clear empty result
    Failure Indicators: Unhandled exception
    Evidence: .sisyphus/evidence/task-7-scoring-edge.txt
  ```

  **Commit**: YES — `feat(experiments): add scoring pipeline`

- [ ] 8. Bin Calibration Methodology

  **What to do**:
  - Create `experiments/methodologies/bin_cal.py`
  - Inherits from `MethodologyInterface`
  - Implements `estimate()`:
    1. Parse market ticker via `ticker_parser.parse_weather_ticker()`
    2. Load forecast via `forecast_loader.load_forecast()`
    3. Compute delta = forecast_temp_high - threshold
    4. Bin delta into ranges: [-inf,-8), [-8,-4), [-4,-2), [-2,0), [0,2), [2,4), [4,8), [8,inf)
    5. Look up accuracy from `calibration_bins` via `db_utils.get_calibration_bins()`
    6. If insufficient samples (<10): fall back to uniform prior (0.5)
    7. Return: Beta(alpha,beta).mean as estimated_prob, min(1.0, samples/50) as confidence
    8. reasoning = {bin_range, sample_count, historical_accuracy, prior_type}

  **Must NOT do**:
  - NO live API calls — prepopulated SQLite only
  - NO smoothing or interpolation between bins
  - NO duplicate shared utilities — use ticker_parser, forecast_loader, db_utils

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 9, 10)
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 11
  - **Blocked By**: Tasks 2, 3, 4, 5

  **References**:
  - `src/traderbot/simulation/adaptation.py:53-70` — `BetaParams` class for Beta distribution math
  - `experiments/methodologies/base.py` — `MethodologyInterface`
  - `experiments/methodologies/ticker_parser.py` — `parse_weather_ticker()`
  - `experiments/methodologies/forecast_loader.py` — `load_forecast()`
  - `experiments/methodologies/db_utils.py` — `get_calibration_bins()`

  **Acceptance Criteria**:

  ```
  Scenario: Bin calibration produces valid probabilities across delta ranges
    Tool: Bash
    Steps:
      1. Run bin_cal against test DB with populated calibration_bins
      2. Verify: estimated_prob in [0.01, 0.99], confidence in [0.1, 1.0]
      3. Test edge cases: extreme deltas (-20F, +20F), zero delta
      4. Verify correct bin assignment: delta=+3 -> [2,4) bin
    Expected Result: Valid probabilities, correct bin assignment, no crashes
    Failure Indicators: Prob outside valid range, wrong bin, crash on edge cases
    Evidence: .sisyphus/evidence/task-8-bin-cal.txt

  Scenario: Fallback to uniform prior when insufficient samples
    Tool: Bash
    Steps:
      1. Create test scenario with < 10 samples in a bin
      2. Verify estimated_prob ~ 0.5, confidence is low
    Expected Result: Returns ~0.5 with low confidence when data is sparse
    Failure Indicators: Crash, extreme probability, confidence=1.0 with 0 samples
    Evidence: .sisyphus/evidence/task-8-bin-cal-sparse.txt
  ```

  **Commit**: YES — `feat(experiments): add bin calibration methodology`

- [ ] 9. Logistic Regression Methodology

  **What to do**:
  - Create `experiments/methodologies/logistic_reg.py`
  - Inherits from `MethodologyInterface`
  - Implements `estimate()`:
    1. Parse market ticker via `ticker_parser.parse_weather_ticker()`
    2. Load forecast via `forecast_loader.load_forecast()`
    3. Feature engineering: forecast_delta, forecast_delta_squared, timestep, city_encoded (one-hot), month, forecast_spread
    4. Train sklearn LogisticRegression on historical data from SQLite (or hand-rolled if sklearn unavailable)
    5. Return sigmoid(linear_combination) as estimated_prob
    6. Confidence from model's predict_proba spread
    7. Fallback to (0.5, 0.1) when < 20 training records
    8. reasoning = {coefficients, feature_values, training_samples, training_accuracy}

  **Must NOT do**:
  - NO live API calls
  - NO complex feature engineering beyond listed features
  - NO neural networks
  - NO duplicate shared utilities

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 8, 10)
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 11
  - **Blocked By**: Tasks 2, 3, 4, 5

  **References**:
  - `experiments/methodologies/base.py` — `MethodologyInterface`
  - `experiments/methodologies/ticker_parser.py`, `forecast_loader.py`, `db_utils.py`
  - sklearn.linear_model.LogisticRegression

  **Acceptance Criteria**:

  ```
  Scenario: Logistic regression produces valid probabilities
    Tool: Bash
    Steps:
      1. Run logistic_reg against test DB with >= 20 training records
      2. Verify: estimated_prob in [0.01, 0.99], confidence in [0.1, 1.0]
      3. Verify probabilities vary across different markets
    Expected Result: Valid, varying probabilities
    Failure Indicators: All same prob, crash, prob outside valid range
    Evidence: .sisyphus/evidence/task-9-logistic-reg.txt
  ```

  **Commit**: YES — `feat(experiments): add logistic regression methodology`

- [ ] 10. LLM Synthesis Methodology

  **What to do**:
  - Create `experiments/methodologies/llm_synthesis.py`
  - Inherits from `MethodologyInterface`
  - Implements `estimate()`:
    1. Construct structured prompt with: market question, forecast snapshot, timestep context, prior decisions
    2. Send to Ollama (glm-5.1) via HTTP: `POST http://host.docker.internal:11434/api/generate`
    3. Parse response for: estimated_prob, confidence, reasoning text
    4. Enforce: prob in [0.01, 0.99], confidence in [0.1, 1.0]
    5. Fallback on timeout/parse failure: (0.5, 0.1, {reasoning: "fallback"})
  - NO artificial constraints on token budget or rate limiting — LLM operates naturally

  **Must NOT do**:
  - NO live API calls to Kalshi/Open-Meteo — only Ollama for LLM inference
  - NO multi-turn reasoning — single prompt, single response
  - NO duplicate shared utilities
  - NO token budget or rate limit constraints

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 8, 9)
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 11
  - **Blocked By**: Tasks 2, 3, 4, 5

  **References**:
  - `experiments/methodologies/base.py` — `MethodologyInterface`
  - `experiments/methodologies/ticker_parser.py`, `forecast_loader.py`
  - Ollama API: `http://host.docker.internal:11434/api/generate`

  **Acceptance Criteria**:

  ```
  Scenario: LLM synthesis produces valid probability with reasoning
    Tool: Bash
    Preconditions: Ollama running with glm-5.1 on host
    Steps:
      1. Run llm_synthesis against test DB
      2. Verify: estimated_prob in [0.01, 0.99], confidence in [0.1, 1.0], reasoning non-empty
      3. Verify probabilities vary across different markets
    Expected Result: Valid, varying probabilities with reasoning text
    Failure Indicators: Empty reasoning, same prob for all, prob outside range
    Evidence: .sisyphus/evidence/task-10-llm-synth.txt

  Scenario: Graceful fallback on LLM failure
    Tool: Bash
    Steps:
      1. Mock Ollama to return timeout or invalid response
      2. Verify fallback: estimated_prob=0.5, confidence=0.1, reasoning="fallback"
    Expected Result: Returns (0.5, 0.1, fallback) on failure
    Failure Indicators: Crash, exception propagation, hanging
    Evidence: .sisyphus/evidence/task-10-llm-fallback.txt
  ```

  **Commit**: YES — `feat(experiments): add LLM synthesis methodology`

- [ ] 11. Ensemble Methodology

  **What to do**:
  - Create `experiments/methodologies/ensemble.py`
  - Inherits from `MethodologyInterface`
  - Implements `estimate()` by calling bin_cal, logistic_reg, and llm_synthesis
  - Combines outputs with configurable weights: bin_cal=0.4, logistic_reg=0.4, llm_synthesis=0.2
  - Weighted estimated_prob = sum(weight * prob for each method)
  - Weighted confidence = sum(weight * conf for each method)
  - Fallback: if any method fails, redistribute its weight proportionally
  - reasoning = {individual_results: [{method, prob, confidence, weight}], weights}

  **Must NOT do**:
  - NO dynamic weight adjustment (future evaluation framework)
  - NO calling external services directly — delegate to methodology modules

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Tasks 8, 9, 10)
  - **Parallel Group**: End of Wave 3
  - **Blocks**: Task 12
  - **Blocked By**: Tasks 8, 9, 10

  **References**:
  - `experiments/methodologies/bin_cal.py` — Bin calibration method
  - `experiments/methodologies/logistic_reg.py` — Logistic regression method
  - `experiments/methodologies/llm_synthesis.py` — LLM synthesis method

  **Acceptance Criteria**:

  ```
  Scenario: Ensemble combines three methodologies correctly
    Tool: Bash
    Steps:
      1. Mock bin_cal->0.7, logistic_reg->0.65, llm_synthesis->0.8
      2. Run ensemble with weights 0.4, 0.4, 0.2
      3. Verify: 0.4*0.7 + 0.4*0.65 + 0.2*0.8 = 0.70
    Expected Result: Weighted average matches calculation
    Failure Indicators: Wrong math, crash when one method fails
    Evidence: .sisyphus/evidence/task-11-ensemble.txt

  Scenario: Weight redistribution when one method fails
    Tool: Bash
    Steps:
      1. Mock bin_cal->0.7, logistic_reg->0.65, llm_synthesis->ERROR
      2. Redistribute llm_synthesis's 0.2 weight proportionally
      3. Verify result uses only working methods with redistributed weights
    Expected Result: Graceful degradation with redistributed weights
    Failure Indicators: Crash, zero probability, all methods failing
    Evidence: .sisyphus/evidence/task-11-ensemble-fallback.txt
  ```

  **Commit**: YES — `feat(experiments): add ensemble methodology`

- [ ] 12. Docker Configs + Compose

  **What to do**:
  - Create `experiments/docker/Dockerfile.methodology`:
    - Base: python:3.12-slim
    - Install: sqlite3, httpx (for Ollama), scikit-learn (for logistic_reg)
    - Copy methodologies/, simulation/, db/ into container
    - ENTRYPOINT: `python -m simulation.harness --db /data/experiment.db --methodology $METHODOLOGY`
  - Create `experiments/docker/docker-compose.yml`:
    - 4 services: bin_cal, logistic_reg, llm_synthesis, ensemble
    - Each mounts shared experiment DB read-only
    - Each mounts results directory write-only
    - Sets METHODOLOGY env var per service
    - Network: host mode for LLM container to reach Ollama
  - Create `experiments/docker/run.sh` — convenience script to build and run all containers
  - Framework only — NOT deployed to macpro-linux

  **Must NOT do**:
  - NO deployment to macpro-linux (framework only)
  - NO live API access from containers
  - NO modifications to production Docker or docker-compose configs
  - NO privileged access

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on all methodology implementations)
  - **Parallel Group**: Wave 4
  - **Blocks**: Nothing (final verification depends on this)
  - **Blocked By**: Tasks 6, 11

  **References**:
  - Ollama API: `http://host.docker.internal:11434/api/generate`

  **Acceptance Criteria**:

  ```
  Scenario: Docker builds succeed for all 4 containers
    Tool: Bash
    Steps:
      1. `cd experiments/docker && docker compose build`
      2. Verify all 4 services build without errors
      3. `docker compose run bin_cal python -c "from methodologies.bin_cal import BinCalMethodology"` — no import errors
    Expected Result: All 4 containers build and can import their methodology
    Failure Indicators: Build errors, import errors
    Evidence: .sisyphus/evidence/task-12-docker-build.txt
  ```

  **Commit**: YES — `feat(experiments): add Docker configs and compose`

- [ ] 13. Comparison Report Generator

  **What to do**:
  - Create `experiments/results/compare.py`
  - Reads scoring output from all 4 methodologies
  - Generates markdown comparison table:
    - Per-methodology Brier score, calibration error, edge realization rate, total P&L, avg confidence
    - Per-methodology P&L by timestep (early vs late entry)
    - Per-methodology best/worst markets
  - Statistical significance: paired comparison (bootstrap or paired t-test)
  - Winner declaration: methodology with lowest Brier score AND positive P&L
  - Output: `experiments/results/comparison_report.md`

  **Must NOT do**:
  - NO over-interpretation — present data, let reader draw conclusions
  - NO declaring "best" if differences are not statistically meaningful

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (only depends on Task 7)
  - **Parallel Group**: Wave 4
  - **Blocks**: F3 (real QA)
  - **Blocked By**: Task 7

  **References**:
  - `experiments/simulation/scoring.py` — Scoring pipeline output format

  **Acceptance Criteria**:

  ```
  Scenario: Comparison report generates valid markdown from 4 methodology scores
    Tool: Bash
    Steps:
      1. Create mock scoring outputs for 4 methodologies
      2. Run `python -m results.compare --input-dir mock_scores/`
      3. Verify report has: methodology comparison table, timestep analysis, winner declaration
      4. Verify valid markdown
    Expected Result: Complete markdown report with all 4 methodologies compared
    Failure Indicators: Missing methodology, invalid markdown, crash on mock data
    Evidence: .sisyphus/evidence/task-13-comparison-report.txt
  ```

  **Commit**: YES — `feat(experiments): add comparison report generator`

---

## Final Verification Wave

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists. For each "Must NOT Have": search for forbidden patterns. Check evidence files in `.sisyphus/evidence/`. Compare deliverables against plan.
  Output: `Must Have [6/6] | Must NOT Have [9/9] | Tasks [13/13] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Review all files in `experiments/`. Check for: missing imports, hardcoded paths, Docker build issues. Verify all methodologies implement MethodologyInterface. Verify simulation harness is methodology-agnostic. Verify shared utilities are used (no duplicate ticker parsing or forecast loading).
  Output: `Build [PASS/FAIL] | Interface [PASS/FAIL] | Shared Code [PASS/FAIL] | Docker [PASS/FAIL] | VERDICT`

- [ ] F3. **Real QA** — `unspecified-high`
  Build Docker images. Run simulation for at least 2 markets across all 4 containers. Verify: (1) each methodology returns MethodologyResult, (2) simulation presents 10 timesteps per market, (3) scoring pipeline produces output, (4) containers don't interfere. Save evidence to `.sisyphus/evidence/`.
  Output: `Containers [4/4] | Markets [2/2] | Timesteps [20/20] | Scores [4/4] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  Verify: no modifications to `src/traderbot/`, no live API calls in containers, no deployment to macpro-linux, no production CLI changes. All code in `experiments/`. Methodologies use shared utilities (no duplication). Database is prepopulated static data only.
  Output: `Scope [CLEAN/VIOLATED] | Production Impact [NONE/N files] | Duplication [NONE/N instances] | Deployment [NONE/FOUND] | VERDICT`

---

## Commit Strategy

- **1**: `feat(experiments): add seed format documentation for actual database schema` — experiments/db/
- **2**: `feat(experiments): add MethodologyInterface ABC` — experiments/methodologies/base.py, __init__.py
- **3**: `feat(experiments): add ticker parser utility` — experiments/methodologies/ticker_parser.py
- **4**: `feat(experiments): add forecast loader utility` — experiments/methodologies/forecast_loader.py
- **5**: `feat(experiments): add DB utilities` — experiments/methodologies/db_utils.py
- **6**: `feat(experiments): add simulation harness` — experiments/simulation/
- **7**: `feat(experiments): add scoring pipeline` — experiments/simulation/scoring.py
- **8**: `feat(experiments): add bin calibration methodology` — experiments/methodologies/bin_cal.py
- **9**: `feat(experiments): add logistic regression methodology` — experiments/methodologies/logistic_reg.py
- **10**: `feat(experiments): add LLM synthesis methodology` — experiments/methodologies/llm_synthesis.py
- **11**: `feat(experiments): add ensemble methodology` — experiments/methodologies/ensemble.py
- **12**: `feat(experiments): add Docker configs and compose` — experiments/docker/
- **13**: `feat(experiments): add comparison report generator` — experiments/results/compare.py

---

## Success Criteria

### Verification Commands
```bash
# Verify all shared modules import correctly
cd experiments && python -c "from methodologies.base import MethodologyInterface, MethodologyResult"
cd experiments && python -c "from methodologies.ticker_parser import parse_weather_ticker"
cd experiments && python -c "from methodologies.forecast_loader import load_forecast"
cd experiments && python -c "from methodologies.db_utils import get_connection"

# Verify all methodologies implement the interface
cd experiments && python -c "from methodologies.bin_cal import BinCalMethodology; assert issubclass(BinCalMethodology, MethodologyInterface)"
cd experiments && python -c "from methodologies.logistic_reg import LogisticRegMethodology; assert issubclass(LogisticRegMethodology, MethodologyInterface)"
cd experiments && python -c "from methodologies.llm_synthesis import LLMSynthesisMethodology; assert issubclass(LLMSynthesisMethodology, MethodologyInterface)"
cd experiments && python -c "from methodologies.ensemble import EnsembleMethodology; assert issubclass(EnsembleMethodology, MethodologyInterface)"

# Build Docker images
cd experiments/docker && docker compose build

# Verify no production code changes
git diff main -- src/
# Expected: no output (no changes to production code)
```

### Final Checklist
- [ ] All 4 methodologies implement MethodologyInterface
- [ ] Shared utilities used (no duplicate parsing or loading)
- [ ] Simulation harness is methodology-agnostic
- [ ] Scoring pipeline produces all 6 metrics
- [ ] Comparison report ranks methodologies with statistical significance
- [ ] No modifications to `src/traderbot/` (experiment is self-contained)
- [ ] No deployment to macpro-linux (framework only)
- [ ] Docker containers build successfully (not deployed)
