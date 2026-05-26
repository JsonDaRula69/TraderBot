
## Experiment Infrastructure QA Learnings (2026-05-26)

### Module Import Path
- Use `PYTHONPATH=src` for all Python commands in `/Users/djtchill/Documents/Projects/Traderbot/main/`
- Python executable: `.venv/bin/python` (system python3 not in PATH)

### SQLite Internal Tables
- SQLite AUTOINCREMENT creates a `sqlite_sequence` internal table
- When counting user tables, filter with `name NOT LIKE 'sqlite_%'` to avoid false positives
- The 5 application tables are: markets, forecast_snapshots, market_prices, settlement_actuals, agent_decisions

### Harness Market Selection
- `select_markets` requires at least `markets_per_cell` (default=2) markets per (prefix, bucket) combination
- With only 1 market per bucket, `select_markets` returns `{}` (empty dict)
- This is by design for statistical validity (need pairs for paired t-test)

### Mock LLM Pattern for Testing
- `ControlTreatment.bypass_llm=True` → no LLM call needed, uses `_control_decision`
- `CalibrationBundleTreatment.bypass_llm=False` → requires working `LLMClient`
- Mock provider: `class MockProvider: def generate(self, prompt): return json.dumps({...})`
- Failing provider: `class FailProvider: def generate(self, prompt): raise ConnectionError('timeout')`
- Harness catches per-treatment failures via `except Exception` in `_run_ticker`

### Running Tests
- `PYTHONPATH=src uv run pytest src/traderbot/experiment/tests/ -v` works
- Requires `uv` (not `pip`) for dependency management
