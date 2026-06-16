# ADR-023: SysAdmin cron/heartbeat activation protocol

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-023
**Tags:** sysadmin, cron, heartbeat, lifecycle

## Context

Cron and heartbeat jobs should not be registered at deploy time. Different phases of the agent lifecycle require different scheduled tasks.

## Decision

Cron and heartbeat jobs are designed as templates and deployed along with SysAdmin, but remain dormant until SysAdmin activates them. SysAdmin follows a predefined activation protocol for each phase transition.

## Consequences

- SysAdmin starts with oversight jobs only (health check, error logging)
- Backtesting phase adds backtest oversight jobs
- Paper phase adds paper oversight and decision-loop jobs
- Live phase adds live oversight and trading jobs
- One-shot bootstrap job triggers the initial activation protocol
- Custom jobs follow `sysadmin-custom-*` naming convention

## Notes for AutoDev Agents

Never register cron/heartbeat jobs at deploy time. They must be activated by SysAdmin as part of the lifecycle protocol. The `traderbot cron activate --role <agent> --phase <phase>` command is the activation mechanism.
