# ADR-018: Three-layer self-improvement architecture

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-018
**Tags:** self-improvement, agent-debate, learning, architecture

## Context

Agents need to improve their trading performance over time. A single approach (just learnings or just debates) is insufficient. The improvement system needs to operate at different timescales and scopes.

## Decision

Three layers of self-improvement:
1. **Layer 1: Reactive agent learnings** — Category agents document findings in `.learnings/` during normal operations. After 3+ recurrences, flagged for promotion.
2. **Layer 2: Proactive pipeline improvement (agent-debate)** — 5-round debate cycle using OpenClaw's `sessions_spawn`/`sessions_send`/`sessions_yield`. One concept per cycle. Statistical rigor required.
3. **Layer 3: Autonomous development team (AutoDev)** — Picks up GitHub issues, implements code changes, deploys fixes. Currently in development.

## Consequences

- Layer 1 is always running, passive
- Layer 2 is continuous and proactive, runs indefinitely
- Layer 3 is event-driven (GitHub issues from SysAdmin, agents, or humans)
- Dev-Liaison bridges Layer 2 and Layer 3 (DD-034)
- Each layer operates at different scope: operational tweaks, pipeline changes, code changes

## Notes for AutoDev Agents

AutoDev IS Layer 3. This is our role in the system. We pick up GitHub issues with the `autodev-request` label. The liaison agent bridges TraderBot's Layer 2 (agent-debate) to our Layer 3 via webhooks and GitHub. The 5-round debate cycle (DD-038) produces proposals that may result in GitHub issues for us.
