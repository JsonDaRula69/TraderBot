# TraderBot — AI Agent Conventions

This file defines conventions for AI-assisted development of this project. All AI agents working on this codebase must follow these rules.

## Project Identity

- **Name**: TraderBot
- **Language**: Python 3.12+
- **Package manager**: uv (preferred) or pip
- **Type checking**: Pydantic models for all API data; no `as any`, `# type: ignore`
- **Testing**: pytest with async support
- **Linting**: ruff (formatter + linter)
- **Current version**: v0.11.55

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

## API Verification Protocol

Before making any code changes that involve OpenClaw, Kalshi, or any other external API/service:

1. **Verify your assumptions first** — do not assume you know the correct function names, parameters, or behavior
2. Use the **context7 MCP** to find first-party documentation for the API or library
3. Use the **grep_app tool** to find real-world usage examples in open-source code
4. **Do NOT spawn a librarian subagent** for this — that is for deep/broad research across multiple sources. For targeted API verification, use context7 + grep_app directly
5. Only proceed with implementation once you've confirmed the correct API surface

This prevents recurring issues from implementing against assumed APIs that don't match reality.

## Decision Records

Record non-obvious decisions in `docs/decisions/` as ADRs when:
- Choosing between multiple approaches
- Making a tradeoff with visible downsides
- Deviating from established patterns