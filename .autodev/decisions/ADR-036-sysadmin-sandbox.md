# ADR-036: SysAdmin sandbox — unsandboxed with principled restrictions

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-036
**Tags:** sysadmin, sandbox, security, agents

## Context

SysAdmin needs broad access for fleet management and self-improvement coordination, but must not be able to trade.

## Decision

SysAdmin runs unsandboxed (sandbox.mode: off) on the host, like a regular OpenClaw agent. Principled restrictions replace sandboxing:

- **No trading tools**: `traderbot__trade`, `traderbot__scan`, `traderbot__analyze`, and all category-specific tools are in its `deny` list
- **Workspace file immutability**: Core workspace files cannot be edited
- **Lifecycle confirmation required**: Promoting from paper to live requires explicit confirmation
- **Read access to everything**: `enabled_categories: []` gives access to all data sources

## Consequences

- SysAdmin has full read access to all categories and data
- SysAdmin cannot execute trades or modify its own workspace instructions
- SysAdmin manages agent lifecycle transitions but cannot bypass confirmation
- SysAdmin uses `sessions_spawn`, `sessions_send`, `sessions_yield` for debate coordination (DD-038)

## Notes for AutoDev Agents

SysAdmin's tool restrictions are enforced at the MCP level, not just at the workspace instruction level. When implementing SysAdmin tools, never add trading capabilities. The `deny` list is the authoritative enforcement mechanism.
