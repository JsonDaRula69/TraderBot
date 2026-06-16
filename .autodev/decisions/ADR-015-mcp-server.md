# ADR-015: TraderBot as MCP server with OpenClaw gateway

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-015
**Tags:** mcp, openclaw, architecture, tools

## Context

Agents need to interact with TraderBot's data pipeline, trading tools, and analysis capabilities. The integration point must be clean and allow per-agent access control.

## Decision

TraderBot registers as an MCP server via the OpenClaw gateway. Agents call TraderBot tools through MCP. The MCP server resolves the profile token on every call and enforces category access control.

## Consequences

- TraderBot MCP server communicates with OpenClaw via stdio
- Profile tokens are explicit tool parameters (DD-025)
- MCP tools are namespaced by category (DD-035)
- OpenClaw is NOT a trust boundary — TraderBot enforces auth (DD-037)
- The MCP server is started by OpenClaw, not independently

## Notes for AutoDev Agents

This is a core architectural constraint. TraderBot is not a REST API or CLI tool for agents — it's an MCP server. All agent interactions with TraderBot data and trading happen through MCP tool calls. The profile token is the authentication mechanism, not an API key.
