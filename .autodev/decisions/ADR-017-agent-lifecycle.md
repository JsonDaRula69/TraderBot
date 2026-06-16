# ADR-017: Agent lifecycle — backtesting → paper → live → suspended

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-017
**Tags:** agents, lifecycle, backtesting, paper, live, sysadmin

## Context

Agents need a controlled progression from untested to live trading. Automated promotion is dangerous — human judgment is needed for phase transitions.

## Decision

Four states: BACKTESTING → PAPER → LIVE → SUSPENDED. SysAdmin manages all transitions. Agents start in backtesting. Cron/heartbeat jobs are not registered at deploy time — SysAdmin activates them phase by phase.

## Consequences

- Backtesting: simulated fills on historical data, no real money
- Paper: simulated fills with slippage, no real money
- Live: real Kalshi API calls, real money
- Suspended: agent paused, no trading
- Promotion requires explicit SysAdmin confirmation (DD-036)
- Suspension can be immediate but must log reason and trigger investigation
- Each phase has its own set of cron/heartbeat jobs (DD-023)

## Notes for AutoDev Agents

This is a safety-critical decision. Never automate phase transitions. The deployment bar (exact metrics for backtest→paper and paper→live) is still TBD — SysAdmin uses judgment plus data. The `traderbot profile update <agent> --mode <mode>` command is the transition mechanism.
