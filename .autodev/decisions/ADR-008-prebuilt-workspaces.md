# ADR-008: Prebuilt agent workspaces — no customization

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-008
**Tags:** agents, workspace, immutability

## Context

TraderBot previously allowed users to customize agent behavior. This created variability, user error, and made fleet-wide behavior tuning impossible.

## Decision

Agent workspace files (AGENTS.md, SOUL.md, TOOLS.md, IDENTITY.md, HEARTBEAT.md) are immutable templates shipped with the package. Users cannot modify core workspace files. `traderbot deploy` injects them into the correct OpenClaw workspace directories.

## Consequences

- Workspace templates live in `src/traderbot/workspace/` as package data
- Category-specific variants (weather/AGENTS.md, etc.) are selected based on the agent's assigned categories
- Injection logic (`profiles/injection.py`) is simplified — no user customization, just template deployment
- Fine-tuning of agent behavior is done by the TraderBot team, not end users

## Notes for AutoDev Agents

This is a hard constraint. When implementing workspace files, they must be shipped as package data. The `profiles/injection.py` module deploys them during `traderbot deploy`. Category variants exist as subdirectories (e.g., `workspace/weather/AGENTS.md`). Never add user customization hooks to workspace files.
