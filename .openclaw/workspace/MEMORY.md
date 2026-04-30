# MEMORY.md

_Long-term curated memory. Distilled from daily logs in `memory/`._

## Key Decisions

- 2026-04-30: Multi-agent profile system deployed — each agent gets isolated data dirs, risk params capped by HARD_LIMITS
- 2026-04-30: Auto-update system added — checks GitHub on startup and every 6h, configurable via `traderbot update configure`

## Patterns Observed

- Market spreads widen 5-10 min before close — avoid entry during spread widening

## Lessons Learned

- PEP 668 blocks system-wide pip installs on Ubuntu 24.04+ — always use venv
- `Path(".traderbot")` is relative to CWD, not `~` — always use `Path.home() / ".traderbot"` for data paths
- LEARNINGS.md deduplication was missing — same entries were appended every heartbeat cycle

## People

(No contacts yet)

## Projects

- TraderBot v0.08.63 — multi-agent trading platform on Kalshi