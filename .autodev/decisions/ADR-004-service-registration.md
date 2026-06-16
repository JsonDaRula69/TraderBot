# ADR-004: Service registration in setup

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-004
**Tags:** service, systemd, launchd, setup, deployment

## Context

TraderBot runs as an always-on daemon (DD-016). Service registration must happen during setup, not as a separate manual step.

## Decision

Service/cron registration happens inside `traderbot setup`. Service templates (systemd units, launchd plists, Task Scheduler tasks) are package data files read via `importlib.resources` (DD-007) and deployed by Python code.

## Consequences

- `traderbot cron setup` is called internally by setup, not separately
- Data pipeline timer installation is part of setup
- Shell install scripts are retired — logic moves to Python
- Path substitution uses `{placeholder}` syntax resolved via `shutil.which('traderbot')` (DD-022)

## Notes for AutoDev Agents

Service templates must use `{placeholder}` syntax for paths, resolved at deploy time. All operations must be idempotent (DD-013). Every resource must have a cleanup path in uninstall.
