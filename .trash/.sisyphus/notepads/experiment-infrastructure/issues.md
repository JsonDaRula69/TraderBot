
## Code Quality Review Findings (2026-05-26)

### Unused Imports (minor, in test files only)
- `src/traderbot/experiment/tests/test_registry.py:11` — unused `datetime` import
- `src/traderbot/experiment/tests/test_harness.py:5` — unused `datetime, UTC` imports

### LSP/Ruff Warnings (0 errors, style-only)
- `populate.py:16` — TC001: Move `Market` import into TYPE_CHECKING block
- `experiment_schema.py:5` — TC003: Move `sqlite3` into TYPE_CHECKING block
- `results.py:4` — TC003: Move `sqlite3` into TYPE_CHECKING block
- `results.py:20` — UP017: Use `datetime.UTC` alias

### Pre-existing (NOT in scope of new files)
- `cli.py:300,415` — `# type: ignore[arg-type]` in pre-existing CLI code

### Broad Exception Catches (justified)
- `harness.py:334` — `except Exception:` with `logger.exception()`, continues experiment run
- `populate.py:211,224` — `except Exception as exc:` on forecast/price inserts, logs warning

### Verification Results
- Compile: 18/18 PASS
- Tests: 24/24 PASS (0.53s)
- type:ignore: 0 in new files
- empty except: 0
- as any: 0
- AI slop: none detected
