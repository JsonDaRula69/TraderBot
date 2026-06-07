# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Installer `--update` now detects pipx installations and uses `pipx upgrade traderbot` instead of git pull
- `traderbot uninstall` now detects pipx installations and uses `pipx uninstall` instead of `pip uninstall`
- `traderbot update` now detects pipx installations and uses `pipx upgrade` instead of `pip install --upgrade`
- Added `get_install_method()` to `paths.py` — returns "pipx", "pip", or "git"
- Installer script (`install/traderbot-installer.sh`) now delegates interactive configuration to `traderbot setup` instead of its own `interactive_config_flow()` function, removing ~1200 lines of duplicated credential prompting, keyring setup, master password, and profile creation logic that is already handled by the Python CLI

### Fixed

- Paper settlement cash crediting now correctly adds proceeds to cash balance instead of overwriting
- Paper P&L computation is side-aware (long/short) — short positions profit when price falls
- Paper slippage model crosses the ask for buys (was using bid for both sides)
- Portfolio valuation uses cash-only buying power instead of inflating with position collateral
- Void settlement handling — voided markets are skipped in settlement processing
- Settlement sync propagates settled positions back to decisions table for audit trail
- Live API tests now pass API keys explicitly to `NewsAggregator()` instead of relying on config fallback
- `test_newsapi_top_headlines`, `test_openweathermap_weather`, `test_fred_economic_data` properly authenticate
- CoinGecko live tests cover all 3 auth tiers: free (unauthenticated), demo (x-cg-demo-api-key), pro (x-cg-pro-api-key)
- `COINGECKO_TIER` secret added to CI workflow for tier-aware CoinGecko testing
- Move `pytest.register_assert_rewrite("tests.news")` to root conftest.py (correct placement)
- Revert Voyage test skip — assert real API responses, don't paper over auth issues
- Windows CI: `continue-on-error` for Windows test step (ONNX Runtime KeyboardInterrupt during teardown is an ONNX bug, not a test failure)
- PYTHONWARNINGS=ignore::UserWarning on Windows to suppress ONNX Runtime's unsupported OS warning
- Pip install readiness: `get_source_root()` raises `FileNotFoundError` in pip-installed scenarios instead of returning wrong path
- Pip install readiness: `injection.py` workspace template resolution falls back to `get_data_dir()` when source tree unavailable
- Pip install readiness: `updater.py` version resolution uses `importlib.metadata` first, source tree as fallback
- Pip install readiness: `sandbox.py` handles missing source tree gracefully in pip-installed scenarios
- Added `src/traderbot/py.typed` for PEP 561 type checking compliance
- Added `src/traderbot/experiment/__init__.py` as proper package marker
- Removed `numpy` from direct dependencies (transitive via `scipy`)
- Explicit `experiment/tests` exclusion in wheel and sdist build config
- Fixed `TradingProfile` Pydantic model — moved `MarketCategory` out of `TYPE_CHECKING` guard for runtime evaluation
- Removed `from __future__ import annotations` from `updater.py` and `models.py` (breaks Pydantic and mock patching)
- Fixed `test_updater.py` mocks — patched `traderbot.paths.get_source_root` instead of removed `traderbot.updater.Path`
- Fixed `test_injection.py` — mock `_resolve_workspace_root` instead of `__file__` spoofing

### Added

- `BayesianAdapter` persistence — adapter state survives across agent sessions via DB serialization
- Breaker→adaptation weighted feedback — circuit breaker events feed into adapter weight adjustment
- Auto-experiment trigger on `FULL_STOP` — when a FULL_STOP halt fires, an experiment is automatically created to evaluate the cause
- Deployment clears `FULL_STOP` blocker — deploying a new strategy version automatically clears the FULL_STOP halt state
- Side column in positions table — positions display shows long/short direction explicitly

### Changed

- `FULL_STOP` 24h auto-recovery documented (was documented as "manual only")
- Cron tables reconciled across documentation — all docs now reference the same schedule definitions (`/historical/markets`, `/historical/trades`, `/historical/markets/{ticker}`) for archived data instead of live `/markets/` endpoints — live endpoints only return post-cutoff data. Added response format guardrails that warn when expected keys (`market`, `markets`, `trades`) are missing before normalization.
- Phantom `KALSHI_RATE_LIMIT_RPS` env var removed from docs and installers — replaced with actual `KALSHI_READ_BUDGET_TOKENS` (default 200) and `KALSHI_WRITE_BUDGET_TOKENS` (default 100). Effective RPS = budget / endpoint_cost (default 10).

### Added

- `traderbot auth detect-tier` command probes CoinGecko API to determine tier (free/demo/pro) and auto-stores result
- `traderbot setup` — interactive setup wizard covering Python check, data dir, DB init, Kalshi credentials, optional service credentials, master password, and profile creation (replaces installer's `interactive_config_flow` for pipx users)
- `traderbot bootstrap --full` — delegates to the full setup wizard for backward compatibility; legacy bootstrap unchanged without `--full` flag

### Fixed

- Paper settlement cash crediting now correctly adds proceeds to cash balance instead of overwriting
- Paper P&L computation is side-aware (long/short) — short positions profit when price falls
- Paper slippage model crosses the ask for buys (was using bid for both sides)
- Portfolio valuation uses cash-only buying power instead of inflating with position collateral
- Void settlement handling — voided markets are skipped in settlement processing
- Settlement sync propagates settled positions back to decisions table for audit trail
- Live API tests now pass API keys explicitly to `NewsAggregator()` instead of relying on config fallback
- `test_newsapi_top_headlines`, `test_openweathermap_weather`, `test_fred_economic_data` properly authenticate
- CoinGecko live tests cover all 3 auth tiers: free (unauthenticated), demo (x-cg-demo-api-key), pro (x-cg-pro-api-key)
- `COINGECKO_TIER` secret added to CI workflow for tier-aware CoinGecko testing
- Move `pytest.register_assert_rewrite("tests.news")` to root conftest.py (correct placement)
- Revert Voyage test skip — assert real API responses, don't paper over auth issues
- Windows CI: `continue-on-error` for Windows test step (ONNX Runtime KeyboardInterrupt during teardown is an ONNX bug, not a test failure)
- PYTHONWARNINGS=ignore::UserWarning on Windows to suppress ONNX Runtime's unsupported OS warning
- Pip install readiness: `get_source_root()` raises `FileNotFoundError` in pip-installed scenarios instead of returning wrong path
- Pip install readiness: `injection.py` workspace template resolution falls back to `get_data_dir()` when source tree unavailable
- Pip install readiness: `updater.py` version resolution uses `importlib.metadata` first, source tree as fallback
- Pip install readiness: `sandbox.py` handles missing source tree gracefully in pip-installed scenarios
- Added `src/traderbot/py.typed` for PEP 561 type checking compliance
- Added `src/traderbot/experiment/__init__.py` as proper package marker
- Removed `numpy` from direct dependencies (transitive via `scipy`)
- Explicit `experiment/tests` exclusion in wheel and sdist build config
- Fixed `TradingProfile` Pydantic model — moved `MarketCategory` out of `TYPE_CHECKING` guard for runtime evaluation
- Removed `from __future__ import annotations` from `updater.py` and `models.py` (breaks Pydantic and mock patching)
- Fixed `test_updater.py` mocks — patched `traderbot.paths.get_source_root` instead of removed `traderbot.updater.Path`
- Fixed `test_injection.py` — mock `_resolve_workspace_root` instead of `__file__` spoofing

### Added

- `BayesianAdapter` persistence — adapter state survives across agent sessions via DB serialization
- Breaker→adaptation weighted feedback — circuit breaker events feed into adapter weight adjustment
- Auto-experiment trigger on `FULL_STOP` — when a FULL_STOP halt fires, an experiment is automatically created to evaluate the cause
- Deployment clears `FULL_STOP` blocker — deploying a new strategy version automatically clears the FULL_STOP halt state
- Side column in positions table — positions display shows long/short direction explicitly

### Changed

- `FULL_STOP` 24h auto-recovery documented (was documented as "manual only")
- Cron tables reconciled across documentation — all docs now reference the same schedule definitions (`/historical/markets`, `/historical/trades`, `/historical/markets/{ticker}`) for archived data instead of live `/markets/` endpoints — live endpoints only return post-cutoff data. Added response format guardrails that warn when expected keys (`market`, `markets`, `trades`) are missing before normalization.
- Phantom `KALSHI_RATE_LIMIT_RPS` env var removed from docs and installers — replaced with actual `KALSHI_READ_BUDGET_TOKENS` (default 200) and `KALSHI_WRITE_BUDGET_TOKENS` (default 100). Effective RPS = budget / endpoint_cost (default 10).

### Added

- `tests/test_openclaw_compliance.py` — validates all OpenClaw CLI invocations against Dep_Docs (command, subcommand, and flag correctness). Catches flag-name mistakes like `--schedule`→`--cron` at test time
- `tests/test_kalshi_compliance.py` — validates all Kalshi API endpoint paths and HTTP methods against Dep_Docs. Catches deprecated/typo'd endpoint paths at test time

### Changed

- HARD_LIMITS max_position_per_market_pct ceiling raised from 5% to 15% (issue #73)

### Fixed

- `traderbot data forecasts` display mode no longer crashes with `AttributeError: 'CityForecast' object has no attribute 'temperature_high'` — all references changed to `high_temp_f` (bug #132)
- `WeatherDataProvider` now lazily re-creates httpx client when called across multiple `asyncio.run()` boundaries, preventing `RuntimeError: Event loop is closed` on repeated CLI invocations (bug #132)
- `traderbot auth set-kalshi` now always prompts for credentials instead of silently re-using .env values — enables credential rotation without manual cleanup
- `traderbot auth set-kalshi` PEM prompt now uses `sys.stdin.read()` instead of `typer.prompt()` to capture multi-line PEM blocks — single-line prompt was truncating pasted keys (PR #93)
- `traderbot update` version comparison now uses Git tags API (`/git/refs/tags`) instead of `releases/latest` — `releases/latest` only returns GitHub Releases (created on tag push), so every version between Release creation and the next tag push appeared as "Update available: v0.15.NN → v0.15.00" (PR #94)
- `_reregister_cron_jobs()` in update pipeline now calls both `cron setup --replace` and `cron setup-heartbeat-tasks --replace` for every agent — previously only heartbeat tasks were re-registered (PR #89)
- `cron setup` was passing `--schedule` (wrong flag) and positional `agent_id` (wrong position) to `openclaw cron add` — now passes `--cron` and `--agent` correctly, which was why decision/heartbeat/news loops never registered (PR #90)
- Installer Phase 2 now configures `tools.sessions.visibility: agent` and `tools.agentToAgent.enabled: true` for fresh installs (PR #82)
- Remaining issues #51, #53, #61 closed with documentation comments

## [0.14.95] — 2026-06-04

### Fixed

- Installer Phase 2 OpenClaw session visibility for fresh installations (PR #82)
- OpenClaw visibility and auth scope validation for updater (PR #81)

## [0.14.81] — 2026-06-03

### Fixed

- Data loader pagination delay and date filtering for Kalshi 429 rate-limit handling (PR #80, fixes #50)
- Ensemble consensus scoring implementation with provider injection (PR #79, fixes #54)
- Forecast bias recording wired into settlement pipeline via new `traderbot data record-bias` CLI (PR #78, fixes #58)
- Phantom edge detection with executable-price validation in weather signal engine (PR #77, fixes #59)
- Circuit breaker heartbeat triggers auto-recovery with fresh metrics via `halt --recover` (PR #76, fixes #55)
- Per-market position limit now uses per-ticker position value instead of aggregate portfolio-wide value (PR #75, fixes #62)
- Circular import chain in `cli/helpers.py` resolved by extracting DB helpers to `paths.py` (PR #71, fixes #70)
- 19 Windows CI test failures — ANSI stripping, `uv run --frozen`, `shell: bash` for matrix tests (PR #71)
- 6 CLI trade tests fixed with proper mocking and `TradingProfile` model

### Added

- Auth scope validation via `traderbot auth check --validate-scopes` (PR #81, fixes #47)
- Phantom edge detection with 4 conditions: executable-price gap, volatility spread, stale data, orderbook depth (PR #77)
- `traderbot data record-bias` CLI command for historical forecast bias logging (PR #78)
- `traderbot halt --recover` flag to trigger circuit breaker auto-recovery (PR #76)
- `position_value_for_ticker()` helper in `paper.py` for per-ticker position computation (PR #75)

### Changed

- OpenClaw visibility set to `agent` with `agentToAgent.enabled: true` for sysadmin-to-agent messaging (PR #81)
- `tools.sessions.visibility: agent` configured in both installer and updater (PR #81, PR #82)

## [0.14.79] — 2026-06-02

### Fixed

- CI pipeline retriggers and lockfile verification
- Ruff format checks scoped to `src/traderbot` only

### Added

- Comprehensive AGENTS.md documenting GitHub/CI procedures, CTX memories, branch protection

## [0.14.78] — 2026-06-02

### Fixed

- Performance import resolution
- Various CI workflow fixes

## [0.14.70] — 2026-06-02

### Fixed

- Regression tests for bugs #51, #61, cron indent, ecmwf_ifs, duplicate cron, auth --validate
- Duplicate entries removed from `_AGENT_HEARTBEAT_CRON_JOBS` and `_SYSADMIN_HEARTBEAT_CRON_JOBS`
- Deprecated `ecmwf_ifens` renamed to `ecmwf_ifs` in data CLI

### Added

- `--validate` flag to `auth check` for API credential validation

## [0.14.60–0.14.69] — 2026-06-01

### Fixed

- `initial_cents` used for `portfolio_value_cents` (fixes #61, #51)
- Except indentation and agent_id→agent_user in news-ingest timer removal
- PEM key written to file, `get_data_dir()` used in `auth set-kalshi`
- PATH setup ensures OpenClaw CLI found via npm-global/bin
- Weather learning-review reverted to learnings-only
- `get_current_version` strips v prefix for consistent display
- `check_for_updates` signature includes `force/check_interval_minutes/dev` kwargs
- Rebuilt `updater.py` — single `apply_update` delegates to standalone script
- WS daemon and gateway restart use `Popen` (non-blocking)
- Backup loop skips `.update_backup` directories — prevents infinite nesting

### Added

- Standalone Python updater with self-update — replaces bash bootstrap script
- Route learning-review to GitHub issue filing via `github` skill

### Removed

- Bash bootstrap script — replaced by Python updater

## [0.14.30–0.14.59] — 2026-06-01/02

### Fixed

- Cron `--replace` JSON parse — strips "Update available" banner
- Unified WS cache — ticker channel prices in `event_category_cache.json`
- Experiment flow — sub-agent check-in, performance halt, GitHub issue routing
- Expose GFS/ECMWF/GEM ensemble data in `traderbot data forecasts` command
- `positions` command adds live market prices from Kalshi unauthenticated endpoints
- All ERRORS.md/LEARNINGS.md/FEATURE_REQUESTS.md references normalized to `.learnings/` prefix
- Empty scan = SYSTEM ERROR, not "no markets"
- WS daemon PEM detection — validates both BEGIN+END markers
- All 17 cron messages now write to `.learnings/ERRORS.md`
- Enforce `tools.profile=coding` for all agents — enables sessions_send, exec, fs tools
- DbDecision risk_checks string→bool coercion
- Drawdown calculation uses `halt --json` not cost basis
- DB integrity protections — auto-backup on update
- `check-settlements` 401 handling — catch and surface actionable error
- WS daemon PEM resolution — detect file path vs PEM content
- Missing `get_data_dir` import in ws_daemon
- VERSION file drift corrected (v0.14.18 → v0.14.23)
- Performance command shows open position cost and remaining paper balance
- Paper trade balance deduction, experiment-execution cadence, WS daemon indent, httpx timeouts
- Duplicate ERRORS.md — Hard Rules used bare path

## [0.14.00–0.14.29] — 2026-06-01

### Fixed

- ChromaDB telemetry handler noise suppression
- Update hang — `capture_output=True` pipe buffer filled
- Config.py missing `private_key_path` field
- Heartbeat writes to nested workspace dir inside sandbox
- `trade.py` `estimated_prob` always set to `price/100` — overwrote user-supplied `--estimated-prob`
- Rate limiter accounts for Kalshi endpoint cost (200 tokens/sec / 10 cost = 20 effective RPS)
- Scan retry 3x on empty/error
- WS daemon seed fixes — variable names, event_ticker check, 429 handling, limit=200, status=open param
- WS daemon aclose→close, _client.get→_request
- Missing imports (os, signal, sys, time, Path, logging)
- FRED backfill Semaphore(1) + retry tracking
- Add progress prints to `apply_update`
- WS daemon writes `cache_size` on startup

### Added

- WS daemon (systemd) — streams `market_lifecycle_v2`, `ticker`, `fills` to ws_cache/
- `traderbot ws start/stop/status/cache` CLIs
- WS daemon wired into installer, updater, bootstrap update script

### Changed

- WS daemon writes to `event_category_cache.json` directly — single source of truth

## [0.13.00–0.13.99] — 2026-05-24 to 2026-06-01

### Fixed

- Decision-loop scan limit 200→50 to avoid Kalshi rate limiting
- Removed extraHosts DNS block — broke CLI scan
- Main agent excluded from agent cron loop
- Paper trade uses local profile balance, not Kalshi API
- Trade AttributeError — use `PortfolioService` not `MarketService.get_portfolio()`
- Bootstrap script missing PATH for openclaw CLI
- Install-data-pipeline path doubled
- Restored missing `@cron_app.command` decorator on `setup-heartbeat-tasks`
- Lazy-import `cron_app` so update works even with broken modules
- `--replace` cron remove by ID, not name
- VERSION file sync with latest tag
- Uninstall missing user data prompt, gateway stop before npm uninstall
- Decision-loop retry, position sizing formula, learning-promotion spawn
- Kalshi PEM fallback for sandbox path mismatch
- Gateway restart timeout — use `Popen` instead of blocking `run`

### Added

- Bootstrap update script + fallback in `apply_update` for bricked modules
- Decision-loop cron, bootstrap hook enable, bootstrap-extra-files
- Staggered cron cadences, auth-check jobs, pipeline-health

### Removed

- Tool profile changes reversed — root cause was `models.defaults.model` not set

## [0.12.10–0.12.44] — 2026-05-18 to 2026-05-22

### Security

- OS keyring integration for credential storage
- Ed25519 update signatures + Kalshi TLS cert pinning

### Added

- Windows installer (PowerShell) + deployment docs
- Per-agent sandbox config, cron --replace, profile --overwrite, Docker binds
- SysAdmin profile with all-categories access
- Comprehensive audit + 102 new tests across CLI, Kalshi, DB, data pipeline

### Fixed

- Gateway restart timeout — use Popen instead of blocking run
- Sandbox binds, FRED rate-limit retry, update path rebuilds image
- Uninstall — Docker build cache prune, remove sandbox image and orphan containers
- Uninstall — remove `/usr/local/bin` and `~/.local/bin` symlinks
- Split heartbeat cron jobs into sysadmin vs agent lists
- Auto-refresh session token at 25min

### Refactored

- Unify uninstall — Python CLI is single source of truth, bash delegates
- Remove all BOOTSTRAP.md/BOOT.md references
- Make OpenClaw context plug-and-play configurable
- Make `openclaw.json` source of truth for agent discovery

## [0.11.00–0.11.99] — 2026-05-13 to 2026-05-17

### Fixed

- Profile update `--initial-balance-cents` not applied
- Separate bootstrap into 3 phases — identity → human → trading params
- Timezone and market-selection prompts removed from bootstrap
- `repo_root` resolution for news-ingest timer templates
- Scan rate limiting, series discovery, category mapping
- NewsItem field names in backfill
- Open-Meteo rate limiting, ChromaDB telemetry, sync docs with code
- News-context fallback to category-only when time filter excludes all articles
- Bump fetch_all limit so DataPoints are not truncated by news items
- OWM /group fallback to individual calls
- ChromaDB embedding dimension mismatch handling

### Added

- Backfill CLI for historical weather + econ data
- News-source parallel fetching with ChromaDB DataPoint storage
- `scan --continuous` flag
- Default `initial_balance_cents` to 10000, prompt on profile create/assign

### Changed

- Series-based market discovery for daily/hourly resolution markets

## [0.10.00–0.10.216] — 2026-05-12 to 2026-05-13

### Breaking

- RSA-PSS auth replaces session-token auth (Kalshi V2 migration)

### Added

- OpenClaw Docker sandbox with build script
- `traderbot cron setup` CLI for OpenClaw loop registration
- `--version` flag
- AES-256 encrypted file fallback for profiles on headless Linux
- Per-profile data isolation (DB, ChromaDB, audit dirs)
- Profile management CLI commands (create, assign, update, unassign)
- Profile-aware config loading with auth resolution chain
- Auto-build sandbox Docker image during install and profile assign
- `traderbot uninstall` command
- `traderbot resume` command to clear circuit breaker halt

### Fixed

- 3 critical Kalshi V2 API bugs
- Decision-loop cron updated to market hours
- Market open interest configurable in PaperTrader
- V2 order body uses correct field names — `count` and `price`
- NewsAPI param validation and rate-limit tracking
- Cron `--replace` remove by ID, not name
- Per-agent DB isolation — `base_dir` now includes profile name
- `scan` default limit 20→500
- Sandbox defaults to off — cron loops require host-side access
- OpenClaw config schema violations fixed
- `profile assign --force` to reassign existing token
- Token display removed from interactive output (RAW_TOKEN only in script mode)
- Installer hangs on agent assignment — `--yes` skips interactive prompts
- Uninstall — use `sudo rm` for root-owned service files
- Update checker uses GitHub tags API (not releases)

## [0.09.00–0.09.24] — 2026-05-10

### Fixed

- PIN Python 3.12 for chroma-hnswlib compat, upgrade chromadb to >=0.5.0
- OpenClaw config path from `config.json` to `openclaw.json`
- Systemd service templates for per-agent persistence

### Added

- `traderbot cron setup` command for OpenClaw loop registration
- Bootstrap wizard for initial agent setup
- TOOLS.md full CLI reference, WAL protocol, cron setup

## [0.08.00–0.08.99] — 2026-05-08

### Added

- Profile system — `TradingProfile` model, `ProfileRegistry`, `AgentRiskLimits`
- Token auto-injection into OpenClaw agent TOOLS.md
- Dual-platform installer (systemd + launchd)
- Venv-based install + system-level services
- AES-256 encrypted file fallback for profiles on headless Linux
- OpenClaw multi-agent discovery from IDENTITY.md
- Category analyzer protocol with `MarketCategory` enum

### Fixed

- Circular imports in agent_limits.py
- Stale HEARTBEAT.md references
- OpenClaw workspace compliance — WAL/learning bugs, missing workspace files
- Installer handles broken git repos, TTY issues, multi-agent paths

## [0.07.00] — 2026-05-07

### Added

- News module — sources, embeddings, models, classifier, sentiment scorer, impact assessor
- News and sentiment CLI commands
- Integration tests for news pipeline

### Fixed

- Ruff lint errors in news module

## [0.06.00] — 2026-05-06

### Added

- Decision logging and self-learning pipeline
- WAL protocol, pattern promotion, feature requests
- Learnings CLI command with filtering and promotion

## [0.05.00] — 2026-05-05

### Added

- Simulation engine with multiple strategy support
- `traderbot bootstrap`, `traderbot compare` CLI commands
- 35 simulation integration tests

## [0.04.00] — 2026-05-03

### Added

- Analysis engine — indicators, odds, portfolio analysis
- CLI commands (db/positions, db/decisions)
- OpenClaw workspace templates and SKILL.md
- Signals module with market scanning

## [0.03.00] — 2026-05-01

### Added

- Kalshi trading module — order placement, portfolio queries
- Signals module wired into CLI
- Phase 3 (CLI + OpenClaw + DB persistence) completion

## [0.02.00] — 2026-04-29

### Added

- Kalshi adapter with V2 API support
- Risk gate — circuit breaker, position limits, Kelly sizing
- Market models and orderbook parsing

## [0.01.00] — 2026-04-27

### Added

- Project scaffolding with `pyproject.toml` and package structure
- Versioning system
- Pydantic model conventions
- Ruff linting configuration

[Unreleased]: https://github.com/JsonDaRula69/TraderBot/compare/v0.14.95...HEAD
[0.14.95]: https://github.com/JsonDaRula69/TraderBot/compare/v0.14.81...v0.14.95
[0.14.81]: https://github.com/JsonDaRula69/TraderBot/compare/v0.14.79...v0.14.81
[0.14.79]: https://github.com/JsonDaRula69/TraderBot/compare/v0.14.78...v0.14.79
[0.14.78]: https://github.com/JsonDaRula69/TraderBot/compare/v0.14.70...v0.14.78
[0.14.70]: https://github.com/JsonDaRula69/TraderBot/compare/v0.14.69...v0.14.70
[0.14.60]: https://github.com/JsonDaRula69/TraderBot/compare/v0.14.59...v0.14.69
[0.14.30]: https://github.com/JsonDaRula69/TraderBot/compare/v0.14.29...v0.14.59
[0.14.00]: https://github.com/JsonDaRula69/TraderBot/compare/v0.13.99...v0.14.29
[0.13.00]: https://github.com/JsonDaRula69/TraderBot/compare/v0.12.44...v0.13.99
[0.12.10]: https://github.com/JsonDaRula69/TraderBot/compare/v0.11.99...v0.12.44
[0.11.00]: https://github.com/JsonDaRula69/TraderBot/compare/v0.10.216...v0.11.99
[0.10.00]: https://github.com/JsonDaRula69/TraderBot/compare/v0.09.24...v0.10.216
[0.09.00]: https://github.com/JsonDaRula69/TraderBot/compare/v0.08.99...v0.09.24
[0.08.00]: https://github.com/JsonDaRula69/TraderBot/compare/v0.07.00...v0.08.99
[0.07.00]: https://github.com/JsonDaRula69/TraderBot/compare/v0.06.00...v0.07.00
[0.06.00]: https://github.com/JsonDaRula69/TraderBot/compare/v0.05.00...v0.06.00
[0.05.00]: https://github.com/JsonDaRula69/TraderBot/compare/v0.04.00...v0.05.00
[0.04.00]: https://github.com/JsonDaRula69/TraderBot/compare/v0.03.00...v0.04.00
[0.03.00]: https://github.com/JsonDaRula69/TraderBot/compare/v0.02.00...v0.03.00
[0.02.00]: https://github.com/JsonDaRula69/TraderBot/compare/v0.01.00...v0.02.00
[0.01.00]: https://github.com/JsonDaRula69/TraderBot/releases/tag/v0.01.00