# ADR-034: Dev-Liaison — TraderBot subject matter expert and AutoDev liaison

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-034
**Tags:** agents, liaison, autodev, bridge, communication

## Context

Layer 3 (AutoDev) needs a bridge to the TraderBot agent team. Someone needs to provide architecture expertise, assess feasibility, and coordinate between the two systems.

## Decision

Dev-Liaison is a named agent running on the OpenClaw gateway alongside TraderBot agents. It is a specialist consultant and communication bridge, NOT an autonomous developer.

## Consequences

- Agent ID: `dev-liaison`
- Sandbox mode: `off` (runs on host, like SysAdmin)
- Provides feasibility perspective during improvement debate cycles (Round 3)
- Partners with SysAdmin for diagnostics and issue investigation
- Bridges between Layer 2 (pipeline improvement) and Layer 3 (dev team)
- Receives webhook notifications from AutoDev
- Sends wake signals to AutoDev when TraderBot agents file GitHub issues
- Updates verification: coordinates with TraderBot agents after AutoDev deploys changes

## Webhook Communication

| Channel | Direction | Mechanism | Latency |
|---------|-----------|-----------|---------|
| Wake signal | Either direction | OpenClaw webhooks / Discord bot | Seconds |
| GitHub | Both directions | Issues, PRs, labels, comments | 30 min (heartbeat) |

## Notes for AutoDev Agents

Dev-Liaison is the bridge. When we complete work, we signal the liaison via webhook (autodev:completed, autodev:blocked, autodev:deployed). When TraderBot needs engineering work, the liaison files a GitHub issue with `autodev-request` label and sends a wake signal. The liaison does NOT write code or deploy changes.
