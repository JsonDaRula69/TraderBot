# ADR-002: OpenClaw is a hard dependency

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-002
**Tags:** openclaw, architecture, dependency

## Context

TraderBot needs an agent runtime for LLM orchestration, session management, cron scheduling, and channel integration. OpenClaw provides all of these.

## Decision

OpenClaw is a hard dependency. TraderBot cannot run without it. TraderBot provides tools and data via MCP; OpenClaw provides the agent runtime.

## Consequences

- `traderbot setup` verifies OpenClaw is installed before proceeding
- All agent lifecycle management (sessions, cron, heartbeat) goes through OpenClaw
- OpenClaw is NOT a trust boundary — TraderBot enforces auth and access control itself (DD-012 → DD-037)
- No standalone mode exists

## Notes for AutoDev Agents

This is a fundamental architecture constraint. TraderBot's MCP server connects to OpenClaw via stdio. The Dev-Liaison agent (DD-034) uses OpenClaw's webhook system to communicate with AutoDev. Never implement features that bypass OpenClaw for agent management.
