# TraderBot v2 — Security and Authentication

> This document covers the complete security architecture: Infisical secrets management, MCP authentication, per-agent isolation, token rotation, and the division of secrets responsibility. Grounded in DD-010, DD-011, DD-015, DD-025, DD-036, DD-037.

---

## Security Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      Host Machine                            │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │  Infisical    │  │  TraderBot   │  │  OpenClaw Gateway  │ │
│  │  (Docker)     │  │  Service      │  │                    │ │
│  │              │  │              │  │  - Agent sessions   │ │
│  │  Project:    │  │  - MCP server│  │  - Cron/heartbeat  │ │
│  │   "TraderBot"│  │  - Data pipe │  │  - SecretRef inject │ │
│  │   "Agent     │  │  - Token rot │  │  - Tool routing    │ │
│  │    Tokens"   │  │              │  │                    │ │
│  └──────┬───────┘  └──────┬───────┘  └────────┬───────────┘ │
│         │                 │                    │              │
│         │    ┌────────────┴──────────┐         │              │
│         │    │   secrets/secrets.json │         │              │
│         │    │   (local fallback)     │         │              │
│         │    └───────────────────────┘         │              │
│         │                                      │              │
└─────────┼──────────────────────────────────────┼──────────────┘
          │                                      │
          │        ┌─────────────────────────────┘
          │        │
          │   ┌────┴────────────────────┐
          │   │  Docker Container       │
          │   │  (per category agent)   │
          │   │                         │
          │   │  TRADERBOT_PROFILE_TOKEN │  ← Injected via OpenClaw SecretRef
          │   │  (scoped to this agent) │     (NOT in files inside container)
          │   │                         │
          │   │  Agent workspace (RO)   │
          │   │  Agent data dir (RW)    │
          │   │                         │
          │   │  NO API keys visible     │
          │   │  NO other agent data     │
          │   └─────────────────────────┘
          │
     ┌────┴────┐
     │ SysAdmin │  (unsandboxed, on host)
     │         │  INFISICAL_TOKEN via SecretRef
     │         │  No trading tools
     │         │  Read access to everything
     └─────────┘
```

---

## Infisical Secrets Management (DD-037)

### Two-Project Structure

**Project 1: "TraderBot"** — API keys and service credentials

Namespace organization:
```
global/
  kalshi.api_key
  kalshi.private_key_pem
  voyage.api_key
  newsapi.api_key
  twitter.bearer_token
  reddit.client_id
  reddit.client_secret
weather/
  openweathermap.api_key
economics/
  fred.api_key
crypto/
  coingecko.api_key
sports/
  thesportsdb.api_key
```

Common keys (NewsAPI, Twitter, Reddit) are in the `global` namespace. Category-specific keys are in their own namespace. The MCP server selects the correct key based on the calling agent's profile, but initially all profiles point to the same global Kalshi key.

**Project 2: "TraderBot Agent Tokens"** — Profile tokens (one per agent)

```
sysadmin_token    → resolves to sysadmin profile
weather_token     → resolves to weather profile
economics_token   → resolves to economics profile
dev-liaison_token       → resolves to dev-liaison profile
```

### Machine Identities

- `traderbot-service`: read/write access to both projects. This is the bootstrap secret stored in OpenClaw SecretRef as `INFISICAL_TOKEN`.
- Per-agent machine identities: read access only to their own token in "TraderBot Agent Tokens".

### Token Provisioning Flow

1. TraderBot generates a profile token (cryptographically random, 256-bit)
2. Profile token stored as Infisical secret in "TraderBot Agent Tokens" project
3. OpenClaw SecretRef configured to inject this token into the agent's environment:
   ```
   openclaw config set secrets.providers.traderbot_weather \
     --provider-type env \
     --provider-command "infisical secrets get weather_token --project traderbot-agent-tokens" \
     --env-var TRADERBOT_PROFILE_TOKEN
   ```
4. Token is passed to agent via `TRADERBOT_PROFILE_TOKEN` environment variable
5. When agent calls an MCP tool, TraderBot MCP server resolves the token to a profile

### Token Rotation (4-hour cycle)

1. TraderBot service maintains a rotation timer
2. Every 4 hours, for each active profile:
   a. Generate a new 256-bit random token
   b. Store new token in Infisical (replacing old)
   c. Signal OpenClaw to refresh the SecretRef for that agent
   d. Old token is immediately invalidated
3. SysAdmin heartbeat includes token staleness check (30-minute warning before expiry)
4. If Infisical is unavailable during rotation:
   - Current token remains valid until rotation succeeds
   - SysAdmin is alerted that rotation failed
   - Retry every 15 minutes
   - After 24 hours of failed rotation, fleet is suspended

### Local Encrypted Fallback

For users who don't want Infisical (air-gapped systems, minimal setups, testing):

```
~/.traderbot/secrets/secrets.json (0600 permissions)
```

- **Machine-derived encryption**: Key derived from hostname + username + machine ID hash. Unreadable if copied to another machine, auto-decrypts on original machine
- **File integrity monitoring**: SHA-256 hash stored alongside (`secrets.json.sha256`), verified at startup
- **Audit logging**: Last-read and last-write timestamps per secret in `secrets.json.meta`
- **Limitations**: No automatic token rotation (must manually `traderbot token rotate --agent <name>`), basic audit logging only
- **Clear warning at deploy**: "⚠ Local storage provides basic security but no automatic token rotation or Infisical's audit logging. Infisical is recommended for production deployments."

---

## MCP Authentication (DD-025)

### Identity Resolution

Every TraderBot MCP tool accepts a `token` parameter. The agent's workspace instructions (TOOLS.md) include the token in every call. The MCP server resolves the token to a profile:

```python
@tool
async def traderbot_scan(token: str, category: str, ...):
    profile_name, agent_id = resolve_token(token)
    if profile_name is None:
        return {"error": "Invalid or expired profile token"}
    profile = registry.get_profile(profile_name)
    if category not in profile.enabled_categories:
        return {"error": f"Category '{category}' not enabled for agent '{agent_id}'"}
    # ... execute scan
```

### Security Properties

- Tokens are 256-bit cryptographically random, stored in Infisical
- An agent can only use its own token — it doesn't know other agents' tokens
- Even if an agent reads another agent's token from OpenClaw config, the MCP server validates that the token matches the agent's profile categories
- The `permissions` field on `TradingProfile` provides an additional layer of control
- Tokens rotate every 4 hours (Infisical) or manually (local fallback)

### Why Not OpenClaw Agent Context?

OpenClaw's MCP protocol does not currently pass agent identity (`_meta.agent_id`) in tool calls. Approach A (token as explicit parameter) works today with existing infrastructure. If OpenClaw adds agent context in the future, we can migrate transparently — the MCP server would check both the `token` parameter and the `_meta.agent_id` field.

---

## Per-Agent Isolation (DD-010, DD-011)

### Docker Sandbox

All category agents run in Docker containers (mandatory, no opt-out):
- Base image: `python:3.12-slim-bookworm`
- Agent data dir bind-mounted RW: `~/.traderbot/paper-{category}/`
- Workspace files bind-mounted RO: `~/.openclaw/workspace/{category}/`
- No blanket `~/.traderbot/` mount — each agent only sees its own data
- No API tokens or secrets inside containers — only `TRADERBOT_PROFILE_TOKEN` via SecretRef
- SysAdmin runs unsandboxed on host (DD-036)

### Tool-Level Filtering

OpenClaw's `toolFilter` and per-agent `alsoAllow` enforce which MCP tools each agent can see:

```json5
{
  id: "weather",
  sandbox: { mode: "all" },
  tools: {
    deny: ["group:runtime", "group:fs"],
    alsoAllow: [
      "bundle-mcp",
      "traderbot__weather_forecast_prob",
      "traderbot__weather_accuracy",
      "traderbot__weather_seasonal_context",
      "traderbot__weather_decision_brief",
      "traderbot__market_edge",
      "traderbot__market_prices",
      "traderbot__trade",
      "traderbot__positions",
      "traderbot__heartbeat",
      "traderbot__performance",
      "traderbot__audit",
      "traderbot__learnings",
    ],
  },
}
```

SysAdmin's deny list explicitly blocks trading and category-specific tools (DD-036).

### Data Isolation

- Per-agent per-mode SQLite databases (DD-032)
- ChromaDB shared collections with category metadata filtering
- SysAdmin can read all databases (enabled_categories: [])
- Category agents can only read their own data

---

## Division of Secrets Responsibility

| Secret Type | Manager | Storage | Access |
|---|---|---|---|
| OpenClaw LLM keys, gateway auth, channel tokens | OpenClaw SecretRef | Infisical project "OpenClaw" (or OpenClaw's own provider) | OpenClaw gateway on host only |
| TraderBot API keys (Kalshi, Voyage, NewsAPI, etc.) | Infisical | Infisical project "TraderBot" | TraderBot service on host only |
| Agent profile tokens | Infisical | Infisical project "TraderBot Agent Tokens" | TraderBot service (resolution) + OpenClaw SecretRef (injection) |
| Infisical machine identity token | OpenClaw SecretRef | OpenClaw config (env provider) | TraderBot service only |
| TraderBot service auth token | Infisical | Infisical project "TraderBot" | TraderBot service only |

**Key principle**: Agents never see API tokens. They interact with TraderBot through MCP tools only. TraderBot handles all API communication on the backend.
