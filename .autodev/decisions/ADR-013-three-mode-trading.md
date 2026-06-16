# ADR-013: Three-mode trading — backtesting/paper/live

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-013
**Tags:** trading, modes, backtesting, paper, live

## Context

Agents need a progression path from unproven to live trading. Direct deployment to live is dangerous. A backtesting mode validates the agent's decision-making on historical data before any real money is at stake.

## Decision

Three trading modes: backtest → paper → live → (suspended). Each mode has its own isolated database. The same MCP tools work across all modes — routing happens on the backend based on the agent's profile.

## Consequences

- Backtest mode: simulated fills on historical data, no real API calls
- Paper mode: simulated fills with slippage model, no real money at risk
- Live mode: real API calls to Kalshi, real money
- Suspended: agent is paused, no trading
- Mode transitions are managed by SysAdmin (DD-017, DD-023)
- Per-agent per-mode SQLite isolation (DD-032)

## Notes for AutoDev Agents

The MCP server routes tool calls based on profile token → profile → mode. Agents never need to know their mode — the same tool calls work regardless. PaperSlippageModel adds realistic slippage in paper mode (DD-021). SysAdmin activates cron/heartbeat jobs phase by phase (DD-023).
