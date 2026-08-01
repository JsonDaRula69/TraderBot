
## 2026-05-24 — Treatment Plugin Registry (T11)

- Created `src/traderbot/experiment/registry.py`:
  - `register_treatment(name, cls)` — validates subclass of `TreatmentInterface`
  - `discover_treatments(package)` — auto-discovers via `pkgutil.iter_modules` + `inspect.getmembers`
  - `get_treatment(name) -> type | None` — simple dict lookup
  - `list_treatments() -> list[str]` — sorted keys from `_REGISTRY`
  - Internal `_REGISTRY` is a plain dict (mirrors `profiles/registry.py` pattern)
- Created `src/traderbot/experiment/llm_integration.py`:
  - `LLMIntegration.create_client()` wraps `traderbot.llm.LLMClient` with `OllamaProvider`
  - API keys read from `OLLAMA_API_KEY` or `OLLAMA_API_KEYS` (handled by `OllamaProvider`)
- Updated `src/traderbot/experiment/__init__.py` to export all public symbols.
- Created `tests/experiment/test_registry.py` with 6 tests:
  - `discover_treatments()` returns `{}` when package is empty
  - `register_treatment` + `get_treatment` round-trip
  - `list_treatments` returns sorted names
  - `get_treatment("missing")` returns `None`
  - Registration rejects non-class and non-subclass inputs (TypeError)
- All tests pass (6/6).

## 2026-05-24 — Results Module (T16)

- Created `src/traderbot/experiment/results.py`:
  - `ExperimentResults` dataclass: treatment_name, pnl, weighted_brier, skip_rate, p_value, cohens_d, conf_interval, power, improvement (bool), sample_size, mean_pnl, direction
  - `score_run(db_path, run_id)`: loads decisions + settlements from DB, aligns by observation (ticker, timestep, replicate), calls `compare_treatments` + `power_analysis` from `traderbot.simulation.statistics`, returns list of ExperimentResults (control first)
  - `format_results(results, output_format="json")` — JSON is the default (agent-friendly); "human" for console
  - `ExperimentResults.to_json() -> dict` — all metrics + improvement indicator
  - `ExperimentResults.summary() -> str` — human-readable console output
  - `compute_pnl`, `compute_weighted_brier`, `compute_skip_rate` — experiment-specific scoring functions (operate on DB decision dicts, not BacktestTrade objects from simulation/performance.py)
  - Improvement: p < 0.05 AND Cohen's d > 0 AND positive mean_delta → direction="better"
  - All monetary values in int cents
- Key design decisions:
  - Scoring functions are defined inline in results.py because `performance.py` operates on `BacktestTrade` objects (simulation-specific), not experiment DB rows. Importing from performance.py would require adapting trades to BacktestTrade, adding unnecessary coupling.
  - Observations are aligned by (ticker, timestep, replicate) so all treatments have equal-length paired PnL lists (missing/skipped = 0 PnL). This ensures `scipy.stats.ttest_rel` comparisons are valid.
  - `position_size_cents` is used as the stake: +size on correct, -size on wrong, 0 on skip.
  - Brier is position-weighted by `|position_size_cents|`, rewarding larger correct bets more.
- Updated `__init__.py` to export `ExperimentResults`, `score_run`, `format_results`.
- Created `tests/experiment/test_results.py` with 47 tests covering:
  - ExperimentResults JSON/summary output
  - Decision direction normalization
  - Individual PnL computation (correct/wrong/skip/missing settlement)
  - Total PnL aggregation
  - Weighted Brier (perfect, worst, weighted, empty, skip-only)
  - Skip rate
  - score_run integration (DB fixture, PnL verification, improvement flag, error cases)
  - format_results (json default, timestamp, run_id, human format)
  - Edge cases: unknown run, empty decisions, invalid format

## 2026-05-24 — Data Population Pipeline (T14)

- Created `src/traderbot/experiment/populate.py` ported from V3's `experiments/v3/data_sources/populate_db.py` and `kalshi_fetcher.py`
- Key porting decisions:
  - **Replaced `from experiments.v3.*` imports** with production `traderbot.*` modules:
    - `traderbot.analysis.ticker.parse_ticker` instead of local V3 helpers
    - `traderbot.analysis.accuracy.compute_accuracy, save_accuracy`
    - `traderbot.data_sources.openmeteo.fetch_forecast_series, save_forecasts`
    - `traderbot.db.experiment_schema.init_experiment_schema`
    - `traderbot.paths.get_data_dir` for default path
  - **Kept `KalshiClient.get()` for event/market discovery** as required (not DataLoader-replaceable)
  - **Ported `_discover_markets()`, `_fetch_market_detail()`** using raw `client.get()` since they need low-level status code handling (404 detection)
  - **Ported `_fetch_trade_history()`** to use production `HistoryService.get_historical_trades()` directly
  - **Inlined all kalshi_fetcher.py helpers** rather than importing/porting that module
- **Lock file mechanism**: `{db_path}.lock` — checked on entry, created during run, cleaned up via finally block
- **Public API**:
  - `async def populate_experiment_db(db_path, max_markets) -> int` — async core
  - `def populate_cmd(db_path, max_markets, verbose) -> int` — sync wrapper via `asyncio.run()`
  - `def verify_data(db_path)` — database inspection
  - `def main()` — CLI entry with argparse
- **Default DB path**: `~/.traderbot/experiments/experiment.db` via `get_data_dir() / "experiments" / "experiment.db"`
- Removed unnecessary docstrings from private functions; kept only one-liners on public API matching existing production style
- Original V3 files preserved in `experiments/` for rollback safety
