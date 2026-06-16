# ADR-019: Time-lapse behavioral simulation for backtesting

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-019
**Tags:** backtesting, simulation, testing, agents

## Context

Statistical replay of historical data is insufficient. Agents make decisions based on their perceptions of market conditions, not just numerical inputs. A behavioral simulation must exercise the agent's actual decision-making process on historical data.

## Decision

Backtesting is time-lapse behavioral simulation, not just statistical replay. The simulation engine drives the agent through historical time periods, feeding it historical data and recording its decisions. The agent makes real decisions on simulated data.

## Consequences

- Simulation engine manages time progression, data feeding, and fill simulation
- Agent receives historical data as if it were live
- Decisions are recorded with full context for later analysis
- The same MCP tools work in backtest mode (DD-013)
- Backtest mode uses separate per-agent databases (DD-032)

## Notes for AutoDev Agents

The simulation engine must be faithful to historical conditions. If an agent would have made a decision on June 15th at 10am, the simulation must provide the data that was available at that exact time. This means the data pipeline must store historical data with timestamps and the simulation must replay it in chronological order.
