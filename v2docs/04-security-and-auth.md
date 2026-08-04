# TraderBot v2 — Security and Authentication

> This document covers the complete security architecture: Infisical secrets management, MCP authentication, per-agent isolation, token rotation, and the division of secrets responsibility. Grounded in DD-010, DD-011, DD-015, DD-025, DD-036, DD-037.

> **Implementation status:** Phase 1.5 is code complete and locally tested
> (2.0.0a38, 233 Python tests + 11 TypeScript tests pass). Infisical is
> the default external secrets backend, with `SecretsStore` selecting
> automatically between the Infisical SDK and the encrypted local fallback.
> `TokenStoreAdapter` installs `SecretsStore` behind the existing `TokenStore`
> seam so profile-token resolution uses Infisical-backed secrets by default.
> `LocalEncryptedStore` provides the offline fallback; `LocalTokenStore` is
> preserved as a read-only migration source. Token rotation, the scheduler,
> the `openclaw-infisical-resolver` exec provider, and the migration script
> are all committed and tested. API credential validation and the full deploy
> wizard integration remain future work.

---

## Target Security Architecture (Phase 1.5)

The diagram below shows the Infisical-backed architecture that is now
implemented. `SecretsStore` is the runtime facade; `LocalEncryptedStore` is the
offline fallback.

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

## Current Phase 1.5 Authentication

- Every tool receives an explicit `token` argument.
- `TRADERBOT_USE_HARDCODED_AUTH=0` selects real auth through `TokenStore`.
- By default `SecretsResolver` installs a `TokenStoreAdapter` backed by
  `SecretsStore` (Infisical primary, `LocalEncryptedStore` fallback). The
  resolver reads `~/.traderbot/infisical-credentials.json` and falls back to
  the local encrypted store when credentials are missing or Infisical is
  unreachable.
- `LocalTokenStore` at `~/.traderbot/tokens.json` is still readable for
  one-way migration to Infisical via `traderbot secrets migrate`.

## Current Phase 1.5 Infisical Secrets Management (DD-037)

### Two-Project Structure

**Project 1: "TraderBot"** — API keys and service credentials

Namespace organization (the `global` and `tokens` namespaces map to
Infisical environment slug `prod`, matching the deployed instance):
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

The `prod` environment slug matches the actual Infisical deployment; earlier
roadmap drafts used `production`.

### Implemented Token Provisioning Flow

1. TraderBot generates a profile token (cryptographically random, 256-bit)
2. Profile token is stored as an Infisical secret in "TraderBot Agent Tokens"
   (`prod` environment), secret name `<agent_id>_token`
3. OpenClaw SecretRef is configured to inject this token into the agent's
   environment via the `openclaw-infisical-resolver` exec provider
4. Token is passed to agent via `TRADERBOT_PROFILE_TOKEN` environment variable
5. When the agent calls an MCP tool, the TraderBot MCP server resolves the
   token to a profile through the `TokenStoreAdapter` → `SecretsStore` chain

This flow is driven by the Phase 1.1 `before_tool_call` plugin hook (issue #187
closed) plus the Phase 1.5 `openclaw-infisical-resolver` exec provider. The
exec provider is the OpenClaw SecretRef surface; the plugin hook still resolves
caller identity and injects the token host-side. Config with both is in
`configs/openclaw/with-plugin.json` (`secrets.providers.infisical`,
`mcp.servers.traderbot.env.TRADERBOT_USE_HARDCODED_AUTH=0`).

### Implemented Token Rotation (4-hour cycle)

Implemented in `src/traderbot/secrets/rotation.py`:

1. `TokenRotationManager.rotate_all()` rotates each active profile token
2. `RotationScheduler` runs an asyncio loop every 4 hours
3. For each active profile:
   a. Generate a new 256-bit random token
   b. `SecretsStore.rotate_profile_token(agent_id, new_token)` replaces the
      secret in Infisical and preserves profile/categories/permissions
   c. Old token is immediately invalidated in Infisical
   d. OpenClaw refreshes its exec-provider SecretRef on the next poll
4. `TokenRotationManager.get_staleness()` supports the SysAdmin heartbeat warning
5. If Infisical is unavailable during rotation:
   - The current token remains valid until rotation succeeds
   - Failure is recorded per agent; retry is scheduled inside the 4-hour loop
   - After 24 hours of continuous failure, `mcp/resolver.py`
     `_SUSPENDED_PROFILES` suspends the affected profile

### Implemented Local Encrypted Fallback

For users who do not want to run Infisical (air-gapped systems, minimal setups,
testing), `LocalEncryptedStore` at `~/.traderbot/secrets/secrets.json` is the
current fallback. It is also selected automatically by `SecretsResolver` when
Infisical credentials are absent or the server is unreachable.

```
~/.traderbot/secrets/secrets.json (0600 permissions)
```

- **File layout**: `~/.traderbot/secrets/secrets.json` (0600 permissions) +
  `~/.traderbot/secrets/secrets.json.sha256` (0600)
- **Whole-file encryption**: the entire namespace tree is encrypted as one
  Fernet token inside a versioned envelope. Service and key names are not
  visible in the raw file.
- **Machine-derived encryption key**: key derived from hostname + username +
  machine ID hash. The file is unreadable if copied to another machine, but
  decrypts automatically on the original machine without a user-supplied password.
- **File integrity monitoring**: a SHA-256 hash of the file contents is stored
  alongside it; at startup, TraderBot verifies the hash and raises if tampering
  is detected.
- **No rotation**: local fallback does not auto-rotate; manual rotation via
  `traderbot token rotate --agent <name>` is required.
- **Deploy warning**: `⚠ Local storage provides basic security but no automatic
  token rotation or Infisical's audit logging. Infisical is recommended for
  production deployments.`
- **Migration source**: `~/.traderbot/tokens.json` remains readable for the
  one-way migration script (`src/traderbot/secrets/migrate.py`) and is not
  written to by the new token path.

This `LocalEncryptedStore` API-secret store is separate from the legacy
`LocalTokenStore` profile-token file at `~/.traderbot/tokens.json`. The legacy
file is now a read-only migration source, not a runtime token store.

---

## MCP Authentication (DD-025) — Current Behavior

### Identity Resolution

Every TraderBot MCP tool accepts a `token` parameter. With real auth enabled,
`mcp/resolver.py` first installs a `TokenStoreAdapter` (lazy-init, once) and
 then resolves the token through the adapter → `SecretsStore` →
"TraderBot Agent Tokens" (`prod`). Suspended profiles fail closed and return
`(None, None)`.

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

> **Current Phase 1.5 behavior:** each implemented tool evaluates access in the
> order **token → tool permission → category**. Category validation is applied
> only to category-bearing tools; currently that is `market_edge`. The current
> `auth_check` validates the profile token and `auth_check` permission, then
> reports profile, agent, mode, enabled categories, and permissions. It does
> not check external API credentials.

### Current Security Properties

- With real auth, profile-token resolution goes through `TokenStoreAdapter` →
  `SecretsStore` (Infisical primary, `LocalEncryptedStore` fallback)
- A valid token resolves to one profile and agent; profile permissions are
  checked before category access
- The `permissions` field on `TradingProfile` provides an additional layer of control
- Category-bearing tools reject unknown or disabled categories
- Profile suspension (`_SUSPENDED_PROFILES`) makes rotated-but-failed tokens fail
  closed

The OpenClaw plugin hook and exec provider now handle secure per-agent token
delivery. The remaining deployment work is live Infisical provisioning and the
full deploy wizard.

### Why Not OpenClaw Agent Context?

OpenClaw's MCP protocol does not currently pass agent identity
(`_meta.agent_id`) in tool calls. Explicit token parameters work in TraderBot
and local transport tests, but deployment still needs secure per-agent token
delivery. If OpenClaw adds trusted agent context, TraderBot can check both the
token and `_meta.agent_id`.

---

## Per-agent token injection via OpenClaw plugin hook + Infisical exec provider

> **Phase 1.1 — deployment verified on macpro-linux (2026-08-03).** E2E
> token injection confirmed: plugin loads, hook fires at priority 100, token
> resolved from the `infisical` exec provider, MCP server resolves the weather
> profile.
>
> Implementation plan: `.omo/plans/phase1-1-token-injector.md`.

### Architecture

```
Agent (model) → OpenClaw tool dispatch → before_tool_call hook
  → reads ctx.agentId (trusted)
  → resolves the `infisical` exec-provider SecretRef for that agent
  → injected token value is fetched by `scripts/openclaw-infisical-resolver`
     from Infisical ("TraderBot Agent Tokens", `prod` env)
  → injects token into params.token
  → MCP call to TraderBot with authenticated token
  → TraderBot `resolver.py` → `TokenStoreAdapter` → `SecretsStore` validates
     token → `TradingProfile` → `auth.py`
```

The hook runs host-side in the OpenClaw gateway, so the model never sees or
controls the injected token. `ctx.agentId` is host-derived from the caller's
OpenClaw agent session, not from anything the model supplies. The hook resolves
the agent's token from a Vault-backed SecretRef using OpenClaw's
`resolveSecretRefValues` helper, then returns the full params object with the
extra `token` field. Unrecognized agents fail closed.

### Security properties

- Token never enters model context — the agent workspace does not contain tokens
- Token never written to config files — exec-provider SecretRefs resolve to
  in-memory snapshots
- Per-agent isolation via `ctx.agentId`
- Unknown agents fail closed (`{ block: true }`)
- TraderBot server-side auth preserved — `resolver.py` → `TokenStoreAdapter` →
  `SecretsStore` → `TradingProfile` → `auth.py` is still the enforcement boundary

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

The verified config is in `configs/openclaw/with-plugin.json`. It registers:

- `plugins.traderbot-token-injector` (Phase 1.1 hook)
- `secrets.providers.infisical` with command
  `/usr/local/bin/openclaw-infisical-resolver`, passEnv
  `["INFISICAL_TOKEN", "INFISICAL_DOMAIN"]`, and `jsonOnly: true`
- Agent token ids such as `weather_token`, `sysadmin_token`, `dev-liaison_token`
- `mcp.servers.traderbot.env.TRADERBOT_USE_HARDCODED_AUTH: "0"` so the MCP
  subprocess runs in real-auth mode

This replaces the earlier Vault-based `secrets.providers.vault` example.

### References

- [Plugin hooks — before_tool_call](https://docs.openclaw.ai/plugins/hooks)
- [SecretRef credential surface](https://docs.openclaw.ai/reference/secretref-credential-surface)
- Production reference: [dev.to/micelclaw — before_tool_call token hook](https://dev.to/micelclaw/deterministic-agent-identity-a-beforetoolcall-hook-fills-the-token-the-model-kept-getting-wrong-3nln)
- `configs/openclaw/with-plugin.json` in this repo

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
