# ADR-025: MCP identity resolution and tool filtering

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-025
**Tags:** mcp, auth, security, identity, tokens

## Context

MCP tool calls need to know which agent is making the call and what permissions that agent has. The identity and authorization mechanism must be secure and verifiable.

## Decision

Profile tokens serve as explicit MCP tool parameters. The server resolves token → profile → categories → mode → permissions on every call. OpenClaw's `alsoAllow` filtering restricts which tools each agent can see.

## Consequences

- Every MCP tool call includes a `token` parameter
- Server resolves: token → profile → categories, mode, permissions
- Invalid tokens return authentication errors
- Category filtering is enforced at the MCP level (DD-011)
- OpenClaw is NOT a trust boundary — TraderBot MCP server enforces everything

## Notes for AutoDev Agents

Profile tokens are provisioned via Infisical (DD-037). They are NOT API keys — they are scoped tokens that identify the agent and its permissions. Never store tokens in source code. Use OpenClaw's SecretRef mechanism for token injection.
