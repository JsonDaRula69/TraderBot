# V3 Experiment Test Environment

## TL;DR

> **Build a rigorous, treatment-agnostic test environment that simulates real-world Kalshi trading conditions and measures agent performance by delta profit.** The environment accepts up to 3 treatment plug-ins + 1 control (which queries production code directly), uses stratified market sampling (2×3×2 grid), within-subjects design, and produces statistically rigorous output (paired t-tests, effect sizes, CIs). We are NOT designing experimental treatments — we are building the lab.

> **Deliverables**:
> - Real data pipeline (Kalshi API + Open-Meteo Previous Runs → SQLite DB)
> - Treatment-agnostic experiment harness with plug-in architecture (TreatmentInterface)
> - Production-mirroring control treatment (calls `generate_signal()` directly)
> - Treatment spec/instruction sheet for building future treatments
> - Real-time P&L calculation with delta profit
> - Statistical analysis engine (paired comparisons, effect sizes, confidence intervals)
> - Stratified market selector (2×3×2 grid, 24+ markets)
> - Bayesian probability computation module (all 3 strike types)
> - Experiment runner CLI with configurable treatments, replicates, and market pools

> **Estimated Effort**: Large (6-8 focused sessions)
> **Parallel Execution**: YES - 4 waves + Phase 0
> **Critical Path**: Phase 0 → Wave 1 (data + schema) → Wave 2 (core engine) → Wave 3 (integration + CLI) → Wave 4 (verification)

---

## Context

### Original Request
Build a controlled simulation that mirrors real-world Kalshi conditions as closely as possible to test up to 3 treatments against a control group, measuring performance by delta profit.

### Interview Summary
**Key Discussions**:
- V2 implementation has fundamental gaps: empty DB, synthetic data, broken band delta, no within-subjects design, no delta profit, hardcoded treatments, control doesn't mirror production
- User wants the control to query production code directly (`from traderbot.analysis.signals import generate_signal`) — not rebuild it
- User wants a Phase 0 task that creates a treatment spec/instruction sheet for other agents to use
- TreatmentInterface designed: harness provides ALL data via TreatmentContext, each treatment chooses what to include
- All 17 testfuckups.md failures must be addressed
- Folder reorganization: v2/ for archived code, v3/ for new infrastructure, treatments/ for plug-ins

**Research Findings**:
- `generate_signal()` is a pure function (no API calls) that takes `ticker, prices, orderbook, estimated_prob, news_sentiment` and returns `CombinedSignal`. Computes RSI, Bollinger, EMA internally. Can be imported and called with historical data.
- Open-Meteo Previous Runs API is free, no credentials needed
- Kalshi API access exists via TraderBot's existing adapter (`KalshiClient` with RSA-PSS auth, rate limiter)
- `v2_experiment_data.db` is 0 bytes — needs complete data pipeline
- **OrderBook data**: `generate_signal()` needs an `OrderBook` with bid/ask levels for `detect_edge()` and `implied_probability()`. Historical orderbook snapshots may not be available for settled markets. Must store or reconstruct approximate orderbooks.

### Metis Review
**Identified Gaps** (addressed):
- V3 design doc has a CODE BUG: `prob_greater()` function is copy-pasted from `prob_between()` — must fix
- OrderBook reconstruction needed for control treatment — can't call `generate_signal()` without it
- No test coverage exists in `experiments/tests/` — must add
- Technical indicator minimums confirmed: RSI needs 2+ prices (returns 50.0 otherwise), Bollinger/EMA work with any length

---

## Work Objectives

### Core Objective
Build a rigorous, treatment-agnostic simulation test environment for Kalshi weather market trading that:
1. Uses 100% real data (no synthesized forecasts or prices)
2. Accurately simulates what an agent experiences at each timestep
3. Supports within-subjects design (each market tested under all treatment conditions)
4. Measures performance by delta profit (treatment P&L minus control P&L)
5. Produces statistically rigorous output (paired t-tests, confidence intervals, effect sizes)
6. Includes a production-mirroring control that calls real `generate_signal()` code
7. Provides a treatment spec sheet so any agent can build treatments

### Concrete Deliverables
- `experiments/v3/__init__.py` — Package init
- `experiments/v3/db_schema.py` — SQLite schema for real data
- `experiments/v3/data_sources/kalshi_fetcher.py` — Kalshi API data fetcher
- `experiments/v3/data_sources/openmeto_fetcher.py` — Open-Meteo Previous Runs fetcher
- `experiments/v3/data_sources/accuracy_calculator.py` — Per-city per-lead-time accuracy
- `experiments/v3/ticker_parser.py` — All strike types (less/greater/between)
- `experiments/v3/treatment_interface.py` — ABC + dataclasses for treatment plug-ins
- `experiments/v3/probability.py` — Bayesian CDF computation (scipy.stats.norm)
- `experiments/v3/harness.py` — Within-subjects experiment runner
- `experiments/v3/market_selector.py` — Stratified sampling (2×3×2 grid)
- `experiments/v3/scoring.py` — P&L, weighted Brier, delta profit
- `experiments/v3/statistics.py` — Paired t-tests, Cohen's d, CIs
- `experiments/v3/cli.py` — CLI entry point
- `experiments/v3/control.py` — Production-mirroring control treatment
- `experiments/v3/llm_client.py` — LLM call handler with retry/backoff/rate limiting
- `experiments/treatments/` — Directory for treatment plug-ins
- `experiments/docs/treatment_spec.md` — Treatment building instruction sheet
- `experiments/docs/scope_boundaries.md` — Clear delineation between lab scope and treatment scope
- `experiments/tests/` — Test coverage for all modules

### Definition of Done
- [ ] Data pipeline fetches real data from Kalshi API + Open-Meteo Previous Runs
- [ ] Per-city per-lead-time forecast accuracy computed from real settlement data
- [ ] Market selector produces stratified sample from 2×3×2 grid (24+ markets)
- [ ] Harness runs any treatment that implements TreatmentInterface
- [ ] Harness supports within-subjects design (each market under all treatments)
- [ ] Harness supports configurable replication count (default 3)
- [ ] Control treatment calls production `generate_signal()` directly
- [ ] Scoring computes P&L with delta profit as primary metric
- [ ] Scoring computes paired t-tests, Cohen's d, confidence intervals
- [ ] No future peeking in price extraction
- [ ] All three strike types handled correctly
- [ ] `pytest experiments/tests/` passes with >80% coverage
- [ ] Treatment spec sheet exists with clear instructions for building new treatments
- [ ] Folder reorganization complete (v2/ archived, v3/ new, treatments/ separate)

### Must Have
- Real data pipeline (Kalshi API + Open-Meteo Previous Runs)
- TreatmentInterface plug-in architecture with TreatmentContext providing ALL available data
- Production-mirroring control treatment calling real `generate_signal()` code
- Treatment spec/instruction sheet for future treatment builders
- Within-subjects design with randomized order per treatment
- P&L calculation with delta profit as primary metric
- Stratified market selection (2×3×2 grid)
- Statistical analysis (paired t-tests, effect sizes, CIs)
- No future peeking in price extraction
- Support for all three strike types (less, greater, between)
- Configurable replication count (minimum 3 per market per treatment)
- API key management via environment variables (NEVER hardcoded)
- LLM error handling with rate limiting, retry with exponential backoff, graceful degradation

### Must NOT Have (Guardrails)
- No experimental treatment content design (raw_data, structured_prob, calibration_bundle prompts are out of scope)
- No changes to production TraderBot code (experiments/ only, plus importing from src/)
- No hardcoded API keys (use .env)
- No synthesized data (everything from real APIs)
- No sigmoid-based probability (use scipy.stats.norm.cdf)
- No between-subjects design (must be within-subjects)
- No ad-hoc market selection (must be stratified)
- No single-run results (must support replication)
- No AI slop: obvious comments, over-abstraction beyond TreatmentInterface, generic names

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES — pytest is available
- **Automated tests**: YES (TDD)
- **Framework**: pytest with async support

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Data Pipeline**: Use Bash (curl) — Verify API responses, DB population
- **Probability Module**: Use Bash (pytest) — Verify scipy computation against known values
- **Harness**: Use Bash (pytest + dry-run) — Verify treatment plug-in loading, within-subjects randomization
- **Scoring**: Use Bash (pytest) — Verify P&L, Brier, paired t-tests against hand-computed values
- **CLI**: Use Bash (tmux) — Run dry-run, validate output format

---

## Execution Strategy

### Phase 0: Foundation and Spec (sequential, before waves)

```
Phase 0 (Foundation + Spec — sequential prerequisites):
├── Task 0a: Folder reorganization — archive v2, create v3/, treatments/ [quick]
├── Task 0b: Treatment spec/instruction sheet [writing]
├── Task 0c: DB schema + migration module [quick]
└── Task 0d: TreatmentInterface ABC + TreatmentContext dataclasses [deep]
```

### Parallel Execution Waves

```
Wave 1 (Foundation — data and core modules):
├── Task 1: Kalshi data fetcher [deep]
├── Task 2: Open-Meteo forecast fetcher [deep]
├── Task 3: Forecast accuracy calculator [unspecified-high]
├── Task 4: Ticker parser (all strike types) [quick]
└── Task 5: Probability computation module (scipy) [deep]

Wave 2 (Core engine — harness and scoring):
├── Task 6: LLM client with rate limiting and retry [unspecified-high]
├── Task 7: Market selector (stratified sampling) [unspecified-high]
├── Task 8: Production-mirroring control treatment [deep]
├── Task 9: Within-subjects experiment harness [deep]
└── Task 10: P&L and scoring engine [unspecified-high]

Wave 3 (Integration — CLI, stats, spec):
├── Task 11: Statistical analysis module [deep]
├── Task 12: CLI runner [quick]
├── Task 13: End-to-end integration test [deep]
└── Task 14: Documentation and README [writing]

Wave FINAL (Verification):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| 0a | — | 0b, 0c, 0d, all Wave 1+ |
| 0b | 0a, 0d | — |
| 0c | 0a | 1, 2, 3 |
| 0d | 0a | 6, 8, 9 |
| 1 | 0c | 7, 8, 9 |
| 2 | 0c | 3 |
| 3 | 0c, 2 | 5 |
| 4 | 0a | 5 |
| 5 | 3, 4 | 8 |
| 6 | 0d | 9 |
| 7 | 1 | 9 |
| 8 | 1, 5 | 9 |
| 9 | 0d, 6, 7, 8 | 12, 13 |
| 10 | 0c | 11, 13 |
| 11 | 10 | 13 |
| 12 | 9 | 13 |
| 13 | 9, 11, 12 | F1-F4 |
| 14 | 13 | — |

### Agent Dispatch Summary

- **Phase 0**: 4 tasks — 0a `quick`, 0b `writing`, 0c `quick`, 0d `deep`
- **Wave 1**: 5 tasks — 1 `deep`, 2 `deep`, 3 `unspecified-high`, 4 `quick`, 5 `deep`
- **Wave 2**: 5 tasks — 6 `unspecified-high`, 7 `unspecified-high`, 8 `deep`, 9 `deep`, 10 `unspecified-high`
- **Wave 3**: 4 tasks — 11 `deep`, 12 `quick`, 13 `deep`, 14 `writing`
- **Final**: 4 reviews — F1 `oracle`, F2 `unspecified-high`, F3 `unspecified-high`, F4 `deep`

---

## TODOs

### Phase 0: Foundation and Spec

- [x] 0a. Folder Reorganization — Archive V2, Create V3 Structure

  > **STATUS**: PARTIALLY COMPLETE — Folder reorganization executed. Directories created and files moved. Remaining: write `docs/scope_boundaries.md` (delegated to Task 0b scope expansion).

  **What to do**:
  - Create `experiments/v3/` directory with `__init__.py`
  - Create `experiments/v3/data_sources/` directory with `__init__.py`
  - Create `experiments/v3/tests/` directory
  - Create `experiments/treatments/` directory with `__init__.py`
  - Move existing V2 code to `experiments/v2/` (methodologies/, simulation/, compile_data.py, v2_experiment_data.db, docker/, results/)
  - Move documentation to `experiments/docs/` (EXPERIMENT_EVOLUTION.md, V3.md, cold_start_fix.md, testfuckups.md, db/seed_format.md)
  - Ensure all imports still work after reorganization (add `__init__.py` files as needed)
  - Run existing v2 tests (if any) to verify nothing broke
  - Delete `.DS_Store` files

  **Must NOT do**:
  - No modifying V2 code functionality — only moving files
  - No deleting V2 code — it's archived for reference
  - No changes to production TraderBot code in `src/`

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (foundation for everything else)
  - **Parallel Group**: Phase 0
  - **Blocks**: 0b, 0c, 0d, all Wave 1+
  - **Blocked By**: None (can start immediately)

  **References**:
  - `experiments/experiments/` — Current directory structure (V2 code mixed with docs)
  - `.sisyphus/drafts/v3-experiment-evaluation.md` — Folder structure proposal
  - `experiments/docs/testfuckups.md` — Section "Architecture Boundary Violations"

  **Acceptance Criteria**:

  - [ ] `experiments/v3/` directory exists with `__init__.py`
  - [ ] `experiments/v3/data_sources/` directory exists with `__init__.py`
  - [ ] `experiments/v2/` directory contains all archived V2 code
  - [ ] `experiments/treatments/` directory exists with `__init__.py`
  - [ ] `experiments/docs/` contains EXPERIMENT_EVOLUTION.md, V3.md, cold_start_fix.md, testfuckups.md
  - [ ] No `.DS_Store` files in experiments/

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Directory structure verification
    Tool: Bash (ls)
    Preconditions: Reorganization complete
    Steps:
      1. `ls experiments/v3/` — verify __init__.py, data_sources/, tests/ exist
      2. `ls experiments/v2/` — verify methodologies/, simulation/, compile_data.py exist
      3. `ls experiments/treatments/` — verify __init__.py exists
      4. `ls experiments/docs/` — verify EXPERIMENT_EVOLUTION.md, V3.md, testfuckups.md exist
    Expected Result: All directories exist with correct structure
    Failure Indicators: Missing directories or files
    Evidence: .sisyphus/evidence/task-0a-directory-structure.txt
  ```

  **Commit**: YES
  - Message: `chore(v3): reorganize folder structure — archive v2, create v3 and treatments directories`
  - Files: All moved/created files
  - Note: Directory reorganization already executed. Commit the current state.

- [x] 0b. Treatment Spec/Instruction Sheet + Scope Boundaries Document

  **What to do**:
  - Create `experiments/docs/treatment_spec.md`
  - Document the complete TreatmentInterface specification including:
    - `TreatmentInterface` ABC: `name` property, `format_prompt(ctx)` method, `validate_response(response)` method
    - `TreatmentContext` dataclass: all fields with types and descriptions (MarketData, ForecastData, AccuracyData, PriceData, TechnicalData, PriorDecisions)
    - Expected LLM response format: `{"decision": "buy_yes"|"buy_no"|"skip", "estimated_prob": float, "confidence": float, "reasoning": string}`
    - How to create a new treatment: step-by-step guide (create file in `treatments/`, implement TreatmentInterface, point CLI to it)
    - How the harness calls your treatment: order of operations, what data you receive at each timestep
    - How delta profit is computed: treatment P&L minus control P&L per market, aggregated with paired t-tests
  - Include code examples showing a minimal treatment implementation
  - Include the control treatment as a reference implementation (calls production `generate_signal()`)
  - Document the data contract clearly: what TreatmentContext provides, what each field means, where it comes from
  - **Create `experiments/docs/scope_boundaries.md`** — clearly delineate the two concerns:
    - **Testing Lab** (`v3/`): Data pipeline, experiment execution, scoring, statistics, infrastructure. Treatment-agnostic — never imports from `treatments/`, never formats prompts, never decides what data a treatment sees.
    - **Treatment Design** (`treatments/`): Plug-in modules that implement TreatmentInterface. Choose what information to present. Never modify DB schema, scoring, or experiment execution.
    - **The Boundary Rule**: `v3/` code MUST NEVER import from `treatments/` or know treatment names. `treatments/` code MUST NEVER modify infrastructure. The only connection is the `TreatmentInterface` contract.
    - **Why**: V2 violated this boundary — all treatment prompts were hardcoded inside `treatment_harness.py`. Adding a treatment required rewriting the harness. V3 separates them so the lab is stable and treatments are drop-in modules.
    - Document which modules belong in `v3/` vs `treatments/` with a table

  **Must NOT do**:
  - No designing experimental treatment content (raw_data, structured_prob, etc.)
  - No specifying prompt templates for experimental treatments
  - No implementation code — this is a spec document, not executable code

  **Recommended Agent Profile**:
  - **Category**: `writing`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with 0c, 0d after 0a)
  - **Parallel Group**: Phase 0
  - **Blocks**: — (no downstream tasks depend on this document)
  - **Blocked By**: Task 0a (folder structure must exist), Task 0d (TreatmentInterface spec must be defined)

  **References**:
  - `experiments/.sisyphus/drafts/v3-experiment-evaluation.md` — TreatmentInterface spec discussion
  - `experiments/experiments/simulation/treatment_harness.py` — V2 treatment approach (what NOT to do)
  - `src/traderbot/analysis/signals.py` — Production `generate_signal()` signature and behavior

  **Acceptance Criteria**:

  - [ ] `experiments/docs/treatment_spec.md` exists and covers all sections
  - [ ] `experiments/docs/scope_boundaries.md` exists and clearly delineates lab vs treatment scope
  - [ ] TreatmentInterface ABC fully documented with all methods and return types
  - [ ] TreatmentContext dataclass fully documented with all fields and types
  - [ ] Step-by-step guide for creating new treatments
  - [ ] Code example of minimal treatment implementation
  - [ ] Delta profit computation method documented
  - [ ] Data contract (what TreatmentContext provides, where data comes from) documented

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Spec completeness
    Tool: Bash (grep)
    Preconditions: treatment_spec.md exists
    Steps:
      1. Check "TreatmentInterface" section exists
      2. Check "TreatmentContext" section exists
      3. Check "How to create a new treatment" section exists
      4. Check "Delta profit" section exists
      5. Check code example exists
    Expected Result: All 5 sections present in spec
    Failure Indicators: Any section missing
    Evidence: .sisyphus/evidence/task-0b-spec-completeness.txt
  ```

  **Commit**: YES
  - Message: `docs(v3): add treatment spec and scope boundaries documents`
  - Files: `experiments/docs/treatment_spec.md`, `experiments/docs/scope_boundaries.md`

- [x] 0c. DB Schema and Migration Module

  **What to do**:
  - Create `experiments/v3/db_schema.py`
  - Define SQLite schema with tables:
    - `markets`: ticker (PK), city, strike_type, floor_strike, ceiling_strike, threshold, resolution_date, settlement_result, actual_value, event_ticker, series_ticker
    - `forecast_snapshots`: id, ticker (FK), timestep, days_before, forecast_temp_f, source, forecast_date_raw
    - `market_prices`: id, ticker (FK), timestep, yes_price, no_price, trade_count, open_interest, extracted_at
    - `settlement_results`: ticker (PK), actual_temp_f, settlement_result, settlement_source
    - `forecast_accuracy`: id, city, lead_time, mae, bias, sample_count, low_confidence
    - `orderbook_snapshots`: id, ticker (FK), timestep, yes_bids_json, no_bids_json, best_yes_bid, best_no_bid, implied_prob
    - `treatment_decisions`: id, run_id, ticker, timestep, treatment_name, replicate, decision, estimated_prob, confidence, reasoning, position_size_cents
    - `experiment_runs`: run_id (PK), treatment_names_json, num_markets, num_replicates, seed, timestamp, status
  - Write `create_tables(conn)` and `verify_schema(conn)` functions
  - Write tests: create DB in memory, verify all tables exist, verify schema matches spec
  - TDD: write failing tests first, then implement

  **Must NOT do**:
  - No changes to `src/traderbot/` or production code
  - No hardcoded API keys
  - No synthesized data generation (that's the data pipeline, not the schema)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with 0b, 0d after 0a)
  - **Parallel Group**: Phase 0
  - **Blocks**: Tasks 1, 2, 3
  - **Blocked By**: Task 0a

  **References**:
  - `experiments/v2/db/seed_format.md` — V2 schema reference (extend with new tables)
  - `experiments/experiments/methodologies/db_utils.py` — Existing DB utility pattern (connection, row factory)
  - V3.md lines 230-240 — Data sources table

  **Acceptance Criteria**:

  - [ ] Test file created: `experiments/v3/tests/test_db_schema.py`
  - [ ] `pytest experiments/v3/tests/test_db_schema.py` → PASS
  - [ ] All 8 tables defined in schema with correct columns
  - [ ] `orderbook_snapshots` table exists (needed for control treatment)
  - [ ] `create_tables(conn)` creates all tables without error
  - [ ] `verify_schema(conn)` passes after table creation

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Schema creation and verification
    Tool: Bash (pytest)
    Preconditions: Clean temporary directory
    Steps:
      1. Run `python -c "from experiments.v3.db_schema import create_tables, verify_schema; import sqlite3; conn = sqlite3.connect(':memory:'); create_tables(conn); assert verify_schema(conn)"`
      2. Run `pytest experiments/v3/tests/test_db_schema.py -v`
    Expected Result: All 8 tables created, verify_schema returns True, all tests pass
    Failure Indicators: Table creation error, missing columns, verify_schema returns False
    Evidence: .sisyphus/evidence/task-0c-schema-creation.txt
  ```

  **Commit**: YES
  - Message: `feat(v3): add DB schema and migration module`
  - Files: `experiments/v3/__init__.py`, `experiments/v3/db_schema.py`, `experiments/v3/tests/test_db_schema.py`

- [x] 0d. TreatmentInterface ABC + TreatmentContext Dataclasses

  **What to do**:
  - Create `experiments/v3/treatment_interface.py`
  - Define the following dataclasses (frozen=True, as shown in the spec discussion):
    - `MarketData`: ticker, city, strike_type, threshold, floor_strike, ceiling_strike, resolution_date, settlement_result
    - `ForecastData`: forecast_temp_f, source, days_before, timestep
    - `AccuracyData`: city, lead_time, mae, bias, sample_count, low_confidence
    - `PriceData`: yes_price, no_price, trade_count, open_interest, implied_prob
    - `TechnicalData`: rsi, bollinger_position, ema5, ema20, signal_direction, signal_confidence
    - `PriorDecisions`: decisions list of dicts
    - `TreatmentContext`: market, forecast, accuracy, prices, technicals, prior, timestep, remaining
  - Define `TreatmentInterface` ABC with:
    - `name` property (abstract) → str
    - `format_prompt(ctx: TreatmentContext) -> str` (abstract) — formats the prompt for this treatment
    - `validate_response(response: dict) -> bool` (abstract) — validates the LLM agent's JSON response
  - Define `TreatmentResponse` dataclass: decision (Literal["buy_yes", "buy_no", "skip"]), estimated_prob (float), confidence (float), reasoning (str)
  - Write tests: verify ABC enforcement, verify dataclass creation, verify TreatmentContext holds all data
  - **Key architectural decision**: The harness provides ALL data via TreatmentContext. Each treatment chooses what to include in its prompt. This is the opposite of V2 where the harness filtered data per treatment.

  **Must NOT do**:
  - No treatment content (no prompt templates for specific treatments)
  - No over-abstraction — just the minimum interface needed for plug-in

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with 0b, 0c after 0a)
  - **Parallel Group**: Phase 0
  - **Blocks**: Tasks 6, 8, 9
  - **Blocked By**: Task 0a

  **References**:
  - `experiments/experiments/simulation/treatment_harness.py` lines 100-230 — V2 prompt templates (what NOT to do — hardcoded in harness)
  - `src/traderbot/analysis/signals.py` — Production `generate_signal()` signature (reference for control treatment data needs)
  - `src/traderbot/kalshi/models.py` — Market and OrderBook models (reference for data structure)

  **Acceptance Criteria**:

  - [ ] Test file created: `experiments/v3/tests/test_treatment_interface.py`
  - [ ] `pytest experiments/v3/tests/test_treatment_interface.py` → PASS
  - [ ] TreatmentInterface is an ABC with abstract `name`, `format_prompt`, `validate_response`
  - [ ] All 7 dataclasses defined (MarketData, ForecastData, AccuracyData, PriceData, TechnicalData, PriorDecisions, TreatmentContext)
  - [ ] TreatmentContext holds all data a treatment needs
  - [ ] TreatmentResponse validates decision is one of buy_yes/buy_no/skip
  - [ ] Cannot instantiate TreatmentInterface directly (TypeError)

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Interface contract enforcement
    Tool: Bash (pytest)
    Preconditions: TreatmentInterface ABC and dataclasses defined
    Steps:
      1. Try to instantiate TreatmentInterface directly — verify TypeError
      2. Create MockTreatment that implements name, format_prompt, validate_response
      3. Create TreatmentContext with populated dataclasses
      4. Call format_prompt with TreatmentContext — verify str output
      5. Call validate_response with valid JSON dict — verify True
      6. Call validate_response with invalid dict (wrong decision value) — verify False
    Expected Result: ABC enforced, mock treatment works, validation works
    Failure Indicators: ABC not enforced, dataclass creation fails, validation fails
    Evidence: .sisyphus/evidence/task-0d-interface-contract.txt
  ```

  **Commit**: YES
  - Message: `feat(v3): add TreatmentInterface ABC and TreatmentContext dataclasses`
  - Files: `experiments/v3/treatment_interface.py`, `experiments/v3/tests/test_treatment_interface.py`

### Wave 1: Data Pipeline and Core Modules

- [x] 1. Kalshi Data Fetcher

  **What to do**:
  - Create `experiments/v3/data_sources/kalshi_fetcher.py`
  - Use TraderBot's existing Kalshi API adapter (`src/traderbot/kalshi/`) for authentication and API calls — DO NOT reimplement auth
  - Implement `fetch_settled_markets(event_prefix="KXHIGH")` — fetch all settled Kalshi weather high markets
  - Implement `fetch_market_details(ticker)` — get strike_type, floor_strike, ceiling_strike, settlement_result, actual_value
  - Implement `fetch_trade_history(ticker, start_ts, end_ts)` — get individual trades with timestamps for price extraction
  - Implement `fetch_orderbook_snapshot(ticker)` — get orderbook at a point in time for control treatment (best yes/no bids)
  - Implement `extract_prices_at_timestep(trades, timestep_windows)` — extract YES/NO prices at each timestep with NO future peeking (last trade before window end only)
  - Handle all three strike types: less (KXHIGH*-T*), greater (KXHIGH*-T*), between (KXHIGH*-B*)
  - Store results in SQLite via db_schema functions
  - API key from environment variables `KALSHI_API_KEY` and `KALSHI_PRIVATE_KEY_PEM` — NEVER hardcoded
  - Write tests: mock API responses, verify correct parsing, verify no future peeking

  **Must NOT do**:
  - No hardcoded API keys
  - No changes to production Kalshi adapter code
  - No modifying `src/traderbot/kalshi/` — only import and use it

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 2, 4 — all depend on 0c but not each other)
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 7, 8, 9
  - **Blocked By**: Task 0c

  **References**:
  - `src/traderbot/kalshi/markets.py` — Existing Kalshi market fetching code
  - `src/traderbot/kalshi/models.py` — Market, OrderBook, OrderBookLevel models
  - `src/traderbot/kalshi/auth.py` — Authentication handling
  - `src/traderbot/kalshi/history.py` — HistoryService with get_settled_markets(), get_historical_trades()
  - V3.md lines 230-240 — Data sources table

  **Acceptance Criteria**:

  - [ ] Test file created: `experiments/v3/tests/test_kalshi_fetcher.py`
  - [ ] `pytest experiments/v3/tests/test_kalshi_fetcher.py` → PASS
  - [ ] `fetch_settled_markets()` returns correct market data for all strike types
  - [ ] `extract_prices_at_timestep()` never includes trades after timestep window close
  - [ ] `fetch_orderbook_snapshot()` returns OrderBook data for control treatment
  - [ ] API keys loaded from environment variables, not hardcoded

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: No future peeking in price extraction
    Tool: Bash (pytest)
    Preconditions: Mock trade history with trades at T-4, T-3, T-2, T-1, T-0 and one trade AFTER settlement
    Steps:
      1. Create mock trades with timestamps spanning 5 timestep windows plus one post-settlement
      2. Call `extract_prices_at_timestep(mock_trades, timestep_windows)`
      3. Assert each timestep uses ONLY the last trade before that window closes
      4. Assert the post-settlement trade is NEVER included
    Expected Result: Each timestep price from last trade in its window only
    Failure Indicators: Any timestep includes a trade from a later window
    Evidence: .sisyphus/evidence/task-1-no-future-peeking.txt

  Scenario: All strike types parsed correctly
    Tool: Bash (pytest)
    Preconditions: Mock market data for each strike type
    Steps:
      1. Parse "KXHIGHNY-26MAY08-T64" → strike_type=less, threshold=64
      2. Parse "KXHIGHTSEA-26MAY11-T75" → strike_type=greater, threshold=75
      3. Parse "KXHIGHAUS-26APR01-B90.5" → strike_type=between, floor=90, ceiling=91
    Expected Result: All three strike types parsed with correct thresholds
    Failure Indicators: Any strike type misparsed
    Evidence: .sisyphus/evidence/task-1-strike-types.txt
  ```

  **Commit**: YES
  - Message: `feat(v3): add Kalshi data fetcher`
  - Files: `experiments/v3/data_sources/kalshi_fetcher.py`, `experiments/v3/tests/test_kalshi_fetcher.py`

- [x] 2. Open-Meteo Forecast Fetcher

  **What to do**:
  - Create `experiments/v3/data_sources/openmeto_fetcher.py`
  - Use Open-Meteo Previous Runs API (free, no auth) to fetch historical forecasts
  - Implement `fetch_historical_forecast(lat, lon, target_date, lead_days)` — forecast at T-N days before target
  - Implement `fetch_forecast_series(lat, lon, target_date)` — all 5 timesteps (T-4 through T-0) for one market
  - Store forecasts in `forecast_snapshots` table with `source="open-meteo-previous"`
  - Handle rate limiting (courtesy delays between requests)
  - Write tests: mock API responses, verify date arithmetic for lead times

  **Must NOT do**:
  - No use of `compile_data.py`'s synthetic forecast approach
  - No API keys needed (Open-Meteo is free)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 1, 4)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 3
  - **Blocked By**: Task 0c

  **References**:
  - `src/traderbot/news/sources.py` — Existing Open-Meteo integration (current forecasts, not previous runs)
  - V3.md lines 230-240 — "Forecasts at lead times from Open-Meteo Previous Runs API"
  - V3.md lines 296-308 — Accuracy computation pseudocode

  **Acceptance Criteria**:

  - [ ] Test file created: `experiments/v3/tests/test_openmeto_fetcher.py`
  - [ ] `pytest experiments/v3/tests/test_openmeto_fetcher.py` → PASS
  - [ ] `fetch_historical_forecast()` correctly computes target_date - lead_days
  - [ ] `fetch_forecast_series()` returns 5 timesteps (T-4 through T-0)

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Correct lead time calculation
    Tool: Bash (pytest)
    Preconditions: Target date is 2026-05-10
    Steps:
      1. Call `fetch_historical_forecast(30.27, -97.74, "2026-05-10", lead_days=4)`
      2. Verify the API call uses the forecast made on 2026-05-06 for date 2026-05-10
      3. Call `fetch_forecast_series(30.27, -97.74, "2026-05-10")`
      4. Verify 5 results for T-4 (May 6) through T-0 (May 10)
    Expected Result: Date arithmetic correct for all lead times
    Failure Indicators: Wrong date for any lead time
    Evidence: .sisyphus/evidence/task-2-lead-time-calc.txt
  ```

  **Commit**: YES
  - Message: `feat(v3): add Open-Meteo forecast fetcher`
  - Files: `experiments/v3/data_sources/openmeto_fetcher.py`, `experiments/v3/tests/test_openmeto_fetcher.py`

- [x] 3. Forecast Accuracy Calculator

  **What to do**:
  - Create `experiments/v3/data_sources/accuracy_calculator.py`
  - Compute per-city, per-lead-time forecast accuracy from REAL data (not synthesized)
  - Implement `compute_accuracy(conn)` — queries `forecast_snapshots` and `settlement_results`, computes MAE and bias
  - For each city, for each lead_time (T-0 through T-4):
    - `bias = mean(forecast_temp - actual_temp)` across all settled markets for that city
    - `mae = mean(|forecast_temp - actual_temp|)` across all settled markets for that city
    - `sample_count = count(markets)` for that city
  - Store results in `forecast_accuracy` table
  - Flag cities with < 3 samples as low_confidence
  - Write tests: compute accuracy from known forecast+settlement pairs, verify values

  **Must NOT do**:
  - No synthesized bias values (unlike `compile_data.py`'s `CITY_BIAS_F`)
  - No hardcoded accuracy numbers

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Task 2 for forecast data)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 5
  - **Blocked By**: Tasks 0c, 2

  **References**:
  - V3.md lines 37-44 — Accuracy data table showing expected values
  - V3.md lines 296-308 — Accuracy computation pseudocode

  **Acceptance Criteria**:

  - [ ] Test file created: `experiments/v3/tests/test_accuracy_calculator.py`
  - [ ] `pytest experiments/v3/tests/test_accuracy_calculator.py` → PASS
  - [ ] `compute_accuracy()` returns MAE, bias, sample_count per city per lead_time
  - [ ] Values are computed from real settlement results, not hardcoded
  - [ ] Cities with < 3 samples flagged as low_confidence

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Accuracy computation from known data
    Tool: Bash (pytest)
    Preconditions: In-memory DB with 5 Austin markets: forecasts [90.1, 88.5, 91.2, 89.3, 87.8] and settlements [88.8, 87.0, 90.0, 88.5, 87.2]
    Steps:
      1. Call `compute_accuracy(conn)` on the populated DB
      2. Verify Austin MAE = mean(|forecasts - settlements|) ≈ 1.08
      3. Verify Austin bias = mean(forecasts - settlements) ≈ 1.08
      4. Verify sample_count = 5
    Expected Result: MAE and bias match hand-computed values within 0.01°F
    Failure Indicators: Values differ by > 0.01°F from hand computation
    Evidence: .sisyphus/evidence/task-3-accuracy-computation.txt
  ```

  **Commit**: YES
  - Message: `feat(v3): add forecast accuracy calculator`
  - Files: `experiments/v3/data_sources/accuracy_calculator.py`, `experiments/v3/tests/test_accuracy_calculator.py`

- [x] 4. Ticker Parser for All Strike Types

  **What to do**:
  - Create `experiments/v3/ticker_parser.py`
  - Parse Kalshi weather tickers into structured data for ALL three strike types:
    - `KXHIGHAUS-26APR01-B90.5` → `{city: "Austin", strike_type: "between", floor: 90, ceiling: 91, threshold: 90.5}`
    - `KXHIGHTSEA-26MAY07-T66` → `{city: "Seattle", strike_type: "less", threshold: 66}`
    - `KXHIGHTSEA-26MAY11-T75` → `{city: "Seattle", strike_type: "greater", threshold: 75}`
  - Map city prefixes to full names, lat/lon, timezone
  - Handle `KXLOW*` prefix for low-temperature markets too
  - Extract resolution date from ticker string
  - Write tests: parse known tickers, verify all fields

  **Must NOT do**:
  - Don't modify `experiments/v2/methodologies/ticker_parser.py` — create new file in v3/
  - Don't hardcode city data — extend the mapping from existing parser

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 1, 2, 3)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 5
  - **Blocked By**: Task 0a

  **References**:
  - `experiments/v2/methodologies/ticker_parser.py` — Existing parser (extend, don't copy)
  - V3.md lines 244-257 — The 10 specific market tickers to parse correctly

  **Acceptance Criteria**:

  - [ ] Test file created: `experiments/v3/tests/test_ticker_parser_v3.py`
  - [ ] `pytest experiments/v3/tests/test_ticker_parser_v3.py` → PASS
  - [ ] All 10 V3 market tickers parse correctly with correct strike_type, threshold, city

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Parse all V3 market tickers
    Tool: Bash (pytest)
    Preconditions: All 10 V3 ticker strings available
    Steps:
      1. Parse each of the 10 V3 tickers
      2. Verify strike_type matches expected (7 between, 2 less, 1 greater)
      3. Verify city names, thresholds, floors, ceilings are correct
    Expected Result: All 10 tickers parse without error with correct fields
    Failure Indicators: Any ticker misparsed or wrong strike_type
    Evidence: .sisyphus/evidence/task-4-ticker-parsing.txt
  ```

  **Commit**: YES
  - Message: `feat(v3): add ticker parser for all strike types`
  - Files: `experiments/v3/ticker_parser.py`, `experiments/v3/tests/test_ticker_parser_v3.py`

- [x] 5. Bayesian Probability Computation Module

  **What to do**:
  - Create `experiments/v3/probability.py`
  - Implement `prob_less(forecast, threshold, city_bias, city_mae) -> float` — P(actual < threshold)
    - Uses `scipy.stats.norm.cdf(threshold, loc=forecast - city_bias, scale=city_mae)`
  - Implement `prob_greater(forecast, threshold, city_bias, city_mae) -> float` — P(actual > threshold)
    - Uses `1 - norm.cdf(threshold, loc=forecast - city_bias, scale=city_mae)` — **CRITICAL: NOT the prob_between formula**
    - NOTE: V3.md has a BUG where `prob_greater()` uses the `prob_between()` formula. This MUST use `1 - norm.cdf(threshold)`.
  - Implement `prob_between(forecast, floor, city_bias, city_mae) -> float` — P(actual ∈ [floor, floor+1))
    - Uses `norm.cdf(floor + 1, loc=forecast - city_bias, scale=city_mae) - norm.cdf(floor, loc=forecast - city_bias, scale=city_mae)`
  - Implement `compute_ci(prob, city_mae, sample_count) -> tuple[float, float]` — 95% CI
  - Write tests with hand-computed values

  **Must NOT do**:
  - No sigmoid-based probability (the broken V2 approach)
  - No `center - |forecast - center|` delta (the broken V2 approach)
  - Don't reuse `treatment_harness.py`'s `_compute_delta` or `_sigmoid`

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Tasks 3 and 4)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 8
  - **Blocked By**: Tasks 3, 4

  **References**:
  - V3.md lines 183-214 — Probability computation formulas (NOTE: prob_greater has a bug — uses floor param from prob_between)
  - V3.md lines 216-228 — Worked examples with expected values
  - `experiments/v2/simulation/treatment_harness.py` lines 70-85 — `_compute_delta()` (what NOT to do)
  - `experiments/v2/simulation/treatment_harness.py` lines 247-249 — `_sigmoid()` (what NOT to do)

  **Acceptance Criteria**:

  - [ ] Test file created: `experiments/v3/tests/test_probability.py`
  - [ ] `pytest experiments/v3/tests/test_probability.py` → PASS
  - [ ] `prob_less(88.9, 66, 1.3, 1.6)` returns value > 0.99
  - [ ] `prob_between(88.9, 90, 1.3, 1.6)` returns value near 0.092
  - [ ] `prob_greater(90.1, 95, 1.3, 1.6)` returns value near 0.0
  - [ ] `prob_greater` uses `1 - norm.cdf(threshold)`, NOT `norm.cdf(floor+1) - norm.cdf(floor)` (bug fix verification)

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Known probability values (V3.md worked examples)
    Tool: Bash (pytest)
    Preconditions: scipy and numpy installed
    Steps:
      1. prob_less(88.9, 66, 1.3, 1.6) → expect > 0.99 (Austin, less, near-certain)
      2. prob_less(62.3, 64, -0.2, 1.7) → expect ~0.65 (NYC, less, moderate)
      3. prob_between(88.9, 90, 1.3, 1.6) → expect ~0.09 (Austin, band, small prob)
      4. prob_greater(90.1, 95, 1.3, 1.6) → expect near 0.0 (Austin, greater, far above)
      5. prob_between(87.2, 90, 1.3, 2.0) → expect ~0.15 (Austin, T-1 band, larger uncertainty)
    Expected Result: All values match hand-computed scipy.stats.norm results within 0.01
    Failure Indicators: Any value differs from expected by > 0.05
    Evidence: .sisyphus/evidence/task-5-probability-values.txt

  Scenario: V3 bug fix verification (prob_greater uses correct formula)
    Tool: Bash (pytest)
    Preconditions: prob_greater implemented
    Steps:
      1. Call prob_greater(88.5, 95, 1.3, 1.6)
      2. Manually compute: 1 - norm.cdf(95, loc=87.2, scale=1.6) ≈ 0.0001
      3. Verify prob_greater returns approximately 0.0001, NOT the prob_between formula result
    Expected Result: prob_greater uses 1-norm.cdf, NOT norm.cdf(floor+1)-norm.cdf(floor)
    Failure Indicators: prob_greater returns value > 0.5 (wrong formula)
    Evidence: .sisyphus/evidence/task-5-bug-fix-verification.txt
  ```

  **Commit**: YES
  - Message: `feat(v3): add Bayesian probability computation module`
  - Files: `experiments/v3/probability.py`, `experiments/v3/tests/test_probability.py`

### Wave 2: Core Engine — Harness and Scoring

- [x] 6. LLM Client with Rate Limiting and Retry

  **What to do**:
  - Create `experiments/v3/llm_client.py`
  - Implement LLM call handler with:
    - Rate limiting: max 10 calls per minute (token bucket)
    - Retry with exponential backoff: up to 3 retries on 429 (rate limit) and 503 (server error)
    - Configurable timeout per call (default 120s)
    - Malformed JSON recovery: attempt to extract JSON from LLM response, fall back to skip decision if unparseable
    - Graceful degradation: default to "skip" with low confidence on persistent failure, log the failure, continue
  - Use Ollama API (`/api/generate`) with model `glm-5.1:cloud`
  - API key from environment variable `OLLAMA_API_KEY` — NEVER hardcoded
  - Write tests: mock API responses, verify retry logic, verify rate limiting, verify malformed JSON handling

  **Must NOT do**:
  - No hardcoded API keys (unlike V2's `_OLLAMA_API_KEY`)
  - No unbounded retries

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 7, 8 — all depend on 0d but not each other)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 9
  - **Blocked By**: Task 0d

  **References**:
  - `experiments/v2/simulation/treatment_harness.py` lines 312-355 — `_call_ollama()` (reference for API call pattern, but NOT for error handling — V2 has none)

  **Acceptance Criteria**:

  - [ ] Test file created: `experiments/v3/tests/test_llm_client.py`
  - [ ] `pytest experiments/v3/tests/test_llm_client.py` → PASS
  - [ ] Rate limiting enforced (max 10 calls/min)
  - [ ] Retry with backoff on 429 and 503
  - [ ] Malformed JSON returns skip decision with low confidence
  - [ ] API key loaded from environment variable

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Rate limiting
    Tool: Bash (pytest)
    Preconditions: Mock LLM API that responds instantly
    Steps:
      1. Call LLM client 12 times in rapid succession
      2. Verify calls 1-10 complete immediately
      3. Verify calls 11-12 are delayed to stay within 10/min limit
    Expected Result: No more than 10 calls per minute
    Failure Indicators: More than 10 calls in a 60-second window
    Evidence: .sisyphus/evidence/task-6-rate-limiting.txt

  Scenario: Retry with exponential backoff
    Tool: Bash (pytest)
    Preconditions: Mock LLM API that returns 429 twice then 200
    Steps:
      1. Call LLM client
      2. Verify it retries after 429 (first retry after ~1s, second after ~2s)
      3. Verify it returns the successful response after retries
    Expected Result: 429 → wait → 429 → wait → 200 → success
    Failure Indicators: Immediate failure on first 429, or infinite retry
    Evidence: .sisyphus/evidence/task-6-retry-backoff.txt
  ```

  **Commit**: YES
  - Message: `feat(v3): add LLM client with rate limiting and retry`
  - Files: `experiments/v3/llm_client.py`, `experiments/v3/tests/test_llm_client.py`

- [x] 7. Stratified Market Selector

  **What to do**:
  - Create `experiments/v3/market_selector.py`
  - Implement stratified sampling across a 2×3×2 factor grid:
    - **Difficulty**: near-threshold (YES price 0.20-0.80), far-from-threshold (< 0.20 or > 0.80)
    - **Strike_type**: less, greater, between
    - **Lead_time_bucket**: short (T-0/T-1), medium (T-2/T-3), long (T-4+)
  - Target 2 markets per cell → 2×3×2 = 12 strata × 2 = **24 markets minimum**
  - Implement `select_markets(conn, markets_per_cell=2, seed=42)` → returns dict mapping stratum key to list of tickers
  - Implement `compute_stratum(market, prices_at_t0)` → determines stratum
  - Support reproducibility with seed parameter
  - Handle edge cases: some strata may have < 2 markets (rare combos); log and proceed
  - Write tests: verify stratification, verify reproducibility with seed

  **Must NOT do**:
  - No ad-hoc market selection (must be stratified)
  - No fewer than 2 markets per cell (unless insufficient data)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 6, 8)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 9
  - **Blocked By**: Task 1

  **References**:
  - V3.md lines 244-257 — The 10 existing market tickers (reference only — we need 24+)
  - Oracle consultation: "2×3×2 factor grid with 2 markets per cell = 24 markets minimum"

  **Acceptance Criteria**:

  - [ ] Test file created: `experiments/v3/tests/test_market_selector.py`
  - [ ] `pytest experiments/v3/tests/test_market_selector.py` → PASS
  - [ ] `select_markets()` returns at least 24 markets across 12 strata
  - [ ] Same seed produces same market selection (reproducibility)

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Stratification correctness
    Tool: Bash (pytest)
    Preconditions: DB with 50+ settled Kalshi weather markets
    Steps:
      1. Call `select_markets(conn, markets_per_cell=2, seed=42)`
      2. For each selected market, compute its stratum
      3. Verify each stratum has exactly 2 markets (or fewer if insufficient data)
      4. Verify total markets ≥ 24
    Expected Result: All populated strata have 2 markets each
    Failure Indicators: Any stratum empty, or > 2 markets in a stratum
    Evidence: .sisyphus/evidence/task-7-stratification.txt
  ```

  **Commit**: YES
  - Message: `feat(v3): add stratified market selector`
  - Files: `experiments/v3/market_selector.py`, `experiments/v3/tests/test_market_selector.py`

- [x] 8. Production-Mirroring Control Treatment

  **What to do**:
  - Create `experiments/treatments/control.py`
  - Implement `ControlTreatment(TreatmentInterface)` that:
    - `name` property returns `"control"`
    - `format_prompt(ctx: TreatmentContext) -> str` calls production `generate_signal()` with ctx data, then formats the output exactly as `traderbot analyze` + `traderbot signals` would display it
    - `validate_response(response: dict) -> bool` validates decision/estimated_prob/confidence/reasoning
  - Import `from traderbot.analysis.signals import generate_signal` and `from traderbot.kalshi.models import OrderBook, OrderBookLevel`
  - Reconstruct `OrderBook` from `ctx.prices` and `ctx.technicals` (using yes_bids/no_bids from DB orderbook_snapshots)
  - Call `generate_signal(ticker=ctx.market.ticker, prices=[...] , orderbook=reconstructed_orderbook, estimated_prob=ctx.prices.implied_prob)`
  - Format the output to match what `traderbot analyze` + `traderbot signals` displays (market details, technicals, signal direction, confidence)
  - If `generate_signal()` fails or returns None, format a fallback prompt using just market data
  - Write tests: mock generate_signal, verify output matches production format

  **Must NOT do**:
  - No recreating production logic — call the real `generate_signal()` function
  - No weather forecast data or accuracy data in the control prompt — that's what experimental treatments add
  - No changes to production TraderBot code

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 6, 7)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 9
  - **Blocked By**: Tasks 1, 5

  **References**:
  - `src/traderbot/analysis/signals.py` — `generate_signal()` function to import and call
  - `src/traderbot/kalshi/models.py` — `OrderBook` and `OrderBookLevel` models
  - `src/traderbot/analysis/__init__.py` — Exports for signal generation
  - V3.md lines 62-107 — Control treatment description (what data it should include)

  **Acceptance Criteria**:

  - [ ] Test file created: `experiments/v3/tests/test_control_treatment.py`
  - [ ] `pytest experiments/v3/tests/test_control_treatment.py` → PASS
  - [ ] ControlTreatment.name returns "control"
  - [ ] ControlTreatment.format_prompt calls generate_signal with correct parameters
  - [ ] Control prompt includes: market details, technical indicators (RSI, Bollinger, EMA), signal direction, signal confidence
  - [ ] Control prompt does NOT include: forecast data, accuracy data, Bayesian probability
  - [ ] Fallback prompt works when generate_signal fails

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Control prompt mirrors production output
    Tool: Bash (pytest)
    Preconditions: Mock generate_signal returning typical output
    Steps:
      1. Create ControlTreatment instance
      2. Create TreatmentContext with populated MarketData, PriceData, TechnicalData
      3. Call format_prompt(ctx)
      4. Verify prompt contains: market details, RSI, Bollinger position, EMA crossover, signal direction, signal confidence, implied probability
      5. Verify prompt does NOT contain: forecast_temp, city_bias, MAE, Bayesian probability
    Expected Result: Prompt matches production output format, excludes weather data
    Failure Indicators: Missing technical indicators, or presence of forecast/accuracy data
    Evidence: .sisyphus/evidence/task-8-control-prompt.txt

  Scenario: Fallback when generate_signal fails
    Tool: Bash (pytest)
    Preconditions: Mock generate_signal returning None or raising exception
    Steps:
      1. Create ControlTreatment instance
      2. Call format_prompt(ctx) with failing mock
      3. Verify fallback prompt includes market prices and basic data
      4. Verify no crash or error
    Expected Result: Fallback prompt generated, no crash
    Failure Indicators: Exception raised, or empty prompt
    Evidence: .sisyphus/evidence/task-8-control-fallback.txt
  ```

  **Commit**: YES
  - Message: `feat(v3): add production-mirroring control treatment`
  - Files: `experiments/treatments/control.py`, `experiments/treatments/__init__.py`, `experiments/v3/tests/test_control_treatment.py`

- [x] 9. Within-Subjects Experiment Harness

  **What to do**:
  - Create `experiments/v3/harness.py`
  - Implement the core experiment runner that:
    - Accepts a list of TreatmentInterface plug-ins + a control treatment
    - For each market: runs ALL treatments (within-subjects) in randomized order
    - Supports configurable replication (default 3 per market per treatment)
    - Fetches market data, forecast, accuracy, prices from DB for each timestep
    - Calls `treatment.format_prompt(ctx)` to build prompt
    - Sends prompt to LLM via `llm_client.py`
    - Stores decision in `treatment_decisions` table
    - Supports checkpoint/resume (can continue from last saved decision)
  - Implement `_randomize_treatment_order(treatments, market_ticker, seed)` — deterministic per market
  - Implement `_format_prior_decisions(decisions)` — formats previous timestep decisions as text
  - Implement `_build_treatment_context(ticker, timestep, conn)` — assembles TreatmentContext from DB data
  - Write tests: mock LLM responses, verify within-subjects design, verify randomization, verify resume

  **Must NOT do**:
  - No between-subjects design (each market must see ALL treatments)
  - No treatment content (only the plug-in interface)
  - No hardcoded API keys

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Tasks 0d, 6, 7, 8)
  - **Parallel Group**: Wave 2
  - **Blocks**: Tasks 12, 13
  - **Blocked By**: Tasks 0d, 6, 7, 8

  **References**:
  - `experiments/v2/simulation/treatment_harness.py` lines 415-524 — Existing harness (reference for LLM call logic, DO NOT copy)
  - `experiments/v3/treatment_interface.py` (Task 0d) — The plug-in interface
  - `experiments/v3/llm_client.py` (Task 6) — LLM call handler

  **Acceptance Criteria**:

  - [ ] Test file created: `experiments/v3/tests/test_harness.py`
  - [ ] `pytest experiments/v3/tests/test_harness.py` → PASS
  - [ ] Harness accepts TreatmentInterface plug-ins
  - [ ] Within-subjects: each market runs under ALL treatments
  - [ ] Treatment order randomized per market
  - [ ] Replication count configurable
  - [ ] Checkpoint/resume works after interruption

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Within-subjects verification
    Tool: Bash (pytest)
    Preconditions: Mock LLM returning skip, 4 mock treatments, 3 markets, 2 replicates
    Steps:
      1. Run harness with mock LLM and 4 treatments
      2. Verify each market has results for all 4 treatments x 2 replicates
      3. Verify treatment order differs across markets (randomization)
    Expected Result: All markets × treatments × replicates covered
    Failure Indicators: Missing treatment for any market
    Evidence: .sisyphus/evidence/task-9-within-subjects.txt

  Scenario: Checkpoint resume
    Tool: Bash (pytest)
    Preconditions: Harness interrupted after 2 of 5 markets
    Steps:
      1. Start run, simulate interruption after market 2
      2. Resume from checkpoint
      3. Verify markets 3-5 processed, markets 1-2 NOT reprocessed
    Expected Result: Resume continues correctly
    Failure Indicators: Duplicate processing or missing markets
    Evidence: .sisyphus/evidence/task-9-checkpoint-resume.txt
  ```

  **Commit**: YES
  - Message: `feat(v3): add within-subjects experiment harness`
  - Files: `experiments/v3/harness.py`, `experiments/v3/tests/test_harness.py`

- [x] 10. P&L and Scoring Engine

  **What to do**:
  - Create `experiments/v3/scoring.py`
  - Implement P&L calculation with position sizing:
    - buy_yes + settlement=YES: profit = position_size × (1 - yes_price)
    - buy_yes + settlement=NO: loss = position_size × yes_price
    - buy_no + settlement=NO: profit = position_size × yes_price
    - buy_no + settlement=YES: loss = position_size × (1 - yes_price)
    - skip: P&L = 0, position_size = 0
  - Implement delta profit: treatment P&L minus control P&L, per market, per replicate
  - Implement weighted Brier score: 2.0× contested (YES price 0.20-0.80), 0.5× blowout
  - Implement per-group metrics: separate for contested vs blowout, by strike_type, by lead_time
  - Implement skip rate: fraction of "skip" decisions
  - All metrics computed per-replicate, averaged across replicates
  - Write tests with hand-computed P&L values

  **Must NOT do**:
  - No sigmoid probability (treatment content, not scoring)
  - No between-subjects comparison (all within-subjects paired)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 6, 7, 8, 9)
  - **Parallel Group**: Wave 2
  - **Blocks**: Tasks 11, 13
  - **Blocked By**: Task 0c

  **References**:
  - V3.md lines 261-279 — Metrics specification

  **Acceptance Criteria**:

  - [ ] Test file created: `experiments/v3/tests/test_scoring.py`
  - [ ] `pytest experiments/v3/tests/test_scoring.py` → PASS
  - [ ] P&L calculation matches hand-computed values
  - [ ] Delta profit correctly subtracts control P&L from treatment P&L
  - [ ] Weighted Brier applies 2.0× to contested, 0.5× to blowouts
  - [ ] Skip rate computed correctly

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: P&L calculation correctness
    Tool: Bash (pytest)
    Preconditions: Known decisions with expected P&L
    Steps:
      1. buy_yes at yes_price=0.60, settlement=YES: profit = 100 × 0.40 = 40
      2. buy_no at yes_price=0.60, settlement=NO: profit = 100 × 0.60 = 60
      3. skip: P&L = 0
    Expected Result: All P&L values match within 1 cent
    Failure Indicators: Any P&L differs by > 1 cent
    Evidence: .sisyphus/evidence/task-10-pnl-calculation.txt

  Scenario: Delta profit computation
    Tool: Bash (pytest)
    Preconditions: Control P&L = -20, Treatment P&L = +35 on same market
    Steps:
      1. Call compute_delta_profit(control, treatment)
      2. Verify delta = 35 - (-20) = 55 cents
    Expected Result: Delta profit = 55 cents
    Failure Indicators: Wrong sign or magnitude
    Evidence: .sisyphus/evidence/task-10-delta-profit.txt
  ```

  **Commit**: YES
  - Message: `feat(v3): add P&L and scoring engine`
  - Files: `experiments/v3/scoring.py`, `experiments/v3/tests/test_scoring.py`

### Wave 3: Integration — CLI, Statistics, Tests, Docs

- [x] 11. Statistical Analysis Module

  **What to do**:
  - Create `experiments/v3/statistics.py`
  - Implement: `paired_t_test(treatment_pnl, control_pnl)` — paired t-test on per-market delta profit
  - Implement: `cohens_d(treatment_pnl, control_pnl)` — effect size
  - Implement: `confidence_interval(delta_pnl, confidence=0.95)` — 95% CI on mean delta profit
  - Implement: `compare_treatments(results_db, run_id)` — full comparison report between all treatments vs control
  - Implement market-stratified analysis: metrics separately for contested vs blowout, by strike_type, by lead_time
  - Output as JSON-serializable dict
  - Write tests with known data, verify t-test results match scipy

  **Must NOT do**:
  - No visualization (separate concern)
  - No ML models (descriptive statistics only)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 9, 12)
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 13
  - **Blocked By**: Task 10

  **References**:
  - `experiments/v2/results/compare.py` — Existing comparison report format (reference)

  **Acceptance Criteria**:

  - [ ] Test file created: `experiments/v3/tests/test_statistics.py`
  - [ ] `pytest experiments/v3/tests/test_statistics.py` → PASS
  - [ ] `paired_t_test()` returns correct t-statistic and p-value
  - [ ] `cohens_d()` matches hand-computed effect size
  - [ ] `confidence_interval()` matches scipy computation

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Paired t-test verification
    Tool: Bash (pytest)
    Preconditions: Known paired data: treatment P&L = [+10,+5,-3,+8,+2], control P&L = [+2,-1,-5,+1,-3]
    Steps:
      1. Compute delta P&L: [8, 6, 2, 7, 5]
      2. Run paired_t_test(treatment, control)
      3. Verify results match scipy.stats.ttest_rel()
    Expected Result: t-stat ≈ 5.83, p-value ≈ 0.004
    Failure Indicators: Values differ from scipy by > 0.001
    Evidence: .sisyphus/evidence/task-11-paired-ttest.txt
  ```

  **Commit**: YES
  - Message: `feat(v3): add statistical analysis module`
  - Files: `experiments/v3/statistics.py`, `experiments/v3/tests/test_statistics.py`

- [x] 12. CLI Runner

  **What to do**:
  - Create `experiments/v3/cli.py`
  - Implement CLI entry point with argparse:
    - `--db` path to SQLite database (required)
    - `--control` path to control treatment module (required)
    - `--treatments` list of treatment module paths (up to 3)
    - `--markets` number per cell (default 2)
    - `--replicates` number per market per treatment (default 3)
    - `--seed` random seed (default 42)
    - `--model` LLM model (default "glm-5.1:cloud")
    - `--output` results JSON path
    - `--dry-run` validate setup without LLM calls
    - `--verify-data` check DB has sufficient markets
  - Implement `--verify-data` mode: query DB, check market count, verify forecast coverage, verify prices
  - Implement `--dry-run` mode: load treatments, select markets, preview randomization, exit without LLM calls
  - Write tests: verify argparse, verify dry-run mode, verify data validation

  **Must NOT do**:
  - No treatment content in CLI (treatments are plug-ins)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 10, 11)
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 13
  - **Blocked By**: Task 9

  **References**:
  - `experiments/v2/simulation/treatment_harness.py` lines 621-647 — Existing CLI pattern (reference)

  **Acceptance Criteria**:

  - [ ] Test file created: `experiments/v3/tests/test_cli.py`
  - [ ] `pytest experiments/v3/tests/test_cli.py` → PASS
  - [ ] `python -m experiments.v3.cli --help` shows all options
  - [ ] `--dry-run` mode completes without LLM calls

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Dry-run validation
    Tool: Bash (pytest)
    Preconditions: Populated DB with mock data
    Steps:
      1. Run `python -m experiments.v3.cli --db :memory: --dry-run --control experiments.treatments.control`
      2. Verify output shows market selection, treatment order, replicate plan
      3. Verify no LLM calls made
    Expected Result: Dry-run completes with plan output, no errors
    Failure Indicators: LLM call attempted, missing argument error
    Evidence: .sisyphus/evidence/task-12-dry-run.txt
  ```

  **Commit**: YES
  - Message: `feat(v3): add CLI runner`
  - Files: `experiments/v3/cli.py`, `experiments/v3/tests/test_cli.py`

- [x] 13. End-to-End Integration Test

  **What to do**:
  - Create `experiments/v3/tests/test_integration.py`
  - Integration test exercising the full pipeline:
    1. In-memory DB with 3 markets (1 less, 1 greater, 1 between)
    2. Mock forecasts, prices, accuracy, orderbook data
    3. Control treatment (calls real generate_signal with mock data)
    4. 1 mock experimental treatment (returns fixed decisions)
    5. Run harness with mock LLM
    6. Verify decisions stored in DB correctly
    7. Run scoring on results
    8. Run statistical analysis
    9. Verify output contains P&L, Brier, delta profit, t-test
  - Use `unittest.mock.patch` to mock LLM calls, not data pipeline

  **Must NOT do**:
  - No real API calls in tests (all mocked)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Tasks 9, 11, 12)
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 14, Final Verification
  - **Blocked By**: Tasks 9, 11, 12

  **References**:
  - All v3 modules (harness, scoring, statistics, cli)

  **Acceptance Criteria**:

  - [ ] `pytest experiments/v3/tests/test_integration.py -v` → PASS
  - [ ] Full pipeline runs end-to-end with mock data
  - [ ] Decisions stored correctly in DB
  - [ ] Scoring produces P&L, Brier, skip rate
  - [ ] Statistics produces delta profit, t-test, effect size
  - [ ] Within-subjects constraints met

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Full pipeline with mock data
    Tool: Bash (pytest)
    Preconditions: In-memory DB with 3 markets, control + 1 treatment, 2 replicates, mock LLM
    Steps:
      1. Run harness with mock LLM
      2. Verify decisions stored for all markets × treatments × replicates × timesteps
      3. Run scoring and statistics
      4. Verify no future peeking in prices
    Expected Result: All decisions stored, P&L computed, delta profit computed, t-test runs
    Failure Indicators: Missing decisions, NaN results, future peeking detected
    Evidence: .sisyphus/evidence/task-13-integration-test.txt
  ```

  **Commit**: YES
  - Message: `test(v3): add end-to-end integration test`
  - Files: `experiments/v3/tests/test_integration.py`

- [x] 14. Documentation and README

  **What to do**:
  - Create `experiments/v3/README.md`
  - Document: architecture overview, how to add a treatment (reference treatment_spec.md), data pipeline, CLI commands, statistical methodology
  - Update `experiments/docs/EXPERIMENT_EVOLUTION.md` with V3 section

  **Must NOT do**:
  - No experimental treatment content documentation

  **Recommended Agent Profile**:
  - **Category**: `writing`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Task 13)
  - **Parallel Group**: Wave 3
  - **Blocks**: Final Verification
  - **Blocked By**: Task 13

  **References**:
  - `experiments/docs/testfuckups.md` — Lessons learned reference
  - `experiments/docs/treatment_spec.md` (Task 0b) — Treatment spec for cross-reference

  **Acceptance Criteria**:

  - [ ] `experiments/v3/README.md` exists and covers all sections
  - [ ] `experiments/docs/EXPERIMENT_EVOLUTION.md` updated with V3 section

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: README completeness
    Tool: Bash (grep)
    Preconditions: README.md exists
    Steps:
      1. Check "How to add a treatment" section exists
      2. Check "Running an experiment" section exists
      3. Check "Statistical methodology" section exists
    Expected Result: All sections present
    Failure Indicators: Any section missing
    Evidence: .sisyphus/evidence/task-14-readme.txt
  ```

  **Commit**: YES
  - Message: `docs(v3): add experiment documentation`
  - Files: `experiments/v3/README.md`, `experiments/docs/EXPERIMENT_EVOLUTION.md`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [x] F1. **Plan Compliance Audit** — `oracle`** → APPROVE
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`** → APPROVE
  Run `ruff check` + `pytest`. Review all changed files for: type ignores, empty catches, console.log in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names.
  Output: `Build [PASS/FAIL] | Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high`** → APPROVE
  Start from clean state. Execute EVERY QA scenario from EVERY task. Save to `.sisyphus/evidence/final-qa/`. Test edge cases: empty DB, invalid tickers, LLM timeout, malformed JSON response.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`** → APPROVE
  For each task: read "What to do", read actual diff. Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance. Verify no experimental treatment content was designed (only control + interface). Verify folder reorganization happened (v2/ archived, v3/ new, treatments/ separate).
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **0a**: `chore(v3): reorganize folder structure — archive v2, create v3 and treatments directories`
- **0b**: `docs(v3): add treatment spec instruction sheet`
- **0c**: `feat(v3): add DB schema and migration module`
- **0d**: `feat(v3): add TreatmentInterface ABC and TreatmentContext dataclasses`
- **1**: `feat(v3): add Kalshi data fetcher`
- **2**: `feat(v3): add Open-Meteo forecast fetcher`
- **3**: `feat(v3): add forecast accuracy calculator`
- **4**: `feat(v3): add ticker parser for all strike types`
- **5**: `feat(v3): add Bayesian probability computation`
- **6**: `feat(v3): add LLM client with rate limiting and retry`
- **7**: `feat(v3): add stratified market selector`
- **8**: `feat(v3): add production-mirroring control treatment`
- **9**: `feat(v3): add within-subjects experiment harness`
- **10**: `feat(v3): add P&L and scoring engine`
- **11**: `feat(v3): add statistical analysis module`
- **12**: `feat(v3): add CLI runner`
- **13**: `test(v3): add end-to-end integration test`
- **14**: `docs(v3): add experiment documentation`

---

## Success Criteria

### Verification Commands
```bash
cd /Users/djtchill/Documents/Projects/Traderbot/experiments
python -m pytest experiments/tests/ -v          # Expected: all tests pass
python -m experiments.v3.cli --dry-run           # Expected: completes without errors
python -m experiments.v3.cli --verify-data        # Expected: validates DB has 24+ markets
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass
- [ ] Data pipeline fetches real Kalshi + Open-Meteo data
- [ ] Harness runs treatment-agnostic experiments
- [ ] Control treatment calls production `generate_signal()` directly
- [ ] P&L and delta profit computed correctly
- [ ] Statistical analysis produces paired t-tests, effect sizes, CIs
- [ ] Treatment spec sheet exists and is clear enough for another agent to build treatments
- [ ] Folder reorganization complete (v2/ archived, v3/ new, treatments/ separate)