# ADR-009: 8-step deploy flow

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-009
**Tags:** deployment, setup, cli, flow

## Context

The first-time configuration process needs a clear sequential flow ensuring each step's prerequisites are met before proceeding.

## Decision

Deploy follows this exact order:
1. **OpenClaw config** — Configure LLM model/provider, gateway, daemon, comms channels. Create the `main` agent.
2. **SysAdmin setup** — Inject workspace files, register cron/heartbeat jobs, authenticate with TraderBot.
3. **Category selection** — For each category: create agent, inject workspace, register heartbeat, authenticate. Then `openclaw doctor`.
4. **API tokens** — Prompt for tokens relevant to selected categories. Infisical health check (DD-037).
5. **Database creation** — Per-agent per-mode SQLite databases. Shared ChromaDB with category filtering.
6. **Backfill** — All data sources begin collection at install time (DD-027). Kalshi historical data.
7. **Simulation start** — Agents begin in backtesting mode (DD-017). NOT paper trading.
8. **Verify** — Health check, connection test, cron verification.

## Consequences

- Each step is idempotent (DD-013)
- Step 2 sets up SysAdmin which manages all subsequent activation (DD-023)
- Step 7 starts backtesting, NOT paper trading (reconciled from original DD-009)
- Step 4 uses Infisical, not 1Password (superseded by DD-037)

## Notes for AutoDev Agents

This is the deploy flow. It must be followed exactly. Step ordering matters because later steps depend on earlier ones. The `traderbot deploy` CLI command implements this flow. Each step must be individually re-runnable.
