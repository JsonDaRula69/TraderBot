# TraderBot — AI Agent Conventions

This file defines conventions for AI-assisted development of this project. All AI agents working on this codebase must follow these rules.

## Project Identity

- **Name**: TraderBot
- **Language**: Python 3.12+
- **Package manager**: uv
- **Type checking**: Pydantic models for all API data; no `as any`, `# type: ignore`
- **Testing**: pytest with async support
- **Linting**: ruff (formatter + linter)
- **Current version**: 0.14.74

## Versioning Scheme

- **Format**: `MAJOR.MINOR.PATCH` (e.g. `0.14.74`)
- **Every commit** increments the patch version by 1 (0.14.73 → 0.14.74 → 0.14.75 …)
- **Milestone releases** increment the minor version and reset patch to 00 (0.14.99 → 0.15.00)
- **Major releases** increment the major version and reset minor/patch (1.0.0)
- **Tags**: Every commit must be tagged with its version (`git tag v0.14.74`)
- **Version file**: `VERSION` at repo root is the single source of truth — no `v` prefix (hatchling reads it for PyPI publishing)
- **PyPI**: Tag pushes trigger auto-publish via `.github/workflows/python-publish.yml`

## Git Discipline

- **All commits MUST be made via Pull Requests** — never push directly to main. This ensures CI runs on every change and provides full traceability.
- **PR flow**: create branch → commit → push → open PR → wait for CI → merge.
- **CI must pass before merge** — every PR requires green status on: `Lint & format`, `Unit tests`, `Test (ubuntu-latest|macos-latest|windows-latest)`, and `Build wheel`.
- **Auto-merge for human operator** (`jsondarula`): bypasses PR review requirement (branch protection is configured with bypass allowance). PRs from `jsondarula` can be merged once CI passes without additional review.
- **External contributors** require 1 approving review before merge.
- **Branch protection**: `main` is protected — requires CI status checks, up-to-date branch, and enforces admins. Force pushes are blocked.
- **One concern per commit** — no mixing features, fixes, and docs in one commit
- **Conventional commits**: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `ci:`, `test:`, `deps:`
- **Always tag**: `git tag v0.14.78` after every commit (note: `v` prefix on tag, no `v` in VERSION file)
- **Tag + push via PR merge**, not during development. Tags are pushed when the PR is merged to main.
- **Never commit** `.env`, credentials, or API keys
- **Version increment**: update `VERSION` (increment PATCH by 1) as part of the commit — never as a separate step
- **Sisyphus attribution**: every commit includes ultrawork attribution in the description:
  ```bash
  git commit -m "type: message" \
    -m "Ultraworked with [Sisyphus](https://github.com/code-yeongyu/oh-my-openagent)" \
    -m "Co-authored-by: Sisyphus <clio-agent@sisyphuslabs.ai>"
  ```

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

## Testing Discipline

- **Run before commit**: execute `uv run pytest -m "not live"` before every commit. All tests must pass.
- **Markers**: use the standard marker taxonomy defined in `pyproject.toml`:
  - `unit` — pure unit tests with no external dependencies (fastest)
  - `integration` — tests with mocked external services
  - `live` — tests that hit real API endpoints (skipped in CI, requires credentials)
  - `slow` — tests excluded from fast runs
- **CI pipeline** (`.github/workflows/ci.yml`), layered in this order:
  1. `frozen-check`: validates lockfile is fresh (`uv sync --frozen`)
  2. `lint`: ruff lint + format
  3. `unit`: fast unit tests only (`-m "unit"`) — gates subsequent jobs
  4. `test`: full matrix (ubuntu/macos/windows) — `-m "not live"`
  5. `live`: API smoke tests (Kalshi, Open-Meteo, CoinGecko, TheSportsDB, OpenWeatherMap, FRED, NewsAPI, VoyageAI, Google Trends) — runs on push to main + weekly. Skipped on fork PRs (secrets unavailable).
  6. `build`: builds wheel + verifies `pip install` works
- **Pull requests trigger the full pipeline** (lint → unit → matrix → build).
- **Push to main** runs the same pipeline. Doc-only changes are skipped via `paths-ignore`.
- **Weekly schedule** (Mondays 06:00 UTC) runs the full pipeline + CodeQL.
- **Live tests** run on push to main and weekly schedule — skipped on PRs (fork PRs lack secrets).
- **Concurrency**: in-progress runs are automatically cancelled when a new push arrives.
- **Coverage**: new code should maintain or improve module-level coverage. Uploaded to Codecov on Linux.
- **Adding new API tests**: when adding a new API-dependent feature, add a `@pytest.mark.live` test AND wire the required secret in `.github/workflows/ci.yml`. The CI workflow is the single source of truth for which secrets are tested.

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

- **Custom exceptions**: define domain-specific exceptions in `traderbot/exceptions.py`. Prefer typed exceptions over `Exception` or string returns.
- **CLI commands**: use `typer.Exit(1)` with a descriptive `[red]Error:[/red]` rich message. Never let unhandled exceptions bubble to the user raw.
- **No silent swallows**: never `except Exception: pass`. At minimum log the error. Use broad catches only at module boundaries (e.g., subprocess calls to external tools).
- **Retry policy**: transient errors (network, rate limits) retry with exponential backoff before failing. Auth/config errors fail immediately.
- **Error context**: include relevant state information in exception messages (file paths, IDs, return codes). Avoid leaking secrets (tokens, API keys).
- **Chain of trust**: library code raises typed exceptions. CLI code catches and formats them. Never print raw tracebacks to end users.

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
