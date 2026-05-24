

### 2026-05-24 — Legacy Experiments Cleanup (T20)
- Deleted `experiments/v3/` directory (entire V3 source tree, fully migrated to `src/traderbot/`)
- Deleted `experiments/treatments/` directory (V2 treatment wrappers, fully migrated)
- Deleted `experiments/v2/methodologies/` directory (8 methodology files, fully migrated)
- Verified `grep -r "from experiments" src/ tests/` returned zero matches — no orphaned imports remain
- Ran `uv run pytest tests/ -x --tb=short`: 339 passed, 2 skipped before hitting pre-existing profile injection failure (`test_inject_token_into_existing_env_section`) unrelated to this cleanup
- Ran `uv run traderbot experiment --help`: CLI works correctly, shows populated/run/verify/results/list-treatments commands
- Preserved remaining `experiments/` content: `__init__.py`, `docs/`, `results/`, `v2/` (compile_data.py, docker/, results/, simulation/, v2_experiment_data.db)
- No empty parent directories to clean up — `experiments/v2/` still contains active V2 artifacts
- Note: `respx` was missing from dev dependencies; installed as `uv add --dev respx` to fix test collection error in `tests/test_history.py`
