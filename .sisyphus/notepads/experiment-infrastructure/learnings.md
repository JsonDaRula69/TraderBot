# Learnings - Experiment Infrastructure Tests

## Test Suite Created: 2026-05-26

### Key Patterns
- `score_run()` requires a file-path DB (opens its own connection internally), so in-memory tests need `tempfile.NamedTemporaryFile`
- `LLMClient` takes a `provider` kwarg with a `.generate(prompt) -> str` method — easy to mock with `unittest.mock.MagicMock`
- Registry module uses a module-level `_registry` dict that needs `.clear()` between tests to avoid cross-contamination
- `Harness.run()` gracefully handles empty DB (no markets selected via `select_markets`) — returns without error, records 0 decisions
- `_control_decision()` is a module-level function, not a method — testable directly without a Harness instance

### Module Import Paths
- Schema: `traderbot.db.experiment_schema.create_tables`
- Shared: `traderbot.experiment.shared` (TreatmentContext, ValidatedDecision, TreatmentInterface, etc.)
- Registry: `traderbot.experiment.registry` (discover_treatments, register_treatment, get_treatment, list_treatments)
- Harness: `traderbot.experiment.harness.Harness`
- Results: `traderbot.experiment.results.ExperimentResults`, `score_run`
- Treatments: `traderbot.experiment.treatments.control.ControlTreatment`, `traderbot.experiment.treatments.calibration_bundle.CalibrationBundleTreatment`
- LLM Client: `traderbot.llm.client.LLMClient`
### CalibrationBundleTreatment Implementation: 2026-05-26
- `CalibrationBundleTreatment` created at `src/traderbot/experiment/treatments/calibration_bundle.py`
- `TREATMENT_REGISTRY` in `treatments/__init__.py` is a `list[type]` (not a dict) — holds treatment classes, not instances
- `TreatmentContext` dataclasses have optional fields (e.g., `brier_score: float | None`, `rsi: float | None`) — format_prompt must handle None gracefully with "N/A" fallback
- `format_prompt` returns a full structured string prompt with sections: MARKET PARAMETERS, FORECAST DATA, ACCURACY METRICS, CURRENT PRICES, TECHNICAL INDICATORS, PRIOR DECISIONS, SYSTEM CONTEXT, ANALYSIS INSTRUCTIONS
- `validate_response` checks types and ranges explicitly before constructing `ValidatedDecision` — the dataclass `__post_init__` also validates but we validate first for clear error messages
- Ruff W292 (no newline at EOF) is enforced — always end files with trailing newline

## Experiment Infrastructure Code Quality (2026-05-26)

### Architecture Patterns
- Clean separation: `shared.py` (frozen dataclasses + ABC) → treatments (implement interface) → registry (discovers) → harness (orchestrates)
- `results.py` implements own paired t-test + incomplete beta function (no scipy hard dep, scipy optional fallback)
- `populate.py` separates async I/O via `asyncio.run()` wrapper
- `client.py` uses `Protocol` + `runtime_checkable` for duck-typed provider interface
- `experiment_schema.py` uses idempotent `CREATE TABLE IF NOT EXISTS` with FK constraints

### Testing Patterns
- Tests use in-memory SQLite (`:memory:`) with `create_tables()` for fast setup
- `test_harness.py` includes architecture boundary test (AST parse to verify no treatment impl imports)
- `test_results.py` uses temp file for score_run since it opens its own connection
- Mock LLMClient via `MagicMock` provider for harness tests

### Quality Standards Met
- All frozen dataclasses prevent accidental mutation
- `ValidatedDecision.__post_init__` enforces invariants at construction
- `TreatmentInterface` ABC prevents incomplete implementations
- Registry validates subclass relationship at discovery time
