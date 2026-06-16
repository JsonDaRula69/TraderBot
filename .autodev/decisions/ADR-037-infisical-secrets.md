# ADR-037: Secrets management — Infisical as primary vault

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-037
**Tags:** secrets, infisical, security, vault, auth

## Context

Secrets management needed a unified approach. Previous decisions (DD-012 encrypted vault, DD-014 auth architecture, DD-024 auth implementation, DD-026 1Password) were all superseded by this single decision.

## Decision

Infisical is the primary secrets vault. Two-project structure (TraderBot service + OpenClaw agents). Machine identity `traderbot-service` has read/write. Each agent's machine identity has read access only to its own token. The `INFISICAL_TOKEN` bootstrap secret is stored via OpenClaw SecretRef.

## Consequences

- 1Password is NOT used (DD-026 superseded)
- Custom encrypted vault is NOT used (DD-012 superseded)
- Infisical runs on all platforms including headless Linux
- Token rotation every 4 hours via Infisical API
- Fallback: local encrypted `secrets.json` with machine-derived encryption for air-gapped systems
- Profile tokens are provisioned via Infisical and injected as SecretRef

## Consequences (OpenClaw integration)
- OpenClaw's `SecretRef` mechanism is used for token injection
- Agents never see API tokens — only profile tokens
- `INFISICAL_TOKEN` is the bootstrap secret that allows access to all other secrets

## Notes for AutoDev Agents

Never store secrets in source code. Use Infisical for all secrets management. If Infisical is unavailable, the local encrypted fallback provides read-only access. Profile tokens are the authentication mechanism for MCP tools (DD-025). The Infisical Client SDK is used within the TraderBot service.
