# ADR-011: Per-agent data source access control

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-011
**Tags:** security, mcp, data, isolation, agents

## Context

Each category agent should only access data relevant to its category. A weather agent should not see economics data, and vice versa.

## Decision

Category filtering at CLI/MCP level. `enabled_categories` on agent profiles determines which data sources and MCP tools each agent can access. The MCP server enforces this filtering on every tool call.

## Consequences

- Agent profile has `enabled_categories` field (empty for SysAdmin = all access)
- MCP tools are namespaced by category (DD-035): `traderbot__weather_*`, `traderbot__economics_*`, etc.
- OpenClaw `alsoAllow` filtering restricts which MCP tools each agent sees
- Database access is per-agent per-mode (DD-032)
- ChromaDB uses category metadata filtering

## Notes for AutoDev Agents

Enforcement happens at two levels: MCP server (which tools are available) and OpenClaw (which tools are in the agent's allowlist). Both must be consistent. SysAdmin has `enabled_categories: []` which gives access to all categories but is denied trading tools (DD-036).
