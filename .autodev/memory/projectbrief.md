# TraderBot v2 — Project Brief

**Immutable truth:** `v2roadmap.md` + `v2docs/` — do not modify.

## What

Autonomous agent trading platform on OpenClaw Kalshi. Always-on service with MCP server, data pipeline, and Docker-sandboxed category agents. Trades real money.

## Stack

OpenClaw (agent runtime), Kalshi (WebSocket+REST), Infisical (secrets), SQLite per-agent per-mode, ChromaDB (vectors), Docker (sandbox), pipx (install).

## Key Decisions

- DD-010: Mandatory Docker for category agents
- DD-015: TraderBot as MCP server via OpenClaw gateway
- DD-034: Dev-Liaison bridges AutoDev ↔ TraderBot
- DD-037: Infisical as primary secrets vault
- DD-038: Agent-debate self-improvement (5-round cycle)

## Deployment Target

**ssh macpro-linux**

## AutoDev Bridge

AutoDev (OpenCode + OmO) ↔ Dev-Liaison (OpenClaw) ↔ TraderBot. Communication: webhooks + Discord + GitHub.
