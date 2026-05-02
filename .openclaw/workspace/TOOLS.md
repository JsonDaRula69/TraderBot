# TOOLS.md - Local Notes

_Skills define how tools work. This file is for our setup specifics._

> **⚠️ STRICTLY FORBIDDEN: Modifying this file, AGENTS.md, or SOUL.md requires explicit human approval. These are immutable operating constraints. Never edit them without being asked.**

## TraderBot CLI

- **Binary**: `traderbot` (installed via `uv` or `pip install -e .`)
- **Python**: 3.12+
- **Config**: `.env` file (never committed) with `KALSHI_API_KEY`, `KALSHI_PRIVATE_KEY`
- **Demo mode**: `KALSHI_DEMO=true` routes to `demo-api.kalshi.co` (fake money)

## Environment

- **DB**: SQLite at `traderbot.db` (in workspace)
- **ChromaDB**: Local instance for vector embeddings (graceful fallback if unavailable)
- **Voyage AI**: Embedding API (graceful fallback to VADER/TextBlob if unavailable)

## Key Commands

| What | Command |
|---|---|
| Market scan | `traderbot scan --json` |
| Analyze market | `traderbot analyze TICKER --json` |
| Place trade | `traderbot trade TICKER --direction yes --quantity N --price CENTS --json` |
| Check positions | `traderbot positions --json` |
| Self-review | `traderbot heartbeat --json` |
| Circuit breaker | `traderbot halt` |
| News check | `traderbot news --json` |
| Sentiment | `traderbot sentiment --ticker TICKER --json` |

## Gotchas

- `traderbot trade` requires price in **cents** (int), not dollars
- Circuit breaker at HALT/FULL_STOP blocks all new trades
- `--json` flag is required for machine-readable output
- Bayesian adaptation has a 4-update/day cooldown — don't expect updates every heartbeat