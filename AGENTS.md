# TraderBot — AI Agent Conventions

This file defines conventions for AI-assisted development of this project. All AI agents working on this codebase must follow these rules.

## Project Identity

- **Name**: TraderBot
- **Language**: Python 3.12+
- **Package manager**: uv
- **Type checking**: Pydantic models for all API data; no `as any`, `# type: ignore`
- **Testing**: pytest with async support
- **Linting**: ruff (formatter + linter)
- **Current version**: v0.13.52

## Versioning Scheme

- **Format**: `MAJOR.MINOR.PATCH` (zero-padded: `v0.00.01`)
- **Every commit** increments the patch version by 1 (v0.00.01 → v0.00.02 → v0.00.03 …)
- **Milestone releases** increment the minor version and reset patch to 00 (v0.00.99 → v0.01.00)
- **Major releases** increment the major version and reset minor/patch (v1.00.00)
- **Tags**: Every commit must be tagged with its version (`git tag v0.00.0N`)
- **Version file**: `VERSION` at repo root is the single source of truth — update it before every commit

## Git Discipline

- **Commit early and often** — every code change gets its own commit and push
- **One concern per commit** — no mixing features, fixes, and docs in one commit
- **Conventional commits**: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`
- **Always tag**: `git tag v0.00.0N` after every commit
- **Always push**: commit + tag + push in one step: `git add . && git commit -m "type: msg" && git tag v0.00.0N && git push && git push --tags`
- **Never commit** `.env`, credentials, or API keys
- **Traceability**: every change is recoverable; rollback is always one `git revert` away

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
- **Coverage**: new code should maintain or improve module-level coverage. Existing gaps don't justify widening them.
- **Fixtures**: use shared fixtures from `tests/conftest.py` and `tests/news/conftest.py`. Don't duplicate fixture setup across test files.
- **Parity**: bug fixes must include a regression test. New features must include tests for the public API surface.
- **Pattern**: prefer `MockDataProvider` over monkeypatching HTTP calls. Use `respx` (available in dev deps) for HTTP-level mocking when needed.

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

## API Verification Protocol

Before making any code changes that involve OpenClaw, Kalshi, or any other external API/service:

1. **Verify your assumptions first** — do not assume you know the correct function names, parameters, or behavior
2. Use the **context7 MCP** to find first-party documentation for the API or library
3. Use the **grep_app tool** to find real-world usage examples in open-source code
4. **Do NOT spawn a librarian subagent** for this — that is for deep/broad research across multiple sources. For targeted API verification, use context7 + grep_app directly
5. Only proceed with implementation once you've confirmed the correct API surface

This prevents recurring issues from implementing against assumed APIs that don't match reality.
