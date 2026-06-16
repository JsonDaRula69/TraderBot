# ADR-021: Paper trading — simulated fills, three-mode DB isolation

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-021
**Tags:** paper-trading, simulation, database, isolation

## Context

Paper trading must be indistinguishable from live trading from the agent's perspective, while keeping data isolated between modes.

## Decision

Paper trading uses the same MCP tools as live trading. The MCP server routes on the backend based on the agent's profile mode. Paper mode uses a PaperSlippageModel for fill simulation. Each mode has its own SQLite database.

## Consequences

- Agents never need to know their mode (DD-009)
- PaperSlippageModel adds realistic slippage to simulated fills
- Per-agent per-mode SQLite databases (DD-032)
- Paper mode makes no real API calls to Kalshi
- Paper mode records all trades for later analysis

## Notes for AutoDev Agents

The PaperSlippageModel is critical for realistic paper trading. It must account for market impact, bid-ask spread, and fill delays. The `compute_pnl()` and `settle_position()` functions (DD-029) handle settlement for all modes.
