# ADR-010: Mandatory Docker sandbox for category agents

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-010
**Tags:** docker, sandbox, security, agents, isolation

## Context

Category agents (weather, economics, etc.) execute arbitrary code from data sources and LLM outputs. Without sandboxing, a compromised agent could access other agents' data or the host system.

## Decision

All category agents run in Docker containers. This is mandatory — no opt-out. SysAdmin runs unsandboxed on the host (DD-036).

## Consequences

- Base image: `python:3.12-slim-bookworm`
- Bind mounts: agent data dir (RW), workspace files (RO), TRADERBOT_PROFILE_TOKEN via SecretRef
- No API tokens or secrets inside containers — only profile tokens
- Network access is controlled by the sandbox configuration
- Docker setup is a step in `traderbot deploy` (DD-003)
- SysAdmin has `sandbox.mode: off` (DD-036)

## Notes for AutoDev Agents

This is a hard security constraint. Never implement a way to bypass the Docker sandbox for category agents. The MCP server enforces category access control (DD-011). If you need to debug a category agent, use Docker exec, not unsandboxed execution.
