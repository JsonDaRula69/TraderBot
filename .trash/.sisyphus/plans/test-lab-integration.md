# Integrate V3 Test Lab into Production

## TL;DR

> **Quick Summary**: Move the V3 experiment test lab into production packages while strengthening it on three axes: TRUTH (mirror real Kalshi conditions, strict statistics), SPEED (fast AI-agent iteration, JSON output, treatment registry), and LEARNINGS (comprehensive logging of every decision, prompt, response, and scoring outcome). Extend existing modules rather than duplicating. Drop V1 treatments, migrate V2 treatments+methodologies, replace kalshi_fetcher with production services.
> 
> **Deliverables**:
> - `traderbot.experiment` package (treatment, harness, selector, registry, populate, results, logging, treatments/, methodologies/)
> - `traderbot.llm` package (modular LLM client with Ollama-Cloud, multi-key fallback, provider pattern)
> - `traderbot.data_sources` package (openmeto.py)
> - `traderbot.analysis.accuracy` (new), `traderbot.analysis.ticker` (new)
> - Extended `traderbot.analysis.odds` (prob_less/greater/between/compute_ci)
> - Extended `traderbot.simulation.performance` (weighted_brier, delta_profit, skip_rate, pnl)
> - `traderbot.simulation.statistics` (new: t-test, Cohen's d, CIs, power analysis)
> - `traderbot.db.experiment_schema` (9 tables: 8 V3 + decision_audit_log)
> - CLI `experiment` sub-app with JSON output, results scoring, treatment registry
> - Comprehensive experiment logging (prompts, responses, decisions, scoring)
> - Treatment plugin registry (auto-discovery + manual override)
> - Migrated tests (18+ test files → proper locations under tests/)
> - scipy/numpy added to project dependencies
> 
> **Estimated Effort**: Large
> **Parallel Execution**: YES - 5 waves
> **Critical Path**: Scaffolding → LLM module + Treatment ABC → Core modules → Harness + Results + Logging → CLI → Final verification

---

## Context

### Original Request
Integrate V3 test lab into production, extending existing mechanisms rather than duplicating them.

### Interview Summary
**Key Discussions**:
- Original draft had phantom module references (`Market.category_sub` doesn't exist, `implied_probability` in wrong file)
- V1/V2 treatments were entirely missing from draft — V1 dropped, V2 migrated (including methodologies)
- `populate_db.py` (358 lines) was missing from draft
- Test migration (18 files, ~365 methods) was missing from draft
- TickerParser incorrectly classified as "partial overlap" — entirely new
- TreatmentContext ↔ Strategy shape mismatch needed resolution
- Fixed position sizing for experiments vs dynamic production sizing

**Research Findings**:
- Production `Market` model has NO `category_sub`, `strike_type`, `threshold`, `city` fields
- Production `init_schema()` creates only `positions` + `decisions`; `learnings` is separate
- Production CLI uses `app.add_typer()` pattern for auth, cron, profile sub-apps
- V3 CLI uses argparse — must rewrite to Typer sub-app
- V2 treatments already implement V3's `TreatmentInterface` via wrapper pattern
- V2 treatments hardcode `_DB_PATH = Path("experiments/v2/...")` — needs parameterization
- `populate_db.py` uses `KalshiClient` as async HTTP client for market discovery
- `kalshi_fetcher.py` has duplicate `fetch_market_details` with populate_db.py's private version
- scipy/numpy are NOT in pyproject.toml but statistics.py requires them
- Harness has 3 dispatch paths: `format_prompt` (LLM), `direct_decide` (programmatic), `compute_decision` (deterministic)
- Ollama API: `/api/generate` correct endpoint, Ollama-Cloud uses `Authorization: Bearer $OLLAMA_API_KEY`
- V3 CLI never calls `score_run()` or `compare_treatments()` — results not scored!
- No structured logging of LLM prompts/responses in V3

### Metis Review (Round 1)
**Identified Gaps** (addressed):
- scipy/numpy missing from dependencies: Added Task 1 (scaffolding) to add them
- V2 hardcoded DB paths: Added as explicit fix in V2 migration tasks
- populate_db.py uses KalshiClient for market discovery: Kept production services usage
- Duplicate fetch_market_details: Unified in populate.py
- No rollback plan: Guardrail — keep `experiments/v3/` intact until integration verified

### Metis Review (Round 2)
**Critical Gaps** (addressed):
- **Async/Sync boundary**: Production `KalshiClient` is async (`httpx.AsyncClient`). V3 harness is sync. Resolution: `populate.py` is async (wraps `asyncio.run()`), `traderbot.llm` is sync (experiment harness is sync), harness remains sync. CLI entry uses `asyncio.run()` for populate.
- **V2 methodology files not migrated**: V2 treatments import `from experiments.v2.methodologies.*`. Resolution: Migrate V2 methodologies to `traderbot.experiment.methodologies/` as part of Task 13.
- **Experiment DB default path**: When no `--db` provided, default to `~/.traderbot/experiments/experiment.db`.
- **Concurrent experiment runs**: SQLite doesn't handle concurrent writes. Resolution: Add `--run-id` flag (auto-generated UUID). Each run gets unique row in `experiment_runs` table. Lock file during populate.
- **Treatment versioning**: `TreatmentInterface` gets optional `version: str` class attribute. Logged with every run.

### Investigation Round (User-Requested)
**6 deep-dive investigations conducted:**

1. **Ollama API Verified**: `/api/generate` is correct endpoint. Ollama-Cloud uses `Authorization: Bearer $OLLAMA_API_KEY`. Cloud base URL: `https://ollama.com/api`. Error codes: 400, 404, 429, 500, 502, 503. Structured output via `format: "json"`.
2. **Kalshi API Verified**: Production `KalshiClient` has `.get()/.post()/.delete()` via `_request()` with RSA-PSS auth. EventsService, MarketService replace direct API calls. populate.py uses production services.
3. **Agent Role Boundaries**: SysAdmin orchestrates: populate → verify → run → review → PR. V3 loads treatments via importlib string path. No plugin registry existed — now added.
4. **Statistical Rigor Audit**: V3 uses real settlement data (good). CLI never called scoring/stats (now fixed). Weighted Brier accounts for difficulty (good). Power analysis added.
5. **Logging Audit**: Production uses `logging.getLogger`. V3 had no structured logging. Now: ExperimentLogger captures prompts, responses, decisions, scoring.
6. **CLI Agent-Usability Audit**: V3 CLI was not agent-friendly (argparse, no JSON, no scoring). Now: Typer, JSON output, structured results, treatment registry, exit codes.

---

## Work Objectives

### Core Objective
Move the V3 experiment test lab into production packages while strengthening it on three axes:
1. **Truth**: Mirror real Kalshi conditions with strict statistical analysis (real settlement data, proper significance testing, effect sizes, power analysis)
2. **Speed**: Fast, lightweight iteration for AI agents (JSON output, structured results, treatment registry, minimal overhead)
3. **Learnings**: Comprehensive logging of every decision, prompt, response, and scoring outcome for post-hoc analysis

### Concrete Deliverables
- `src/traderbot/experiment/` package (7 modules + treatments/ + methodologies/ sub-packages)
- `src/traderbot/llm/` package (modular LLM client, Ollama-Cloud provider, multi-key fallback)
- `src/traderbot/data_sources/` package (1 module)
- `src/traderbot/analysis/accuracy.py` (new)
- `src/traderbot/analysis/ticker.py` (new)
- Extended `src/traderbot/analysis/odds.py` (4 new functions)
- Extended `src/traderbot/simulation/performance.py` (4 new functions)
- `src/traderbot/simulation/statistics.py` (new + power analysis)
- `src/traderbot/db/experiment_schema.py` (9 tables)
- CLI `experiment` sub-app with JSON output, results scoring, treatment registry
- Comprehensive experiment logging (prompts, responses, decisions, scoring)
- Treatment plugin registry
- Tests migrated to `tests/` directory structure

### Definition of Done
- [ ] `python -m pytest tests/experiment/ tests/analysis/ tests/simulation/test_statistics.py tests/simulation/test_performance.py tests/db/test_experiment_schema.py tests/data_sources/ tests/llm/ -v` → all pass
- [ ] `traderbot experiment --help` shows populate, verify, run, results, list-treatments subcommands
- [ ] `traderbot experiment run --dry-run` validates treatments without LLM calls
- [ ] `traderbot experiment run --treatments control,new_method --output results.json --output-format json` outputs scored JSON results
- [ ] No `import experiments.v3` remains anywhere in `src/`
- [ ] `ruff check src/traderbot/experiment/ src/traderbot/llm/` → clean
- [ ] LLM client works with OLLAMA_API_KEY env var, supports multiple keys as fallbacks
- [ ] Every experiment run produces a complete audit log (prompts, responses, decisions, scores)
- [ ] `traderbot experiment results --run-id X` returns structured JSON with scoring + statistics

### Must Have
- V3 TreatmentInterface ABC and TreatmentContext preserved exactly
- V2 treatments AND methodologies migrated (not just wrappers)
- Production KalshiClient + Services used for market data (async populate.py)
- Modular LLM client (`traderbot.llm`) with Ollama-Cloud, multi-key fallback, provider pattern
- Separate experiment DB (--db flag, default `~/.traderbot/experiments/experiment.db`)
- Fixed position sizing (100 cents) for experiment control
- All 8 V3 experiment tables + decision_audit_log table in experiment_schema.py
- Real Kalshi settlement data for scoring (not hypothetical)
- Comprehensive logging: every prompt, response, decision, scoring result
- JSON output format for AI-agent consumption (`--output-format json`)
- CLI calls scoring + statistics after every run
- Treatment plugin registry (`list-treatments` command)
- Statistical rigor: effect sizes, confidence intervals, power analysis
- `--run-id` for concurrent run isolation

### Must NOT Have (Guardrails)
- Do NOT merge experiment tables into production `init_schema()` — keep separate
- Do NOT add `category_sub` or weather fields to production `Market` model
- Do NOT modify the risk module's hard limits
- Do NOT hardcode DB paths — use --db flag or default `~/.traderbot/experiments/experiment.db`
- Do NOT add OpenClaw-specific dependencies — experiment harness is LLM-agnostic
- Do NOT delete `experiments/v3/` until integration is fully verified (rollback safety)
- Do NOT change V3's TreatmentInterface ABC — migrate as-is (add optional `version` only)
- Do NOT use `float` for monetary values — all in `int` cents
- Do NOT log API keys in any log output (mask like production CLI `_mask_token`)
- Do NOT make LLM client Ollama-only — design as modular provider pattern
- Do NOT skip scoring/statistics in `experiment run` — every run must produce scored results
- Do NOT make populate.py sync — production KalshiClient is async
- Do NOT make LLM module async — experiment harness is sync, LLM calls stay sync
- Do NOT allow concurrent writes to experiment DB without --run-id isolation

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** - ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest under tests/)
- **Automated tests**: Tests-after (migrate existing V3 tests, extend for new locations)
- **Framework**: pytest
- **TDD**: No — V3 already has tests, we're migrating not rewriting

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Library/Module**: Use Bash (pytest) — run tests, assert pass count
- **CLI**: Use Bash — run `traderbot experiment --help`, verify output
- **Import verification**: Use Bash (`python -c "from traderbot.experiment import ..."`) — verify imports work

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately - foundation + scaffolding):
├── Task 1:  Project scaffolding + dependencies [quick]
├── Task 2:  traderbot.db.experiment_schema [quick]
├── Task 3:  traderbot.analysis.accuracy [quick]
├── Task 4:  traderbot.analysis.ticker [quick]
├── Task 5:  traderbot.simulation.statistics + power analysis [quick]
├── Task 6:  traderbot.data_sources.openmeto [quick]
└── Task 7:  Extend traderbot.analysis.odds with prob_* functions [quick]

Wave 2 (After Wave 1 - core modules + LLM, MAX PARALLEL):
├── Task 8:  traderbot.llm — modular LLM client [deep]
├── Task 9:  traderbot.experiment.treatment (ABC + Context) [unspecified-high]
├── Task 10: Extend traderbot.simulation.performance with scoring [unspecified-high]
├── Task 11: Treatment registry + LLM integration [quick]
├── Task 12: Comprehensive experiment logging [deep]
└── Task 13: V2 treatment + methodology migration + control [unspecified-high]

Wave 3 (After Wave 2 - integration layer):
├── Task 14: traderbot.experiment.populate [deep]
├── Task 15: traderbot.experiment.harness [deep]
├── Task 16: traderbot.experiment.results — scoring + stats + JSON [deep]
├── Task 17: CLI experiment Typer sub-app [unspecified-high]
└── Task 18: Test migration [deep]

Wave 4 (After Wave 3 - cleanup + verification):
├── Task 19: Integration verification + cleanup [deep]
└── Task 20: Delete experiments/v3/ + experiments/treatments/ [quick]

Wave FINAL (After ALL tasks — 4 parallel reviews):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
-> Present results -> Get explicit user okay

Critical Path: Task 1 → Task 8 → Task 12 → Task 15 → Task 16 → Task 17 → Task 19 → F1-F4 → user okay
Max Concurrent: 7 (Wave 1)
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| 1 | - | 2-20 |
| 2 | 1 | 14, 15, 18 |
| 3 | 1 | 14, 18 |
| 4 | 1 | 11, 13, 14, 18 |
| 5 | 1 | 18 |
| 6 | 1 | 14, 18 |
| 7 | 1 | 9, 18 |
| 8 | 1 | 12, 15, 17 |
| 9 | 1, 7 | 13, 15 |
| 10 | 1 | 15, 16, 18 |
| 11 | 1, 4, 9 | 15, 17 |
| 12 | 1, 2, 8 | 15, 17 |
| 13 | 1, 4, 9 | 15 |
| 14 | 1, 2, 3, 4, 6 | 17 |
| 15 | 8, 9, 10, 11, 12, 13 | 16, 17, 18 |
| 16 | 10, 15 | 17 |
| 17 | 14, 15, 16 | 19 |
| 18 | 2-12, 15 | 19 |
| 19 | 17, 18 | 20 |
| 20 | 19 | - |

### Agent Dispatch Summary

- **Wave 1**: 7 tasks — T1→`quick`, T2→`quick`, T3→`quick`, T4→`quick`, T5→`quick`, T6→`quick`, T7→`quick`
- **Wave 2**: 6 tasks — T8→`deep`, T9→`unspecified-high`, T10→`unspecified-high`, T11→`quick`, T12→`deep`, T13→`unspecified-high`
- **Wave 3**: 5 tasks — T14→`deep`, T15→`deep`, T16→`deep`, T17→`unspecified-high`, T18→`deep`
- **Wave 4**: 2 tasks — T19→`deep`, T20→`quick`
- **FINAL**: 4 tasks — F1→`oracle`, F2→`unspecified-high`, F3→`unspecified-high`, F4→`deep`

---

## TODOs

- [ ] 1. Project Scaffolding + Dependencies

  **What to do**:
  - Add `scipy` and `numpy` to `pyproject.toml` dependencies (required by `statistics.py`)
  - Create package directories: `src/traderbot/experiment/`, `src/traderbot/experiment/treatments/`, `src/traderbot/experiment/methodologies/`, `src/traderbot/data_sources/`, `src/traderbot/llm/`
  - Add `__init__.py` to each new package with `__all__` exports
  - Create test directories: `tests/experiment/`, `tests/data_sources/`, `tests/analysis/` (if not exist), `tests/llm/`
  - Run `uv sync` to install new dependencies
  - Verify `python -c "import scipy; import numpy"` works

  **Must NOT do**:
  - Do NOT modify existing production dependencies
  - Do NOT add experiment-specific dev dependencies

  **Recommended Agent Profile**: `quick`, Skills: []

  **Parallelization**: Wave 1, Blocks: 2-20, Blocked By: None

  **References**:
  - `src/traderbot/db/__init__.py` — Package init pattern
  - `pyproject.toml:dependencies` — Where to add scipy/numpy

  **Acceptance Criteria**:
  - [ ] `python -c "import scipy; import numpy"` succeeds
  - [ ] All package `__init__.py` files exist
  - [ ] `uv sync` completes without errors

  **QA Scenarios**:
  ```
  Scenario: New packages importable
    Tool: Bash
    Steps:
      1. python -c "from traderbot.experiment import *; from traderbot.data_sources import *; from traderbot.llm import *"
      2. python -c "import scipy; import numpy; print('OK')"
    Expected Result: All commands exit 0
    Evidence: .sisyphus/evidence/task-1-import-check.txt
  ```

  **Commit**: YES — `feat(deps): add scipy/numpy; scaffold experiment, data_sources, llm packages`

- [ ] 2. Experiment Database Schema

  **What to do**:
  - Create `src/traderbot/db/experiment_schema.py` from `experiments/v3/db_schema.py`
  - `init_experiment_schema(conn)` creates 9 tables: `markets`, `forecast_snapshots`, `market_prices`, `settlement_results`, `forecast_accuracy`, `orderbook_snapshots`, `treatment_decisions`, `experiment_runs`, **`decision_audit_log`** (new)
  - `decision_audit_log`: id, run_id, treatment, market, prompt_text, response_text, decision, confidence, estimated_prob, timestamp
  - Port all CRUD helper functions
  - Keep table schemas identical to V3 (plus new audit table)
  - Do NOT call from production `init_schema()`

  **Must NOT do**:
  - Do NOT modify production `init_schema()`
  - Do NOT change V3 table definitions

  **Recommended Agent Profile**: `quick`, Skills: []

  **Parallelization**: Wave 1, Blocks: 14, 15, 18, Blocked By: 1

  **References**:
  - `src/traderbot/db/__init__.py` — DB module pattern
  - `experiments/v3/db_schema.py` — Source: all CREATE TABLE statements, CRUD functions

  **Acceptance Criteria**:
  - [ ] All 9 tables created by `init_experiment_schema()`
  - [ ] Production `init_schema()` NOT modified

  **QA Scenarios**:
  ```
  Scenario: Schema creates all 9 tables including audit log
    Tool: Bash
    Steps:
      1. python -c "import sqlite3; from traderbot.db.experiment_schema import init_experiment_schema; conn = sqlite3.connect(':memory:'); init_experiment_schema(conn); tables = [t[0] for t in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]; print(sorted(tables)); assert 'decision_audit_log' in tables"
    Expected Result: All 9 tables listed
    Evidence: .sisyphus/evidence/task-2-schema-tables.txt
  ```

  **Commit**: YES — `feat(db): add experiment schema with 9 tables`

- [ ] 3. Per-City Forecast Accuracy Module

  **What to do**:
  - Create `src/traderbot/analysis/accuracy.py` from `experiments/v3/data_sources/accuracy_calculator.py`
  - Port `compute_accuracy()` and `save_accuracy()` functions
  - Create test file `tests/analysis/test_accuracy.py`

  **Must NOT do**:
  - Do NOT add to `traderbot.analysis.__init__.__all__` yet (Wave 3 integration)

  **Recommended Agent Profile**: `quick`, Skills: []

  **Parallelization**: Wave 1, Blocks: 14, 18, Blocked By: 1

  **References**: `experiments/v3/data_sources/accuracy_calculator.py`

  **Acceptance Criteria**:
  - [ ] `python -c "from traderbot.analysis.accuracy import compute_accuracy, save_accuracy"` succeeds
  - [ ] `pytest tests/analysis/test_accuracy.py -v` passes

  **Commit**: YES — `feat(analysis): add per-city forecast accuracy module`

- [ ] 4. Kalshi Weather Ticker Parser

  **What to do**:
  - Create `src/traderbot/analysis/ticker.py` from `experiments/v3/ticker_parser.py`
  - Port: `parse_ticker()`, `is_high_temp()`, `ParseError`, `CITY_MAP`, `CITY_COORDS`, `CITY_TIMEZONES`
  - This is ENTIRELY NEW — production `Market` has no weather fields
  - Create test file `tests/analysis/test_ticker.py`

  **Must NOT do**:
  - Do NOT add weather fields to production `Market` model
  - Do NOT reference non-existent `Market.category_sub`

  **Recommended Agent Profile**: `quick`, Skills: []

  **Parallelization**: Wave 1, Blocks: 11, 13, 14, 18, Blocked By: 1

  **References**: `experiments/v3/ticker_parser.py`

  **Acceptance Criteria**:
  - [ ] `python -c "from traderbot.analysis.ticker import parse_ticker, CITY_MAP"` succeeds
  - [ ] `pytest tests/analysis/test_ticker.py -v` passes

  **Commit**: YES — `feat(analysis): add Kalshi weather ticker parser`

- [ ] 5. Statistical Comparison Module + Power Analysis

  **What to do**:
  - Create `src/traderbot/simulation/statistics.py` from `experiments/v3/statistics.py`
  - Port: `compare_treatments()`, `paired_ttest()`, `cohens_d()`, confidence interval functions
  - **Add**: `power_analysis(effect_size, n, alpha=0.05) -> float` — post-hoc power
  - **Add**: `min_sample_size(effect_size, alpha=0.05, power=0.80) -> int` — minimum N
  - Keep scipy.stats imports
  - Create test file `tests/simulation/test_statistics.py`

  **Must NOT do**:
  - Do NOT change statistical computation logic
  - Do NOT add to `traderbot.simulation.__init__` yet

  **Recommended Agent Profile**: `quick`, Skills: []

  **Parallelization**: Wave 1, Blocks: 18, Blocked By: 1

  **References**: `experiments/v3/statistics.py`

  **Acceptance Criteria**:
  - [ ] `python -c "from traderbot.simulation.statistics import compare_treatments, power_analysis, min_sample_size"` succeeds

  **Commit**: YES — `feat(simulation): add statistical comparison module with power analysis`

- [ ] 6. Open-Meteo Forecast Fetcher

  **What to do**:
  - Create `src/traderbot/data_sources/openmeto.py` from `experiments/v3/data_sources/openmeto_fetcher.py`
  - Port: `fetch_forecast_series()`, `save_forecasts()`
  - Create test file `tests/data_sources/test_openmeto.py`

  **Recommended Agent Profile**: `quick`, Skills: []

  **Parallelization**: Wave 1, Blocks: 14, 18, Blocked By: 1

  **References**: `experiments/v3/data_sources/openmeto_fetcher.py`

  **Acceptance Criteria**:
  - [ ] `python -c "from traderbot.data_sources.openmeto import fetch_forecast_series"` succeeds

  **Commit**: YES — `feat(data-sources): add Open-Meteo forecast fetcher`

- [ ] 7. Extend Analysis Odds with Probability Functions

  **What to do**:
  - Add 4 functions to `src/traderbot/analysis/odds.py`:
    - `prob_less(mu, sigma, threshold)`, `prob_greater()`, `prob_between()`, `compute_ci()`
  - Port logic from `experiments/v3/probability.py` (scipy.stats.norm)
  - Update `traderbot.analysis.__init__.py` to re-export
  - Extend tests in `tests/analysis/test_odds.py`
  - Keep existing `implied_probability()` — do NOT modify

  **Must NOT do**:
  - Do NOT modify existing `implied_probability()`
  - Do NOT create new `probability.py` module — extend `odds.py`

  **Recommended Agent Profile**: `quick`, Skills: []

  **Parallelization**: Wave 1, Blocks: 9, 18, Blocked By: 1

  **References**: `src/traderbot/analysis/odds.py`, `experiments/v3/probability.py`

  **Acceptance Criteria**:
  - [ ] `python -c "from traderbot.analysis.odds import prob_less, prob_greater, prob_between, compute_ci"` succeeds
  - [ ] Existing `implied_probability` tests still pass

  **Commit**: YES — `feat(analysis): extend odds module with probability functions`

- [ ] 8. Modular LLM Client (`traderbot.llm`)

  **What to do**:
  - Create `src/traderbot/llm/` package as a **modular, reusable** LLM client
  - `LLMProvider` ABC: `generate(prompt, **kwargs) -> LLMResponse`
  - `OllamaProvider(LLMProvider)`: supports local + Ollama-Cloud
    - Auth: `Authorization: Bearer $OLLAMA_API_KEY` for cloud
    - Base URL env: `OLLAMA_BASE_URL` (default: `https://ollama.com/api` for cloud, `http://localhost:11434` for local)
    - Endpoint: `POST /api/generate` with `model`, `prompt`, `stream: false`, `options`
  - Multi-key fallback: `OLLAMA_API_KEYS` (comma-separated) or `OLLAMA_API_KEY` (single)
    - Try each key on 401/403; rotate on 429
    - When exhausted, queue with `TokenBucket` (10 req/min, burst=10)
  - Error handling: retry 3x on 429/502/503/timeout with exponential backoff
  - Fallback: return structured skip/error response on persistent failure
  - `LLMClient` facade wraps provider + rate limiter + retry + fallback
  - **Never log API keys** — use `_mask_token` pattern
  - Create test file `tests/llm/test_llm_client.py`

  **Must NOT do**:
  - Do NOT make Ollama-only — use provider pattern
  - Do NOT log API keys
  - Do NOT hardcode base URL
  - Do NOT couple to experiment framework

  **Recommended Agent Profile**: `deep`, Skills: []

  **Parallelization**: Wave 2, Blocks: 12, 15, 17, Blocked By: 1

  **References**:
  - `src/traderbot/cli.py:26-28` — `_mask_token()` pattern
  - `src/traderbot/kalshi/client.py` — Production HTTP client pattern
  - `experiments/v3/llm_client.py` — Source: TokenBucket, retry logic
  - Ollama API (verified): `/api/generate`, `Authorization: Bearer`, cloud base URL

  **Acceptance Criteria**:
  - [ ] `python -c "from traderbot.llm import LLMClient, OllamaProvider"` succeeds
  - [ ] API keys never appear in log output
  - [ ] Multi-key fallback works from `OLLAMA_API_KEYS` env var

  **QA Scenarios**:
  ```
  Scenario: Multi-key fallback works
    Tool: Bash
    Steps:
      1. python -c "import os; os.environ['OLLAMA_API_KEYS']='k1,k2,k3'; from traderbot.llm import OllamaProvider; p = OllamaProvider.from_env(model='test'); assert len(p._api_keys) == 3; print('OK')"
    Expected Result: "OK" printed
    Evidence: .sisyphus/evidence/task-8-multi-key.txt
  ```

  **Commit**: YES — `feat(llm): add modular LLM client with Ollama provider and multi-key fallback`

- [ ] 9. TreatmentInterface ABC and Context Models

  **What to do**:
  - Create `src/traderbot/experiment/treatment.py` from `experiments/v3/treatment_interface.py`
  - Port ALL classes/dataclasses: `TreatmentInterface` (ABC), `TreatmentContext`, `TreatmentResponse`, `MarketData`, `ForecastData`, `AccuracyData`, `PriceData`, `TechnicalData`, `PriorDecisions`
  - **Add optional `version: str = ""` class attribute** to TreatmentInterface for run comparability
  - Update `__init__.py` to re-export key symbols
  - Create test file `tests/experiment/test_treatment.py`

  **Must NOT do**:
  - Do NOT change ABC methods — preserve `format_prompt()`, `validate_response()`, optional `direct_decide()`
  - Do NOT add Pydantic models — keep dataclasses
  - Do NOT merge with BacktestEngine.Strategy protocol

  **Recommended Agent Profile**: `unspecified-high`, Skills: []

  **Parallelization**: Wave 2, Blocks: 13, 15, Blocked By: 1, 7

  **References**: `experiments/v3/treatment_interface.py`

  **Acceptance Criteria**:
  - [ ] ABC enforcement works (cannot instantiate directly)
  - [ ] `TreatmentContext` is frozen
  - [ ] `version` attribute exists on TreatmentInterface

  **Commit**: YES — `feat(experiment): add TreatmentInterface ABC and context models`

- [ ] 10. Extend Performance Module with Experiment Scoring

  **What to do**:
  - Add 4 functions to `src/traderbot/simulation/performance.py`:
    - `compute_weighted_brier()`, `compute_delta_profit()`, `compute_skip_rate()`, `compute_pnl()`
  - Port from `experiments/v3/scoring.py`
  - Keep existing functions — do NOT modify
  - Update `traderbot.simulation.__init__.py`
  - Extend tests

  **Must NOT do**:
  - Do NOT modify existing functions
  - Do NOT use float for monetary values — `compute_pnl` returns int cents

  **Recommended Agent Profile**: `unspecified-high`, Skills: []

  **Parallelization**: Wave 2, Blocks: 15, 16, 18, Blocked By: 1

  **References**: `experiments/v3/scoring.py`, `src/traderbot/simulation/performance.py`

  **Acceptance Criteria**:
  - [ ] New functions import correctly
  - [ ] Existing tests still pass

  **Commit**: YES — `feat(simulation): extend performance with experiment scoring`

- [ ] 11. Treatment Plugin Registry + LLM Integration

  **What to do**:
  - Create `src/traderbot/experiment/registry.py`
  - `register_treatment(name, cls)` and `discover_treatments() -> dict[str, type[TreatmentInterface]]`
  - Auto-discover in `traderbot.experiment.treatments` package via `importlib`
  - Support manual override via `--control module.path:ClassName`
  - `list-treatments` CLI subcommand
  - Update harness to use `traderbot.llm.LLMClient`

  **Must NOT do**:
  - Do NOT require code changes to register treatments
  - Do NOT duplicate LLM client logic

  **Recommended Agent Profile**: `quick`, Skills: []

  **Parallelization**: Wave 2, Blocks: 15, 17, Blocked By: 1, 4, 9

  **References**:
  - `src/traderbot/profiles/registry.py` — Registry pattern
  - `experiments/v3/cli.py` — importlib loading pattern

  **Acceptance Criteria**:
  - [ ] `discover_treatments()` returns dict including 'control', 'v2_bin_cal'
  - [ ] `traderbot experiment list-treatments` shows available treatments

  **Commit**: YES — `feat(experiment): add treatment plugin registry`

- [ ] 12. Comprehensive Experiment Logging

  **What to do**:
  - Create `src/traderbot/experiment/logging.py`
  - `ExperimentLogger` captures: config, per-step prompts/responses, decisions, scoring, statistics
  - Output to SQLite (decision_audit_log table) AND JSON file per run
  - JSON: `{timestamp}_{seed}_{model}.json` in `--output-dir` (default: `~/.traderbot/experiment_logs/`)
  - Follows production `logging.getLogger(__name__)` pattern
  - **Never log API keys** — use `_mask_token` pattern

  **Must NOT do**:
  - Do NOT log API keys
  - Do NOT make logging optional — default for all runs

  **Recommended Agent Profile**: `deep`, Skills: []

  **Parallelization**: Wave 2, Blocks: 15, 17, Blocked By: 1, 2, 8

  **References**:
  - `src/traderbot/risk/audit.py` — Audit trail pattern
  - `src/traderbot/cli.py:26-28` — `_mask_token()`
  - `experiments/v3/scoring.py:score_run()` — Scoring results to log

  **Acceptance Criteria**:
  - [ ] Every run produces JSON log file
  - [ ] JSON contains config, decisions, scoring, statistics
  - [ ] API keys never in logs

  **Commit**: YES — `feat(experiment): add comprehensive experiment logging module`

- [ ] 13. V2 Treatment Migration + Control + Methodologies

  **What to do**:
  - Migrate V2 methodologies from `experiments/v2/methodologies/` to `src/traderbot/experiment/methodologies/`:
    - `base.py`, `bin_cal.py`, `logistic_reg.py`, `ensemble.py`, `llm_synthesis.py`, `forecast_loader.py`, `db_utils.py`
  - Migrate V2 treatment wrappers to `src/traderbot/experiment/treatments/`
  - Create `control.py` — ControlTreatment with `direct_decide()` calling `generate_signal()`
  - Fix hardcoded DB paths: parameterize via `--db` flag or `paths.get_db_path()`
  - Add `version: str` class attribute to each treatment
  - Update imports: `experiments.v2.methodologies` → `traderbot.experiment.methodologies`

  **Must NOT do**:
  - Do NOT migrate V1 treatments (no TreatmentInterface)
  - Do NOT remove `direct_decide()` dispatch path
  - Do NOT leave `experiments/v2` imports in migrated code

  **Recommended Agent Profile**: `unspecified-high`, Skills: []

  **Parallelization**: Wave 2, Blocks: 15, Blocked By: 1, 4, 9

  **References**:
  - `experiments/treatments/v2_bin_cal.py` etc. — V2 wrappers
  - `experiments/v2/methodologies/` — V2 methodology files
  - `src/traderbot/analysis/signals.py:generate_signal()` — Production signal for control

  **Acceptance Criteria**:
  - [ ] All V2 treatments import correctly from new paths
  - [ ] No `experiments/v2` imports in migrated code
  - [ ] No hardcoded DB paths

  **Commit**: YES — `feat(experiment): migrate V2 treatments, methodologies, and control`

- [ ] 14. Data Population Pipeline

  **What to do**:
  - Create `src/traderbot/experiment/populate.py` from `experiments/v3/data_sources/populate_db.py`
  - **Must be async** (production KalshiClient uses `httpx.AsyncClient`)
  - Use production `KalshiClient`, `EventsService`, `MarketService`, `HistoryService`
  - CLI entry wraps: `asyncio.run(populate_experiment_db(...))`
  - Add lock file to prevent concurrent populate on same DB
  - Default DB path: `~/.traderbot/experiments/experiment.db`

  **Must NOT do**:
  - Do NOT port `kalshi_fetcher.py` as module
  - Do NOT make sync — production KalshiClient is async
  - Do NOT allow concurrent writes without lock

  **Recommended Agent Profile**: `deep`, Skills: []

  **Parallelization**: Wave 3, Blocks: 17, Blocked By: 1, 2, 3, 4, 6

  **References**:
  - `src/traderbot/kalshi/client.py` — Production async client
  - `experiments/v3/data_sources/populate_db.py` — Source
  - `src/traderbot/kalshi/services.py` — EventsService, MarketService

  **Acceptance Criteria**:
  - [ ] No `from experiments.v3` imports
  - [ ] Uses production KalshiClient + services

  **Commit**: YES — `feat(experiment): add data population pipeline`

- [ ] 15. Within-Subjects Experiment Harness

  **What to do**:
  - Create `src/traderbot/experiment/harness.py` from `experiments/v3/harness.py`
  - Uses `traderbot.llm.LLMClient` (not V3's llm_client)
  - Uses `ExperimentLogger` to log every prompt, response, decision
  - Preserves all 3 dispatch paths: `format_prompt`, `direct_decide`, `compute_decision`
  - Keeps checkpoint and within-subjects design
  - Supports `--run-id` for concurrent isolation

  **Must NOT do**:
  - Do NOT merge with BacktestEngine
  - Do NOT remove dispatch paths

  **Recommended Agent Profile**: `deep`, Skills: []

  **Parallelization**: Wave 3, Blocks: 16, 17, 18, Blocked By: 8, 9, 10, 11, 12, 13

  **References**: `experiments/v3/harness.py`

  **Acceptance Criteria**:
  - [ ] Imports from `traderbot.llm`, not `experiments.v3`
  - [ ] `pytest tests/experiment/test_harness.py -v` passes

  **Commit**: YES — `feat(experiment): add within-subjects harness runner`

- [ ] 16. Results Module — Scoring + Statistics + JSON Output

  **What to do**:
  - Create `src/traderbot/experiment/results.py` — THE module V3 was missing
  - `score_run(db_path, run_id) -> ExperimentResults`:
    1. Load treatment_decisions from DB
    2. Load settlement_results from DB
    3. Call `compute_pnl`, `compute_weighted_brier`, `compute_skip_rate` (performance.py)
    4. Call `compare_treatments` with paired t-test, Cohen's d, CIs (statistics.py)
    5. Call `power_analysis` for observed effect size (statistics.py)
    6. Return structured `ExperimentResults`
  - `ExperimentResults.to_json()` — machine-readable
  - `ExperimentResults.summary()` — human-readable console
  - Improvement indicator: treatment vs control (p-value, effect size, direction)

  **Must NOT do**:
  - Do NOT run experiments without scoring
  - Do NOT use text as default output — JSON is agent-friendly default

  **Recommended Agent Profile**: `deep`, Skills: []

  **Parallelization**: Wave 3, Blocks: 17, 18, Blocked By: 10, 15

  **References**: `experiments/v3/scoring.py:score_run()`, `experiments/v3/statistics.py:compare_treatments()`

  **Acceptance Criteria**:
  - [ ] `ExperimentResults.to_json()` produces valid JSON with all metrics
  - [ ] Results include improvement indicator (p-value, Cohen's d, direction)

  **Commit**: YES — `feat(experiment): add results module with scoring, statistics, and JSON output`

- [ ] 17. CLI Experiment Typer Sub-App

  **What to do**:
  - Create `src/traderbot/experiment/cli.py` as Typer sub-app
  - Subcommands: `populate`, `verify`, `run`, `results`, `list-treatments`
  - **Agent-friendly**: `--output-format json` (default), `--output PATH`, exit codes (0=success, 1=failure, 2=improvement)
  - **`experiment run` automatically calls `score_run()` after harness completes**
  - **`experiment results --run-id X --output-format json` re-generates results from DB**
  - Register: `app.add_typer(experiment_app, name="experiment")`
  - Flags: `--db`, `--control`, `--treatments`, `--replicates`, `--seed`, `--model`, `--output`, `--output-format`, `--dry-run`, `--run-id`
  - Default DB: `~/.traderbot/experiments/experiment.db`

  **Must NOT do**:
  - Do NOT keep argparse — Typer only
  - Do NOT modify existing CLI sub-apps
  - Do NOT output unscored raw decisions

  **Recommended Agent Profile**: `unspecified-high`, Skills: []

  **Parallelization**: Wave 3, Blocks: 19, Blocked By: 14, 15, 16

  **References**:
  - `src/traderbot/cli.py:30-34,62,65` — Typer pattern
  - `experiments/v3/cli.py` — Source (rewrite to Typer)

  **Acceptance Criteria**:
  - [ ] `traderbot experiment --help` shows 5 subcommands
  - [ ] `traderbot experiment run --dry-run` validates
  - [ ] `traderbot experiment run --output-format json` outputs JSON
  - [ ] Existing sub-apps unaffected

  **Commit**: YES — `feat(cli): add experiment Typer sub-app with JSON output and results`

- [ ] 18. Test Migration

  **What to do**:
  - Migrate ALL V3 test files to `tests/` structure (18+ files)
  - Update ALL import paths: `from experiments.v3.*` → `from traderbot.*`
  - Add new tests for: LLM client, results module, registry, logging
  - Delete kalshi_fetcher tests (module replaced by production services)
  - Verify ~365 test methods preserved

  **Must NOT do**:
  - Do NOT change test logic — only import paths
  - Do NOT keep `from experiments.v3` imports

  **Recommended Agent Profile**: `deep`, Skills: []

  **Parallelization**: Wave 3, Blocks: 19, Blocked By: 2-12, 15

  **Acceptance Criteria**:
  - [ ] All migrated tests pass
  - [ ] No `from experiments` imports in `tests/`
  - [ ] ~365 test methods preserved

  **Commit**: YES — `test: migrate V3 tests to production test structure`

- [ ] 19. Integration Verification + Cleanup

  **What to do**:
  - Verify ALL imports work end-to-end
  - Update `__init__.py` files with proper `__all__` re-exports
  - Run full test suite
  - Run `ruff check` on all new files
  - Verify `traderbot experiment --help` and `traderbot experiment run --dry-run`
  - Verify existing CLI sub-apps still work

  **Must NOT do**:
  - Do NOT delete `experiments/v3/` yet (Task 20)

  **Recommended Agent Profile**: `deep`, Skills: []

  **Parallelization**: Wave 4, Blocks: 20, Blocked By: 17, 18

  **Acceptance Criteria**:
  - [ ] Full test suite passes
  - [ ] No V3 imports in `src/`
  - [ ] `traderbot experiment --help` works

  **Commit**: YES — `feat: integration verification and import consolidation`

- [ ] 20. Delete Legacy Experiments Code

  **What to do**:
  - Delete `experiments/v3/` directory (35 files)
  - Delete `experiments/treatments/` directory (11 files)
  - Delete `experiments/v2/methodologies/` directory (migrated to src/)
  - Clean up empty `experiments/` directory
  - Run full test suite to confirm nothing breaks

  **Must NOT do**:
  - Do NOT delete before Task 19 confirms integration works
  - Do NOT delete any `src/traderbot/` files

  **Recommended Agent Profile**: `quick`, Skills: []

  **Parallelization**: Wave 4, Blocks: None, Blocked By: 19

  **Acceptance Criteria**:
  - [ ] `experiments/` directory removed
  - [ ] Full test suite passes
  - [ ] CLI still works

  **Commit**: YES — `chore: remove legacy experiments/v3, treatments, and methodologies`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists. For each "Must NOT Have": search for forbidden patterns. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `ruff check` + `python -m pytest` on all new modules. Review for: `as any`, empty catches, unused imports, excessive comments, generic names.
  Output: `Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  Execute EVERY QA scenario from EVERY task. Test CLI: `traderbot experiment --help`, `populate`, `run --dry-run`, `results`, `list-treatments`. Test JSON output. Verify no V3 imports.
  Output: `Scenarios [N/N pass] | Integration [N/N] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1 — everything in spec built, nothing beyond spec built. Check "Must NOT do" compliance.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

- **1**: `feat(deps): add scipy/numpy; scaffold packages`
- **2**: `feat(db): add experiment schema with 9 tables`
- **3**: `feat(analysis): add per-city forecast accuracy`
- **4**: `feat(analysis): add Kalshi weather ticker parser`
- **5**: `feat(simulation): add statistical comparison with power analysis`
- **6**: `feat(data-sources): add Open-Meteo forecast fetcher`
- **7**: `feat(analysis): extend odds with probability functions`
- **8**: `feat(llm): add modular LLM client with multi-key fallback`
- **9**: `feat(experiment): add TreatmentInterface ABC and context models`
- **10**: `feat(simulation): extend performance with experiment scoring`
- **11**: `feat(experiment): add treatment registry and LLM integration`
- **12**: `feat(experiment): add comprehensive experiment logging`
- **13**: `feat(experiment): migrate V2 treatments, methodologies, and control`
- **14**: `feat(experiment): add data population pipeline`
- **15**: `feat(experiment): add within-subjects harness runner`
- **16**: `feat(experiment): add results module with scoring and JSON output`
- **17**: `feat(cli): add experiment Typer sub-app with JSON output`
- **18**: `test: migrate V3 tests to production test structure`
- **19**: `feat: integration verification and import consolidation`
- **20**: `chore: remove legacy experiments code`

---

## Success Criteria

### Verification Commands
```bash
python -c "from traderbot.experiment import TreatmentInterface, TreatmentContext, TreatmentResponse"  # OK
python -c "from traderbot.experiment.harness import Harness"  # OK
python -c "from traderbot.experiment.selector import select_markets"  # OK
python -c "from traderbot.experiment.registry import discover_treatments"  # OK
python -c "from traderbot.experiment.results import score_run, ExperimentResults"  # OK
python -c "from traderbot.experiment.logging import ExperimentLogger"  # OK
python -c "from traderbot.llm import LLMClient, OllamaProvider"  # OK
python -c "from traderbot.analysis.odds import prob_less, prob_greater, prob_between, compute_ci"  # OK
python -c "from traderbot.analysis.accuracy import compute_accuracy"  # OK
python -c "from traderbot.analysis.ticker import parse_ticker, CITY_MAP"  # OK
python -c "from traderbot.simulation.statistics import compare_treatments, power_analysis"  # OK
python -c "from traderbot.simulation.performance import compute_weighted_brier, compute_delta_profit"  # OK
python -c "from traderbot.db.experiment_schema import init_experiment_schema"  # OK
python -c "from traderbot.data_sources.openmeto import fetch_forecast_series"  # OK
traderbot experiment --help  # Shows populate, verify, run, results, list-treatments
traderbot experiment run --dry-run  # Validates without errors
traderbot experiment list-treatments  # Shows available treatments
python -m pytest tests/experiment/ tests/analysis/ tests/simulation/test_statistics.py tests/db/test_experiment_schema.py tests/data_sources/ tests/llm/ -v  # All pass
ruff check src/traderbot/experiment/ src/traderbot/llm/ src/traderbot/data_sources/  # Clean
grep -r "from experiments" src/traderbot/  # Zero matches
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass
- [ ] No `import experiments.v3` in src/
- [ ] CLI `experiment` sub-app functional
- [ ] LLM client multi-key fallback works
- [ ] JSON output format works
- [ ] Comprehensive logging produces audit trail
- [ ] Treatment registry discovers treatments