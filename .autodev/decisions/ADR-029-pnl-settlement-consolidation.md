# ADR-029: P&L and settlement logic consolidation

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-029
**Tags:** trading, pnl, settlement, architecture

## Context

P&L calculation and position settlement logic was scattered across multiple modules. This created inconsistency risks and made it hard to reason about trading outcomes.

## Decision

Consolidate all P&L and settlement logic into a single `trading.py` module. Two unified functions: `compute_pnl()` and `settle_position()`. These handle all modes (backtest, paper, live).

## Consequences

- Single source of truth for P&L calculation
- Single source of truth for position settlement
- All modes use the same functions, routing happens at call site
- Backtesting and paper modes use simulated fills through these same functions

## Notes for AutoDev Agents

Never implement P&L or settlement logic outside of `trading.py`. If you need to calculate profit or settle a position, use `compute_pnl()` and `settle_position()`. This is a money-handling function — dedicated tests with known inputs and expected outputs are mandatory (standing order #4).
