# BetBot — AI Agent Conventions

This file defines conventions for AI-assisted development of this project. All AI agents working on this codebase must follow these rules.

## Project Identity

- **Language**: Python 3.12+
- **Package manager**: uv (preferred) or pip
- **Type checking**: Pydantic models for all API data; no `as any`, `# type: ignore`
- **Testing**: pytest with async support
- **Linting**: ruff (formatter + linter)

## Architecture Constraints

- The **risk module is immutable** — never modify hard limits without explicit human approval
- The **toolkit never decides strategy** — it computes, enforces, and executes, but the agent decides
- No API keys in code — use environment variables or `.env` files (never committed)
- All trade decisions must be logged with full reasoning in the audit trail

## Code Style

- Use Pydantic v2 models for all data structures
- Prefer `async` for I/O-bound operations (Kalshi API calls, WebSocket streams)
- Prefer `sync` for CPU-bound analysis (statistics, indicators)
- Document every public function with a one-line docstring
- No AI slop: no obvious comments (`# increment counter`), no boilerplate docstrings that restate the function name

## File Organization

- `src/betbot/kalshi/` — exchange adapter (API-specific code)
- `src/betbot/analysis/` — pure computation (no I/O)
- `src/betbot/risk/` — enforcement layer (no strategy logic)
- `src/betbot/simulation/` — backtesting engine
- `src/betbot/news/` — external data pipeline
- `src/betbot/db/` — persistence layer

## Git Conventions

- Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`
- One concern per commit
- Never commit `.env`, credentials, or API keys
- Semantic versioning on tags

## Decision Records

Record non-obvious decisions in `docs/decisions/` as ADRs when:
- Choosing between multiple approaches
- Making a tradeoff with visible downsides
- Deviating from established patterns