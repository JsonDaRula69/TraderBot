# ADR-031: Module-by-module review findings

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-031
**Tags:** architecture, review, refactoring, modules

## Context

A systematic review of each module identified inconsistencies, circular dependencies, and architectural issues that needed to be resolved for v2.

## Decision

The review covered: simulation, profiles, kalshi, analysis, risk, CLI, experiment, and DB modules. Key findings:
- Risk module needs consolidation (scattered risk checks)
- CLI has circular imports (resolved by DD-030)
- Analysis module needs category-specific toolkits (DD-035)
- Experiment module needs integration with agent-debate framework (DD-038)
- DB needs per-agent per-mode isolation (DD-032)

## Consequences

- Module restructuring follows the decisions above
- Each module reviewed has specific action items documented in the roadmap
- P&L consolidation is a cross-cutting concern (DD-029)

## Notes for AutoDev Agents

When working on a specific module, review the DD-031 findings for that module first. The findings are in the v2roadmap.md under the DD-031 section. They inform what needs to change and what must be preserved.
