# TraderBot v2 — Security and Authentication

> This document covers the complete security architecture: Infisical secrets management, MCP authentication, per-agent isolation, token rotation, and the division of secrets responsibility. Grounded in DD-010, DD-011, DD-015, DD-025, DD-036, DD-037.

> **Implementation status:** Phase 1 is a development milestone, not a
> deployable release. The current code implements profile-token resolution,
> permission and category enforcement, strict MCP inputs, and a hardened local
> profile-token store. Infisical, provider credential validation, automatic
> rotation, and deploy integration remain planned for Phase 1.5. Secure
> per-agent token injection through OpenClaw is deployment-verified via the
> Phase 1.1 `before_tool_call` plugin hook (issue #187 closed; issue #164
> closed). Vault SecretRef integration is deferred to Phase 1.5 (issue #165).
> Implementation plan: `.omo/plans/phase1-1-token-injector.md`.

---

## Target Security Architecture (Phase 1.5)

The diagram below is the planned Infisical-backed architecture. It is not the
current Phase 1 runtime.

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

## Current Phase 1 Authentication

- Every tool receives an explicit `token` argument.
- `TRADERBOT_USE_HARDCODED_AUTH=0` selects real auth through `TokenStore`;
  every other value, including an unset variable, uses the Phase 0 hardcoded
  development mapping.
- `LocalTokenStore` persists 256-bit profile tokens at
  `~/.traderbot/tokens.json`. Writes use a private same-directory temporary
  file and atomic replacement; the final file is mode `0600` on POSIX.
- The local store is not encrypted and has no expiry timer or automatic
  rotation. Corrupt or malformed payloads fail closed as an empty store.
- API credentials and Infisical are outside the current phase. Phase 1 does
  not validate Kalshi, VoyageAI, NewsAPI, or other provider credentials.

## Planned Infisical Secrets Management (Phase 1.5, DD-037)

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

### Planned Token Provisioning Flow

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

This flow is not currently representable by the pinned OpenClaw configuration schema. Agent entries are strict and do not accept `env` or `mcp`; root environment values are global, and `mcp.servers.*.env` is shared by the one server process. The committed config remediation removes the invalid agent fields. Secure per-agent delivery is now handled by the `before_tool_call` plugin hook (Phase 1.1, issue #187 closed), which injects per-agent tokens host-side without requiring schema-invalid config fields.

### Planned Token Rotation (4-hour cycle)

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

### Planned API-Secret Local Fallback

For future Phase 1.5 users who do not want Infisical (air-gapped systems,
minimal setups, testing), the design proposes:

```
~/.traderbot/secrets/secrets.json (0600 permissions)
```

- **Machine-derived encryption**: Key derived from hostname + username + machine ID hash. Unreadable if copied to another machine, auto-decrypts on original machine
- **File integrity monitoring**: SHA-256 hash stored alongside (`secrets.json.sha256`), verified at startup
- **Audit logging**: Last-read and last-write timestamps per secret in `secrets.json.meta`
- **Limitations**: No automatic token rotation (must manually `traderbot token rotate --agent <name>`), basic audit logging only
- **Clear warning at deploy**: "⚠ Local storage provides basic security but no automatic token rotation or Infisical's audit logging. Infisical is recommended for production deployments."

This planned API-secret store is separate from the current
`LocalTokenStore` profile-token file at `~/.traderbot/tokens.json`.

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
    if not profile.is_tool_permitted("traderbot__scan"):
        return {"error": "Permission denied"}
    if category not in profile.enabled_categories:
        return {"error": f"Category '{category}' not enabled for agent '{agent_id}'"}
    # ... execute scan
```

> **Current Phase 1 behavior:** each implemented tool evaluates access in the
> order **token → tool permission → category**. Category validation is applied
> only to category-bearing tools; currently that is `market_edge`. The current
> `auth_check` validates the profile token and `auth_check` permission, then
> reports profile, agent, mode, enabled categories, and permissions. It does
> not check external API credentials.

### Current Security Properties

- Tokens generated by `generate_token()` are 256-bit cryptographically random
- The token file is private on POSIX and replaced atomically
- A valid token resolves to one profile and agent; profile permissions are checked before category access
- The `permissions` field on `TradingProfile` provides an additional layer of control
- Category-bearing tools reject unknown or disabled categories

The current code cannot prove which OpenClaw agent supplied a token. Securely
giving each agent only its own token is the unresolved injection blocker, not
an implemented security property. Infisical storage and four-hour rotation are
future Phase 1.5 design details.

### Why Not OpenClaw Agent Context?

OpenClaw's MCP protocol does not currently pass agent identity
(`_meta.agent_id`) in tool calls. Explicit token parameters work in TraderBot
and local transport tests, but deployment still needs secure per-agent token
delivery. If OpenClaw adds trusted agent context, TraderBot can check both the
token and `_meta.agent_id`.

---

## Per-agent token injection via OpenClaw plugin hook

> **Phase 1.1 — deployment verified on macpro-linux (2026-08-03).** E2E
> token injection confirmed: plugin loads, hook fires at priority 100, token
> resolved from env provider, MCP server resolves the weather profile.
> Three fixes were required during deployment testing (see Constraints below).
> This section documents the verified architecture for secure per-agent token
> injection using OpenClaw's first-party `before_tool_call` plugin hook.
>
> Implementation plan: `.omo/plans/phase1-1-token-injector.md`.

### Architecture

```
Agent (model) → OpenClaw tool dispatch → before_tool_call hook
  → reads ctx.agentId (trusted)
  → resolves Vault SecretRef for that agent
  → injects token into params.token
  → MCP call to TraderBot with authenticated token
  → TraderBot resolver.py validates token → TradingProfile → auth.py
```

The hook runs host-side in the OpenClaw gateway, so the model never sees or
controls the injected token. `ctx.agentId` is host-derived from the caller's
OpenClaw agent session, not from anything the model supplies. The hook resolves
the agent's token from a Vault-backed SecretRef using OpenClaw's
`resolveSecretRefValues` helper, then returns the full params object with the
extra `token` field. Unrecognized agents fail closed.

### Security properties

- Token never enters model context — the agent workspace does not contain tokens
- Token never written to config files — Vault SecretRefs resolve to in-memory snapshots
- Per-agent isolation via `ctx.agentId`
- Unknown agents fail closed (`{ block: true }`)
- TraderBot server-side auth preserved — `resolver.py` → `TradingProfile` → `auth.py` is still the enforcement boundary

### Critical constraints

All verified against OpenClaw source at commit `cbd4b8de` and confirmed
on-target on macpro-linux (2026-08-03, gateway v2026.7.1-2):

1. **`params` is a full replace** — always return `{ ...event.params, token }`, never `{ token }` alone
2. **`token` must be declared in the tool's `inputSchema`** — or the MCP SDK silently strips it. **Must be optional** (`str | None = None`): the SDK validates the schema BEFORE the hook runs, so a required token field rejects the call before injection (commit `f1aa518`).
3. **Run at high priority** (e.g., `priority: 100`) — if another hook requests approval first, `freezeParamsForDifferentPlugin` can silently discard injected params
4. **`ctx.agentId` is conditional** — fail closed when absent
5. **Codex app-server native relay cannot rewrite params** — only blocking. Verify TraderBot tools aren't consumed exclusively through that path
6. **Gateway must be v2026.7.1-2+** for `before_tool_call` to fire on MCP tool calls — older gateways silently skip the hook (commit `f8b5065`)
7. **Plugin manifest requires `openclaw` metadata + `configSchema`** — `package.json` must contain the `openclaw` block (`{"extensions": ["./src/index.ts"], "compat": {...}}`) and `openclaw.plugin.json` must contain a `configSchema` field, or the gateway rejects the plugin at load (commit `f8b5065`)
8. **MCP server subprocess does NOT inherit gateway systemd drop-in env vars** — `TRADERBOT_USE_HARDCODED_AUTH=0` must be set explicitly in `mcp.servers.traderbot.env` in `openclaw.json`, not just the gateway's systemd unit (commit `0dbc981`). Without it the subprocess runs in hardcoded mode and rejects real tokens.

### References

- [Plugin hooks — before_tool_call](https://docs.openclaw.ai/plugins/hooks)
- [Vault SecretRefs](https://docs.openclaw.ai/plugins/vault/)
- [SecretRef credential surface](https://docs.openclaw.ai/reference/secretref-credential-surface)
- Production reference: [dev.to/micelclaw — before_tool_call token hook](https://dev.to/micelclaw/deterministic-agent-identity-a-beforetoolcall-hook-fills-the-token-the-model-kept-getting-wrong-3nln)

---

## Per-Agent Isolation (DD-010, DD-011)

### Docker Sandbox Configuration Status

The target architecture requires all category agents to run in Docker containers with the properties below. A separate OpenClaw remediation hardens agent tool policies only; it does not encode these bind mounts and has not been deployed or tested on target hardware:
- Base image: `python:3.12-slim-bookworm`
- Agent data dir bind-mounted RW: `~/.traderbot/paper-{category}/`
- Workspace files bind-mounted RO: `~/.openclaw/workspace/{category}/`
- No blanket `~/.traderbot/` mount — each agent only sees its own data
- No profile token is injected by the remediation fragments
- SysAdmin runs unsandboxed on host (DD-036)

### Tool-Level Filtering

The remediation fragments use explicit `allow` and `deny` policies. This is intentional: first-party OpenClaw code treats a lone
`alsoAllow` as additive to an implicit `*`, so it is not a restrictive
allowlist. Sandboxed agents also use a second sandbox-tool gate for
`bundle-mcp` and required session tools:

```json5
{
  id: "weather",
  sandbox: { mode: "all" },
  tools: {
    allow: [
      "traderbot__health",
      "traderbot__auth_check",
      "traderbot__profile_list",
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
    deny: ["group:runtime", "group:fs"],
    sandbox: {
      tools: { allow: ["bundle-mcp", "sessions_send"] },
    },
  },
}
```

Only `health`, `auth_check`, `profile_list`, and `market_edge` currently exist;
the remaining names in the full design are planned. SysAdmin stays unsandboxed
per DD-036 and its deny list explicitly blocks trading and category-specific
tools. The gateway artifact registers TraderBot once at root `mcp.servers`; the remediation agent fragments omit invalid nested `mcp` and per-agent `env` fields.

### Target Data Isolation (not implemented in Phase 1)

- Per-agent per-mode SQLite databases (DD-032)
- ChromaDB shared collections with category metadata filtering
- SysAdmin can read all databases (enabled_categories: [])
- Category agents can only read their own data

---

## Planned Division of Secrets Responsibility (Phase 1.5)

| Secret Type | Manager | Storage | Access |
|---|---|---|---|
| OpenClaw LLM keys, gateway auth, channel tokens | OpenClaw SecretRef | Infisical project "OpenClaw" (or OpenClaw's own provider) | OpenClaw gateway on host only |
| TraderBot API keys (Kalshi, Voyage, NewsAPI, etc.) | Infisical | Infisical project "TraderBot" | TraderBot service on host only |
| Agent profile tokens | Infisical | Infisical project "TraderBot Agent Tokens" | TraderBot service (resolution) + OpenClaw SecretRef (injection) |
| Infisical machine identity token | OpenClaw SecretRef | OpenClaw config (env provider) | TraderBot service only |
| TraderBot service auth token | Infisical | Infisical project "TraderBot" | TraderBot service only |

**Target principle**: Agents never see API tokens. They interact with TraderBot
through MCP tools only, and TraderBot handles API communication on the backend.
This table is planned architecture, not a claim that Infisical, provider
credential validation, token injection, rotation, or deployment is complete.
