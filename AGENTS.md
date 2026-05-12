# TraderBot — AI Agent Conventions

This file defines conventions for AI-assisted development of this project. All AI agents working on this codebase must follow these rules.

## Project Identity

- **Name**: TraderBot
- **Language**: Python 3.12+
- **Package manager**: uv (preferred) or pip
- **Type checking**: Pydantic models for all API data; no `as any`, `# type: ignore`
- **Testing**: pytest with async support
- **Linting**: ruff (formatter + linter)
- **Current version**: v0.08.21

## Versioning Scheme

- **Format**: `MAJOR.MINOR.PATCH` (zero-padded: `0.00.01`)
- **Every commit** increments the patch version by 1 (0.00.01 → 0.00.02 → 0.00.03 …)
- **Milestone releases** increment the minor version and reset patch to 00 (0.00.99 → 0.01.00)
- **Major releases** increment the major version and reset minor/patch (1.00.00)
- **Tags**: Every commit must be tagged with its version (`git tag v0.00.0N`)
- **Version file**: `VERSION` file at repo root contains the current version string

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
- No real-money API calls in tests — demo API calls are allowed, marked with `@pytest.mark.live`
- All trade decisions must be logged with full reasoning in the audit trail
- All Pydantic models MUST use `ConfigDict(strict=True, extra="forbid")` — including `BaseSettings` subclasses
- All monetary values in cents as `int` — never `float`

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

## Profile-Aware Trading

Multi-agent deployment uses profiles to isolate agent configurations. When `TRADERBOT_PROFILE_TOKEN` is set in the environment, the CLI resolves it to a `TradingProfile` and applies profile-specific risk limits and category filters.

### Profile Token Resolution

The token is resolved at CLI startup:

```python
profile = get_current_profile()  # Reads TRADERBOT_PROFILE_TOKEN env var
```

If the token is valid, the profile's risk parameters are used for `evaluate_trade()`. If no token is set, `HARD_LIMITS` apply as defaults.

### Profile Constraints

When a profile is active:

- **Category filtering**: Markets not in `enabled_categories` are rejected before any sizing
- **Position ceiling**: `AgentRiskLimits.max_position_per_market_pct` enforces `min(profile_limit, HARD_LIMITS)`
- **Risk multiplier**: `profile.risk_multiplier` scales final position size downward
- **Data isolation**: DB, ChromaDB, and audit paths use `profile.base_dir`

### What Profiles Cannot Do

Profiles cannot exceed `HARD_LIMITS` ceilings. `AgentRiskLimits` enforces this at runtime. An agent running with a permissive profile cannot exceed hard limits.

### Credential Isolation

Each profile has its own keyring namespace: `traderbot.profiles.<profile_name>.<service>`. Credentials stored under a profile are not accessible to other profiles or the global namespace.

## Decision Records

Record non-obvious decisions in `docs/decisions/` as ADRs when:
- Choosing between multiple approaches
- Making a tradeoff with visible downsides
- Deviating from established patterns