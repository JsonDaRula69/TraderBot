# TraderBot — AI Agent Conventions

This file defines conventions for AI-assisted development of this project. All AI agents working on this codebase must follow these rules.

## Project Identity

- **Name**: TraderBot
- **Language**: Python 3.12+
- **Package manager**: uv
- **Type checking**: Pydantic models for all API data; no `as any`, `# type: ignore`
- **Testing**: pytest with async support
- **Linting**: ruff (formatter + linter)
- **Version**: See `VERSION` file at repo root

## Source of Truth

**`v2docs/`** (in `.autodev/reference/v2docs/`) is the authoritative source for all architecture, API specs, security design, data pipeline, agent lifecycle, and deployment flow. NEVER edit files in `v2docs/` without explicit human approval.

The **v2 decision index** (DD-001 through DD-038) in `v2docs/10-decision-index.md` is the canonical record of all design decisions. Superseded decisions (DD-012, DD-014, DD-024, DD-026) are no longer valid. All implementation must conform to active decisions.

## Documentation Sync (Standing Order)

**Before every `git push`, update all relevant documentation to reflect the changes in that push.** This is a standing order that applies to every push, every time — not just when the user asks.

1. **`v2docs/`** — update any section affected by the changes (architecture, security, tools, deploy, etc.). Keep `v2docs/v2roadmap.md` synced with `v2roadmap.md` (they must be byte-identical).
2. **`v2roadmap.md`** — update the progress tracking section if a milestone, phase, or decision status changed.
3. **GitHub issues** — post a comment on any issue whose status, findings, or blockers are affected by the changes. Link the commit SHA.
4. **`CHANGELOG.md`** — add a one-liner under the current version describing the user-visible impact.
5. **`docs/`** — update any feature/module docs that reference the changed code.

The update must happen BEFORE the push, not after. If documentation cannot be completed before the push, hold the push until it can. Never push code whose documentation is stale.

## Versioning Scheme

- **Format**: `MAJOR.MINOR.PATCH` (e.g. `0.15.00`)
- **Every commit** increments the patch version by 1
- **Milestone releases** increment the minor version and reset patch to 00
- **Major releases** increment the major version and reset minor/patch
- **Version file**: `VERSION` at repo root is the single source of truth — no `v` prefix (hatchling reads it for PyPI publishing)
- **Tags**: Every commit must be tagged with its version (`git tag v0.15.NN`). Tags push on PR merge via the Release workflow, not during development.
- **PyPI**: Tag pushes trigger auto-publish via `.github/workflows/python-publish.yml`

## Git Discipline

- **All commits MUST be made via Pull Requests** — never push directly to main.
- **PR flow**: create branch → commit → push → open PR → wait for CI → merge.
- **CI must pass before merge** — every PR requires green status on: `Lint & format`, `Unit tests`, `Test (ubuntu-latest|macos-latest|windows-latest)`, and `Build wheel`.
- **Branch protection**: `main` is protected — requires CI status checks, up-to-date branch, and enforces admins. Force pushes blocked.
- **One concern per commit** — no mixing features, fixes, and docs in one commit
- **Conventional commits**: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `ci:`, `test:`, `deps:`
- **Never commit** `.env`, credentials, or API keys
- **Version increment**: update `VERSION` (increment PATCH by 1) as part of the commit.
- **Attribution**: every commit includes `Engineered by AutoDev - Powered by Sisyphus` co-author in the description.

## Installation (v2)

**pipx is the sole supported installation method** (DD-001). All previous methods (plain pip, venv, installer script) are retired.

```bash
pipx install traderbot
traderbot deploy
```

The `install/traderbot-installer.sh` and `traderbot bootstrap` commands are retired (DD-001, DD-005). First-time configuration is handled by `traderbot deploy`, which runs the 8-step deploy flow (DD-009):

1. OpenClaw config
2. SysAdmin setup
3. Category selection
4. Infisical and API tokens
5. Database creation
6. Backfill
7. Simulation start (agents begin in backtesting mode)
8. Verification

Full deploy flow details: `v2docs/02-installation-and-deploy.md`.

### Uninstalling

```bash
traderbot uninstall
```

Removes services, data, cron jobs, and OpenClaw state with prompts per category.

### Updating

```bash
traderbot update
```

Pipx-installed → `pipx upgrade traderbot`. Update pipeline details are deferred (per roadmap open items).

## Decision Records

All design decisions are tracked in the v2 decision index (`v2docs/10-decision-index.md`). When a new architectural decision is made:

- Record it as a new DD entry in the decision index
- Update the relevant v2docs section
- Cross-reference dependencies and superseded decisions

Keep decision records short and factual: Context → Decision → Consequences.

## Changelog

Maintain `CHANGELOG.md` at repo root using Keep a Changelog format.

- Entries grouped by release version, newest first.
- Categories: **Added**, **Changed**, **Fixed**, **Removed**, **Deprecated**.
- Update alongside the VERSION bump on every commit.
- Each entry is a one-liner describing the user-visible impact.

## Secrets and Credentials (DD-037)

- **Infisical** is the primary secrets vault (two-project structure: "TraderBot" for API keys, "Agent Tokens" for profile tokens)
- **Never hard-code** credentials or API keys in source files
- **Fallback chain**: Infisical → local encrypted storage → interactive prompt
- **Profile tokens**: Injected via OpenClaw SecretRef, not stored in files inside containers
- **Token rotation**: Every 4 hours via the always-on TraderBot service
- **Validation**: use Pydantic validators on settings fields. Invalid config should fail fast at startup, not silently at runtime.
- **Machine identity**: Infisical machine identity "traderbot-service" with read/write access

## Dependencies

- **Adding deps**: `uv add <package>` — this updates both `pyproject.toml` and the lockfile. Commit the lockfile changes.
- **Version policy**: pin minimum versions with `>=`. Avoid ranges wider than minor version unless the API is known unstable.
- **Dev deps**: go in `[dependency-groups] dev` in `pyproject.toml`. Test-only deps don't belong in `[project.dependencies]`.
- **Justification**: before adding a new dependency, consider if stdlib or existing deps can solve the problem. Each new dependency is a maintenance liability.
- **Optional deps**: Category-specific dependencies (e.g. `cfgrib` for weather backtesting) go in `[project.optional-dependencies]` via `pip install traderbot[weather-backtest]`

## Data Pipeline Constraints (DD-016, DD-027, DD-028)

The unified `data/` module handles all data fetching. Key constraints for any changes touching the data pipeline:

- **WebSocket-first Kalshi data**: REST API only for startup seeding, reconnection recovery, and historical data. REST polling for current market data is a bug.
- **All data sources collect at install time** (DD-027): backfill is not filtered by enabled categories
- **Rate limits must be respected**: each provider has its own rate limit policy
  - FRED: 120 req/min free tier. Use 3-attempt retry with `Retry-After` header backoff.
  - Open-Meteo: Free, no API key needed.
  - CoinGecko: Tier-dependent (demo/pro). Validated on credential setup.
  - NewsAPI: Rate-limited by plan tier.
  - Kalshi: WebSocket handles real-time; REST endpoints have their own rate limits.
- **New data providers** must follow the `BaseDataProvider` ABC pattern in `data/base_provider.py` and register in `data/registry.py`
- **New data providers** must implement rate-limiting consistent with existing providers

## Sandbox Architecture (DD-010, DD-036)

- **Category agents**: Mandatory Docker sandbox (DD-010). No opt-out.
- **SysAdmin**: Unsandboxed (`sandbox.mode: off`), but denied all trading tools (DD-036)
- **Base image**: `python:3.12-slim-bookworm`
- **Bind mounts**: set via `agents.defaults.sandbox.docker.binds`
- **Agent data** is preserved across image rebuilds — data lives on host, not in the container image
- **Profile tokens** injected via OpenClaw SecretRef — NOT in files inside containers

## Dep_Docs Verification Rule

Before implementing anything that touches external APIs (Kalshi, OpenClaw, FRED, NewsAPI, Voyage, CoinGecko):

1. **Check `.autodev/reference/` first** — contains pre-fetched authoritative API documentation for all dependencies.
2. **Search existing source code** for usage patterns matching the target API
3. Only then use **context7 MCP** or **grep_app** if reference docs are missing coverage or the API version has changed

This prevents implementing against stale assumptions.
