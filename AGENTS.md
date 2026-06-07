# TraderBot — AI Agent Conventions

This file defines conventions for AI-assisted development of this project. All AI agents working on this codebase must follow these rules.

## Project Identity

- **Name**: TraderBot
- **Language**: Python 3.12+
- **Package manager**: uv
- **Type checking**: Pydantic models for all API data; no `as any`, `# type: ignore`
- **Testing**: pytest with async support
- **Linting**: ruff (formatter + linter)
- **Current version**: 0.15.56

## Installation

TraderBot supports two installation methods:

1. **pipx (recommended)** — isolated, always-available CLI:
   ```bash
   pipx install traderbot
   traderbot setup
   ```
   pipx isolates TraderBot in its own virtualenv, avoiding the `externally-managed-environment` error on modern Linux. After install, run `traderbot setup` for the interactive configuration wizard.

2. **Installer script** — full-featured, includes Docker sandbox and OpenClaw integration:
   ```bash
   bash <(curl -fsSL https://raw.githubusercontent.com/JsonDaRula69/TraderBot/main/install/traderbot-installer.sh)
   ```
   The installer handles venv creation, dependency installation, and interactive configuration.

## Versioning Scheme

- **Format**: `MAJOR.MINOR.PATCH` (e.g. `0.14.74`)
- **Every commit** increments the patch version by 1 (0.14.73 → 0.14.74 → 0.14.75 …)
- **Milestone releases** increment the minor version and reset patch to 00 (0.14.99 → 0.15.00)
- **Major releases** increment the major version and reset minor/patch (1.0.0)
- **Tags**: Every commit must be tagged with its version (`git tag v0.14.74`)
- **Version file**: `VERSION` at repo root is the single source of truth — no `v` prefix (hatchling reads it for PyPI publishing)
- **PyPI**: Tag pushes trigger auto-publish via `.github/workflows/python-publish.yml`

## Git Discipline

- **All commits MUST be made via Pull Requests** — never push directly to main.
- **PR flow**: create branch → commit → push → open PR → wait for CI → merge.
- **CI must pass before merge** — every PR requires green status on: `Lint & format`, `Unit tests`, `Test (ubuntu-latest|macos-latest|windows-latest)`, and `Build wheel`.
- **Auto-merge for human operator** (`jsondarula`): bypasses PR review requirement. PRs from `jsondarula` can be merged once CI passes without additional review.
- **External contributors** require 1 approving review before merge.
- **Branch protection**: `main` is protected — requires CI status checks, up-to-date branch, and enforces admins. Force pushes blocked. Bypass allowance for `jsondarula` set via GraphQL API on rule `BPR_kwDOSIPo7s4ElNFj`. Not exposed in UI for this account tier.
- **One concern per commit** — no mixing features, fixes, and docs in one commit
- **Conventional commits**: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `ci:`, `test:`, `deps:`
- **Always tag**: `git tag v0.14.NN` after every commit (note: `v` on tag, no `v` in VERSION file)
- **Tags push on PR merge** via the Release workflow, not during development.
- **Never commit** `.env`, credentials, or API keys
- **Version increment**: update `VERSION` (increment PATCH by 1) as part of the commit.
- **Sisyphus attribution**: every commit includes Sisyphus co-author in the description.

## Source of Truth

- **`docs/` is the authoritative source** for architecture, API specs, risk design, and roadmap — NEVER edit files in `docs/` without explicit human approval
- **`ROADMAP_PROGRESS.md`** (repo root) tracks implementation progress across all 8 phases — update it when completing phase components or fixing bugs that affect the taxonomy
- **CTX memories** store cross-session context (version, phase status, bug classes, architecture decisions) — keep them current after every significant change
- **`VERSION`** file is the single source of truth for the current version number
- When in doubt about intended behavior, consult `docs/` first, then memories, then code

## Progress Tracking Protocol

1. After completing a component or fixing a bug, update `ROADMAP_PROGRESS.md` with the new status
2. After committing, update CTX memories to reflect the current version and completed work
3. When new bug classes are discovered, add them to both `ROADMAP_PROGRESS.md` (Bug Class Taxonomy section) and CTX CONSTRAINTS memory
4. Before starting work on a new phase, verify prerequisites in `ROADMAP_PROGRESS.md`

## Architecture Constraints

- The **risk module is immutable** — never modify hard limits without explicit human approval
- The **toolkit never decides strategy** — it computes, enforces, and executes, but the agent decides
- No API keys in code — use environment variables or `.env` files (never committed)
- All trade decisions must be logged with full reasoning in the audit trail
- All Pydantic models MUST use `ConfigDict(strict=True, extra="forbid")` — including `BaseSettings` subclasses
- All monetary values in cents as `int` — never `float`

## Agent Operating Procedures

- **Prompt before fixing discovered issues** — If you discover bugs, inconsistencies, or improvement opportunities while working on a task — even if they're unrelated to the current task — always ask the user before fixing them. Don't fix silently or assume permission.
- **Always use the questions tool** — When prompting the user or asking questions, always use the `question` tool. Do not ask questions inline or in plain text.
- **Always maintain a todo list** — Use `todowrite` for every task, even simple ones. If the user interrupts you mid-task, evaluate the priority of the new request and insert it into the todo list in the appropriate order. Never leave tasks with `in_progress` status unfinished.
- **Update VERSION on every commit** — Before every `git commit`, increment the patch version in `VERSION` (repo root). The format is `vMAJOR.MINOR.PATCH` (e.g., `v0.13.23`). The VERSION file is the single source of truth — `traderbot/__init__.py` reads it as primary, with `importlib.metadata` as fallback.
- **CI and branch protection changes require explicit user approval** — Do NOT modify `.github/workflows/*.yml`, branch protection rules via GitHub API, or the list of required status checks without asking the user first and getting written confirmation. These changes affect every PR and every contributor — incorrect modifications can block merges or make the repo insecure. Always propose the change, explain the impact, and wait for approval before making it.

## Code Style

- Use Pydantic v2 models for all data structures
- Prefer `async` for I/O-bound operations (Kalshi API calls, WebSocket streams)
- Prefer `sync` for CPU-bound analysis (statistics, indicators)
- Document every public function with a one-line docstring
- No AI slop: no obvious comments (`# increment counter`), no boilerplate docstrings that restate the function name

## File Organization

- `src/traderbot/kalshi/` — exchange adapter (API-specific code)
- `src/traderbot/analysis/` — pure computation (no I/O)
- `src/traderbot/risk/` — enforcement layer (no strategy logic)
- `src/traderbot/simulation/` — backtesting engine
- `src/traderbot/news/` — external data pipeline
- `src/traderbot/db/` — persistence layer
- `src/traderbot/profiles/` — multi-agent profile system
- `src/traderbot/cli/` — CLI entry point and sub-command modules
- `src/traderbot/experiment/` — experiment design, harness, and evaluation framework
- `src/traderbot/data/` — external data providers (weather, registry)

## CLI Commands

### Setup and Configuration Commands

- `traderbot setup` — Interactive setup wizard (Python check, data dir, DB, credentials, master password, profile). Supports `--dry-run`, `--non-interactive`, `--no-creds`, `--json`.
- `traderbot bootstrap --full` — Delegates to the setup wizard; legacy bootstrap without `--full` remains unchanged.
- `traderbot auth set-key <service> <key>` — Store credentials for non-Kalshi services (newsapi, voyage, twitter, reddit, coingecko, openweathermap, fred). Use `--value` for non-interactive/cron. Use `--tier demo|pro` for coingecko.
- `traderbot auth detect-tier` — Probe CoinGecko API to auto-detect tier (free/demo/pro). Stores result automatically. Supports `--dry-run`, `--json`.

## Testing Discipline

- **Run relevant tests before committing**: execute only the tests that cover the modified code paths. Use `-k` to filter (e.g. `uv run pytest -m "not live" -k "cron"` for cron changes). Do NOT run the full suite locally — that's what CI is for.
- **Full suite runs in CI**: every PR triggers the complete pipeline (lint → unit → matrix → build). Verify all required status checks pass on the PR before merging.
- **Markers**: use the standard marker taxonomy defined in `pyproject.toml`:
  - `unit` — pure unit tests with no external dependencies (fastest). Run via: `uv run pytest -m "unit"`
  - `integration` — tests with mocked external services
  - `live` — tests that hit real API endpoints (skipped in CI, requires credentials)
  - `slow` — tests excluded from fast runs
- **CI pipeline** (`.github/workflows/ci.yml`), layered in this order:
  1. `frozen-check`: validates lockfile is fresh (`uv sync --frozen`)
  2. `lint`: ruff lint + format (`uvx --with ruff ruff check`, `uvx --with ruff ruff format --check`)
  3. `unit`: fast unit tests only (`-m "unit"`) — gates subsequent jobs
  4. `test`: full matrix (ubuntu/macos/windows) — `-m "not live"`
  5. `live`: API smoke tests (Kalshi, Open-Meteo, CoinGecko, TheSportsDB, OpenWeatherMap, FRED, NewsAPI, VoyageAI, Google Trends) — runs on push to main + weekly. Skipped on fork PRs (secrets unavailable).
  6. `build`: builds wheel + verifies `pip install` works
- **Pre-existing test failures must be fixed, not deferred**: if a test was already failing before your changes, fix it in the same PR or a follow-up PR within the same work session. Do NOT treat "pre-existing" as acceptable — a broken test suite is a broken deployment gate. Every CI failure blocks every PR. The only exception is live/API tests that require secrets unavailable in CI (those must be gated behind `@pytest.mark.live` and excluded from required status checks).
- **Setup for local test execution**: use `uv sync --all-extras --dev` to install pytest (it's in `[project.optional-dependencies] dev`, not `[dependency-groups] dev`).
- **CLI trade tests**: these require extensive mocking due to the DB persistence layer (`_resolve_db_path`, `get_connection`, `upsert`). If the circular import chain (`traderbot.cli.app` → `traderbot.cli.trade` → `traderbot.paper` → `traderbot.cli.helpers` → ...) prevents clean mocks, the affected tests need the import chain refactored (extract DB code from CLI).
- **Pull requests trigger the full pipeline** (lint → unit → matrix → build).
- **Push to main** runs the same pipeline. Doc-only changes are skipped via `paths-ignore`.
- **Weekly schedule** (Mondays 06:00 UTC) runs the full pipeline + CodeQL.
- **Live tests** run on push to main and weekly schedule — skipped on PRs (fork PRs lack secrets).
- **Concurrency**: in-progress runs are automatically cancelled when a new push arrives.
- **Coverage**: new code should maintain or improve module-level coverage. Uploaded to Codecov on Linux.
- **Adding new API tests**: when adding a new API-dependent feature, add a `@pytest.mark.live` test AND wire the required secret in `.github/workflows/ci.yml`. The CI workflow is the single source of truth for which secrets are tested.

## GitHub Branches and Protection

- **All commits MUST be made via Pull Requests** — never push directly to main. This ensures CI runs on every change and provides full traceability.
- **PR flow**: create branch → commit → push → open PR → wait for CI → merge.
- **CI must pass before merge** — every PR requires green status on: `Lint & format`, `Unit tests`, `Test (ubuntu-latest|macos-latest|windows-latest)`, and `Build wheel`.
- **Auto-merge for human operator** (`jsondarula`): bypasses PR review requirement (branch protection is configured with bypass allowance via GraphQL API mutation). PRs from `jsondarula` can be merged once CI passes without additional review.
- **External contributors** require 1 approving review before merge.
- **Branch protection configuration** is managed via GitHub REST API (`PUT /repos/{owner}/{repo}/branches/main/protection`). The bypass allowance for `jsondarula` was set via GraphQL mutation on the branch protection rule ID `BPR_kwDOSIPo7s4ElNFj`. Branch protection requires:
  - 8 required status checks (Lint & format, Unit tests, Frozen lockfile check, Test on all 3 OS, Build wheel, Live API tests)
  - Strict status checks (branch must be up-to-date)
  - Enforce admins enabled
  - The `bypass_pull_request_allowances` field is NOT exposed in the GitHub Settings UI for this account tier — it must be set via API.
- **Force pushes** are blocked on `main`.
- **Tags**: `git tag v0.14.78` after every commit (note: `v` prefix on tag, no `v` in VERSION file).
- **Tag + push via PR merge**, not during development. The Release workflow (`release.yml`) auto-creates a GitHub Release when a tag is pushed.

## PyPI Publishing

- **Automatic**: `.github/workflows/python-publish.yml` triggers on tag pushes (`v*`). Builds with `uv build`, publishes with `uv publish`.
- **Required secret**: `PYPI_TOKEN` in GitHub Actions secrets.
- **Manual publish**: `uv build && uv publish` from the repo root.
- **Wheel exclusions**: `tests/` and `experiments/` are excluded from the wheel. Only `src/traderbot/` ships.

### Test File Naming

- **Root-level modules**: `tests/test_<module>.py` (e.g., `src/traderbot/paths.py` → `tests/test_paths.py`)
- **Subpackage modules**: `tests/<subpackage>/test_<module>.py` (e.g., `src/traderbot/kalshi/config.py` → `tests/kalshi/test_config.py`)
- Match the source tree structure one-to-one.

### CLI Test Pattern

Use `CliRunner` from `typer.testing` for all CLI command tests:

```python
from typer.testing import CliRunner
from traderbot.cli import app

runner = CliRunner()

def test_command_help():
    result = runner.invoke(app, ["command", "--help"])
    assert result.exit_code == 0
```

Use `CliRunner.invoke()` for command parsing tests and `subprocess.run()` for end-to-end process tests.

### Live / Integration Tests

Credentials for live API tests are loaded from `.env` at project root (gitignored). Tests that require credentials MUST use the `live` pytest marker:

```python
@pytest.mark.live
def test_kalshi_config_loads_from_env():
    ...
```

- `live` tests are skipped by default in CI (`-m "not live"`)
- Always test the credential-gated path gracefully: if `.env` is missing a key, the test should `pytest.skip("KALSHI_API_KEY not set")` rather than fail
- The `integration_conftest.py` at `tests/integration_conftest.py` provides session-scoped fixtures (`temp_traderbot_env`) that parse credentials and set up a temporary environment — use it for tests that need real Kalshi API access

## Database Integrity

Profile-specific SQLite databases contain all trade positions, decisions, and performance data. Loss or corruption directly breaks agent trading.

**Protection rules:**
- **Never clobber or empty a profile DB**. If a profile's DB path changes (profile rename, re-assign), the old DB must be preserved — never overwritten.
- **Backup before update** — `traderbot update` now automatically backs up all `~/.traderbot/*.db` files to `~/.traderbot/.update_backup/` before any update action. Backups older than 30 days are pruned.
- **Profile DB paths are deterministic**: `get_data_dir() / "paper-{profile_name}" / "db" / "decisions.db"`. Never use a raw `traderbot.db` path when a profile is active — `_resolve_db_path()` redirects to profile-specific DBs.
- **When a profile rename or migration is detected**, verify the new DB path is empty before writing: if the old DB has data and the new path has 0 positions, warn and offer to copy.
- **Manual recovery**: If data is lost, check `~/.traderbot/.update_backup/` for the last backup, or parse SESSION-STATE.md on the agent's workspace for trade logs.

**DB layout:**
- `~/.traderbot/traderbot.db` — global DB (used when no profile is active)
- `~/.traderbot/paper-{profile_name}/db/decisions.db` — profile-specific paper DB
- `~/.traderbot/.update_backup/*.db` — auto-backups from update
- `~/.openclaw/workspace/weather/.traderbot/` — sandbox workspace copy (mirrors host decisions.db)

## Idempotency

All setup and registration operations MUST be idempotent — safe to run twice without side effects or duplication.

- Before creating a resource (cron job, service, agent, profile), remove or replace any existing one with the same name.
- Use `--replace` semantics for cron job registration. If the tooling doesn't support it, add the guard yourself.
- Use existence checks before installing files, creating directories, or adding PATH entries.
- Idempotency failures (duplicate cron jobs, duplicate services) are treated as bugs.

## Resource Lifecycle

Every resource that can be created MUST have a corresponding cleanup path in the uninstall flow.

- **Concrete lifecycle checks before installation**:
  - Docker images: `docker build` → `docker rmi` → `docker builder prune --all`
  - System services: `systemctl enable` → `systemctl disable` + remove unit file
  - Agent workspace files: `propagate_workspace_files` → deleted with `~/.openclaw`
  - Cron jobs: `openclaw cron add` → `openclaw cron remove` (use `--replace`)
  - Symlinks: created at `/usr/local/bin/` and `~/.local/bin/` → removed via `rm -f`
- **Single source of truth**: `traderbot uninstall` (Python CLI) is the canonical teardown. Bash `--uninstall` delegates to it.
- If you add a new resource type, verify the uninstall path handles it before merging.

## Error Handling

- **Custom exceptions**: define domain-specific exceptions in `traderbot/exceptions.py`. All domain exceptions inherit from `TraderBotError` — use `except TraderBotError` to catch the entire domain.
- **Error codes**: every `TraderBotError` subclass has a default numeric error code (see `ErrorCodes` class). `str(exc)` returns `[E{code}] {message}` when code is non-zero. Use `report_error()` from `error_reporter.py` for consistent log-level routing.
- **CLI commands**: use `report_cli_error()` from `cli/helpers.py` which outputs `[red]Error [E{code}]:[/red] {message}` and raises `typer.Exit(1)`. Never use raw `sys.exit(1)` or bare `typer.Exit()`.
- **No silent swallows**: never `except Exception: pass`. At minimum log the error with `logger.exception()` or `logger.error()`. Use `should_silently_fail(module_name)` from `error_reporter.py` for modules that must suppress errors by policy.
- **Retry policy**: transient errors (network, rate limits) retry with exponential backoff before failing. Auth/config errors fail immediately.
- **Error context**: include relevant state information in exception messages (file paths, IDs, return codes). Avoid leaking secrets (tokens, API keys).
- **Chain of trust**: library code raises typed exceptions. CLI code catches and formats them. Never print raw tracebacks to end users.

## Logging

- **Module-level loggers**: every module MUST declare `logger = logging.getLogger(__name__)` at the top. Never use `logging.basicConfig()` — call `configure_root_logger()` from `logging_config.py` once at the CLI entry point.
- **Log levels**: use `logger.exception()` for unexpected failures in `except` blocks (includes traceback). Use `logger.error()` for expected failures. Use `logger.warning()` for degradation. Use `logger.info()` for operational milestones. Use `logger.debug()` for diagnostic detail.
- **Structured logging**: set `TRADERBOT_LOG_FORMAT=json` for JSON output (machine-readable). Default is pipe-delimited. Set `TRADERBOT_LOG_FILE=/path/to/file.log` for file rotation (10MB, 5 backups). Set `TRADERBOT_LOG_LEVELS=module=LEVEL` for per-module level overrides.
- **Correlation IDs**: use `correlation_id(cid)` from `logging_config.py` to trace operations across async module boundaries. The `operation_id` appears in JSON logs and can be read via `operation_id_var.get()`.
- **When diagnosing issues**: always check the logs FIRST. Production logs are in `~/.traderbot/logs/`. Use `TRADERBOT_LOG_LEVELS=traderbot.kalshi=DEBUG,traderbot.risk=DEBUG` to increase verbosity for specific modules without flooding others.
- **Never log secrets**: API keys, tokens, PEM content, and passwords must NEVER appear in log output. Use `SecretStr` fields in Pydantic models and `.get_secret_value()` only in controlled paths.

## Configuration Loading

- **Pattern**: use `pydantic-settings` `BaseSettings` for all configuration classes. Define them in module-level `config.py` files.
- **Entry point**: call `load_dotenv()` exactly once, at the CLI entry point (`traderbot/cli/__init__.py`). Library modules assume env vars are already loaded.
- **Fallback chain**: all credential values resolve via: env var → `.env` file → interactive prompt. Never hard-code defaults for credentials.
- **Validation**: use Pydantic validators on settings fields. Invalid config should fail fast at startup, not silently at runtime.

## Dependencies

- **Adding deps**: `uv add <package>` — this updates both `pyproject.toml` and the lockfile. Commit the lockfile changes.
- **Version policy**: pin minimum versions with `>=`. Avoid ranges wider than minor version unless the API is known unstable.
- **Dev deps**: go in `[dependency-groups] dev` in `pyproject.toml`. Test-only deps don't belong in `[project.dependencies]`.
- **Justification**: before adding a new dependency, consider if stdlib or existing deps can solve the problem. Each new dependency is a maintenance liability.

## Decision Records

Create an ADR in `docs/decisions/` when:

- Choosing between multiple architecture approaches (database, provider, model)
- Making a tradeoff with visible downsides (cost vs latency vs accuracy vs complexity)
- Changing a previously established pattern documented in ADR or AGENTS.md
- Adding a new external dependency with security, permissions, or data impact

Keep ADRs short and factual: Context → Decision → Consequences.

## Changelog

Maintain `CHANGELOG.md` at repo root using Keep a Changelog format.

- Entries grouped by release version, newest first.
- Categories: **Added**, **Changed**, **Fixed**, **Removed**, **Deprecated**.
- Update alongside the VERSION bump on every commit.
- Each entry is a one-liner describing the user-visible impact.

## Dep_Docs Verification Rule

Before implementing anything that touches external APIs (Kalshi, OpenClaw, FRED, NewsAPI, Voyage, CoinGecko):

1. **Check `Dep_Docs/` first** — this directory contains pre-fetched authoritative API documentation. It is the primary source.
2. **Search existing source code** for usage patterns matching the target API
3. Only then use **context7 MCP** or **grep_app** if `Dep_Docs/` is missing coverage or the API version has changed
4. Do NOT spawn a librarian subagent for targeted API verification — that's for deep/broad multi-source research

This prevents implementing against stale assumptions.

## Sandbox Container Architecture

TraderBot agents run inside OpenClaw's Docker sandbox. Key design:

- **Base image**: `python:3.12-slim-bookworm` (not `debian:bookworm-slim` which only has Python 3.11)
- **Bind mounts** are set via `agents.defaults.sandbox.docker.binds` (not `agents.list[N]`)
- **Bind sources outside workspace** require `dangerouslyAllowExternalBindSources: true`
- **traderbot CLI** lives at `/traderbot/.venv/bin` inside the container (not pip-installed in the image)
- **Agent data** is preserved across image rebuilds — data lives on host:
  - `~/.traderbot/` → bind-mounted at `/home/traderbot/.traderbot:rw` (credentials, ChromaDB, positions)
  - `~/.openclaw/workspace/` → bind-mounted at `/workspace:rw` (AGENTS.md, SESSION-STATE.md, MEMORY.md, .learnings/)
  - `~/.openclaw/agents/` → on host only (session logs, cron state)
- **Docker image rebuild** only compiles a fresh base layer — containers are recreated on next agent connection, host bind mounts remain intact
- **Sysadmin (main) runs on host** — `agents.list[0].sandbox.mode: off`

## Update Pipeline Contract

`traderbot update` (Python CLI) and `traderbot-installer.sh --update` both execute this pipeline in order:

1. **pip upgrade** or **git pull** — detects install mode (pip-installed → `pip install --upgrade traderbot`; git-installed → `git pull`)
2. **pip install -e .** (reinstall package, git mode only)
3. **Refresh workspace files** (replace templates, preserve user data)
4. **Rebuild Docker sandbox image** (if Docker available)
5. **Re-apply OpenClaw sandbox config** (binds, dangerouslyAllowExternalBindSources, mode)
6. **Re-register cron jobs** for all deployed agents
7. **Restart OpenClaw gateway** (picks up config changes)

If you add a new OpenClaw config key in the installer, mirror it in `_configure_openclaw_sandbox()` in `src/traderbot/updater.py`.

## Data Source Rate Limiting

External data sources have free-tier rate limits. Current policy:

- **FRED**: 120 req/min free tier. `_backfill_fred()` uses 3-attempt retry with `Retry-After` header backoff. New data sources should follow this pattern.
- **Open-Meteo**: Free, no API key needed. No rate limit issues.
- **CoinGecko**: Tier-dependent (demo/pro). Validated on credential setup.

Harmless errors to ignore:
- `Failed to send telemetry event ClientStartEvent: capture() takes 1 positional argument but 3 were given` — ChromaDB telemetry noise, not a data error
- `HTTP 429` on FRED during initial backfill — retries automatically with backoff
- `ChromaDB telemetry errors` during `data-points` / `news-context` — harmless, data is still queried correctly
