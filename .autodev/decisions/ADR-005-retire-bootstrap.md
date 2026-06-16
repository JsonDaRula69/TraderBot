# ADR-005: Retire bootstrap, rename to deploy

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-005
**Tags:** cli, deployment, naming

## Context

The existing `traderbot bootstrap` command conflicts with OpenClaw's unrelated bootstrap function and creates naming confusion.

## Decision

Remove `traderbot bootstrap`. First-time configuration is now `traderbot deploy`. No `--full` flag — deploy always runs the complete wizard.

## Consequences

- `traderbot bootstrap` command removed from CLI
- `admin.py` loses the bootstrap command registration
- `traderbot deploy` is the single entry point for first-time setup
- The deploy flow follows the 8-step process defined in DD-009

## Notes for AutoDev Agents

Any references to `bootstrap` in the existing codebase must be replaced with `deploy`. The CLI command is `traderbot deploy`, not `traderbot setup` or `traderbot bootstrap`. Setup steps are internally called "setup steps" but the user-facing command is `deploy`.
