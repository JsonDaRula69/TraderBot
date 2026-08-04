# TraderBot v2 Roadmap — Architecture Realignment

> Living document tracking design decisions and pending work from the v2 architecture realignment. Updated as decisions are made.

---


## Quick Reference

### Design Decisions Index

| DD | Topic | Status |
|---|---|---|
| DD-001 | pipx as sole installation method | Decided |
| DD-002 | OpenClaw is a hard dependency | Decided |
| DD-003 | Docker sandbox in setup | Decided |
| DD-004 | Service registration in setup | Decided |
| DD-005 | Retire bootstrap, rename to deploy | Decided |
| DD-006 | OS-aware capability detection | Decided |
| DD-007 | Service templates as package data | Decided |
| DD-008 | Prebuilt agent workspaces (no customization) | Decided |
| DD-009 | 8-step deploy flow | Decided |
| DD-010 | Mandatory Docker sandbox for category agents | Decided |
| DD-011 | Per-agent data source access control | Decided |
| DD-012 | Encrypted vault + SecretRef (superseded by DD-026 → DD-037) | Superseded |
| DD-013 | Three-mode trading (backtesting/paper/live) | Decided |
| DD-014 | Auth and secrets architecture (superseded by DD-026 → DD-037) | Superseded |
| DD-015 | TraderBot as MCP server with OpenClaw gateway | Decided |
| DD-016 | Always-on service with continuous data pipeline | Decided |
| DD-017 | Agent lifecycle: backtesting → paper → live → suspended | Decided |
| DD-018 | Three-layer self-improvement architecture | Decided |
| DD-019 | Time-lapse behavioral simulation for backtesting | Decided |
| DD-020 | Historical data sources for backtesting | Decided |
| DD-021 | Paper trading: simulated fills, three-mode DB isolation | Decided |
| DD-022 | Service template path resolution | Decided |
| DD-023 | SysAdmin cron/heartbeat activation protocol | Decided |
| DD-024 | Auth implementation (superseded by DD-026 → DD-037) | Superseded |
| DD-025 | MCP identity resolution and tool filtering | Decided |
| DD-026 | 1Password as primary secrets vault (superseded by DD-037) | Superseded |
| DD-027 | All data sources collect at install time | Decided |
| DD-028 | news/ and data/ module restructure | Decided |
| DD-029 | P&L and settlement logic consolidation | Decided |
| DD-030 | CLI circular imports — extract DB code from helpers | Decided |
| DD-031 | Module-by-module review findings | Decided |
| DD-032 | Database restructuring for multi-agent multi-mode | Decided |
| DD-033 | GRIB2 processing pipeline for historical weather data | Decided |
| DD-034 | Dev-Liaison — TraderBot subject matter expert and AutoDev liaison | Decided |
| DD-035 | Category-specific analysis toolkits — analysis, not trading signals | Decided |
| DD-036 | SysAdmin sandbox — unsandboxed with principled restrictions | Decided |
| DD-037 | Secrets management — Infisical as primary vault | Decided |
| DD-038 | Agent-debate integration, sub-agent configuration, TEMPLATE.md | Decided |


### Progress Tracking

**Completed in this session:**
- [x] DD-027: All data sources collect at install time
- [x] DD-028: news/ and data/ module restructure
- [x] DD-029: P&L and settlement logic consolidation
- [x] DD-030: CLI circular imports — extract DB code from helpers
- [x] DD-031: Module-by-module review findings (simulation, profiles, kalshi, analysis, risk, cli, experiment, db)
- [x] DD-032: Database restructuring for multi-agent multi-mode architecture
- [x] Kalshi WebSocket as primary real-time data source (DD-016 amendment)
- [x] ChromaDB metadata approach: shared collections with category filtering, per-agent collections for decisions/learnings
- [x] Database restructuring: DD-032 (per-agent per-mode isolation, unified schema, generalized bias tracking, forecast snapshots, indexes, connection pooling, migration system)
- [x] Database efficiency: indexes, PRAGMA optimization, connection pooling, settlement cache consolidation, circuit breaker to DB, retention policy, ChromaDB model migration
- [x] ROADMAP_PROGRESS.md removed from tracking
- [x] Phase 0 review fixes (2026-08-01): `traderbot.paths` restored (H1), `profile_list` derived from registry (H3), MCP error-result semantics (H2), real JSON-RPC e2e tests (H2), hatchling reads `VERSION` (M1), `uv.lock` (M3), CI entry-point smoke (M5)
- [x] Phase 1 core auth development (issue #164): `TokenStore` + hardened `LocalTokenStore`, `ProfileRegistry`, real-auth resolver swap, strict MCP inputs, tool permissions, DD-011 category enforcement, and explicit-token workspace instructions
- [x] Phase 1 local verification: real-auth MCP transport round trips cover an allowed weather call and an out-of-category denial
- [x] Phase 1.1 implementation: `before_tool_call` token injector plugin code complete and locally tested (commit 5b5088e, issue #187); 113 Python tests + 11 TypeScript plugin tests pass; macpro-linux on-target verification complete (see next line)
- [x] Phase 1.1 deployment verification (2026-08-03): E2E injection verified on macpro-linux — plugin loads, hook fires at priority 100, token resolved from env provider, injected into MCP call params, server resolves weather profile. Three fixes required: manifest metadata + configSchema (f8b5065), token optional in schemas (f1aa518), and MCP server env must explicitly set TRADERBOT_USE_HARDCODED_AUTH=0 (0dbc981) — the subprocess does not inherit the gateway's systemd drop-in. Fail-closed verified for unmapped agents (main). Token never enters model context (agent confirms it passed no token). 113 Python + 11 TypeScript tests pass on-target.
- [ ] ~~Update pipeline~~ (deferred until roadmap is complete)
- [x] GRIB2 processing pipeline (DD-033) — decided, implementation pending
- [ ] ~~Docs/code drift~~ (deferred until roadmap is complete)
- [ ] ~~Workspace template source and category templates~~ (shelved — focusing on SysAdmin, Dev-Liaison, Weather agent first)
- [x] SysAdmin sandbox decision — DD-036 (unsandboxed with principled restrictions)
- [x] Secrets management (Infisical) — DD-037
- [x] Phase 1.5 deployment verified (2026-08-04, issue #165): 233 Python + 11 TS pass on macpro-linux. Server-side Infisical integration verified — wrapper resolves all 3 agent tokens, migration converts to 5-field format, `resolve_token` works via TokenStoreAdapter, token rotation verified, MCP stdio E2E resolves weather via Infisical. Live agent-driven E2E verified: weather agent → plugin hook (priority 100) → Infisical exec provider → wrapper resolves `weather_token` → plugin extracts raw token from 5-field JSON doc → injects into params → MCP server resolves via Infisical-backed SecretsStore → `{"status":"ok","auth":"resolved"}`. Fail-closed: unknown agent (main) blocked. Token never enters model context (agent confirmed "No"). Four deployment-discovered fixes: wrapper `extra="ignore"` (6419dc5), plugin JSON-doc token extraction (6419dc5), with-plugin.json `source` vs `type` schema fix (6b6772e), exec provider command ownership requirement (wrapper must be owned by gateway user, not root).
- [x] Self-improvement framework — DD-038 (Round 5 defined, debate integration, sub-agent config, TEMPLATE.md mods)

### Dev-Liaison Testing Protocols

Each development phase has a detailed testing protocol designed for partnership with the dev-liaison agent on macpro-linux. The full protocols are at `docs/dev-liaison-testing-protocols.md`.

| Phase | Issue | Testing Focus | Key Metrics |
|-------|------|--------------|------------|
| 1.1 | #187 | Token injector plugin loads, tokens inject, fail-closed works | 11 TS tests pass, 0 token leaks, fail-closed on unknown agent |
| 1.5 | #165 | Infisical secrets resolution, token rotation, fallback chain | Rotation < 15min, fallback chain works, 0 plaintext secrets |
| 2 | #166 | Always-on service, WebSocket, data pipeline resilience | Service uptime 24h, WS reconnect < 5s, 0 REST polling |
| 3 | #167 | Database isolation, per-agent SQLite, ChromaDB filtering | 0 cross-agent reads, migration exit 0, < 10ms cached read |
| 4 | #168 | pipx install, deploy wizard, service registration | pipx install succeeds, all 8 steps complete, services registered |
| 5 | #169 | Docker sandbox builds, isolation, bind mounts | Sandbox builds, no host file access, bind mounts correct |
| 6 | #170 | Weather toolkit tools, category isolation enforcement | Weather tools respond, non-weather tools denied, category filter works |
| 7a | #171 | Backtesting engine, SimulationClock, edge filtering | Backtest completes, clock advances, edge filter reduces runtime |
| 7b | #172 | Paper trading, risk limits, circuit breaker, promotion | Paper fills simulated, risk limits enforced, breaker triggers on breach |
| 7c | #173 | Mode transitions, demotion, suspension, recovery | Transitions logged, demotion on metrics drop, recovery via backtest |
| 8 | #174 | Debate cycle, learning promotion, experiment harness | 5-round cycle completes, learnings promote at ≥3, experiments run |
| 9 | #175 | New category agents deploy, isolate, and trade | New agents sandboxed, category isolation, tools available |

Dev-liaison runs tests via `exec` on macpro-linux and reports results to Sisyphus using the standard report format defined in the protocols document.

### Pending Discussion Topics

- [ ] ~~**Update pipeline**~~: Deferred until roadmap is complete
- [x] **Authentication implementation details**: Profile tokens as MCP tool parameters, Infisical as primary secrets vault, per-agent tool filtering, migration plan (DD-025, DD-037)
- [x] **Paper-to-live transition mechanism**: Framework designed in DD-017/018/019/021; exact promotion metrics TBD
- [x] **Module-by-module architecture review — data/news overlap**: DD-028 restructures news/ and data/ into unified data pipeline with per-source providers
- [x] **Module-by-module architecture review — P&L/settlement duplication**: DD-029 consolidates P&L and settlement logic into trading.py
- [x] **Module-by-module architecture review — CLI circular imports**: DD-030 extracts DB code from cli/helpers.py into db/
- [x] **Module-by-module architecture review — remaining modules**: DD-031 (simulation, profiles, kalshi, analysis, risk, cli, experiment, db) and DD-032 (database restructuring)
- [x] **news/ vs data/ overlap**: DD-028 — unified data pipeline with per-source providers
- [x] **P&L and settlement logic duplication**: DD-029 — single source of truth in trading.py
- [x] **CLI circular imports**: DD-030 — extract DB code from helpers.py
- [ ] ~~**Docs/code drift**~~: Deferred until roadmap is complete
- [ ] ~~**Workspace template source**~~: Shelved — focusing on SysAdmin, Dev-Liaison, Weather agent first
- [ ] **Category workspace templates**: Only weather exists currently; need to create templates for all 9 categories
- [x] **ChromaDB category metadata**: DD-032 — shared collections use category metadata filtering; per-agent collections for decisions and learnings
- [ ] ~~**Backfill command category filtering**~~: Less critical per DD-027 (all categories backfilled)
- [x] **SysAdmin sandbox decision**: DD-036 — unsandboxed with principled restrictions (MCP tool allowlist, workspace file immutability, lifecycle confirmation)
- [x] **Secrets management (Infisical)**: DD-037 — Infisical as primary vault, local encrypted fallback, token provisioning, rotation
- [x] **Improvement Framework Round 5 definition**: DD-038 — final selection by SysAdmin, implementation path by root cause, Dev-Liaison writes test modules
- [x] **Dev-Liaison build: Architecture for the Dev-Liaison on VoyageAI + database infrastructure (DD-034))
- [x] **agent-debate framework integration**: DD-038 — SysAdmin orchestrates via OpenClaw sessions_spawn/send/yield, not orchestrate.sh
- [x] **OpenClaw multi-model sub-agent spawning**: DD-038 — sessions_spawn with model overrides, ephemeral sub-agents per cycle
- [x] **TEMPLATE.md review**: DD-038 — TraderBot-specific context, statistical rigor guardrails, Kalshi market specificity, success criteria
- [x] **Weather signal engine redesign**: DD-035 — category-specific analysis toolkits replace directional signals with interpretive statistical outputs
- [x] **GRIB2 processing pipeline**: DD-033 — decided (Phase 1: ship with v2, Phase 2: after core stable)


## Design Decisions Log

### DD-001: pipx as sole installation method
**Date**: 2025-06-08
**Status**: Decided
**Context**: TraderBot previously supported three installation methods: pipx, git/source (venv), and plain pip. Each method required parallel code paths in the installer, updater, and CLI. The git/source path involved `traderbot-installer.sh` (1,048 lines), `Install-TraderBot.ps1` (1,303 lines), `traderbot-update.py` (338 lines), venv creation, symlink management, and platform-specific service templates — all producing significant maintenance burden and inconsistency.
**Decision**: pipx is the sole supported installation method. All users arrive via `pipx install traderbot`. The legacy shell/PowerShell installers, venv-based setup, git-clone-and-pip-install flow, and standalone update script are retired.
**Consequences**:
- Removes `install/traderbot-installer.sh` (1,048 lines)
- Removes `install/Install-TraderBot.ps1` (1,303 lines)
- Removes `install/traderbot-update.py` (338 lines)
- Removes venv creation, symlink management, and git-clone logic from installation
- `traderbot setup` becomes the sole first-time configuration experience
- `traderbot update` delegates to `pipx upgrade traderbot` (update pipeline discussed separately)
- pipx handles Python isolation — TraderBot no longer manages its own venv
- Service templates use `{placeholder}` syntax with runtime path resolution (DD-022) — no more hardcoded venv paths

### DD-002: OpenClaw is a hard dependency
**Date**: 2025-06-08
**Status**: Decided
**Context**: TraderBot is not designed for direct human use. It exists to enable OpenClaw agents to become fully autonomous day traders. The CLI is a toolkit the agent calls; the human never interacts with it directly.
**Decision**: OpenClaw is required. `traderbot setup` must verify OpenClaw is installed and install it if missing. There is no "run without OpenClaw" mode.
**Consequences**:
- `traderbot setup` gains an OpenClaw detection + installation step
- Setup fails if OpenClaw cannot be installed
- Docs should not present OpenClaw as optional
- Docker sandbox configuration is part of setup (since agents run in containers)

### DD-003: Docker sandbox configuration belongs in `traderbot setup`
**Date**: 2025-06-08
**Status**: Decided
**Decision**: `traderbot setup` includes Docker sandbox configuration as a setup step.
**Consequences**:
- `install/docker/Dockerfile` and `install/docker/build-sandbox.sh` remain as build artifacts, but orchestration moves into `traderbot setup` (Python CLI calls `docker build`)
- OpenClaw sandbox config (binds, dangerouslyAllowExternalBindSources, mode) is applied by Python code, not shell scripts

### DD-004: Service registration belongs in `traderbot setup`
**Date**: 2025-06-08
**Status**: Decided
**Decision**: `traderbot setup` includes service/cron registration as a setup step.
**Consequences**:
- Service templates (systemd units, launchd plists, Task Scheduler tasks) remain as package data files but are deployed by Python code inside `traderbot setup`
- `traderbot cron setup` is called internally by setup; user doesn't need to run it separately
- Data pipeline timer installation is part of setup

### DD-005: Retire `traderbot bootstrap` without `--full`
**Date**: 2025-06-08
**Status**: Decided
**Decision**: Remove the legacy `bootstrap` command. `traderbot setup` is the only first-time configuration flow. The first-time configuration process itself is now called "deploy" (not "bootstrap") to avoid confusion with OpenClaw's unrelated bootstrap function.
**Consequences**:
- `traderbot bootstrap` command removed from CLI
- `admin.py` loses the bootstrap command registration
- No more `--full` flag — setup always runs the full wizard

### DD-006: OS-aware capability detection in setup
**Date**: 2025-06-08
**Status**: Decided (implementation pending)
**Decision**: `traderbot setup` detects OS capabilities upfront and adjusts prompts and messaging accordingly. No keyring questions on headless Linux. No macOS-specific prompts on Windows. Docker sandbox step is skipped if Docker is not installed.
**Consequences**:
- Need a `detect_capabilities()` function returning: keyring_available, docker_available, service_manager (systemd/launchd/task_scheduler/none), display_available, openclaw_installed
- Setup steps conditionally included/excluded based on detected capabilities
- User sees messages relevant to their OS, not generic ones

### DD-007: Service templates as package data
**Date**: 2025-06-08
**Status**: Decided
**Context**: Service templates (systemd units, launchd plists) need to be accessible from a pipx-installed package. The `install/` directory won't exist in a pipx install.
**Decision**: Move service templates into `src/traderbot/services/` as package data files. `traderbot setup` reads them via `importlib.resources` and does path substitution before deploying to OS-appropriate locations.
**Consequences**:
- `install/services/` directory is retired (templates move to `src/traderbot/services/`)
- `install/docker/` remains as a build artifact (Dockerfile ships with the repo, not the package)
- Shell install scripts (`install-service.sh`, `install-launchd.sh`, `install-ws-daemon.sh`, `install-data-pipeline.sh`) are retired — their logic moves into Python

### DD-008: Prebuilt agent workspaces — no user customization
**Date**: 2025-06-08
**Status**: Decided
**Context**: TraderBot previously allowed users to customize agent behavior. The shift is toward shipping prebuilt workspace files (AGENTS.md, SOUL.md, TOOLS.md, IDENTITY.md, HEARTBEAT.md, etc.) that define agent behavior. This minimizes variability and user error, and enables fine-tuning of agent behavior by the TraderBot team.
**Decision**: Agent workspace files are immutable templates shipped with the package. Users do not customize them. `traderbot setup` injects them into the correct OpenClaw workspace directories during deploy.
**Consequences**:
- Workspace templates live in `src/traderbot/workspace/` (or similar) as package data
- The existing `.openclaw/workspace/` directory is the development source for these templates
- Injection logic (`profiles/injection.py`) is simplified — no user customization, just template deployment
- Category-specific variants (weather/AGENTS.md, etc.) are selected based on the agent's assigned categories

### DD-009: Deploy flow definition
**Date**: 2025-06-08
**Status**: Decided
**Context**: The deploy process needs a clear sequential flow that ensures each step's prerequisites are met before proceeding.
**Decision**: Deploy follows this exact order:

1. **OpenClaw config** — Configure LLM model/provider, web search, gateway, daemon, comms channels. Create the `main` agent with all config choices.
2. **SysAdmin setup** — Choose whether to use the pre-existing `main` agent as sysadmin or create a new one. Then: inject workspace files, register sysadmin cron/heartbeat jobs via OpenClaw gateway, authenticate sysAdmin with TraderBot.
3. **Category selection** — For each selected category: create OpenClaw agent (`openclaw agents add <category>`), inject category workspace files, register heartbeat/cron jobs, authenticate agent with TraderBot. After all agents: run `openclaw doctor`.
4. **API tokens** — Prompt for tokens relevant to selected categories. Kalshi, VoyageAI, NewsAPI, Twitter, Reddit are common to all. Category-specific keys only prompted if the category is enabled.
5. **Database creation** — Create per-agent databases with isolation. Shared ChromaDB with category-scoped queries. Sysadmin gets cross-agent access.
6. **Backfill** — Populate enabled datasource databases with 6 months of historical data, filtered by enabled categories.
7. **Simulation start** — All agents begin by backtesting on already-settled markets using historical data (DD-017, DD-019). Mechanism to promote to paper trading and live trading exists (DD-017).

**Additional note**: SysAdmin should always use the `main` agent. Creating a separate sysadmin agent adds complexity without benefit, since the sysadmin's workspace files already assume it IS the main agent. Recommendation: make step 2 non-optional — sysadmin is always `main`.

### DD-010: Docker isolation is mandatory (not optional)
**Date**: 2025-06-08
**Status**: Decided
**Context**: Previously, Docker sandbox configuration was optional — agents could run on the host. The sysadmin agent always ran without a sandbox (`mode: off`), while category agents ran in Docker containers. This creates a security gap: agents running on the host can modify TraderBot source code, access other agents' data, and bypass risk limits.
**Decision**: Docker isolation is mandatory for all category agents. The sysadmin agent runs on the host (as before, `mode: off`). Every category agent runs inside a Docker sandbox with read-only TraderBot source and isolated filesystem.
**Consequences**:
- `traderbot setup` requires Docker to be installed and running (step in DD-006 capability detection)
- Docker sandbox setup is no longer a "would you like to configure Docker?" prompt — it's a required step
- The Dockerfile in `install/docker/` is always built during setup
- OpenClaw sandbox config (`agents.defaults.sandbox.mode: docker`, `dangerouslyAllowExternalBindSources: true`) is always applied
- This closes the security gap where agents could modify source code or access other agents' data

### DD-011: Per-agent data source access control
**Date**: 2025-06-08
**Status**: Decided

> **Phase 1 implementation update:** Current `HEAD` enforces access in the MCP
> tool layer through `mcp/tools.py` and `mcp/auth.py`, in the order token → tool
> permission → category. The CLI-specific context and audit below are retained
> as the historical pre-MCP rationale; those legacy CLI paths and symbols are
> not present in the v2 source tree.

**Historical context (pre-v2):** Any agent with a TraderBot token could access any CLI command and any data source. The weather agent could theoretically call `traderbot scan --category economics`. This was both a distraction risk (agents trading outside their category) and a security risk.
**Decision**: Each category agent can only access data sources and trading operations relevant to its assigned categories. Current enforcement belongs in the TraderBot MCP tool layer, not only in workspace instructions. The original CLI consequences remain historical design rationale for any future equivalent tools.
**Historical pre-MCP consequences**:
- The `TradingProfile.enabled_categories` field (already exists in the model) becomes the enforcement mechanism
- When a profile token is resolved, the profile's `enabled_categories` are loaded
- CLI commands that accept `--category` will reject categories not in the agent's profile
- `traderbot scan` filters results to enabled categories
- `traderbot trade` rejects trades in disabled categories (already enforced in `evaluate_trade()`)
- `traderbot news-context` filters to enabled category sources
- `traderbot data-points` filters to enabled category data
- ChromaDB queries add `where={"category": "weather"}` when a profile is active
- The current SysAdmin factory explicitly enumerates every `MarketCategory`; `TradingProfile` also treats an empty category list as all permitted
- This is enforced at the CLI level, not at the OpenClaw/workspace level. Even if an agent's AGENTS.md is modified, the CLI will reject out-of-category commands

**Historical pre-v2 enforcement audit (not current `HEAD`)**:
- `evaluate_trade()` already checks `profile.is_category_enabled(market_category)` and returns 0 for disabled categories ✓
- `traderbot news` commands already filter by profile categories ✓
- `traderbot scan --category` does NOT currently enforce profile categories ✗ (needs fix)
- `traderbot data-points` does NOT currently enforce profile categories ✗ (needs fix)
- ChromaDB queries do NOT currently filter by profile categories ✗ (needs fix)
- `traderbot analyze` does NOT enforce profile categories ✗ (needs fix)

**Current Phase 1 enforcement**:
- MCP tool layer authenticates the token, checks tool permission, then enforces category access for category-bearing tools ✓ — `market_edge` is the current category-bearing tool; planned tools remain unimplemented

### DD-012: Authentication redesign — encrypted vault + OpenClaw SecretRef hybrid
**Date**: 2025-06-08
**Status**: Superseded by DD-037; historical design discussion only, not implemented
**Context**: The current authentication system has three problems:

1. **Keyring is insufficient on headless Linux.** The `keyring` package falls back to a plaintext `.env` file when no OS keyring backend is available (no D-Bus session on headless servers). API keys are stored in plaintext on the most security-sensitive deployments.

2. **Agent tokens are not secure.** The current `TRADERBOT_PROFILE_TOKEN` is a 12-character URL-safe string (~72 bits of entropy) stored in plaintext in `.env` files and passed as environment variables. Any agent that can read the filesystem or environment can impersonate another agent.

3. **API tokens lack unified storage.** Kalshi keys, Voyage keys, NewsAPI keys are stored in a mix of keyring (when available) and `.env` (always). There is no encryption at rest for the `.env` fallback.

**Investigation: OpenClaw SecretRef support**

OpenClaw has a built-in secrets management system with three provider types:

- **Env provider** — reads from environment variables (`source: "env"`)
- **File provider** — reads from a JSON or single-value file (`source: "file"`, `provider-mode: json` or `singleValue`)
- **Exec provider** — calls an external binary that returns secrets on stdout (`source: "exec"`)

Any OpenClaw config value that accepts a SecretRef can reference any of these providers. Example:

```json5
channels: {
  discord: {
    token: { source: "env", provider: "default", id: "DISCORD_BOT_TOKEN" }
  }
}
```

OpenClaw also supports custom provider registration:

```bash
openclaw config set secrets.providers.vault \
  --provider-source exec \
  --provider-command /usr/local/bin/openclaw-vault \
  --provider-arg read \
  --provider-arg openai/api-key \
  --provider-json-only \
  --provider-timeout-ms 5000
```

And file-based providers for structured secret stores:

```bash
openclaw config set secrets.providers.vaultfile \
  --provider-source file \
  --provider-path /etc/openclaw/secrets.json \
  --provider-mode json
```

**What OpenClaw SecretRef solves well:**
- LLM API keys (OpenAI, Anthropic, etc.) — OpenClaw needs these for agent orchestration
- Channel tokens (Discord, Slack, Telegram, iMessage) — OpenClaw territory
- Gateway auth tokens — OpenClaw territory
- Any credential that OpenClaw needs to route messages or run agents

**What OpenClaw SecretRef does NOT solve:**
- **TraderBot-specific API keys** (Kalshi, VoyageAI, NewsAPI, category-specific keys) — OpenClaw doesn't know about these
- **Per-agent access control** — SecretRef has no concept of "this token is only for the weather agent." Any agent that can read the OpenClaw config can read any SecretRef value
- **TraderBot profile tokens** — these are TraderBot's mechanism for identifying which agent is calling
- **Docker container access** — an exec provider needs the binary inside the container; a file provider needs the file bind-mounted; an env provider needs the var injected

**Decision: Hybrid approach — OpenClaw SecretRef for OpenClaw concerns, TraderBot encrypted vault for TraderBot concerns**

```
OpenClaw SecretRef (manages):
  +-- LLM API keys (OpenAI, Anthropic, etc.)
  +-- Channel tokens (Discord, Slack, Telegram, etc.)
  +-- Gateway auth token
  +-- Web search API keys

TraderBot Encrypted Vault (manages):
  +-- Global namespace:
  |   +-- kalshi.api_key
  |   +-- kalshi.private_key_pem
  |   +-- voyage.api_key
  |   +-- newsapi.api_key (shared across all agents)
  +-- Per-agent namespaces:
  |   +-- weather.openweathermap_api_key
  |   +-- economics.fred_api_key
  |   +-- crypto.coingecko_api_key
  |   +-- (common keys fall back to global namespace)
  +-- Agent tokens:
      +-- (existing tokens.enc, already Fernet-encrypted, with per-agent scoping)
```

**Vault implementation:**
- Single encrypted file: `~/.traderbot/vault.enc` (Fernet-encrypted, same library as current `tokens.enc`)
- Master key: `~/.traderbot/.vault_key` (0600 permissions, 32 bytes random)
- Namespace-based access: each agent can only read from its namespace + global
- Sysadmin namespace can read all namespaces
- Docker containers receive `vault.enc` and `.vault_key` via bind mount (read-only)

**LLM API key overlap:** Both OpenClaw (for agent orchestration) and TraderBot (for experiment LLM calls) need the LLM API key. Two options:
1. Store in both places (OpenClaw SecretRef + TraderBot vault) — simple, slightly redundant, fully decoupled
2. TraderBot reads from OpenClaw config — avoids duplication but creates a dependency on OpenClaw gateway accessibility from Docker containers

Recommendation: Option 1 for simplicity and isolation. The LLM key is a single value; redundancy is minimal.

**Key migration path:**
1. `traderbot setup` creates the vault and master key during deploy step 4
2. Existing `.env` credentials are migrated into the vault during setup
3. After migration, `~/.traderbot/.env` only contains `TRADERBOT_PROFILE_TOKEN` (which itself migrates into `tokens.enc`)
4. OpenClaw credentials (LLM keys, channel tokens) are configured via OpenClaw SecretRef during deploy step 1
5. The `.env` file is eventually retired entirely — all credentials live in either the vault (TraderBot) or OpenClaw SecretRef (OpenClaw)

**Open questions for authentication redesign:**
- [ ] Docker container access: bind mount vault.enc + .vault_key read-only, or inject master key as environment variable?
- [ ] Per-agent Kalshi keys: support different API keys per agent (for multi-account strategies), or one global Kalshi key sufficient?
- [ ] Exec provider integration: should TraderBot register as an OpenClaw exec provider so OpenClaw can read TraderBot credentials too?
- [ ] Key rotation: how does vault re-encryption work when the master key changes?
- [ ] Should the master key be derived from the user's master password (existing `master_password.py`), or be independent?


### DD-013: Three-mode trading (backtesting/paper/live)
**Date**: 2025-06-08
**Status**: Decided
**Context**: Agents need a safe progression from validation on historical data to real-money trading. A single always-live model is unsafe; a purely simulated model never validates against live market conditions. Trading operates in three distinct modes with a defined promotion path.
**Decision**: Agents trade in three modes — BACKTESTING, PAPER, LIVE — with the same MCP tools regardless of mode. TraderBot routes on the backend based on the calling agent's profile mode (profile-aware MCP routing). Promotion and demotion follow the lifecycle defined in DD-017; backtest mechanics in DD-019; paper/live architecture in DD-021.
**Consequences**:
- All agents start in BACKTESTING (validation on settled markets with historical data)
- Promotion to PAPER requires passing the deployment bar (Sharpe ≥ 1.0, win rate ≥ 55%, sample size ≥ 30)
- Promotion to LIVE requires 30+ paper trades and minimum 14 days of paper trading
- Demotion (to backtesting or suspended) occurs if metrics fall below threshold or risk limits breach
- MCP tools behave identically across modes at the interface level; mode routing happens server-side (see DD-021 mode table)
- Three-mode database isolation: backtest DB (read-only reference), paper DB, live DB (read-write + Kalshi sync)

---

### DD-014: Authentication and secrets architecture

**Date**: 2025-06-08
**Status**: Superseded by DD-015, DD-025, and DD-037; historical design discussion only, not implemented

**Context**: The current architecture has three credential systems: (1) `auth.py` uses keyring → env → `.env` fallback for API tokens, (2) `profiles/tokens.py` uses Fernet-encrypted tokens for agent authentication, and (3) `master_password.py` uses PBKDF2 for trade/simulate command gating. All three systems have problems:

1. **Keyring is unreliable** on headless Linux (no Secret Service daemon), Windows Server, and CI environments.
2. **The `.env` file is bind-mounted into every Docker container** via the blanket `$HOME/.traderbot:/home/traderbot/.traderbot:rw` mount. This means every agent can read all API tokens in plaintext, all other agents' auth tokens, encryption keys, and other agents' databases.
3. **Encryption at rest is theater** for an always-on system. TraderBot agents run 24/7. The decryption key is always available to the TraderBot process. An encrypted vault that is always unlocked is effectively plaintext.
4. **Agents should never access API tokens directly**. They interact with TraderBot through the CLI. If an agent can read API keys (from `.env`, environment variables, or process memory), it could bypass TraderBot's guardrails and call external APIs directly.
5. **Per-agent access control is not enforced** at the CLI level. A weather agent with a valid token can call `traderbot scan --category politics` even though politics isn't in its `enabled_categories`.

**The architectural tension**: The TraderBot CLI runs inside Docker containers and makes direct API calls (Kalshi, VoyageAI, etc.). It needs API keys to function. But if we remove API keys from containers, the CLI can't make API calls. This is the fundamental constraint that drives the daemon architecture.

**Decision**:

**Phase 1 — Immediate access control hardening (during v2 realignment):**

1. **Replace keyring + .env with a secrets store** (`~/.traderbot/secrets/secrets.json`, 0600 permissions)
   - Single JSON file: `{ "kalshi": {"api_key": "...", "private_key_pem": "..."}, "voyage": {"api_key": "..."}, ... }`
   - No encryption at rest (honest about the threat model — always-on system)
   - Strict POSIX file permissions (0600, owner-only read/write)
   - No keyring dependency (removes headless Linux problem entirely)
   - Managed via `traderbot auth set-key` (existing CLI) and `traderbot setup`
   - `.env` file is retired after migration
   - `keyring` dependency can be removed from pyproject.toml

2. **Restructure Docker bind mounts** (per-agent, not blanket)
   - Remove: `$HOME/.traderbot:/home/traderbot/.traderbot:rw` (blanket mount)
   - Add per-agent selective mounts:
     - `~/.traderbot/paper-{category}/:/home/traderbot/.traderbot/paper-{category}/:rw` (agent's own data)
     - `~/.traderbot/chroma/:/home/traderbot/.traderbot/chroma/:ro` (shared ChromaDB, read-only)
     - `$HOME/traderbot:/traderbot:ro` (source code, unchanged)
   - **NOT mounted**: `.env`, `tokens.enc`, `keys/`, `secrets/`, `profiles.enc`, `.master_key`
   - Agent profile token injected via OpenClaw SecretRef (env provider) → `TRADERBOT_PROFILE_TOKEN` env var
   - API keys still accessible to CLI inside container (Phase 1 accepts this limitation)
   - Sysadmin (main) continues running on host with full access

3. **Enhance agent token scoping**
   - Add `enabled_categories` field to token records (inherited from profile at assignment time)
   - Every CLI command validates: token → profile → categories → is this category allowed?
   - Add `permissions` field: `["scan", "analyze", "trade", "data-points", "news-context", ...]`
   - This provides access control at the CLI level even before the daemon architecture

4. **Retire keyring dependency**
   - Remove `keyring` from pyproject.toml
   - Remove keyring code from `auth.py` and `profiles/auth.py`
   - All credential resolution becomes: secrets.json → environment variables → interactive prompt (during setup only)

**Phase 2 — TraderBot host daemon (soon after v2 realignment):**

5. **Build TraderBot daemon** (`traderbot daemon`)
   - Persistent process on the host (systemd/launchd service)
   - Holds all API keys in memory (loaded from `secrets.json` at startup)
   - Listens on Unix socket `~/.traderbot/traderbot.sock`
   - Authenticates requests via agent profile tokens
   - Validates category permissions per request
   - Makes API calls on behalf of authenticated agents
   - Returns data to the thin CLI client inside containers

6. **Refactor CLI into thin client**
   - CLI inside container sends requests to daemon via Unix socket
   - Socket is bind-mounted read-only into containers
   - CLI never touches API keys
   - Local-only commands (reading trade history, ChromaDB queries) still work directly
   - All external API calls route through the daemon

7. **Remove all credentials from container bind mounts**
   - No `.env`, no `secrets.json`, no environment variables with API keys inside containers
   - Only the profile token env var and the daemon socket

**Alternative considered — OpenClaw MCP integration:**
- Register TraderBot as an MCP server with the OpenClaw gateway
- MCP server runs on host with full secret access
- Agents call TraderBot tools through OpenClaw's tool interface
- Leverages OpenClaw's existing infrastructure instead of building a custom daemon
- Requires OpenClaw to support host-side MCP tool execution for sandboxed agents (needs verification)

**Division of secrets responsibility:**

| Secret type | Manager | Storage | Access |
|---|---|---|---|
| OpenClaw LLM keys, gateway auth, channel tokens | OpenClaw SecretRef | `secrets.providers` in `openclaw.json` | OpenClaw gateway on host |
| TraderBot API tokens (Kalshi, Voyage, NewsAPI, etc.) | TraderBot secrets store | `~/.traderbot/secrets/secrets.json` (0600) | TraderBot daemon on host only |
| Agent profile tokens | TraderBot token registry | `~/.traderbot/tokens.enc` (Fernet-encrypted) | Validated by TraderBot CLI/daemon; injected into containers via OpenClaw SecretRef (env provider) |
| Master password | TraderBot | `~/.traderbot/.master_key` (0600) | Host only; auto-auth for paper mode |

**Consequences:**
- Removes `keyring` dependency entirely
- Removes `.env` file from `~/.traderbot/`
- Removes blanket bind mount of `~/.traderbot/` into containers
- Phase 1: API keys are still accessible inside containers (read from `secrets.json` via selective mount or env vars)
- Phase 2: API keys completely removed from containers; all API calls proxied through daemon
- Agent authentication tokens become scoped (categories + permissions)
- Per-agent data isolation is enforced at the bind-mount level
- Sysadmin access to all data is preserved (runs on host, outside containers)

---

### DD-015: TraderBot MCP server architecture

**Date**: 2025-06-08
**Status**: Decided

**Context**: TraderBot currently runs as a CLI inside Docker containers. The entire `~/.traderbot/` directory is bind-mounted into every container with read-write access, giving every agent full access to all API tokens, other agents' databases, and authentication credentials. This violates the isolation and security requirements established in DD-011 and DD-014.

**Investigation of OpenClaw's tool and sandbox infrastructure revealed:**

1. **MCP servers run on the host** — When OpenClaw launches an MCP stdio server (`mcp.servers.<name>.command`), it runs as a child process of the OpenClaw gateway, which runs on the host. The MCP server has full host filesystem access.

2. **MCP tools are available to sandboxed agents** — OpenClaw's sandbox tool policy requires `bundle-mcp` in the nested `tools.sandbox.tools.allow` gate. The tool call is routed from the sandbox container through the gateway to the host-side MCP server process.

3. **Per-agent tool filtering** — Restrictive policy uses an explicit per-agent `tools.allow` list plus `tools.deny`. `tools.alsoAllow` is additive to an implicit wildcard and must not be used as a restrictive allowlist.

4. **`tools.exec.host`** — OpenClaw supports four exec host modes: `auto`, `sandbox`, `gateway`, `node`. For sandboxed agents, `auto` resolves to `sandbox`. Setting `host=gateway` makes exec commands run on the host. However, this applies to ALL exec commands for that agent, which would bypass the sandbox entirely.

5. **OpenClaw SecretRef limitation** — Secret providers exist, but the pinned schema rejects per-agent `env` and nested `mcp` fields while root and MCP-server environments are shared. Config-only secure per-agent profile-token injection is therefore blocked.

> **Phase 1.1 solution: `before_tool_call` plugin hook**
>
> Research into OpenClaw's plugin hook system ([docs.openclaw.ai/plugins/hooks](https://docs.openclaw.ai/plugins/hooks)) identified a first-party-supported mechanism that solves the per-agent token injection problem without a separate proxy server.
>
> An OpenClaw plugin registers a `before_tool_call` hook that:
> 1. Matches `traderbot__*` tool names
> 2. Reads `ctx.agentId` (host-derived, trusted, not model-controllable)
> 3. Resolves the agent's token from a Vault-backed SecretRef via `resolveSecretRefValues` from `openclaw/plugin-sdk/secret-ref-runtime`
> 4. Returns `{ params: { ...event.params, token: resolvedToken } }` to inject the token
> 5. Blocks unrecognized agents (`{ block: true }`)
>
> The model never sees or controls the token. TraderBot's existing `resolver.py` → `TradingProfile` → `auth.py` pipeline still validates the injected token server-side.

**Decision**: TraderBot will register as an MCP server with OpenClaw. This provides the tool transport and lets TraderBot enforce explicit-token authorization and category isolation server-side. Secure per-agent token delivery is handled by an OpenClaw `before_tool_call` plugin hook (issue #187, Phase 1.1), not by static configuration. Implementation plan: `.omo/plans/phase1-1-token-injector.md`. The plugin code is complete and **deployment-verified on macpro-linux** (2026-08-03): E2E injection works — the hook fires, resolves the agent's token from the env provider, injects it into the MCP call, and the server resolves the weather profile. Three fixes were required during deployment testing: manifest metadata + `configSchema` (`f8b5065`), token optional in MCP tool schemas (`f1aa518`), and MCP server env must explicitly set `TRADERBOT_USE_HARDCODED_AUTH=0` (`0dbc981`). 113 Python + 11 TypeScript tests pass on-target. Vault SecretRef integration is deferred to Phase 1.5.

**Architecture:**

```
Agent (Docker container)
   │
   ├── Calls MCP tools via OpenClaw tool interface
   │   (traderbot__scan, traderbot__analyze, traderbot__trade, etc.)
   │
   └── OpenClaw gateway routes tool calls →
           TraderBot MCP server (host process)
           ├── Authenticates the explicit profile-token tool parameter
           ├── Validates category permissions per tool
           ├── Will read provider credentials from the future secrets store
           ├── Makes external API calls (Kalshi, Voyage, etc.)
           └── Returns data to agent
```

**MCP tool design:**
- Common tools: `traderbot__scan`, `traderbot__positions`, `traderbot__heartbeat`, `traderbot__performance`, `traderbot__audit`, `traderbot__learnings`
- Category-scoped tools: `traderbot__weather_forecast`, `traderbot__weather_data`, `traderbot__economics_indicators`, etc.
- Trading tools: `traderbot__trade`, `traderbot__analyze`
- Sysadmin tools: `traderbot__profile_list`, `traderbot__auth_check`, `traderbot__cron_setup`

The authoritative, complete tool reference is `v2docs/09-mcp-tools.md` — this list is illustrative, not exhaustive.

**Category isolation via OpenClaw per-agent tool config:**

> **Historical non-deployable sketch:** This example predates the pinned
> `d1c96302` schema audit. Its `alsoAllow` entries are additive rather than
> restrictive, and its sandbox gate uses the obsolete shape. It is retained to
> preserve the original MCP design rationale; use the explicit `allow` plus
> nested `tools.sandbox.tools.allow` form in DD-025 instead.

```json5
{
  agents: {
    list: [
      {
        id: "weather",
        sandbox: { mode: "all" },
        tools: {
          deny: ["group:runtime", "group:fs"],
          alsoAllow: [
            "traderbot__scan", "traderbot__analyze",
            "traderbot__positions", "traderbot__trade",
            "traderbot__heartbeat", "traderbot__performance",
            "traderbot__weather_forecast", "traderbot__weather_data",
            "traderbot__weather_signals", "traderbot__news_context",
          ],
        },
      },
    ],
  },
  mcp: {
    servers: {
      traderbot: {
        command: "traderbot-mcp-server",
        args: [],
      },
    },
  },
  tools: {
    sandbox: {
      tools: {
        alsoAllow: ["bundle-mcp"],
      },
    },
  },
}
```

**What changes:**
- **New**: `traderbot-mcp-server` CLI command that starts the MCP server
- **New**: MCP tool definitions for all current CLI commands
- **New**: Per-agent OpenClaw configuration with tool allowlists
- **Changed**: Docker bind mounts become minimal (only agent data + workspace, no secrets)
- **Changed**: Agent workspace TOOLS.md describes MCP tool calls, not CLI commands
- **Changed**: `~/.traderbot/secrets/secrets.json` replaces `.env` + keyring (DD-014 Phase 1)
- **Changed**: Agent profile tokens injected via OpenClaw SecretRef env provider, not bind-mounted files
- **Removed**: TraderBot CLI bind mount from Docker container (`/traderbot/.venv/bin`)
- **Removed**: Blanket bind mount of `~/.traderbot/` into containers
- **Removed**: Keyring dependency
- **Removed**: `.env` file for API tokens

**What stays the same:**
- Sysadmin agent runs on host (sandbox mode: off) and can still use CLI directly
- TraderBot CLI still exists for human debugging, sysadmin use, and setup/deploy
- Per-agent data isolation: each agent gets its own SQLite and ChromaDB partition
- Docker sandbox is mandatory for category agents (DD-010)
- Prebuilt workspace templates (DD-008)

**Authentication flow:**
1. Agent calls an MCP tool (e.g., `traderbot__scan`) via OpenClaw's tool interface
2. OpenClaw routes the call to the TraderBot MCP server (host process)
3. MCP server receives the tool call with OpenClaw session context (agent ID)
4. MCP server maps agent ID → TraderBot profile → enabled categories
5. MCP server validates the tool is available for the agent's categories
6. MCP server reads required API tokens from `secrets.json` (host-side, 0600)
7. MCP server makes the external API call
8. MCP server returns the data to the agent

**API token access model:**
- TraderBot MCP server (host process): reads all API tokens from `secrets.json`
- Category agents (containers): never see API tokens, only receive tool results
- Sysadmin agent (host): can use CLI directly, has full access
- Per-agent Kalshi keys: MCP server selects the correct key based on the calling agent's profile

**Consequences:**
- Eliminates the need for a TraderBot daemon (OpenClaw gateway IS the daemon)
- Eliminates the blanket bind-mount security hole
- Provides clean category isolation via OpenClaw's per-agent tool filtering
- Removes the need for API tokens inside containers
- Removes the need for keyring (MCP server reads from `secrets.json` on host)
- Requires building `traderbot-mcp-server` as a new CLI entry point
- Requires updating workspace templates from CLI commands to MCP tool descriptions
- Requires updating `traderbot setup` to configure OpenClaw MCP and per-agent tool policies
- TraderBot CLI inside containers is no longer needed (but still exists for host-side use)

---

### DD-016: TraderBot as always-on service with continuous data pipeline

**Date**: 2025-06-08
**Status**: Decided

**Context**: TraderBot is designed to be fully autonomous and always-on. Both OpenClaw and TraderBot launch at boot and run continuously. Currently, data fetching is triggered by agent cron jobs (decision loops call `traderbot scan`, heartbeat loops call `traderbot heartbeat`). This reactive model means data is only fetched when an agent asks for it, introducing latency and redundant API calls. Trading data is time-sensitive — delays of even a few minutes can determine outcomes. API rate limits must be respected while maximizing data freshness.

**Decision**: TraderBot runs as a persistent system service (systemd/launchd/Task Scheduler) that proactively fetches and organizes data independent of agent requests. When agents request information via MCP tools, data is served from local databases — not fetched on-demand from external APIs.

**Architecture — TraderBot service components:**

```
TraderBot service (host, always-on, launches at boot)
│
├── WebSocket daemon (persistent Kalshi connection)
│   ├── Subscriptions: ticker, orderbook_delta, market_lifecycle_v2, user_fills, user_orders
│   ├── Maintains real-time cache of market prices, orderbooks, positions, fills
│   ├── Seeds cache from REST on startup if stale
│   └── Re-subscribes orderbook_delta when new markets appear
│
├── Data collection workers (scheduled via internal timers, not OpenClaw cron)
│   ├── Market scanner: reads open markets from WebSocket cache (new markets detected via market_lifecycle_v2)
│   ├── News ingest: fetches + embeds news every 30 min (all categories)
│   ├── Weather data: fetches NWS forecasts + Open-Meteo historical every hour
│   ├── Economic indicators: fetches FRED data daily
│   ├── Crypto prices: fetches CoinGecko every 15 min (when crypto enabled)
│   ├── Sports data: fetches TheSportsDB daily (when sports enabled)
│   └── Settlement monitor: checks recently settled markets every hour
│
├── MCP server (responds to agent tool calls)
│   ├── Reads from local databases, NOT external APIs
│   ├── Returns WebSocket-cached data for real-time requests (orderbook, ticker)
│   ├── Returns SQLite/ChromaDB data for historical queries
│   ├── Validates agent identity and category permissions
│   └── Sub-millisecond response for cached data
│
└── Local databases
    ├── SQLite: market data, trade decisions, positions, settlements (per-agent)
    ├── ChromaDB: news embeddings, data points, market patterns (shared, category-filtered)
    └── WebSocket cache: real-time Kalshi prices, orderbooks, fills, positions
```

**Key principle: TraderBot fetches, agents query.**
- TraderBot's data collection workers proactively fetch and organize data on a schedule
- Agents request information via MCP tools, which query local databases
- This eliminates per-request API latency and reduces redundant API calls
- API rate limits are managed centrally by the TraderBot service
- WebSocket provides real-time Kalshi data with zero polling latency

**Latency model:**

| Data type | Source | Freshness | Latency to agent |
|---|---|---|---|
| Market prices (ticker) | WebSocket cache | Real-time (< 1s) | < 1ms (local read) |
| Orderbook | WebSocket cache | Real-time (< 1s) | < 1ms (local read) |
| Open markets list | WebSocket cache (market_lifecycle_v2) | Real-time (< 1s) | < 1ms (local read) |
| News context | News ingest worker | ≤ 30 min | < 1ms (local read) |
| Weather forecasts | Weather worker | ≤ 1 hr | < 1ms (local read) |
| Economic indicators | FRED worker | ≤ 24 hr | < 1ms (local read) |
| Trading signals | Computed on query | Uses latest cached data | < 10ms (computation) |
| Historical market data | Kalshi REST API | On demand (backfill/cache) | Variable (API latency) |
| Historical candlesticks | Kalshi REST API | On demand (backfill/cache) | Variable (API latency) |
| Trade execution | Live API call | N/A | Variable (API latency) |

**WebSocket-first principle:**
- The Kalshi WebSocket is the **sole** source for all real-time Kalshi data — market prices, orderbooks, fills, order status, and market lifecycle events
- REST API is used **only** for: (1) seeding the cache on startup when WebSocket is not yet connected, (2) recovering from WebSocket disconnections, and (3) fetching historical data (settled markets, candlesticks, historical trades)
- No REST polling for current market data — the WebSocket provides a continuous stream, and any REST call for data that the WebSocket already provides is a bug
- All market prices, orderbooks, fills, and order status come through WebSocket with sub-second latency
- The `market_lifecycle_v2` channel detects new markets as they appear — no REST scan needed to discover them
- Data collection workers that need Kalshi data (market scanner, settlement monitor) read from the WebSocket cache, not from REST endpoints

**Consequences:**
- TraderBot service must be registered as a system service during `traderbot setup`
- Service manages its own data collection schedule (internal timers, not OpenClaw cron)
- OpenClaw cron jobs remain for agent decision loops and heartbeat (these are agent behaviors, not data collection)
- The `cron_loops.py` three-loop model is retired — data collection is TraderBot's job, not triggered by agent loops
- Current news-ingest systemd timer is absorbed into the TraderBot service
- `ws_daemon.py` becomes a core component of the service (currently a standalone CLI command)
- MCP tool responses are fast because data is pre-fetched and locally available
- API rate limits are managed in one place (the service) instead of being scattered across agent cron jobs
- Trade execution is the only path that requires a live API call (cannot be pre-fetched)

**Relationship to DD-015 (MCP architecture):**
- The TraderBot service IS the MCP server. They are the same process.
- The service starts at boot, opens the WebSocket, starts data collection workers, and listens for MCP tool calls over stdio.
- Agents call MCP tools → service queries local DB → returns cached data.
- This means the MCP server is not just a request-response handler; it's a full autonomous data pipeline.

**Open questions:**
- How does the TraderBot service communicate its health/status to OpenClaw? (likely via OpenClaw's heartbeat mechanism)
- How do we handle the transition from per-agent cron-triggered data fetching to centralized service-managed data collection?

**Resolved:**
- ~~Should the WebSocket daemon run as a separate process or as a thread within the service?~~ The WebSocket daemon is a core component of the TraderBot service process (DD-016 architecture diagram). It runs as an async task within the main process, not a separate service unit. The old `traderbot-ws-daemon.service` is retired.

---

### DD-017: SysAdmin role — oversight, guardrails, and self-improvement orchestration

**Date**: 2025-06-08
**Status**: Decided

**Context**: TraderBot is fully autonomous. SysAdmin's role is not to trade but to provide oversight, coordinate between agents, prevent deviation from operating procedure, and orchestrate the self-improvement loop. Agents start in backtesting (not paper trading) and must earn their way to live trading through measurable performance.

**Decision**: SysAdmin is the fleet orchestrator with three core responsibilities: oversight, coordination, and self-improvement enablement.

**SysAdmin responsibilities:**

1. **Oversight** — Monitor fleet health and prevent deviation:
   - Circuit breaker monitoring (`traderbot halt --json` every 30 min)
   - Performance review across all agents (P&L, win rate, drawdown every 6 hours)
   - Auth credential verification (`traderbot auth check --json` every hour)
   - Pipeline health (data freshness, WebSocket daemon status, backfill staleness)
   - Learning review (promote patterns with recurrence ≥ 3 to PENDING_REVIEW)

2. **Coordination** — Route information between agents:
   - Receive experiment proposals from category agents via `sessions_send`
   - Review proposed experiments, queue valid ones in test-lab/backlog.md
   - Deploy validated improvements via `traderbot profile update`
   - Notify agents of deployment status via `sessions_send`
   - Coordinate resource sharing (avoid duplicate API calls, share market data)

3. **Self-improvement orchestration** — Drive the improvement cycle:
   - Daily evaluation of each agent's performance
   - Root cause analysis when agents underperform
   - Design experiments to test improvements
   - Validate experiment results against deployment bar
   - Submit code-level improvements as GitHub issues
   - Deploy parameter-level improvements via profile updates

**Agent lifecycle — four states:**

```
BACKTESTING → PAPER TRADING → LIVE TRADING → (SUSPENDED)
     ↑              │               │               │
     └──────────────┘               │               │
     (demoted if metrics            │               │
      fall below threshold)        │               │
                                    └───────────────┘
                                     (demoted if risk
                                      limits breached)
```

**State 1: BACKTESTING (initial state)**
- Freshly deployed agents begin by backtesting on already-settled markets using historical data
- Backtest validates the model and allows rapid improvement without real money or even paper money at risk
- The 6-month backfill (DD-009 Step 6) provides the historical data for backtesting
- Agent runs `traderbot backtest --strategy <strategy> --category <cat> --from <6mo_ago> --to <today> --json`
- Daily evaluation: SysAdmin reviews backtest Sharpe, win rate, and sample size
- Promotion criteria (deployment bar): Sharpe ≥ 1.0, win rate ≥ 55%, sample size ≥ 30 trades
- If backtest fails: SysAdmin and agent investigate together via `sessions_send`

**State 2: PAPER TRADING**
- Agent trades on live markets with simulated money
- Paper positions tracked in per-agent SQLite DB
- All trade decisions logged with full reasoning in audit trail
- Daily evaluation continues
- Promotion criteria to live: Sharpe ≥ 1.0, win rate ≥ 55%, 30+ paper trades, minimum 14 days of paper trading
- Demotion back to backtesting if metrics fall below threshold

**State 3: LIVE TRADING**
- Agent trades on live markets with real money (Kalshi API)
- All risk limits enforced by TraderBot's risk module (immutable hard limits)
- Circuit breaker monitors for runaway losses
- Demotion to paper trading if drawdown exceeds threshold or circuit breaker triggers
- SysAdmin monitors live agents more frequently (heartbeat every 30 min)

**State 4: SUSPENDED**
- Agent is suspended from all trading (circuit breaker FULL_STOP)
- SysAdmin investigates root cause
- Agent must re-validate through backtesting before resuming

**Self-improvement cycle (detailed):**

1. **Daily evaluation** — SysAdmin reviews each agent's performance from the previous day:
   - `traderbot performance --json --from <yesterday> --to <today>`
   - Check P&L, win rate, Sharpe ratio, drawdown, position count
   - Compare against deployment bar thresholds

2. **Loss investigation** — If an agent's balance sheet shows a loss:
   - SysAdmin sends investigation prompt via `sessions_send` to the category agent
   - Category agent and SysAdmin collaborate to determine root cause
   - **Top-level question**: Was this caused by TraderBot's analysis/data model, or by agent behavior?
   - Sub-questions:
     - Were the right data sources available and fresh? (data pipeline issue → TraderBot code change)
     - Were the right tools/symbols available? (tool gap → TraderBot feature)
     - Did the agent follow its TOOLS.md instructions? (behavior issue → workspace template change)
     - Was the signal quality sufficient? (model issue → analysis module improvement)
     - Were there better analytical methods available? (ML model, statistical method → TraderBot enhancement)
     - Was the market condition unusual? (regime change → risk parameter adjustment)

3. **Improvement design** — Based on root cause:
   - **TraderBot code change needed**: Design an experiment, submit as GitHub issue
   - **Workspace template change needed**: Update AGENTS.md/SOUL.md/TOOLS.md, deploy to agents
   - **Risk parameter adjustment**: Adjust via `traderbot profile update`, test in backtest first
   - **Data source improvement**: Add new data source or improve existing pipeline, submit as GitHub issue

4. **Test-lab iteration** — Improvements are tested in the test-lab:
   - SysAdmin queues experiment in `test-lab/backlog.md`
   - Experiment runs: `traderbot experiment run --treatments control,variant --replicates 3`
   - Results validated against deployment bar
   - Iterate until metrics are met

5. **Deployment** — Validated improvements are deployed:
   - Parameter changes: `traderbot profile update <agent> --field <param> --value <val>`
   - Workspace template changes: Update files in `.openclaw/workspace/<category>/` and re-propagate
   - Code changes: Submit as GitHub issue with full experiment design, test results, expected benefit

**Investigation framework — root cause categories:**

| Category | Root Cause | Resolution Path | Owner |
|---|---|---|---|
| Data quality | Stale, missing, or incorrect data | Fix data pipeline, add data source | TraderBot code issue |
| Data coverage | Missing data source for relevant signals | Add new data source | TraderBot feature issue |
| Analysis model | Signal quality insufficient, wrong indicators | Improve analysis module | TraderBot code issue |
| Risk parameters | Edge threshold, position sizing, drawdown limits | Adjust profile parameters | SysAdmin (profile update) |
| Agent behavior | Agent didn't follow TOOLS.md, made unauthorized trades | Update workspace template | Workspace template issue |
| Market regime | Unusual market conditions, black swan | Add regime detection, adjust risk | TraderBot + workspace |
| Tool gap | Agent needed a tool that doesn't exist | Add MCP tool | TraderBot feature issue |

**Learning promotion flow:**
- Agent discovers pattern → logs in `.learnings/LEARNINGS.md` with Recurrence-Count
- When Recurrence-Count ≥ 3 across 2+ sessions within 30 days → promote to PENDING_REVIEW
- SysAdmin reviews PENDING_REVIEW patterns during heartbeat
- Validated patterns → experiment design → test-lab backlog → experiment run → results
- Results meet deployment bar → deploy or submit GitHub issue
- Results don't meet bar → archive with reasoning, try different approach

**Relationship to existing code:**
- `src/traderbot/simulation/engine.py` — BacktestEngine (already exists, used for backtesting)
- `src/traderbot/experiment/` — Experiment framework (populate, run, evaluate) (already exists)
- `src/traderbot/learning.py` — Learning pattern tracking and promotion (already exists)
- `.openclaw/workspace/test-lab/` — Test lab backlog and results (already exists)
- `.openclaw/workspace/.learnings/` — Learning patterns (already exists)

**What changes from current implementation:**
- Deploy Step 7 changes from "all agents begin in paper trading" to "all agents begin by backtesting"
- New agent lifecycle states: backtesting → paper trading → live trading (with promotion/demotion)
- SysAdmin's daily evaluation cycle is formalized (currently ad-hoc in heartbeat)
- Root cause investigation framework is new (currently just "promote learnings")
- GitHub issue submission for code-level improvements is new
- Agent lifecycle state transitions need `traderbot profile update --mode` support for backtesting/paper/live

**What stays the same:**
- BacktestEngine, experiment framework, learning system all exist and are functional
- Test-lab backlog and results format are well-defined
- The learning promotion threshold (Recurrence-Count ≥ 3) works
- SysAdmin's TOOLS.md already includes experiment and profile management commands

---

### DD-018: Autonomous Improvement Framework

**Date**: 2025-06-15
**Status**: Decided

**Context**: TraderBot's self-improvement system operates at three layers, each with distinct scope, triggers, and mechanisms. The agent-debate framework (gumbel-ai/agent-debate) provides the procedural structure for Layer 2.

**Three-layer architecture:**

**Layer 1: Reactive Agent Learnings**
- Scope: Category-specific operational quirks and recurring patterns
- Trigger: Discovered by category agents during normal operations
- Mechanism: Category agents document findings in `./learnings/` folder
- After 3+ recurrences, the finding is flagged for promotion
- Resolution: SysAdmin investigates, verifies root cause, files a GitHub issue
- Most repeated-learnings issues are resolved by updating parameters in AGENTS.md or TOOLS.md

**Layer 2: Proactive Pipeline Improvement (this framework's focus)**
- Scope: Strictly limited to the data-analysis-decision pipeline — data sources, ingestion, processing, statistical interpretation, and agent decision frameworks
- Trigger: Continuous and proactive. Runs indefinitely with no final goal; the only required outcome is incremental improvement every cycle
- Boundary: Issues outside this scope (API failures, profile auth issues, rate limiting) are documented in `Errors.md` and must recur 3 times before SysAdmin investigates and files a GitHub issue
- Gray area: If stale data led to a bad decision, that's a decision-framework issue (this layer), not an infrastructure issue

**Layer 3: Autonomous Development Team (in development)**
- Scope: Full system architecture — any GitHub issue
- Trigger: GitHub issues filed by SysAdmin, agents, or humans
- Mechanism: An isolated team of autonomous dev agents picks up issues, investigates, deploys fixes, and updates CHANGELOG.md
- A feedback loop allows agents to verify, test, and provide feedback on fixes
- Cross-layer coordination: SysAdmin and Dev-Liaison bridge Layer 2 and Layer 3

**Agent-debate framework adoption:**

| Role | Our Agent | Notes |
|---|---|---|
| Orchestrator | SysAdmin (primary instance) | Manages process flow |
| Watcher | Dev-Liaison | Monitors and provides feasibility perspective |
| Adversarial Agent x4 | 2x Category Agent subs + 2x SysAdmin subs | Debaters/researchers |

OpenClaw supports configuring agents to spawn subs with specific models, enabling multi-model debate.

**Dev-Liaison (new role):**
- Built on VoyageAI + database infrastructure
- Purpose: Provide specialist perspective on TraderBot architecture, design, and implementation
- Specifically focused on experiment design and feasibility
- Also serves in Layer 3 (autonomous dev team)
- Partners with SysAdmin to coordinate diagnostics, issue investigations, and product roadmap

**Guardrails:**

1. **Full autonomy**: They develop their own hypotheses, establish success criteria, and design/test proposals. They never stop and wait for human permission. They operate with clear guidelines, checks and balances, and a chain of command.

2. **One concept per cycle**: Each improvement cycle targets exactly one concept. "Implement machine learning models to improve analysis performance" is one concept even if applied differently across pipeline layers. One design decision at a time, measured and validated before moving on.

3. **Critical perspectives grounded in evidence**: Every claim must be grounded in verifiable evidence that specifically models how agent performance will be affected under Kalshi market conditions for the relevant category. Agents are encouraged to debate, investigate, and dissent.

4. **Kalshi market specificity**: The goal is not better prediction in general. The goal is better performance on Kalshi markets specifically. This leads to meaningfully different design outcomes.

5. **Statistical rigor as foundational philosophy**: Base every decision, calculation, and data derivation in principles of statistical analysis. Create hypotheses. Design tests to validate them. Build models to measure correlation and causation. Track trends. Be creative and inquisitive. Keep detailed, complete historical records.

**Improvement cycle (5 rounds):**

**Round 1: Identify Suboptimal Outcomes**
- Each agent analyzes the entire pipeline — code, logs, reports, everything
- Trace each suboptimal outcome back through the full chain to find the root cause
- 4 agents x 10 outcomes = 40 unique root causes total (no duplicates)
- Each documented with evidence showing the full timeline

**Round 2: White Paper Development and Cross-Examination**
- Each agent produces a white paper for each of their 10 suggestions with: statistically validatable hypothesis, research basis, logical analysis, and Kalshi-specific considerations
- Sequential cross-examination: each plan is examined by the other 3 agents one at a time
- Defendant must either refute the charge with evidence or accept and revise
- Debates continue until resolution; next examiner reviews full history

**Round 3: Blind Vote to Select Top Proposals**
- All 6 participants cast one blind vote each
- Criteria: hypothesis validity, improvement-to-effort ratio, profitability impact
- Tie-breaking: each tied agent gives a final evidence-based statement, then re-vote
- Top 5 proposals advance
- Dev-Liaison provides top-line feasibility check on each

**Round 4: In-Depth White Paper and Experiment Design**
- Current code state review
- Deep conceptual research
- Existing implementation search on GitHub (directly analogous and ideologically analogous)
- Statistical experimental design: valid hypothesis, highest reasonable validation standards, must be able to prove the hypothesis valid or invalid

**Round 5: Final Selection and Implementation**
- TBD — to be defined in a future discussion

**Root cause classification:**

TraderBot problems:
- Broken auth/handshake between agent and TraderBot
- Broken TraderBot functions, bugs, glitches
- Poorly designed or insufficient analysis/data models (not customized for the specific category)
- Stale data pipeline issues (if the data pipeline failed to update, leading to stale data in the DB)
- Any infrastructure-level failure that prevented correct data from reaching the agent

Agent problems:
- Missing, insufficient, or inaccurate instructions regarding operating procedure
- Insufficient or vague instructions on decision making and analysis methods
- Poorly designed automation cycles (cron/heartbeat)
- Agent not considering nuanced category-specific factors (e.g., prediction certainty decreasing over time in weather markets)
- Agent hallucinations or unvalidated assumptions

Some problems require modification on both sides: new TraderBot module = new agent instructions + SysAdmin awareness.

**Consequences:**
- Requires building the Dev-Liaison on VoyageAI + database infrastructure
- Requires integrating agent-debate framework into existing OpenClaw infrastructure
- Requires configuring OpenClaw multi-model sub-agent spawning
- TEMPLATE.md from agent-debate framework needs review for TraderBot-specific modifications
- All GitHub issues from Layers 1 and 2 must document the root cause (TraderBot vs agent)
- Round 5 implementation details to be defined separately

---

### DD-019: Time-Lapse Behavioral Simulation (updated)

**Date**: 2025-06-15
**Status**: Decided (updated)

**Context**: Agents begin in backtesting (not paper trading). Backtesting is a time-lapse simulation where the agent speed-runs decision cycles that would have taken place during a 6-month historical period. This is NOT just a statistical backtest — it validates both the TraderBot data/analysis pipeline AND the agent's decision-making behavior.

**Key design principles:**

1. **Real market conditions at each point in time**: The agent must see exactly what it would have seen at that timestamp — not just settlement outcomes. This means using the forecast that was available on day X-4, not the forecast made on day X. Market prices at the time of the trade matter because prediction certainty and edge change as settlement approaches.

2. **TraderBot fetches and analyzes, the agent decides**: TraderBot's role in backtesting is to provide the same quality of data and analysis it would in live mode. The agent's role is to interpret that data and make decisions. This division is where success or failure is determined.

3. **Same tools, same format, regardless of mode**: The MCP tools must be profile-aware so that the agent uses the exact same workflow in backtest, paper, and live modes. The MCP server handles mode-specific behavior transparently. The agent does not need to track its own mode or use different commands.

4. **Profile-aware MCP responses**: When an agent calls `traderbot__scan` in backtest mode, the MCP server returns market data as it existed at the simulation timestamp, not current data. When the agent calls `traderbot__trade`, the MCP server logs to the backtest database, not the live database. The agent is unaware of which mode it's in.

5. **Database isolation by mode and agent**: Each agent has separate databases for backtest, paper, and live trading. In live mode, the agent has READ access to its backtest and paper databases for reference, but WRITE goes to the live database. MCP tool is responsible for writing to the correct database.

6. **Simulation clock**: TraderBot service manages a SimulationClock per backtesting agent. The service advances the clock and triggers agent decision loops via OpenClaw `sessions_send`. At each tick, MCP calls return data as-of the simulation time.

7. **Edge filtering optimization**: Not every moment in a 6-month period has a detectable edge. TraderBot's signal engine can pre-filter intervals with no edge, and only invoke the LLM agent when edge > minimum threshold. This reduces backtesting time from 80+ hours to 8-16 hours.

**Two-phase backtesting:**

**Phase A: Statistical Backtest (fast, existing)**
- Uses existing BacktestEngine with Strategy
- Validates data pipeline, signal computation, and bias adjustments
- No LLM involved — pure computation
- Runs in minutes, not hours
- Identifies which market-condition windows are worth testing in Phase B

**Phase B: Behavioral Simulation (hours, new)**
- Runs the actual LLM agent through decision cycles at accelerated time
- TraderBot service drives the simulation clock and triggers agent loops
- Agent makes real LLM decisions using the same workflow as live trading
- Validates agent behavioral adherence: does it follow SOUL.md, respect risk limits, interpret data correctly?
- Estimated time: 8-16 hours for 6-month simulation with edge-filtering

**Consequences:**
- MCP tools must be mode-aware and return time-appropriate data
- SimulationClock subsystem must be built
- Historical data pipeline must provide "data as it existed at timestamp T" for all data types
- Data quality metadata must be included in all MCP responses
- Existing BacktestEngine becomes Phase A of the two-phase process

---

### DD-020: Historical Data Research Findings

**Date**: 2025-06-15
**Status**: Research complete, implementation decisions pending

**Context**: Time-lapse behavioral simulation (DD-019) requires "data as it existed at timestamp T" — not just "what actually happened" but "what was forecast/predicted at time T for future date Y." This is the most critical data challenge for backtesting. Without multi-day lead time forecasts, we cannot accurately simulate what information the agent had available when making decisions.

**Research results:**

#### Weather Data Sources

| Source | What it provides | Lead time data? | Access | Processing |
|---|---|---|---|---|
| Open-Meteo Historical Forecast API | Historical GFS, ECMWF, GEM model output for past dates (day-0 only) | **No** — day-0 (same-day) forecasts only | Free, no API key | REST API, ready to use |
| Open-Meteo Archive API | Actual observed weather data for past dates | N/A (observations, not forecasts) | Free, no API key | REST API, ready to use |
| NOAA GFS on AWS S3 | Raw GRIB2 model output with full lead times (f000-f384) | **Yes** — "forecast issued on date X for date X+N hours" | Free, public S3 bucket | GRIB2 processing required (wgrib2/cfgrib) |
| ECMWF on AWS S3 | Raw GRIB2 model output with full lead times (0h-144h+) | **Yes** — "forecast issued on date X for date X+N hours" | Free, public S3 bucket | GRIB2 processing required |
| NWS Digital Forecast API | Current point forecasts for US locations | No (current only) | Free, no API key | REST API, XML/JSON |
| Iowa Environmental Mesonet (IEM) | Archived NWS text forecasts | Possibly (API limited/changed) | Free | Uncertain API access |
| Kalshi Historical Candlesticks | OHLC bid/ask + trade prices for settled markets | N/A (market data, not forecasts) | Requires API key | REST API, `GET /historical/markets/{ticker}/candlesticks` |
| Kalshi Forecast Percentile History | Historical raw/formatted forecast percentiles for events | N/A (market consensus data) | Requires API key | REST API, up to 5-second granularity |
| Kalshi Historical Trades | Historical trade data for settled markets | N/A (market data) | Requires API key | REST API, `GET /historical/trades` |

#### Open-Meteo Historical Forecast API (confirmed working)

URL: `https://historical-forecast-api.open-meteo.com/v1/forecast`

Tested and verified:
- Returns GFS, ECMWF, and GEM model output for past dates
- Available variables: temperature, precipitation, wind speed, wind gusts
- Goes back to approximately April 2024 (~14 months)
- Supports `past_days` parameter (up to ~800 days)
- Supports `start_date`/`end_date` range queries
- Multiple models can be requested simultaneously

**Critical limitation**: Only provides day-0 forecasts. Each date has one forecast value per model, representing what that model predicted for that specific day. It does NOT provide "what was forecast on date X for date X+N" (multi-day lead time forecasts). This is insufficient for realistic backtesting because:
- In live trading, the agent has access to 1-day, 2-day, 3-day, etc. advance forecasts
- A 4-day-ahead forecast has different accuracy characteristics than a same-day forecast
- The agent's edge in weather markets depends partly on forecasting skill at different lead times
- Using only day-0 forecasts would artificially inflate backtesting performance

#### NOAA GFS on AWS S3 (confirmed working)

URL: `https://noaa-gfs-bdp-pds.s3.amazonaws.com/`

Verified structure:
- Path format: `gfs.YYYYMMDD/HH/atmos/gfs.tHHz.pgrb2.0p25.fNNN`
- Available forecast hours: f000, f003, f006, f009, ... up to f384 (16 days)
- Model runs: 00z, 06z, 12z, 18z (4 times daily)
- Available from ~2021 onwards
- Raw GRIB2 format requires processing with wgrib2 or cfgrib

**This is the primary source for true multi-day lead time forecasts.** For weather backtesting, we need to answer "what did GFS predict on Jan 13 at 00z for Jan 18?" — and this data provides exactly that.

Processing requirements:
- GRIB2 files need to be downloaded and parsed (1-2 GB per model run, 4 runs/day)
- We only need specific grid points (our Kalshi cities), so we can use wgrib2 to extract just the relevant lat/lon
- Estimated storage for 6 months of GFS data at our 15 cities: ~5-10 GB compressed
- Can be processed on-demand during backtesting, no need to store all raw data

#### ECMWF on AWS S3 (confirmed working)

URL: `https://ecmwf-forecasts.s3.amazonaws.com/`

Verified structure:
- Path format: `YYYYMMDD/HHz/aifs/0p25/oper/YYYYMMDDHH0000-{N}h-oper-fc.grib2`
- Available lead times: 0h, 6h, 12h, ... 144h+ (6-hour intervals up to 6 days)
- Available from recent dates (at least 2025-01-13 verified)
- Same GRIB2 processing requirement as GFS

#### Recommended data strategy for weather backtesting:

**Tier 1: Immediate implementation (available now, ready to use)**
- Open-Meteo Archive API for actual observations (settlement verification)
- Open-Meteo Historical Forecast API for day-0 model consensus (approximate, no lead times)
- Current Kalshi HistoryService for settled markets and trades
- ChromaDB with `published_at` metadata for historical news

**Tier 2: Short-term implementation (requires GRIB2 processing pipeline)**
- NOAA GFS on AWS S3 for true multi-day lead time forecasts
- ECMWF on AWS S3 for true multi-day lead time forecasts (ECMWF is generally more accurate than GFS for medium-range)
- Process only the grid points needed for our 15 Kalshi cities
- Store processed data in SQLite with (model, run_date, valid_date, lead_hours, lat, lon, variable, value) schema

**Tier 3: Ongoing archival (start now for future backtests)**
- Begin archiving NWS forecast snapshots every hour in the data pipeline
- Begin archiving Kalshi orderbook snapshots via WebSocket for real-time depth data (complements historical candlestick API which provides OHLC but not full depth)
- Begin archiving Open-Meteo model consensus snapshots every 6 hours
- These archives become the ground truth for future backtest cycles

**Data gap resolution plan:**

| Data gap | Tier 1 solution | Tier 2 solution | Notes |
|---|---|---|---|
| Historical weather observations | Open-Meteo Archive API | — | Ready to use |
| Historical model consensus (day-0) | Open-Meteo Historical Forecast API | — | No lead times but provides model comparison |
| Historical model consensus (multi-day) | Approximate from day-0 + bias table | NOAA GFS + ECMWF on AWS S3 | Requires GRIB2 pipeline |
| Historical NWS text forecasts | Use GFS model data as proxy | Archive NWS forecasts going forward | NWS doesn't provide historical forecasts via API |
| Historical Kalshi market data | HistoryService | — | Ready to use |
| Historical Kalshi orderbooks | Kalshi historical candlestick API (bid/ask OHLC + trade prices) | — | `GET /historical/markets/{ticker}/candlesticks` with 1min/1hr/1day granularity; also `forecast_percentile_history` endpoint |
| Historical Kalshi forecast percentiles | `forecast_percentile_history` API | — | Up to 5-second granularity for event-level forecast data |
| Historical news with timestamps | ChromaDB with published_at | — | Verify metadata integrity |
| Historical bias data | forecast_bias SQLite (time-filtered) | — | Ensure no look-ahead bias in queries |

**Implementation priority:**
1. Start archiving now: NWS forecasts, Kalshi orderbooks, Open-Meteo consensus (Tier 3)
2. Build GRIB2 processing pipeline for NOAA GFS / ECMWF (Tier 2)
3. Use Tier 1 data for initial backtest cycle while Tier 2 is being built
4. Document the approximation: initial backtests use day-0 forecasts, which inflate certainty relative to live conditions

**Consequences:**
- Need a GRIB2 processing module in `src/traderbot/data/weather/` for Tier 2
- Need an archival pipeline that runs alongside the data collection workers (DD-016)
- forecast_bias SQLite needs `forecast_date` and `valid_date` columns (not just `forecast_date`) to support "forecast on date X for date Y" queries
- SimulationClock must track lead time and adjust data quality metadata accordingly
- Day-0-only backtesting is acceptable for initial cycles but must be documented as an approximation

---

### DD-021: Paper Trading and Live Trading Architecture

**Date**: 2025-06-15
**Status**: Decided

**Context**: Under the MCP architecture (DD-015), the agent calls the same tools regardless of mode. TraderBot routes on the backend based on the agent's profile. Paper trading and live trading use mostly the same data and sources — the only difference is when an agent decides to place an order, under paper trading the order is not submitted to Kalshi and instead recorded and simulated locally in the agent's paper trades database. This database also needs to correctly calculate balance, trade settlement, profit/loss, etc.

**Three-mode trading flow**:

```
Agent calls traderbot__trade(ticker, direction, quantity, price)
         │
         ▼
   MCP Server receives tool call
         │
         ▼
   Resolve agent → profile → mode
         │
    ┌────┼────────────┐
    │    │             │
 BACKTEST   PAPER      LIVE
    │    │             │
    ▼    ▼             ▼
 SimulationClock   PaperTrader   Kalshi API
 returns historical  simulates     submits order
 fill at sim-time    fill with     to exchange
 price               slippage
    │    │             │
    ▼    ▼             ▼
 backtest DB      paper DB      live DB
 (read-only from  (read-only     (read-write
  paper & live     from live)    + Kalshi sync)
  for reference)
```

**Mode-aware MCP tool behavior**:

| Tool | Backtest | Paper | Live |
|---|---|---|---|
| `traderbot__scan` | Returns markets open at sim-time | Returns current markets | Returns current markets |
| `traderbot__analyze` | Returns analysis at sim-time | Returns current analysis | Returns current analysis |
| `traderbot__signals` | Returns signals at sim-time | Returns current signals | Returns current signals |
| `traderbot__trade` | Records in backtest DB, returns simulated fill at sim-time price | Records in paper DB, returns simulated fill with slippage | Submits to Kalshi, records in live DB |
| `traderbot__positions` | Returns backtest positions | Returns paper positions | Returns live positions |
| `traderbot__heartbeat` | Returns sim-time heartbeat data | Returns current heartbeat data | Returns current heartbeat data |
| `traderbot__weather_forecast` | Returns forecast at sim-time | Returns current forecast | Returns current forecast |
| `traderbot__news_context` | Returns news published before sim-time | Returns recent news | Returns recent news |

**Paper trading specifics**: The MCP server receives the agent's trade request, runs risk evaluation against the paper balance, simulates a fill using `PaperSlippageModel` (walks the live orderbook to compute realistic fill price), records the position in the paper database with simulated fill price and slippage, and returns the fill confirmation. The agent never knows it's paper trading — the data it receives is real (current markets, current forecasts, current news). The only difference is that orders aren't submitted to Kalshi.

**Paper balance computation** (single source of truth, unchanged from current):
- `remaining = initial_balance - cost(at open) + settlement_payouts`
- YES won → +100¢ per contract, NO won → +100¢ per contract, lost → 0¢

**Settlement verification** consolidates from two modules into mode-aware routing:

| Mode | Settlement source | Method |
|---|---|---|
| Backtest | Historical data | MCP server checks historical market data at sim-time |
| Paper | Kalshi API + Open-Meteo | `SettlementVerifier` checks settled markets, auto-settles weather bets |
| Live | Kalshi API | `reconcile_settlements` syncs with Kalshi |

**What moves where**:

| Current | What | v2 Location | Reason |
|---|---|---|---|
| `paper.py` | `compute_paper_balance`, `position_value_for_ticker`, `remaining_balance` | `traderbot/trading.py` | Service-layer functions, not CLI |
| `simulation/paper_trader.py` | `PaperTrader`, `PaperSlippageModel`, `PaperFill`, `PaperPosition`, `PaperPortfolio` | `traderbot/trading.py` | Paper fill simulation is a service |
| `simulation/settlement.py` | `SettlementVerifier`, `auto_settle_paper_positions`, `_settle_weather_bets` | `traderbot/trading.py` + `kalshi/settlement.py` | Paper settlement stays in trading; Kalshi settlement moves |
| `simulation/settlement.py` | `_parse_kalshi_ticker` | `kalshi/models.py` | Kalshi ticker parsing belongs with Kalshi models |
| `simulation/performance.py` | `compute_brier_score`, `compute_sharpe`, `compute_max_drawdown`, `compute_calmar`, `compute_win_rate`, `compute_fill_rate`, `compute_edge_capture` | `analysis/portfolio.py` | Metrics consolidate into one module |
| `simulation/adaptation.py` | `BayesianAdapter` | `analysis/adaptation.py` | Adaptation is analysis, not simulation |
| `simulation/engine.py` | `BacktestEngine` | `simulation/engine.py` (renamed to `StatisticalBacktestEngine`) | Phase A engine |
| `cli/trade.py` | Trade evaluation, risk checks, order submission | `traderbot/trading.py` (service) + `cli/trade.py` (thin handler) | Business logic extracted from CLI |

**New `traderbot/trading.py`** contains `execute_trade(profile, ticker, direction, quantity, price, estimated_prob, confidence)` as the main entry point, plus `PaperSlippageModel`, `compute_paper_balance`, `SettlementVerifier` (paper), and `_settle_weather_bets`.

**Agent-facing MCP response** (same format regardless of mode):

```json
{
  "status": "filled",
  "ticker": "KXHIGHTCHI-26JUN02-T81",
  "direction": "yes",
  "quantity": 5,
  "fill_price_cents": 34,
  "slippage_cents": 1,
  "estimated_prob": 0.38,
  "confidence": 0.72,
  "remaining_balance_cents": 9830,
  "mode": "paper"
}
```

The `mode` field is informational only — the agent doesn't change its behavior based on it.

**Consequences**:
- `simulation/paper_trader.py` moves core logic to `traderbot/trading.py`
- `paper.py` moves functions to `traderbot/trading.py`
- `simulation/settlement.py` splits: weather settlement in `trading.py`, Kalshi settlement in `kalshi/settlement.py`
- `simulation/performance.py` metrics merge into `analysis/portfolio.py`
- `TradingProfile.mode` gains `backtest` as a third option
- `profiles/isolation.py` gains mode-aware paths: `backtest-{name}/`, `paper-{name}/`, `live-{name}/`
- CLI `trade` command becomes a thin wrapper calling `trading.execute_trade()`
- MCP `traderbot__trade` tool calls `trading.execute_trade()` with mode routing


### DD-022: Service template path resolution — runtime substitution with resolved pipx paths

**Date**: 2025-06-15
**Status**: Decided

**Context**: Under DD-001, pipx is the sole installation method. Under DD-016, TraderBot runs as a single always-on daemon (not per-agent services). Under DD-007, service templates move to `src/traderbot/services/` as package data read via `importlib.resources`. The current templates hardcode git/source install paths (`/home/%i/traderbot/.venv/bin/traderbot`) and rely on shell scripts (`install-service.sh`, `install-launchd.sh`) to do sed substitution at install time. This approach breaks under pipx because:

1. **Pipx binary paths vary by backend**: virtualenv puts binaries in `~/.local/pipx/venvs/traderbot/bin/traderbot`, while the newer uv backend uses `~/.local/share/uv/tools/traderbot/bin/traderbot`. Hardcoding either path will fail for the other backend.
2. **User-customizable locations**: `PIPX_BIN_DIR`, `PIPX_LOCAL_VENVS`, and `PIPX_VENV_CACHEDIR` environment variables let users override pipx's default paths. The `~/.local/bin/traderbot` symlink is the only stable reference point.
3. **All three service managers require absolute paths at install time**: systemd supports `%h` (home) and `%i` (instance) specifiers but NOT arbitrary PATH lookups. launchd and Windows Task Scheduler have no variable expansion at all. Every ExecStart/ProgramArguments/binPath value must be fully resolved before deployment.
4. **PATH is unreliable at boot**: systemd and launchd services run in minimal environments. `~/.local/bin` may not be on PATH during early boot, so even the symlink path cannot be trusted unless it's resolved to its absolute target.

**Decision**: Service templates use `{placeholder}` syntax (Python `str.format` compatible). `traderbot setup` resolves all paths at install time using `shutil.which('traderbot')` + `.resolve()` and substitutes them before deploying.

**Path resolution function** (`src/traderbot/services/paths.py`):

```python
from dataclasses import dataclass
from pathlib import Path
import shutil
import sys

@dataclass(frozen=True)
class BinPaths:
    traderbot: Path      # Resolved absolute path to traderbot binary
    python: Path         # Resolved absolute path to python in the same venv
    home: Path           # User's home directory

def resolve_bin_paths() -> BinPaths:
    """Resolve binary paths for service template substitution.

    Uses shutil.which('traderbot') to find the binary on PATH,
    then resolves symlinks to get the real venv path.
    Falls back to sys.executable's parent directory if which fails.
    """
    traderbot_bin = shutil.which("traderbot")
    if traderbot_bin:
        traderbot_path = Path(traderbot_bin).resolve()
    else:
        # Fallback: traderbot binary is in the same directory as the running python
        traderbot_path = Path(sys.executable).parent / "traderbot"
        if not traderbot_path.exists():
            traderbot_path = Path(sys.executable).parent / "traderbot.exe"  # Windows
        traderbot_path = traderbot_path.resolve()

    python_path = Path(sys.executable).resolve()
    home = Path.home()

    return BinPaths(traderbot=traderbot_path, python=python_path, home=home)
```

**Template files** (in `src/traderbot/services/`):

| Template | Platform | Placeholders |
|---|---|---|
| `traderbot.service.in` | Linux (systemd) | `{traderbot_bin}`, `{python_bin}`, `{home}` |
| `com.traderbot.daemon.plist.in` | macOS (launchd) | `{traderbot_bin}`, `{python_bin}`, `{home}`, `{user}` |
| `traderbot-daemon.xml.in` | Windows (Task Scheduler) | `{traderbot_bin}`, `{python_bin}`, `{home}` |

The `.in` suffix clearly marks these as templates requiring substitution. The deployment function reads via `importlib.resources`, substitutes, and writes to the platform-appropriate location.

**systemd template** (`traderbot.service.in`):

```ini
[Unit]
Description=TraderBot Daemon
Documentation=https://github.com/JsonDaRula69/TraderBot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={user}
WorkingDirectory={home}/.traderbot
Environment=TRADERBOT_PROFILE_TOKEN={profile_token}
Environment=PYTHONUNBUFFERED=1
ExecStart={traderbot_bin} daemon
Restart=on-failure
RestartSec=10
StartLimitIntervalSec=300
StartLimitBurst=5

StandardOutput=journal
StandardError=journal
SyslogIdentifier=traderbot-daemon

[Install]
WantedBy=multi-user.target
```

Note: this is a single `traderbot.service` unit (not a template unit `@.service`). Under DD-016, TraderBot runs as one daemon process — per-agent services are no longer needed. The daemon internally manages all data collection workers, the MCP server, and the WebSocket connection.

**launchd template** (`com.traderbot.daemon.plist.in`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "…">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.traderbot.daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>{traderbot_bin}</string>
        <string>daemon</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>TRADERBOT_PROFILE_TOKEN</key>
        <string>{profile_token}</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
    <key>WorkingDirectory</key>
    <string>{home}/.traderbot</string>
    <key>UserName</key>
    <string>{user}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{home}/Library/Logs/traderbot-daemon.log</string>
    <key>StandardErrorPath</key>
    <string>{home}/Library/Logs/traderbot-daemon-error.log</string>
</dict>
</plist>
```

**Windows**: The existing `windows_service.py` already uses `sys.executable` directly and constructs `WindowsServiceDef` at runtime — no template file needed. It creates a single `TraderBotDaemon` service with `bin_path=f'"{venv_python}" -m traderbot daemon'`.

**Deployment flow** (inside `traderbot setup`):

1. `resolve_bin_paths()` — find traderbot binary and python path
2. Read template via `importlib.resources.files("traderbot.services").joinpath("traderbot.service.in")`
3. Substitute `{traderbot_bin}`, `{python_bin}`, `{home}`, `{user}`, `{profile_token}`
4. Write to platform-appropriate location:
   - Linux: `sudo cp` to `/etc/systemd/system/traderbot.service` + `systemctl daemon-reload` + `systemctl enable traderbot.service`
   - macOS: `sudo cp` to `/Library/LaunchDaemons/com.traderbot.daemon.plist` + `launchctl load`
   - Windows: `sc.exe create TraderBotDaemon binPath=...` (already handled by `windows_service.py`)
5. Verify service starts: `systemctl start traderbot.service` / `launchctl kickstart system/com.traderbot.daemon` / `sc.exe start TraderBotDaemon`

**What gets retired:**

| File | Lines | Reason |
|---|---|---|
| `install/services/install-service.sh` | 53 | Shell sed substitution → Python `str.format` |
| `install/services/install-launchd.sh` | 55 | Shell sed substitution → Python `str.format` |
| `install/services/install-ws-daemon.sh` | 20 | WS daemon absorbed into main service |
| `install/services/install-data-pipeline.sh` | 203 | Data pipeline absorbed into main service |
| `install/services/traderbot-agent@.service` | 49 | Per-agent service → single daemon |
| `install/services/traderbot-news-ingest@.service` | 38 | Absorbed into daemon |
| `install/services/traderbot-news-ingest@.timer` | 24 | Absorbed into daemon |
| `install/services/traderbot-backfill-data@.service` | 40 | Absorbed into daemon |
| `install/services/traderbot-backfill-data@.timer` | 26 | Absorbed into daemon |
| `install/services/traderbot-ws-daemon.service` | 17 | WS daemon absorbed into main service |

**What gets added:**

| File | Purpose |
|---|---|
| `src/traderbot/services/__init__.py` | Package init |
| `src/traderbot/services/paths.py` | `BinPaths`, `resolve_bin_paths()` |
| `src/traderbot/services/deploy.py` | `deploy_service()`, `remove_service()`, platform dispatch |
| `src/traderbot/services/traderbot.service.in` | Systemd template (single daemon) |
| `src/traderbot/services/com.traderbot.daemon.plist.in` | Launchd template (single daemon) |
| `src/traderbot/windows_service.py` | Existing, simplified to single daemon service |

**Consequences:**
- Path resolution is deterministic and testable: `resolve_bin_paths()` can be unit-tested by mocking `shutil.which`
- No shell scripts in the install process — all service deployment is Python code
- The `traderbot daemon` command becomes the single entry point for the always-on service (DD-016)
- Per-agent systemd/launchd units are eliminated — the daemon handles all agent orchestration internally
- OpenClaw cron/heartbeat still handles agent decision loops and heartbeat, but data collection is TraderBot's responsibility
- Service templates are always in sync with the installed binary because they're resolved at setup time, not hardcoded
- Upgrading traderbot via `pipx upgrade traderbot` may change the binary path (e.g., uv rebuilds the venv). `traderbot setup --verify` or `traderbot update` should re-resolve and redeploy the service unit. This is an idempotent operation.

### DD-023: SysAdmin cron/heartbeat orchestration — phase-aware job lifecycle

**Date**: 2025-06-15
**Status**: Decided

> **Implementation status:** DD-023 records the target orchestration and deploy
> architecture plus a historical pre-v2 module inventory. Current `HEAD` does
> not contain the described cron, deploy, CLI, service, database, or external
> credential modules. Phase 1 implements MCP profile-token auth and
> profile factories; secure OpenClaw token injection is deployment-verified
> (Phase 1.1, issue #187 closed); external provider credentials are deferred
> to Phase 1.5 (issue #165).

**Context**: The current `traderbot cron setup` registers all cron jobs for an agent immediately during deploy, regardless of the agent's lifecycle phase. Under DD-017, agents progress through BACKTESTING → PAPER → LIVE → SUSPENDED states, and the cron jobs they need differ by phase. Additionally, SysAdmin orchestrates when each category agent is activated — the first agent doesn't start until SysAdmin has verified data streams and its own health checks pass.

Under DD-016, TraderBot's always-on service handles data collection proactively. Several current cron jobs (`forecast-check`, `news-scan`, `pipeline-health`) exist because agents had to trigger data fetching themselves. These are no longer needed.

**Decision**: Cron and heartbeat registration does NOT happen at deploy time. Job definitions are designed and shipped as templates within the TraderBot package, but they remain dormant until SysAdmin activates them. SysAdmin follows a predefined protocol for phase transitions but can also create custom jobs when circumstances require it.

**Bootstrap job:**

SysAdmin is deployed with exactly one cron job: a one-shot activation prompt that fires after deploy. This job triggers SysAdmin's startup protocol, after which SysAdmin removes the bootstrap job and registers its own essential jobs as it progresses through the activation sequence.

The bootstrap job is registered during deploy (Step 2) as an isolated cron job with `--at "5m"` (fires 5 minutes after deploy, giving services time to initialize):

```bash
openclaw cron add \
  --name "sysadmin-bootstrap" \
  --at "5m" \
  --session isolated \
  --agent main \
  --delete-after-run \
  --message "You have been deployed. Follow your activation protocol in AGENTS.md: verify TraderBot service health, register your essential cron jobs, then activate the first category agent for backtesting."
```

The `--delete-after-run` flag ensures this job removes itself after the first execution. No other cron or heartbeat jobs exist at deploy time — SysAdmin activates everything from this single starting point.

**Phase-aware job lifecycle:**

SysAdmin activates agents one at a time, verifying each step before proceeding. The deployment flow is:

1. Deploy completes (OpenClaw configured, agents created, databases created, backfill running)
2. SysAdmin verifies data streams are functioning (checks TraderBot service health, WebSocket connection, data freshness)
3. SysAdmin registers its own essential cron jobs: `health-check` (1h) and `error-logger` (15m)
4. SysAdmin enables its own heartbeat (`heartbeat.every: "30m"`)
5. SysAdmin activates the first category agent for backtesting:
   - Registers backtesting-specific jobs for itself and the category agent
   - Enables the category agent's heartbeat
6. When backtesting meets promotion criteria, SysAdmin:
   - Removes backtesting jobs (`openclaw cron remove <jobId>`)
   - Registers paper trading jobs
   - Updates the agent's profile: `traderbot profile update <agent> --mode paper`
7. When paper trading meets breakeven for 2+ days, SysAdmin activates the next category agent (back to step 5)
8. When paper trading meets live promotion criteria, SysAdmin:
   - Removes paper trading jobs
   - Registers live trading jobs
   - Updates the agent's profile: `traderbot profile update <agent> --mode live`

**Job template structure:**

Job definitions are organized by role and phase in `src/traderbot/cron/` as YAML templates:

```
src/traderbot/cron/
├── sysadmin/
│   ├── health-check.yaml        # Always active after deploy verification
│   ├── error-logger.yaml        # Always active after deploy verification
│   ├── backtest-oversight.yaml   # Active when any agent is backtesting
│   ├── paper-oversight.yaml     # Active when any agent is paper trading
│   ├── live-oversight.yaml      # Active when any agent is live trading
│   ├── self-improvement.yaml    # Active when improvement cycle is running
│   └── custom/                  # (empty, created at runtime by SysAdmin)
├── weather/
│   ├── backtest.yaml            # Jobs for weather agent in backtest phase
│   ├── paper.yaml               # Jobs for weather agent in paper phase
│   └── live.yaml                # Jobs for weather agent in live phase
├── economics/
│   └── ...
└── _shared/
    ├── circuit-breaker-check.yaml  # Shared across all trading phases
    └── position-review.yaml        # Shared across paper and live phases
```

Each template contains:

```yaml
name: health-check
phase: always  # always | backtest | paper | live | oversight-backtest | oversight-paper | oversight-live
role: sysadmin
cron_expr: "0 * * * *"
session: isolated
message: |
  Run `traderbot health --json`. Verify: TraderBot service status, 
  WebSocket connection, data freshness per enabled category. Check agent 
  circuit breakers. Surface alerts for any failures. Write anomalies 
  to `.learnings/ERRORS.md`.
```

**SysAdmin's activation protocol (in AGENTS.md):**

SysAdmin's workspace files (AGENTS.md, HEARTBEAT.md) include the activation protocol. This protocol is triggered by the bootstrap job registered at deploy time. The predefined sequence SysAdmin follows:

1. Remove the bootstrap job that triggered this session (it has `--delete-after-run` but confirm removal)
2. Verify TraderBot service is running: `traderbot health --json`
2. Verify data streams are fresh: `traderbot data-points weather --count --json`
3. Register essential self-jobs: `traderbot cron activate --role sysadmin --phase essential`
4. Enable own heartbeat
5. For each enabled category (one at a time):
   a. Verify category data is available: `traderbot data-points <category> --count --json`
   b. Activate category agent: `traderbot profile update <agent> --mode backtest`
   c. Register backtesting jobs: `traderbot cron activate --agent <agent> --role trader --phase backtest`
   d. Register self oversight jobs: `traderbot cron activate --role sysadmin --phase oversight-backtest`
   e. Monitor backtesting progress via heartbeat
   f. When backtesting passes deployment bar:
      - `traderbot cron deactivate --agent <agent> --phase backtest`
      - `traderbot cron activate --agent <agent> --role trader --phase paper`
      - `traderbot cron activate --role sysadmin --phase oversight-paper`
      - `traderbot profile update <agent> --mode paper`
   g. When paper trading meets breakeven threshold for 2+ days, proceed to next category

**Custom job creation:**

SysAdmin can create ad-hoc jobs using `openclaw cron add` directly. Examples:
- Borderline agent performance → add a more frequent `performance-review` job (every 2h instead of 6h)
- New deployment → add a temporary `high-frequency-health-check` (every 10min for 1 hour)
- Market volatility event → add a temporary `volatility-monitor` job
- Agent under investigation → add a focused `investigation-<agent>` job

These custom jobs are tracked by name prefix convention (`sysadmin-custom-*`) so SysAdmin can identify and clean them up later.

**Retired cron jobs (no longer needed under DD-016):**

| Current Job | Reason for Retirement |
|---|---|
| `forecast-check` (weather, 30m) | Data fetched proactively by TraderBot service; WebSocket cache always fresh |
| `news-scan` / `news-ingest` | TraderBot service runs news ingestion continuously |
| `data-forecast-check` | TraderBot service fetches forecasts on schedule; WebSocket for real-time |
| `pipeline-health` (sysadmin, 6h) | TraderBot service health is checked by `health-check`; individual pipeline timers no longer exist |
| `record-bias` (weather, daily) | TraderBot service records bias data continuously; no separate cron needed |
| `gateway-health` (sysadmin, 6h) | Merged into `health-check` — TraderBot service health includes WS, data, and gateway checks |

**Revised SysAdmin job definitions:**

| Job | Phase | Interval | Session | Description |
|---|---|---|---|---|
| `health-check` | Always (after deploy verification) | 1h | Isolated | Combined health: TraderBot service, WS connection, data freshness, auth, circuit breakers |
| `error-logger` | Always (after deploy verification) | 15m | Isolated | Read agent ERRORS.md, investigate, file GitHub issues |
| `backtest-oversight` | Oversight-backtest | 1h | Isolated | Monitor backtesting progress, review results, evaluate promotion criteria |
| `paper-oversight` | Oversight-paper | 6h | Isolated | Deep performance review: P&L, Sharpe, win rate, drawdown, deployment bar evaluation |
| `live-oversight` | Oversight-live | 6h | Isolated | Same as paper-oversight plus live risk monitoring |
| `self-improvement` | Active during improvement cycle | 6h | Isolated | Learning promotion, experiment design, deployment bar validation |

**Revised category agent job definitions (trading phases):**

| Job | Phase | Interval | Session | Description |
|---|---|---|---|---|
| `decision-loop` | Paper, Live | 5m | Isolated | Full trading decision cycle via MCP tools |
| `circuit-breaker-check` | Paper, Live | 30m | Isolated | `traderbot halt --json` risk check |
| `position-review` | Paper, Live | 1h | Isolated | Position health, settlement sync, drawdown check |

Note: Backtesting phase has no category agent cron jobs — the backtesting engine drives the simulation, not the agent's decision loop. The agent participates via `sessions_send` prompts from SysAdmin or the test harness.

**Heartbeat configuration by role:**

| Agent | `heartbeat.every` | `isolatedSession` | `lightContext` | Notes |
|---|---|---|---|---|
| SysAdmin | `30m` | `false` | `false` | Main session with full context — needs continuity for oversight |
| Category (backtest) | `0m` (disabled) | — | — | Agent not actively trading; managed by backtesting engine |
| Category (paper) | `30m` | `true` | `true` | Isolated — trading cycle is driven by cron, heartbeat is for self-review |
| Category (live) | `15m` | `true` | `true` | More frequent — live trading needs closer monitoring |

SysAdmin's heartbeat is NOT isolated — it runs in the main session so SysAdmin maintains awareness of ongoing conversations, agent status, and context from previous oversight cycles.

**`traderbot cron activate` / `traderbot cron deactivate` commands:**

New CLI commands that read phase-specific job templates and register/remove them:

```bash
# Register all jobs for a phase
traderbot cron activate --agent weather --role trader --phase paper
# Reads src/traderbot/cron/weather/paper.yaml templates and calls openclaw cron add for each

# Remove all jobs for a phase
traderbot cron deactivate --agent weather --phase backtest
# Reads job names from template, finds matching cron jobs, calls openclaw cron remove

# Register SysAdmin phase jobs
traderbot cron activate --role sysadmin --phase oversight-paper

# List active jobs for an agent
traderbot cron list --agent weather --json
```

The `--replace` flag on `cron activate` removes existing jobs with matching names before adding (idempotent).

**Consequences:**
- Deploy flow no longer registers cron jobs — SysAdmin activates them as part of its startup protocol
- Job definitions are data-driven (YAML templates), not hardcoded in Python
- SysAdmin follows a predefined activation sequence but can deviate when circumstances require
- Phase transitions (backtest → paper → live) are driven by SysAdmin, not automated
- `traderbot cron setup` is renamed to `traderbot cron activate` with phase-aware templates
- Several current cron jobs are retired (data fetching jobs moved to TraderBot service)
- SysAdmin heartbeat uses main session (not isolated) for continuity of oversight
- Category agent heartbeat is disabled during backtesting (agent managed by simulation engine)
- Custom jobs created by SysAdmin follow naming convention for easy identification and cleanup

---

## Architecture Overview

This section describes the v2 architecture that emerges from the design decisions above: who does what, how deployment works, how data is stored, and how modules map to categories.

### Division of Responsibilities

#### TraderBot (Toolkit)
- **Data sourcing and organization** — Kalshi API, news ingestion, data backfill, forecast data
- **Risk enforcement** — Hard limits, circuit breakers, Kelly sizing, audit trail
- **Analysis and signals** — Statistical indicators, sentiment scoring, edge detection
- **Simulation** — Backtesting, paper trading, experiment framework
- **CLI** — All commands the agent calls (`traderbot scan`, `traderbot trade`, etc.)
- **Database** — Position tracking, decision logging, learnings persistence
- **Profile and credential management** — Token binding, risk parameters, API keys, access control
- **Setup and deploy** — First-time configuration, service registration, verification
- **Access control enforcement** — CLI-level category filtering, credential scoping, agent isolation

#### OpenClaw (Agent Runtime)
- **Agent lifecycle** — Creating agents, assigning workspaces, managing sessions
- **LLM orchestration** — Model selection, provider config, session management
- **Cron and scheduling** — Heartbeat, decision loop, data pipeline timers
- **Inter-agent communication** — `sessions_send`, `sessions_spawn`, sub-agent coordination
- **Channel integration** — Discord, Slack, Telegram, iMessage
- **Gateway** — API routing, session persistence, tool rendering

#### Agent Workspace Files (Immutable, Shipped by TraderBot)
- **AGENTS.md** — Operating rules, hard rules, escalation protocol
- **SOUL.md** — Agent identity, principles, boundaries
- **TOOLS.md** — Permitted CLI commands, permission tiers
- **IDENTITY.md** — Name, personality, role, category
- **HEARTBEAT.md** — Task reference for periodic checks
- **USER.md** — Empty, reserved for human preferences

#### Sysadmin Agent
- Oversees fleet, does NOT trade
- Receives experiment designs from category agents
- Executes backtests, validates results, deploys improvements
- Monitors circuit breakers, agent health, system status
- Target oversight spans all categories; the current SysAdmin factory represents this by explicitly enumerating every `MarketCategory`

#### Category Agents
- Trade ONLY within their assigned category
- Log patterns to `.learnings/`
- Design experiments via sub-agent instances
- Do NOT modify their own profile, risk limits, or workspace files
- Report to sysadmin via heartbeat and SESSION-STATE.md
- Can only access data sources and CLI commands relevant to their category (enforced at CLI level)

---

### Deploy Flow (Detailed)

#### Step 1: OpenClaw Config
- Detect `openclaw` on PATH
- If missing: install via `npm install -g @openclaw/cli` (requires Node.js)
- Run `openclaw setup` — this creates the `main` agent and configures gateway, model provider, web search, comms channels
- Verify: `openclaw gateway status`

#### Step 2: SysAdmin Setup
- User chooses: use `main` as sysadmin (recommended) or create a new agent
- Inject sysadmin workspace files (AGENTS.md, SOUL.md, TOOLS.md, IDENTITY.md, HEARTBEAT.md, USER.md, SESSION-STATE.md, .learnings/)
- Register bootstrap job: one-shot `openclaw cron add --at "5m" --session isolated --agent main --delete-after-run` that prompts SysAdmin to begin its activation protocol (DD-023)
- No other cron or heartbeat jobs registered at deploy time — SysAdmin activates them during its startup protocol (DD-023)
- Create sysadmin profile: `traderbot profile create sysadmin --mode paper --risk-multiplier 0.001 --all-categories`
- Assign profile token to sysadmin agent via OpenClaw SecretRef
- Verify: `traderbot auth check --json`

#### Step 3: Category Selection
- Present available categories: Weather, Economics, Politics, Sports, Crypto, Entertainment, Science & Technology, Health, Social
- User selects one or more
- For each selected category:
  - `openclaw agents add <category>` (creates OpenClaw agent)
  - Inject category workspace files (AGENTS.md, SOUL.md, TOOLS.md, IDENTITY.md, etc.)
  - Configure agent heartbeat: `heartbeat.every: "0m"` (dormant — SysAdmin activates during startup protocol, DD-023)
  - No cron jobs registered at deploy time — SysAdmin activates them phase by phase (DD-023)
  - Create profile: `traderbot profile create <category> --mode backtest --categories <category> --risk-multiplier <default>`
  - Assign profile token to category agent via OpenClaw SecretRef
- After all agents: `openclaw doctor`

#### Step 4: API Tokens
- Global tokens (all agents): Kalshi API key + PEM, VoyageAI
- Common optional tokens (all agents): NewsAPI, Twitter, Reddit
- Category-specific tokens (only if category is enabled):
  - Weather: OpenWeatherMap (Open-Meteo and NWS are free, no key needed)
  - Economics: FRED
  - Crypto: CoinGecko (with tier detection)
  - Sports: TheSportsDB
- Store in encrypted vault (DD-012)

#### Step 5: Database Creation
- Create `~/.traderbot/traderbot.db` (global, schema init)
- Create `~/.traderbot/sysadmin/db/decisions.db` (sysadmin)
- For each category agent: create `~/.traderbot/paper-{category}/db/decisions.db`
- Initialize ChromaDB collections (news, data_points, market_patterns, news_signals, market_conditions)
- Verify: all DB paths writable, ChromaDB accessible

#### Step 6: Backfill
- Run `traderbot backfill --months 6 --categories <enabled_categories> --json`
- Only backfill data sources relevant to enabled categories
- This populates ChromaDB `data_points` collection with historical weather, economics, and crypto data
- Progress reporting during backfill (can take 1-3 minutes for initial seed)

#### Step 7: Simulation Start
- All agents begin in backtesting mode (`mode: backtest`), not paper trading (DD-017, DD-023)
- SysAdmin is activated with heartbeat and essential cron jobs (DD-023)
- SysAdmin activates the first category agent and starts its backtesting phase
- Docker sandbox is started for each category agent (mandatory, DD-010)
- SysAdmin manages phase transitions: backtest → paper → live, one category at a time

#### Step 8: Verification
- OpenClaw gateway reachable
- All agent tokens resolve correctly
- Kalshi credentials valid (`traderbot auth check --json`)
- All cron jobs registered (`openclaw cron list`)
- All DB paths writable
- ChromaDB accessible and collections initialized
- Docker sandbox running (if Docker available)
- Print summary with agent names, profiles, tokens, and status

---

### Database Architecture

#### Constraints
1. Each agent needs separate historical records for paper trades and live trades
2. Some data sources are shared between all agents; others are category-specific
3. Each category agent should only access its own trade history and relevant data sources
4. SysAdmin has access to all trade histories and data sources

#### Phase 1 Authentication Status and Historical Data Baseline
- Single global DB: `~/.traderbot/traderbot.db`
- Per-profile DB: `~/.traderbot/paper-{profile_name}/db/decisions.db`
- ChromaDB collections: `news`, `data_points`, `decisions`, `market_patterns`, `news_signals`, `market_conditions`
- No category-scoped access control on DB or ChromaDB
- MCP token resolution via explicit tool parameter → `LocalTokenStore` (`tokens.json`) → profile name and agent ID
- External provider credential loading and validation are not implemented in Phase 1; they are deferred to the Phase 1.5 secrets/provider/deploy work

#### Recommended Layout

```
~/.traderbot/
├── traderbot.db                    # Global DB (schema version, config, profile registry)
├── vault.enc                       # Historical DD-012 credential-vault proposal; not current Phase 1 storage
├── .vault_key                      # Historical DD-012 key proposal; not used by current Phase 1 auth
├── tokens.json                     # Current LocalTokenStore agent-token registry (0600 on POSIX)
├── profiles.enc                    # Historical DD-012 profile-registry proposal; no current Phase 1 file
├── chromadb/                       # SHARED: all agents read, category filtering via metadata
│   ├── news/                       # News embeddings (category metadata on each doc)
│   ├── data_points/                # Quantitative data (category metadata)
│   ├── market_patterns/            # Pattern signatures (category metadata)
│   ├── news_signals/               # Processed signals (category metadata)
│   └── market_conditions/          # Market resolution conditions (category metadata)
├── sysadmin/
│   └── db/decisions.db             # Sysadmin decisions (oversight, not trading)
├── paper-weather/
│   └── db/decisions.db             # Weather agent paper trade history
├── paper-economics/
│   └── db/decisions.db             # Economics agent paper trade history
├── paper-politics/
│   └── db/decisions.db             # Politics agent paper trade history
├── paper-crypto/
│   └── db/decisions.db             # Crypto agent paper trade history
└── live-{name}/                    # Created only when agent switches to live mode
    └── db/decisions.db             # Live trade history (separate from paper)
```

`LocalTokenStore` is the current Phase 1 backend. It stores profile-token
mappings as private, atomic JSON without Fernet encryption. A future Phase 1.5
backend may implement the same `TokenStore` interface with Infisical. The older
Fernet-based `tokens.enc` and `profiles.enc` layout remains historical rationale,
not current storage.

#### Key Design Choices

**SQLite per agent per mode** — This remains target architecture. Current `TradingProfile.base_dir` derives `~/.traderbot/{mode}-{name}/`, but `profiles/isolation.py` and the per-agent database stack are not present in Phase 1 `HEAD`.

**ChromaDB is shared with metadata filtering** — The `news`, `data_points`, `market_patterns`, `news_signals`, and `market_conditions` collections are global resources. News ingestion runs once (not per-agent) and all agents read from the same collections. Category filtering happens at query time via ChromaDB metadata filters (`where={"category": "weather"}`). This avoids duplicating 6 months of news data per agent.

**Category access control** — Current Phase 1 enforcement is in the MCP tool layer: the token resolves to a profile, tool permission is checked, and category access is enforced for category-bearing tools. The legacy CLI enforcement discussion is historical rationale, not current v2 behavior.

**Paper → live migration** — When an agent transitions from paper to live mode, a new DB path is created: `~/.traderbot/live-{name}/db/decisions.db`. The paper DB is preserved (not overwritten) per the existing DB integrity rules. The profile's `mode` field changes from `"paper"` to `"live"`, and `base_dir` changes accordingly.

**Future API key storage (Phase 1.5)** — Global and category-specific provider credentials are planned for the Infisical-backed secrets architecture in DD-037. No encrypted provider-credential vault or credential validation is implemented in Phase 1.

#### Why not separate ChromaDB per agent?
- ChromaDB vectors for news and data_points are ~6 months of historical data, potentially hundreds of thousands of embeddings. Duplicating per agent would multiply disk usage by N.
- ChromaDB's metadata filtering already supports category-scoped queries.
- The news-ingest pipeline runs once system-wide, not per-agent. Separate ChromaDB instances would require N separate ingest pipelines.

#### Why separate SQLite per agent?
- SQLite is file-based and lightweight. A per-agent DB is ~1-5MB.
- Isolation is enforced at the filesystem level — the weather agent cannot open the economics agent's DB.
- The profile token system already resolves to the correct path.
- The sysadmin can query any agent's DB by path.

#### ChromaDB category metadata verification needed
The `news` and `data_points` collections already have `category` metadata fields. The `decisions`, `market_patterns`, and `market_conditions` collections may not be consistently tagged. This needs verification and potentially a migration to add `category` metadata to all collections.

---

### Category → Workspace Template Mapping

Phase 1 `HEAD` includes workspace files for weather, SysAdmin, and Dev-Liaison. Category-specific templates beyond weather remain future work:

| Category | IDENTITY.md Name | SOUL.md Theme | Data Sources |
|---|---|---|---|
| Weather | Vane 🌪️ | Atmospheric chaos, ensemble models | NWS, Open-Meteo, OpenWeatherMap |
| Economics | Mint 💰 | Data-driven macro, leading indicators | FRED, BLS |
| Politics | Gavel ⚖️ | Polling aggregation, institutional analysis | NewsAPI |
| Sports | Edge 🏟️ | Statistical edge, situational spotting | TheSportsDB |
| Crypto | Flux ₿ | Volatility regimes, on-chain analysis | CoinGecko |
| Entertainment | Spotlight 🎬 | Box office, cultural trend momentum | NewsAPI |
| Science & Technology | Circuit ⚡ | Innovation cycles, breakthrough detection | NewsAPI |
| Health | Pulse ❤️ | Epidemiological modeling, regulatory analysis | NewsAPI |
| Social | Signal 📢 | Virality dynamics, sentiment momentum | Twitter, Reddit |

---

## Module Review

> This section preserves the 2025 pre-v2 module inventory and migration
> rationale. Paths and symbols in its legacy tables are not claims about
> current `HEAD` unless a row explicitly carries a Phase 1 update.

### Retired Code (Cleanup Inventory)

#### `install/` Inventory

| File | Lines | Purpose | v2 Status |
|---|---|---|---|
| `traderbot-installer.sh` | 1,048 | Bash installer (Linux/macOS) | **Retire** |
| `Install-TraderBot.ps1` | 1,303 | PowerShell installer (Windows) | **Retire** |
| `traderbot-update.py` | 338 | Standalone update script | **Discuss separately** |
| `README.md` | 141 | Installer documentation | **Rewrite** |
| `docker/Dockerfile` | 29 | Sandbox base image | **Keep** (build artifact) |
| `docker/build-sandbox.sh` | 38 | Sandbox build script | **Keep** (build artifact, orchestration moves to Python) |
| `services/traderbot-agent@.service` | 49 | Systemd agent daemon template | **Move** to `src/traderbot/services/` |
| `services/traderbot-news-ingest@.service` | 38 | Systemd news ingest service | **Move** to `src/traderbot/services/` |
| `services/traderbot-news-ingest@.timer` | 24 | Systemd news ingest timer | **Move** to `src/traderbot/services/` |
| `services/traderbot-backfill-data@.service` | 40 | Systemd backfill service | **Move** to `src/traderbot/services/` |
| `services/traderbot-backfill-data@.timer` | 26 | Systemd backfill timer | **Move** to `src/traderbot/services/` |
| `services/traderbot-ws-daemon.service` | 17 | Systemd WS daemon service | **Move** to `src/traderbot/services/` |
| `services/install-service.sh` | 53 | Systemd service installer | **Retire** (logic moves to Python) |
| `services/install-launchd.sh` | 55 | Launchd service installer | **Retire** (logic moves to Python) |
| `services/install-ws-daemon.sh` | 20 | WS daemon service installer | **Retire** (logic moves to Python) |
| `services/install-data-pipeline.sh` | 203 | Data pipeline timer installer | **Retire** (logic moves to Python) |
| `services/com.traderbot.agent.plist` | 54 | Launchd plist template | **Move** to `src/traderbot/services/` |

##### Net removal: ~2,861 lines of shell/PowerShell retired

#### Source Code References to Legacy Install Methods

| Module | Legacy Reference | Action Needed |
|---|---|---|
| `paths.py` | `_is_pipx_installed()`, `get_install_method()`, `get_source_root()` | Simplify: remove git/pip detection, always assume pipx |
| `updater.py` | 3-way install detection (pipx/git/pip) | Simplify: pipx only (full discussion deferred) |
| `cli/__init__.py` | Uninstall command detects pipx/git/pip | Simplify: pipx only |
| `cli/setup.py` | Comment references "pipx users" as special case | Remove special-casing |
| `cli/admin.py` | `bootstrap` command with `--full` flag | Remove entirely (DD-005) |
| `platform_compat.py` | `systemd_remove_services()`, `launchd_remove_services()`, `task_scheduler_remove_tasks()` | Keep (used by uninstall), update paths |
| `windows_service.py` | Service management via sc.exe/schtasks | Keep (used by service registration), update paths |
| `cron.py` | `_install_news_ingest_timer()` with systemd template path logic | Keep, update path references |
| `sandbox.py` | `get_source_root()` for src lockdown | Needs pipx-aware path resolution |
| `auth.py` | `_is_keyring_available()` catches exceptions | Replace with encrypted vault (DD-012) |
| `profiles/tokens.py` | Current `TokenStore` interface and `LocalTokenStore` JSON persistence | Keep the interface; add a future Infisical-backed implementation in Phase 1.5 (DD-037) |
| `profiles/auth.py` | Keyring-first credential resolution with `.env` fallback | Replace with encrypted vault (DD-012) |

---

### DD-015 Primary Impact: CLI Demotion

Under DD-015, agents interact with TraderBot through MCP tools, not CLI commands. This fundamentally changes the role of every CLI module:

**What stays**: `cli/setup.py` (pipx install experience), `cli/admin.py` (uninstall, update), `cli/auth.py` (credential management during setup). These are human-facing, used only during initial configuration.

**What changes most**: `cli/trade.py`, `cli/market.py`, `cli/news.py`, `cli/data.py` — these become thin MCP tool handlers that parse arguments and call service-layer functions. The business logic currently embedded in these CLI commands must be extracted.

**What retires**: `cli/cron.py` — under DD-016, data collection runs as an always-on service, not cron jobs. `cli/ws.py` — WebSocket daemon becomes part of the always-on service.

**New module needed**: `traderbot/mcp/` — MCP server implementation with tool definitions. Each current CLI command that agents use gets an MCP tool wrapper.

### Module-by-Module Assessment

> This review evaluates each module against the v2 architecture decisions (DD-001 through DD-021). Issues irrelevant under the new architecture are dropped; issues that persist or are newly created by v2 decisions are highlighted.

Module sizes (lines of Python, excluding `__pycache__`):

| Module | Lines | Files | v2 Impact |
|---|---|---|---|
| `cli/` | 7,486 | 13 | **Major refactor** — CLI becomes thin handler; MCP is primary interface |
| `news/` | 4,750 | 9 | **Restructure** — non-news data sources move to `data/` |
| `kalshi/` | 3,960 | 19 | **Expand** — add candlesticks API, absorb settlement logic |
| `simulation/` | 3,381 | 10 | **Major refactor** — Phase A/B split, SimulationClock, mode-awareness |
| `experiment/` | 3,273 | 25 | **Redesign** — align with DD-018 improvement framework |
| `profiles/` | 2,334 | 13 | **Major refactor** — tokens retire, MCP auth replaces CLI auth |
| `data/` | 1,527 | 10 | **Expand** — become central data source module, add categories |
| `db/` | 1,420 | 9 | **Expand** — mode-aware paths, multi-model bias tracking |
| `analysis/` | 752 | 6 | **Expand** — consolidate metrics, add statistical rigor functions |
| `risk/` | 875 | 6 | **Minimal change** — immutable core, works with MCP auth |
| `llm/` | 168 | 3 | **Expand** — multi-provider support for DD-018 debate |
| Top-level | 4,880 | 21 | **Significant retirements** — auth.py, master_password.py, cron_loops.py |

---

## Progress Tracking

### Discussed Topics

- [x] **Installation method**: pipx as sole method (DD-001)
- [x] **OpenClaw as hard dependency**: Required, not optional (DD-002)
- [x] **Docker isolation**: Mandatory for category agents, not optional (DD-010)
- [x] **Per-agent access control**: CLI-level category filtering (DD-011)
- [x] **Authentication architecture**: MCP server + secrets.json + OpenClaw SecretRef (DD-014, DD-015)
- [x] **MCP server architecture**: TraderBot registers as MCP server with OpenClaw (DD-015)
- [x] **Always-on service**: TraderBot fetches data proactively, agents query via MCP (DD-016)
- [x] **SysAdmin role**: Oversight, guardrails, self-improvement orchestration (DD-017)
- [x] **Agent lifecycle**: BACKTESTING → PAPER → LIVE → SUSPENDED (DD-017)
- [x] **Autonomous improvement framework**: Three-layer system with agent-debate (DD-018)
- [x] **Time-lapse behavioral simulation**: Phase A (statistical) + Phase B (behavioral) (DD-019)
- [x] **Historical data research**: Kalshi candlesticks confirmed, weather data gaps identified (DD-020)
- [x] **Division of responsibilities**: TraderBot fetches/analyzes, agent decides (documented)
- [x] **Prebuilt agent workspaces**: No user customization (DD-008)
- [x] **Deploy flow**: 8-step process from OpenClaw config to verification (DD-009)
- [x] **WebSocket-first principle**: Real-time Kalshi data via persistent connection (DD-016)
- [x] **Database architecture**: Per-agent per-mode isolation (DD-019)
- [x] **Profile-aware MCP tools**: Same tools/format regardless of mode (DD-019)
- [x] **SimAdmin sandbox**: Discussed but deferred — currently unsandboxed, needs rethink (DD-017 note)
- [x] **Data gap research**: Historical orderbooks (Kalshi candlestick API), weather lead times (NOAA GFS/ECMWF on AWS S3)
- [x] **Service template path resolution**: Runtime substitution with resolved pipx paths (DD-022)
- [x] **SysAdmin cron/heartbeat orchestration**: Phase-aware job lifecycle, dormant until activated (DD-023)
- [x] **Dev-Liaison design**: Subject matter expert and development liaison with four-layer knowledge architecture (DD-034)
### DD-024: Authentication implementation details — secrets store, MCP identity, and container isolation

**Date**: 2025-06-15
**Status**: Superseded by DD-025 and DD-037; historical implementation design only, not implemented

**Context**: DD-014 established the auth architecture (secrets store replaces keyring + .env, MCP server replaces CLI-in-container). DD-015 established the MCP server architecture (TraderBot registers as MCP server, agents call tools through OpenClaw gateway, per-agent tool filtering). This decision details the implementation: secrets store format, MCP server identity resolution, Docker bind mount restructuring, profile token injection, and migration path.

**Decision:**

**1. Secrets store format (`~/.traderbot/secrets/secrets.json`)**

Single JSON file with 0600 permissions, structured by namespace:

```json
{
  "global": {
    "kalshi": {
      "api_key": "...",
      "private_key_pem": "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----"
    },
    "voyage": { "api_key": "..." },
    "newsapi": { "api_key": "..." },
    "twitter": { "api_key": "...", "api_secret": "...", "bearer_token": "..." },
    "reddit": { "client_id": "...", "client_secret": "..." }
  },
  "weather": {
    "openweathermap": { "api_key": "..." }
  },
  "economics": {
    "fred": { "api_key": "..." }
  },
  "crypto": {
    "coingecko": { "api_key": "...", "tier": "pro" }
  },
  "sports": {
    "thesportsdb": { "api_key": "..." }
  }
}
```

Namespace rules:
- `global`: credentials shared across all agents (Kalshi, VoyageAI, NewsAPI, Twitter, Reddit)
- `<category>`: credentials specific to that category (only loaded if that category is enabled)
- The MCP server reads the `global` namespace plus the calling agent's category namespace
- SysAdmin profile can read all namespaces (oversight role)

No encryption at rest — the threat model is honest: TraderBot is always-on and needs these credentials continuously. Fernet encryption for an always-unlocked vault is security theater. POSIX file permissions (0600, owner-only) provide the actual access control on the host. Inside Docker containers, the file is not mounted at all (agents never see it).

**2. MCP server identity resolution**

When an agent calls a TraderBot MCP tool, the OpenClaw gateway routes the call. The MCP server needs to know which agent made the call to enforce category access control.

Identity resolution flow:

```
Agent calls traderbot__scan via OpenClaw tool interface
    → OpenClaw gateway receives the tool call with session context
    → Gateway knows: agent ID, session ID, tool name, arguments
    → Gateway routes to TraderBot MCP server (host process)
    → MCP server receives: tool name, arguments, AND OpenClaw session context
    → MCP server extracts agent ID from session context
    → MCP server resolves agent ID → TraderBot profile token → profile name → enabled categories
    → MCP server validates: is this tool available for this agent's categories?
    → MCP server reads API tokens from secrets.json (host-side)
    → MCP server makes external API call with appropriate tokens
    → MCP server returns data to agent
```

The profile token is the authentication credential. It's injected into the agent's environment via OpenClaw SecretRef (env provider) as `TRADERBOT_PROFILE_TOKEN`. When the MCP server receives a tool call, it:

1. Reads `TRADERBOT_PROFILE_TOKEN` from the calling agent's environment (provided by OpenClaw's session context)
2. Resolves the token via `resolve_token()` → gets profile name and agent ID
3. Loads the profile → gets `enabled_categories`, `mode`, `risk_multiplier`, etc.
4. Validates the requested tool against the profile's categories and mode
5. Reads API tokens from `secrets.json` based on the profile's categories
6. Makes the external API call
7. Returns the result

If the profile token is invalid, expired, or the agent's categories don't include the requested tool, the MCP server returns an error response explaining why access was denied.

**3. Docker bind mount restructuring**

Current (insecure):
```
-v $HOME/.traderbot:/home/traderbot/.traderbot:rw   # BLANKET MOUNT — everything accessible
-v $HOME/traderbot:/traderbot:ro                      # Source code
```

New (per-agent, minimal):
```
-v $HOME/.traderbot/paper-{category}/db:/home/traderbot/.traderbot/paper-{category}/db:rw
-v $HOME/.traderbot/paper-{category}/audit:/home/traderbot/.traderbot/paper-{category}/audit:rw
-v $HOME/.traderbot/chroma:/home/traderbot/.traderbot/chroma:ro
-v $HOME/.openclaw/workspace/{category}/:/workspace:rw
# NOT mounted: secrets/, keys/, tokens.enc, profiles.enc, .env, .master_key
```

Key changes:
- No blanket mount of `~/.traderbot/` — only the specific subdirectories the agent needs
- `secrets/` is NOT mounted — the MCP server on the host reads it, not the container
- `tokens.enc` is NOT mounted — profile tokens come via OpenClaw SecretRef env provider
- `chroma/` is read-only — agents query via MCP tools, they don't write directly
- Agent's own `db/` and `audit/` directories are read-write
- Source code mount stays (read-only) for now, but will be removed once CLI-in-container is no longer needed (DD-015 eliminates this requirement)

**4. Profile token injection via OpenClaw SecretRef**

During deploy (Step 3), after creating each category agent:

```bash
# Inject profile token as environment variable via OpenClaw SecretRef
openclaw config set "agents.list[{idx}].tools.alsoAllow[]" "bundle-mcp" \
  --strict-json --merge

# The profile token is stored in OpenClaw's config and injected into the agent's
# environment when OpenClaw starts the container
# The TRADERBOT_PROFILE_TOKEN env var is available inside the container
# The MCP server reads it from the OpenClaw session context
```

The profile token itself is created by TraderBot (`traderbot profile create`) and stored in `~/.traderbot/tokens.enc` (Fernet-encrypted, existing mechanism). The token value is then registered as an OpenClaw SecretRef so it's injected into the agent's environment.

**5. Migration path (`.env` + keyring → `secrets.json`)**

`traderbot setup` handles migration during the deploy flow:

1. Read existing `.env` file if it exists
2. Read existing keyring entries if keyring is available
3. Merge all credentials into `secrets/secrets.json`
4. Delete `.env` after successful migration (with confirmation)
5. Remove keyring entries after successful migration (with confirmation)
6. `traderbot auth set-key <service> <key>` writes to `secrets.json` going forward
7. `keyring` dependency removed from `pyproject.toml`

The `auth.py` module gains a new `SecretsStore` class:

```python
class SecretsStore:
    """Manages ~/.traderbot/secrets/secrets.json (0600 permissions)."""

    def __init__(self, path: Path | None = None):
        self.path = path or get_data_dir() / "secrets" / "secrets.json"
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._data = self._load()

    def get(self, service: str, key: str, namespace: str = "global") -> str | None: ...
    def set(self, service: str, key: str, value: str, namespace: str = "global") -> None: ...
    def get_namespace(self, namespace: str) -> dict[str, dict[str, str]]: ...
    def delete(self, service: str, key: str, namespace: str = "global") -> None: ...
    def migrate_from_env(self, env_path: Path) -> dict[str, int]: ...
    def migrate_from_keyring(self) -> dict[str, int]: ...
```

**6. Per-agent Kalshi keys**

For the initial implementation, all agents share a single Kalshi API key stored in the `global` namespace. Per-agent Kalshi keys (for multi-account strategies) are a future enhancement. The MCP server selects the correct key based on the calling agent's profile, but initially all profiles point to the same key.

**7. `traderbot auth` CLI updates**

```
traderbot auth set-key <service> <key> [--namespace <namespace>] [--value <value>]
    # Write to secrets.json (namespace defaults to "global")

traderbot auth check [--json]
    # Verify all required credentials are present and valid

traderbot auth migrate [--from env|keyring|all]
    # Migrate credentials from legacy sources to secrets.json

traderbot auth list [--json]
    # List all configured services and their sources
```

The `--namespace` flag allows setting category-specific credentials:
```bash
traderbot auth set-key openweathermap api_key --namespace weather
traderbot auth set-key fred api_key --namespace economics
```

**8. What gets retired**

| File/Module | Lines | Reason |
|---|---|---|
| `src/traderbot/auth.py` | 376 | Replaced by `secrets/store.py` (SecretsStore class) |
| `src/traderbot/master_password.py` | 284 | No longer needed — paper mode auto-authenticates via profile token |
| `src/traderbot/profiles/tokens.py` | 358 | Simplified — tokens still exist but resolution changes for MCP |
| `src/traderbot/profiles/auth.py` | ~100 | Keyring resolution removed, replaced by SecretsStore |
| `keyring` dependency | — | Removed from `pyproject.toml` |
| `~/.traderbot/.env` | — | Migrated to `secrets.json`, then deleted |
| `~/.traderbot/.master_key` | — | No longer needed for paper mode auth |

**What gets added**

| File | Purpose |
|---|---|
| `src/traderbot/secrets/__init__.py` | Package init |
| `src/traderbot/secrets/store.py` | `SecretsStore` class with get/set/delete/migrate |
| `src/traderbot/mcp/__init__.py` | Package init |
| `src/traderbot/mcp/server.py` | MCP server entry point (`traderbot-mcp-server` command) |
| `src/traderbot/mcp/tools.py` | MCP tool definitions (scan, analyze, trade, etc.) |
| `src/traderbot/mcp/auth.py` | Profile token resolution, category validation, permission checks |

**9. `TradingProfile` model updates**

The `TradingProfile` model gains a `mode` field that includes `backtest` (DD-019) and a `permissions` field (DD-014):

```python
class TradingProfile(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    name: str
    mode: Literal["backtest", "paper", "live"]  # Added "backtest"
    description: str
    enabled_categories: list[MarketCategory] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=lambda: [
        "scan", "analyze", "trade", "data-points", "news-context",
        "heartbeat", "performance", "audit", "learnings",
    ])
    risk_multiplier: Annotated[float, Field(gt=0, le=1.0)]
    max_position_per_market_pct: Annotated[float, Field(gt=0)]
    max_daily_loss_pct: Annotated[float, Field(gt=0)]
    max_drawdown_pct: Annotated[float, Field(gt=0)]
    max_open_positions: Annotated[int, Field(gt=0)]
    min_liquidity_threshold: Annotated[int, Field(gt=0)]
    min_edge_pct: Annotated[float, Field(gt=0)]
    initial_balance_cents: int | None = 10_000
```

The `permissions` field allows fine-grained control over which MCP tools an agent can access. For example, a backtesting agent wouldn't have `"trade"` permission, while a sysadmin agent would have `"profile_list"` and `"auth_check"` but not `"trade"`.

**Consequences:**
- `keyring` dependency removed — eliminates headless Linux issues entirely
- `.env` file retired — all credentials in structured `secrets.json`
- No credentials inside Docker containers — MCP server on host reads `secrets.json`
- Per-agent bind mounts instead of blanket — each agent only sees its own data
- Profile token via OpenClaw SecretRef — never appears in container files
- MCP server enforces category access at the tool level — agents cannot call tools outside their categories
- `master_password.py` retired — paper mode auto-authenticates, live mode requires explicit authorization
- `auth.py` replaced by `secrets/store.py` — single source of truth for all credentials
- Migration is handled automatically during `traderbot setup` — user confirms before deletion
- Per-agent Kalshi keys supported in the schema but initially all agents share a global key

---


### DD-025: Auth implementation details — MCP identity resolution and migration plan

**Date**: 2025-06-15
**Status**: Decided

> **Phase 1 implementation update:** TraderBot now supports explicit profile
> tokens through `TokenStore`, with a hardened `LocalTokenStore` at
> `~/.traderbot/tokens.json`. Every implemented tool checks access in the order
> **token → tool permission → category**. This has been verified through the
> real MCP transport locally. Phase 1 is now deployable: per-agent token
> injection via the `before_tool_call` plugin hook is built and
> deployment-verified on macpro-linux (Phase 1.1, issue #187 closed).
> External provider credential checks are deferred to secrets/provider/deploy
> work (Phase 1.5, issue #165).

**Context**: DD-024 established the overall auth architecture (secrets store, MCP server, per-agent bind mounts). This decision resolves the critical implementation gap: **how does the TraderBot MCP server identify which agent is calling a tool?**

The MCP server (`traderbot-mcp-server`) runs as a single shared process on the host, launched by the OpenClaw gateway via stdio. All agents route tool calls through this same process. The standard MCP protocol's `tools/call` method does not include caller identity. The MCP server cannot read environment variables from inside Docker containers — it's a separate host process.

**Investigation: OpenClaw MCP identity passing**

The pinned first-party OpenClaw schema and policy implementation establish:
- MCP registration belongs at root `mcp.servers`; a root gateway artifact in `configs/openclaw/` registers TraderBot once
- Agent entries are strict and do not accept per-agent `env`, nested `mcp`, or annotation fields
- Restrictive per-agent policies require explicit `tools.allow`/`tools.deny`; a lone `alsoAllow` is additive to an implicit wildcard
- Root environment values and `mcp.servers.*.env` apply globally or to the shared MCP process, not to one calling agent

OpenClaw does NOT currently pass agent identity (agent ID, session context) to MCP tool calls. The MCP protocol's `tools/call` method is agent-agnostic. There is no `_meta.agent_id` or similar field in the standard.

**Options considered:**

| Approach | How it works | Pros | Cons |
|---|---|---|---|
| **A: Token as tool parameter** | Every MCP tool accepts a `token` parameter. MCP server resolves token → profile → permissions → categories. | Implemented and transport-tested in TraderBot; simple and stateless | Still requires a secure mechanism to give each agent only its own token; neither the legacy nor remediation config can do this |
| **B: Isolated gateway/MCP instances** | Give each agent an isolated gateway or MCP process with its own launch environment. | Strong process-level separation; no shared token environment | More processes and deployment complexity; architecture not selected or tested |
| **C: OpenClaw proxy/plugin adds identity or token** | A gateway plugin/proxy identifies the caller and injects the matching token or trusted identity. | Centralized and compatible with one TraderBot server | Requires plugin/proxy implementation and a trust-boundary review |
| **D: Token in MCP server env** | Single MCP server process gets all tokens in its env. Agent passes agent_id in tool call, server looks up corresponding token. | No token in tool calls | Agent could pass wrong agent_id and access another agent's data (security hole) |

**Decision: Approach A inside TraderBot — token as explicit tool parameter**

Every TraderBot MCP tool accepts a `token` parameter. The workspace instructions
require it in every call. The MCP server resolves the token, checks the full
`traderbot__*` tool permission, and then enforces category access when the tool
has a category. This server-side decision is implemented. Secure token delivery
from OpenClaw is handled by the Phase 1.5 `before_tool_call` plugin hook, not by
static configuration.

> **Token delivery (Phase 1.5):** Per-agent tokens are injected at the OpenClaw
> plugin layer via a `before_tool_call` hook, not passed by the model. The hook
> reads `ctx.agentId` (trusted, host-derived), resolves the agent's token from
> Vault, and rewrites the tool call params to include the `token` field. This
> preserves TraderBot's server-side token-to-profile authorization as the
> enforcement boundary.

```python
# MCP tool definition
@tool
async def traderbot__scan(token: str, category: str, ...):
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

The agent's TOOLS.md workspace file includes:
```
When calling any TraderBot tool, always include your profile token as the `token` parameter.
Your deployment must provide the token securely; current local tests pass it explicitly.
```

**Current security properties:**
- `generate_token()` creates 256-bit URL-safe tokens
- `LocalTokenStore` writes `~/.traderbot/tokens.json` atomically with mode `0600` on POSIX; it does not use Fernet or `tokens.enc`
- A valid token resolves to one profile and agent, then tool permissions and category access are enforced
- Strict Pydantic inputs reject extra or malformed arguments
- The OpenClaw injection blocker is now resolved: the `before_tool_call` plugin
  hook (Phase 1.1, issue #187 closed) injects per-agent tokens host-side.

**Architecture (implemented):**
- A `before_tool_call` plugin hook injects the agent's token into tool call
  params before the MCP server receives them (commit `5b5088e`, verified
  on macpro-linux).
- The config artifacts are now deployable with the plugin active.
- Vault SecretRef integration is deferred to Phase 1.5 (issue #165).

**MCP server configuration (OpenClaw)**

The separate remediation registers TraderBot as:

```json
{
  "mcp": {
    "servers": {
      "traderbot": {
        "command": "traderbot-mcp-server",
        "transport": "stdio"
      }
    }
  }
}
```

`TRADERBOT_SECRETS_PATH` is not part of current Phase 1 behavior. External API
secret resolution is deferred to the secrets/provider/deploy phases.

**Per-agent tool filtering (OpenClaw config)**

The remediation fragments use exact tool names in a restrictive normal `allow` list. Sandboxed agents separately allow `bundle-mcp` at the
sandbox gate:

```json5
{
  agents: {
    list: [
      {
        id: "weather",
        sandbox: { mode: "all" },
        tools: {
          deny: ["group:runtime", "group:fs"],
          allow: [
            "traderbot__health",
            "traderbot__auth_check",
            "traderbot__profile_list",
            "traderbot__market_edge"
          ],
          sandbox: { tools: { allow: ["bundle-mcp"] } },
        },
      },
    ],
  },
}
```

`bundle-mcp` opens the sandbox route to MCP; it is not in the normal agent
allowlist. The request must pass both OpenClaw gates and TraderBot's token,
permission, and category checks. The remediation fragments also include
planned tool names, but only four TraderBot tools currently exist. At this
documentation commit, these strict fragments and the root gateway artifact are
not part of `HEAD`; the committed fragments retain the legacy unsupported
shape.

**Current token lifecycle:**

1. **Creation/storage**: `LocalTokenStore` stores caller-provided or generated 256-bit tokens in `~/.traderbot/tokens.json`
2. **Mode selection**: `TRADERBOT_USE_HARDCODED_AUTH=0` selects `TokenStore`; every other value uses the hardcoded development mapping
3. **Usage**: The caller includes the token in every MCP call; TraderBot resolves token → profile → permission → category
4. **Rotation**: `LocalTokenStore.rotate_token()` removes all old tokens for the profile/agent and persists one fresh token
5. **Not implemented**: OpenClaw token injection, TTL expiry, Infisical synchronization, and scheduled rotation

**SysAdmin auth (host-side, unsandboxed):**

The current SysAdmin factory explicitly enumerates every `MarketCategory` and
uses deny rules for trading, scanning, analysis, market data, and weather tools;
its deny-only permission set therefore permits `health`, `auth_check`, and
`profile_list`. The remediation fragment applies corresponding OpenClaw restrictions. Supplying the profile token through an environment
variable is not implemented by either the legacy or remediation config.

**Service authentication (always-on daemon):**

The Phase 1 MCP server does not read or validate external API credentials.
Infisical-backed service authentication and provider credentials are deferred
to Phase 1.5 secrets/provider/deploy work.

**Migration implementation order:**

1. **Create `src/traderbot/secrets/store.py`** — `SecretsStore` class with `get/set/delete/migrate`
2. **[x] Create `src/traderbot/mcp/server.py`** — MCP server entry point (`traderbot-mcp-server` CLI command) — already exists (Phase 0)
3. **[x] Create `src/traderbot/mcp/tools.py`** — MCP tool definitions with `token` parameter — already exists (Phase 0)
4. **[x] Create `src/traderbot/mcp/auth.py`** — Token resolution, profile loading, category validation — completed in Phase 1
5. **Update `traderbot/setup`** — Migrate credentials from `.env` + keyring to `secrets.json`, delete `.env`
6. **Update `traderbot auth`** — `set-key` writes to `secrets.json`, `check` validates from `secrets.json`, `migrate` handles legacy sources
7. **[x] Keep `keyring` out of v2 dependencies** — absent from `pyproject.toml` in Phase 1 `HEAD`
8. **[x] Legacy `auth.py` is absent from v2 `HEAD`** — future provider credential handling remains tracked by item 1
9. **[x] Legacy `master_password.py` is absent from v2 `HEAD`** — future live-mode confirmation remains unimplemented
10. **[x] Simplify `profiles/tokens.py`** — `TokenStore` ABC + hardened `LocalTokenStore`, no `.env` fallback
11. **[x] Legacy `profiles/auth.py` is absent from v2 `HEAD`** — provider credentials remain deferred to the future `SecretsStore`
12. **[x] Update `profiles/models.py`** — `mode` and `permissions` already exist
13. **Implement the future database-isolation layer** — current `TradingProfile.base_dir` is mode-aware, but no `profiles/isolation.py` module exists in Phase 1 `HEAD`
14. **Update Docker bind mounts** — Per-agent selective mounts, remove blanket mount
15. **Update workspace templates** — TOOLS.md includes `token` parameter in every tool call
16. **Register MCP server with OpenClaw** — `openclaw mcp add traderbot --command traderbot-mcp-server`
17. **Update deploy flow** — Configure per-agent SecretRef for profile token injection

Items 1, 5-6, 13-14, and the deployment parts of 16-17 remain pending. Items 8,
9, and 11 preserve the historical migration intent, but their pre-v2 source
paths are already absent. Item 17 is blocked by the OpenClaw schema constraint
described above; it cannot be completed by adding unsupported agent fields.

**Verified Phase 1 auth/profile/token source in `HEAD`:**

| Path | Verified current role |
|---|---|
| `src/traderbot/mcp/auth.py` | `check_category_access()` enforces category access after authentication and tool permission checks |
| `src/traderbot/mcp/resolver.py` | `resolve_token_adapter()` selects hardcoded or real profile-token resolution |
| `src/traderbot/mcp/tools.py` | Four MCP handlers authenticate explicit tokens and enforce tool permissions; `market_edge` also enforces category access |
| `src/traderbot/profiles/models.py` | `TradingProfile` provides modes, category rules, tool permissions, and mode-aware `base_dir` |
| `src/traderbot/profiles/registry.py` | `ProfileRegistry` loads the SysAdmin, Dev-Liaison, and weather profile factories |
| `src/traderbot/profiles/tokens.py` | `TokenStore` plus `LocalTokenStore` JSON persistence, generation, resolution, listing, and rotation |

**Historical pre-v2 auth migration inventory (not current `HEAD`):**

The paths and symbols below are retained to explain the original migration
rationale. None exists in Phase 1 `HEAD`; their successor provider-credential
functionality remains future Phase 1.5 work.

| Historical path | 2025 behavior | Intended successor |
|---|---|---|
| `src/traderbot/auth.py` | `AuthManager` with keyring → env → `.env` fallback | `SecretsStore` in `secrets/store.py` |
| `src/traderbot/profiles/auth.py` | `ProfileAuthStore` with keyring → env fallback | `SecretsStore.get(namespace=category)` |
| `src/traderbot/master_password.py` | PBKDF2 master password for trade/simulate gating | Profile-token auth plus live-mode confirmation |
| `src/traderbot/profiles/runtime.py` | `get_current_profile()` read `TRADERBOT_PROFILE_TOKEN` from env/`.env` | Explicit token parameter at the MCP boundary |
| `src/traderbot/profiles/config.py` | `resolve_kalshi_credentials()` used keyring/env | `SecretsStore.get("kalshi", "api_key")` |
| `src/traderbot/cli/auth.py` | Auth CLI commands | Human-facing `SecretsStore` management |
| `src/traderbot/cli/setup.py` | Used `AuthManager` for credential setup | Setup-time `SecretsStore` migration |
| `src/traderbot/cli/trade.py` | Used `master_password.require_auth()` | Profile-token auth plus live-mode confirmation |
| `src/traderbot/kalshi/ws_daemon.py` | Used `get_credential("kalshi", ...)` | Host service `SecretsStore.get()` |
| `src/traderbot/news/sources.py` | Used `get_credential()` for provider APIs | Namespaced `SecretsStore.get()` |
| `src/traderbot/news/ingest.py` | Used `get_credential()` for FRED | Namespaced `SecretsStore.get()` |


### DD-026: Secrets management — 1Password as primary vault (SUPERSEDED by DD-037 — see below)

> **This decision is superseded by DD-037.** 1Password was replaced by Infisical as the primary secrets vault because 1Password Connect requires a Business/Teams subscription ($7.99+/month). All architecture, token provisioning, and division of secrets responsibility described below are preserved in DD-037 with Infisical as the backend. DD-026 is kept for historical context only.

**Date**: 2025-06-15
**Status**: Decided

**Context**: DD-012, DD-014, and DD-024 proposed a self-managed secrets store (`secrets.json` or `vault.enc` with OS-protected master key) and DD-025 proposed profile tokens as MCP tool parameters. Subsequent discussion explored per-agent MCP servers, ZKP handshake mechanisms, and session-based authentication to eliminate credentials from containers. Each approach added complexity while either (a) leaving credentials in containers or (b) making OpenClaw the sole trust boundary without independent verification.

The final decision: use 1Password as the primary secrets vault. This provides battle-tested encryption, access control, audit logging, and key management without building custom encryption infrastructure. Profile tokens remain the authentication mechanism (DD-025), stored in and rotated by 1Password.

**Decision:**

**1. 1Password Connect as secrets backend**

All TraderBot secrets are stored in 1Password vaults, accessed via 1Password Connect (self-hosted API server):

```
1Password (cloud vault)
  ├── TraderBot API keys vault
  │   ├── kalshi.api_key
  │   ├── kalshi.private_key_pem
  │   ├── voyage.api_key
  │   ├── newsapi.api_key
  │   ├── twitter.api_key / api_secret / bearer_token
  │   └── reddit.client_id / client_secret
  ├── Category-specific API keys vault
  │   ├── weather.openweathermap_api_key
  │   ├── economics.fred_api_key
  │   ├── crypto.coingecko_api_key / tier
  │   └── sports.thesportsdb_api_key
  └── Agent profile tokens vault
      ├── weather.profile_token
      ├── economics.profile_token
      └── sysadmin.profile_token
```

**2. 1Password Connect architecture**

```
1Password Connect (Docker, runs alongside TraderBot)
  ├── Provides REST API at http://localhost:8080
  ├── Authenticated via 1Password Connect token
  └── Accessible only from localhost (no external exposure)

TraderBot service (host, always-on)
  ├── At startup: authenticates with 1Password Connect
  ├── Retrieves all secrets into memory
  ├── MCP server validates profile tokens from agent tool calls
  └── API calls made with secrets from memory (not from disk)

Agent (container)
  └── TRADERBOT_PROFILE_TOKEN injected via OpenClaw SecretRef → passed in MCP tool calls
```

1Password Connect runs as a Docker container on the same host as TraderBot. It communicates with 1Password's cloud servers to sync vaults. The TraderBot service connects to it via localhost.

**3. Secret resolution flow**

```python
# SecretsStore interface (same API, different backend)
class SecretsStore:
    def get(self, service: str, key: str, namespace: str = "global") -> str | None: ...
    def set(self, service: str, key: str, value: str, namespace: str = "global") -> None: ...
    def get_namespace(self, namespace: str) -> dict[str, dict[str, str]]: ...
    def delete(self, service: str, key: str, namespace: str = "global") -> None: ...

    # 1Password backend
    def _op_get(self, vault: str, item: str, field: str) -> str | None: ...
    def _op_set(self, vault: str, item: str, field: str, value: str) -> None: ...
    def _op_delete(self, vault: str, item: str) -> None: ...
```

Two backends with the same interface:

| Backend | When to use | Storage | Key management |
|---|---|---|---|
| **1Password** (primary) | Default, recommended | 1Password cloud vaults | 1Password manages |
| **Local** (fallback) | No 1Password account, air-gapped systems | `~/.traderbot/secrets/secrets.json` (0600) | OS-protected master key |

Users choose the backend during `traderbot deploy`. 1Password is the default and recommended option. The local fallback exists for users who can't or don't want to use 1Password.

**4. Profile token management**

Profile tokens are stored as 1Password items:

```
Vault: "TraderBot - Agent Tokens"
Item: "weather-agent-token"
  ├── field: "token" (the profile token value)
  ├── field: "profile" (profile name, e.g., "weather")
  ├── field: "agent" (agent ID, e.g., "weather")
  ├── field: "categories" (enabled categories, e.g., "weather")
  └── field: "permissions" (comma-separated, e.g., "scan,analyze,trade")
```

Token rotation: 1Password supports item history and can be automated. TraderBot rotates tokens on a configurable schedule (default: 4 hours). After rotation, the new token is updated in 1Password and the OpenClaw SecretRef is refreshed.

**5. Token rotation and session management**

- Profile tokens rotate every 4 hours by default (configurable per deployment)
- `traderbot token rotate` generates a new token, updates 1Password, and refreshes OpenClaw SecretRef
- SysAdmin heartbeat includes a token staleness check (30-minute warning before expiry)
- The MCP server caches tokens in memory and refreshes from 1Password on cache miss or rotation
- Short-lived tokens limit the blast radius of a compromised token

**6. Deploy flow integration**

During `traderbot deploy` (Step 4: API tokens):

1. Check for 1Password Connect availability
2. If available: create 1Password vaults and items for all configured secrets
3. If not available: fall back to local `secrets.json` storage with a warning
4. Store the 1Password Connect token in OpenClaw SecretRef (env provider)
5. The TraderBot service reads this token at startup to authenticate with 1Password Connect

**7. What gets retired (updated from DD-024)**

| Component | Lines | Replacement |
|---|---|---|
| `auth.py` | 376 | `SecretsStore` with 1Password backend |
| `profiles/auth.py` | 185 | `SecretsStore` with namespace parameter |
| `profiles/tokens.py` | 358 | Simplified — tokens stored in 1Password, resolution stays |
| `master_password.py` | 284 | Eliminated (1Password manages auth) |
| `keyring` dependency | — | Eliminated (1Password replaces keyring) |
| `~/.traderbot/.env` | — | Eliminated |
| `~/.traderbot/tokens.enc` | — | Eliminated (1Password stores tokens) |
| `~/.traderbot/keys/token.key` | — | Eliminated |
| `~/.traderbot/.master_key` | — | Eliminated |

**8. What gets added (updated from DD-024)**

| Component | Purpose |
|---|---|
| `src/traderbot/secrets/__init__.py` | Package init |
| `src/traderbot/secrets/store.py` | `SecretsStore` interface with 1Password and local backends |
| `src/traderbot/secrets/onepassword.py` | 1Password Connect SDK integration |
| `src/traderbot/secrets/local.py` | Local fallback (`secrets.json`, 0600) |
| `src/traderbot/mcp/__init__.py` | Package init |
| `src/traderbot/mcp/server.py` | MCP server entry point (`traderbot-mcp-server` command) |
| `src/traderbot/mcp/tools.py` | MCP tool definitions (scan, analyze, trade, etc.) |
| `src/traderbot/mcp/auth.py` | Profile token resolution, category validation, permission checks |

**9. 1Password Connect deployment**

1Password Connect runs as a Docker container on the TraderBot host:

```yaml
# docker-compose.yml (or equivalent)
services:
  1password-connect:
    image: 1password/connect-api:latest
    ports:
      - "8080:8080"
    volumes:
      - ~/.1password/connect:/home/opc/.1password
    environment:
      - OP_SESSION=  # 1Password Connect token
```

The TraderBot service connects to `http://localhost:8080` to retrieve secrets. The Connect token is stored in OpenClaw SecretRef (env provider) and injected into the TraderBot service's environment.

**10. Container exploit surface mitigation**

The profile token is in the container environment (injected via OpenClaw SecretRef). This is the remaining exploit surface. Mitigations:

- **Short-lived tokens** (4-hour rotation): A stolen token expires quickly
- **Scoped tokens** (category + permissions): A weather token can't access economics data
- **1Password audit logging**: Every token access is logged, enabling detection of anomalous usage
- **No other secrets in containers**: API keys, encryption keys, and other secrets never enter containers

**11. Division of secrets responsibility (updated)**

| Secret type | Manager | Storage | Access |
|---|---|---|---|
| OpenClaw LLM keys, gateway auth, channel tokens | OpenClaw SecretRef | 1Password (or OpenClaw's own vault) | OpenClaw gateway on host only |
| TraderBot API keys (Kalshi, Voyage, NewsAPI, etc.) | 1Password Connect | 1Password vault | TraderBot service on host only |
| Agent profile tokens | 1Password Connect | 1Password vault | TraderBot service (resolution) + OpenClaw SecretRef (injection into containers) |
| 1Password Connect token | OpenClaw SecretRef | OpenClaw config (env provider) | TraderBot service only |
| TraderBot service auth token | 1Password Connect | 1Password vault | TraderBot service only |

**12. Relationship to previous DDs**

- **DD-012** (encrypted vault + SecretRef hybrid): Superseded by DD-026 (superseded by DD-037). Infisical replaces the custom encrypted vault. OpenClaw SecretRef is still used for injecting the Infisical token and profile tokens into agent environments.
- **DD-014** (authentication and secrets architecture): Phase 1 (secrets store) is replaced by 1Password. Phase 2 (daemon architecture) is replaced by the MCP server (DD-015). The key principles remain: no keyring, no `.env`, no blanket bind mounts, per-agent access control, agents never see API tokens.
- **DD-024** (auth implementation details): Updated. The `secrets.json` file is replaced by 1Password Connect. The migration path now includes 1Password vault creation. Docker bind mount restructuring and profile token injection via SecretRef remain unchanged.
- **DD-025** (MCP identity resolution): Remains in effect. Profile tokens are still the authentication mechanism, stored in and rotated by 1Password.

**13. New dependencies**

| Dependency | Purpose | Required? |
|---|---|---|
| `1password-connect-sdk` (Python) | Programmatic access to 1Password Connect | Primary backend |
| 1Password Connect (Docker) | Self-hosted API server | Primary backend |
| 1Password Service Account | Machine-level auth for TraderBot | Primary backend |
| 1Password account | Cloud vault management | Primary backend |

Users who don't want 1Password can use the local fallback backend (`secrets.json` with 0600 permissions), which provides the same API but without 1Password's encryption, audit, or rotation capabilities.

**Consequences:**
- Eliminates custom encryption infrastructure (no Fernet, no OS-protected master key, no platform-specific key storage)
- Eliminates `keyring` dependency entirely
- Eliminates `.env` file, `tokens.enc`, `token.key`, `.master_key`
- 1Password provides encrypted storage, access control, audit logging, and token rotation
- Profile tokens remain in container environments (accepted risk, mitigated by short rotation and scoping)
- Requires users to set up 1Password Connect (Docker container) during deploy
- Local fallback available for users who don't want 1Password
- All previous DDs about encrypted vaults and OS-protected keys are superseded by this decision

---

### DD-027: Data pipeline collects all sources at install, not just enabled categories

**Date**: 2025-06-15
**Status**: Decided

**Context**: Under DD-016, TraderBot is an always-on service that proactively collects data independent of agents. Currently, data collection is gated by enabled categories — only sources relevant to the user's selected categories are fetched and stored.

**Decision**: All data sources begin collection at install time, regardless of which categories the user enables. Category agents still only receive data relevant to their category via MCP tool filtering, but the underlying data pipeline collects everything.

**Rationale**:
- Backtesting requires historical data across all potential categories — a user who enables weather later shouldn't have 6 months of missing weather data
- Collection is cheap (most sources are free APIs or minimal-cost); storage is cheap (SQLite + ChromaDB)
- This enables rapid category activation without waiting for backfill
- MCP tool filtering (`alsoAllow`) ensures category agents still only see their data — the pipeline collects broadly, but access is narrow

**Consequences**:
- Data collection workers run for all sources from service start, not just enabled ones
- API tokens for all common sources (NewsAPI, VoyageAI, Reddit, Twitter, Kalshi) are requested during deploy even if no category needs them yet
- Category-specific API tokens (Open-Meteo, OpenWeatherMap for weather; CoinGecko for crypto) are still only requested if that category might use them — but data collection can begin with just the common tokens
- ChromaDB collections for all categories are created and populated during backfill (DD-009 Step 6)
- Disk usage increases moderately — acceptable tradeoff for enabling instant category activation
- The `--categories` flag for backfill (pending item) becomes less critical since all categories are always backfilled, but may still be useful for re-backfilling a single category

---

### DD-028: news/ and data/ module restructure

**Date**: 2025-06-15
**Status**: Decided

**Context**: Currently `news/` and `data/` have significant overlap:

| Module | Files | Lines | Responsibility |
|---|---|---|---|
| `news/sources.py` | 1 | ~2,364 | NewsAggregator fetches from NewsAPI, Reddit, Twitter, FRED, OpenWeatherMap, Open-Meteo, CoinGecko, TheSportsDB, Google Trends |
| `news/ingest.py` | 1 | ~997 | Fetches, embeds, classifies, sentiment-scores, stores in ChromaDB |
| `news/classifier.py` | 1 | — | NewsClassifier assigns categories |
| `news/sentiment_scorer.py` | 1 | — | Sentiment scoring |
| `news/impact_assessor.py` | 1 | — | Impact assessment |
| `news/embeddings.py` | 1 | — | VoyageAI embedding |
| `data/weather/provider.py` | 1 | ~327 | WeatherDataProvider (NWS + Open-Meteo ensemble) |
| `data/weather/signals.py` | 1 | ~387 | WeatherSignalEngine (forecast vs market edge detection) |
| `data/weather/nws_client.py` | 1 | — | NWS API client |
| `data/weather/geo.py` | 1 | — | City/coordinate mapping |
| `data/base_provider.py` | 1 | — | BaseDataProvider ABC |
| `data/base_signals.py` | 1 | — | BaseSignalEngine ABC |
| `data/registry.py` | 1 | — | Provider registry |

**Overlap problems**:
1. **`news/sources.py` fetches weather and financial data** — Open-Meteo, OpenWeatherMap, FRED, CoinGecko, TheSportsDB are data sources, not news. They're grouped with NewsAPI/Reddit/Twitter because the original design didn't separate "fetching external data" from "processing news articles"
2. **Two separate CLI entry points** — `cli/news.py` and `cli/data.py` have overlapping commands (`news-context` vs `data-points`, `news-summary` vs signal display)
3. **Two separate storage paths** — news goes to ChromaDB `news` collection, data points go to `data_points` collection, but weather forecasts also produce data points stored through news
4. **No unified data pipeline abstraction** — `NewsAggregator` and `WeatherDataProvider` are independent classes with no shared interface for scheduling, rate limiting, or error handling

**Decision**: Under the v2 architecture (DD-016, always-on service), restructure into a unified data pipeline:

```
src/traderbot/
├── data/                          # Unified data pipeline
│   ├── pipeline.py                # DataCollectionService — always-on orchestrator
│   ├── scheduler.py               # Rate-limited, scheduled collection with backoff
│   ├── base_provider.py           # BaseDataProvider ABC (existing, expanded)
│   ├── base_signals.py            # BaseSignalEngine ABC (existing)
│   ├── registry.py                # Provider registry (existing, expanded)
│   ├── providers/                 # One subpackage per source
│   │   ├── newsapi.py             # NewsAPI (articles only)
│   │   ├── reddit.py              # Reddit RSS (articles only)
│   │   ├── twitter.py             # Twitter/X stub
│   │   ├── kalshi.py              # Kalshi market data + candlesticks
│   │   ├── fred.py                # FRED economic data
│   │   ├── coingecko.py          # CoinGecko crypto data
│   │   ├── open_meteo.py         # Open-Meteo forecasts + archive
│   │   ├── openweathermap.py     # OpenWeatherMap current weather
│   │   ├── nws.py                 # NWS forecasts
│   │   ├── thesportsdb.py        # Sports data
│   │   ├── google_trends.py      # Google Trends
│   │   └── voyage.py              # VoyageAI embeddings
│   ├── weather/                   # Weather-specific logic (signals, bias, geo)
│   │   ├── signals.py             # WeatherSignalEngine
│   │   ├── geo.py                 # City/coordinate mapping
│   │   └── bias.py                # Forecast bias tracking
│   ├── processing/                # Post-fetch enrichment
│   │   ├── classifier.py          # Category classification
│   │   ├── sentiment.py           # Sentiment scoring
│   │   ├── impact.py             # Impact assessment
│   │   └── embed.py               # VoyageAI embedding
│   └── models.py                  # Shared data models
├── news/                           # RETIRED — logic moves to data/
└── ...
```

**Migration path**:
1. Create `data/providers/` subpackage and move each source from `news/sources.py` into its own module
2. Create `data/processing/` subpackage and move classifier, sentiment, impact, embeddings from `news/`
3. Create `data/pipeline.py` — the always-on DataCollectionService (DD-016)
4. Create `data/scheduler.py` — rate-limited scheduling (respects per-source rate limits)
5. Update `cli/news.py` and `cli/data.py` to call `data/pipeline.py` internally
6. Eventually retire `cli/news.py` entirely — all data access becomes MCP tools
7. Remove `news/` package once all consumers are migrated

**Consequences**:
- Clear separation between "fetching data" (providers) and "processing articles" (processing)
- Each data source is independently testable, rate-limited, and schedulable
- The `DataCollectionService` orchestrates all providers, running them on appropriate intervals
- MCP tools query the same databases the pipeline populates
- `news/` package is deprecated and eventually removed

---

### DD-029: P&L and settlement logic consolidation

**Date**: 2025-06-15
**Status**: Decided

**Context**: P&L calculation and settlement logic is currently duplicated across multiple modules:

| Location | P&L Calculation | Settlement Logic |
|---|---|---|
| `simulation/paper_trader.py` | `PaperTrader._close_position()` computes P&L as `(fill_price - avg_price) * qty` for yes, `(avg_price - fill_price) * qty` for no | `PaperTrader.record_fill()` opens/closes positions in SQLite |
| `simulation/engine.py` | `_Position.compute_pnl()` computes `(exit - entry) * qty` for yes, `(entry - exit) * qty` for no | `BacktestEngine._compute_result()` aggregates P&L |
| `simulation/settlement.py` | — | `SettlementVerifier.auto_settle_paper_positions()` and `_settle_weather_bets()` |
| `db/positions.py` | `pnl_cents` field on positions | `update_settlement()`, `mark_closed()` |
| `analysis/portfolio.py` | `edge_realization()` computes per-decision P&L | — |
| `simulation/performance.py` | `compute_metrics()` aggregates from BacktestResult | — |

Three separate settlement implementations:
1. `paper_trader.py`: fills via orderbook walk with slippage model
2. `settlement.py`: weather bets via Open-Meteo archive API
3. `engine.py`: backtest settlement via DataLoader outcomes

The P&L direction logic (`yes wins when actual < threshold` vs `no wins when actual > threshold`) appears in all three with subtle variations.

**Decision**: Consolidate into a single `trading.py` module:

1. **Unified P&L calculation** — One function, `compute_pnl(direction, entry_price, exit_price, quantity)` in `traderbot/trading.py`. All modules call this. No more duplicated direction logic.

2. **Unified settlement interface** — `traderbot/trading.py` exposes `settle_position(ticker, outcome)` which routes to the correct settlement method:
   - Paper trading: mark position as settled in paper DB
   - Live trading: reconcile with Kalshi via `kalshi/settlement.py`
   - Backtesting: resolved by DataLoader

3. **`simulation/settlement.py`** splits:
   - Weather settlement logic → `trading.py` (shared settlement rules)
   - Kalshi ticker parsing → `kalshi/models.py` (domain-specific)
   - `SettlementVerifier` → `trading.py` (orchestration)

4. **`paper_trader.py`** uses the unified `compute_pnl()` and `settle_position()` instead of inlining the calculation.

5. **`BacktestEngine`** uses the unified `compute_pnl()` in `_compute_result()`.

**Consequences**:
- Single source of truth for P&L calculation eliminates subtle divergence
- Settlement direction logic (yes/no, threshold/bucket) defined once
- `simulation/settlement.py` is retired — its contents move to `trading.py` and `kalshi/models.py`
- `paper_trader.py` simplified — delegates P&L calculation
- `engine.py` simplified — delegates P&L calculation

---

### DD-030: CLI circular imports — extract DB code from helpers

**Date**: 2025-06-15
**Status**: Decided

**Context**: `cli/helpers.py` contains database-related functions (e.g., `resolve_db_path`, `get_connection`, DB path resolution) alongside CLI utility functions (e.g., `report_cli_error`, formatting helpers). This creates circular import chains: `cli/app.py` → `cli/trade.py` → `paper.py` → `cli/helpers.py` → DB code → more CLI modules. The DB code has no business being in a CLI helper module.

**Decision**: Extract all DB-related functions from `cli/helpers.py` into `db/connections.py` or appropriate `db/` modules. `cli/helpers.py` retains only CLI-specific utilities (formatting, error reporting, console helpers).

**Consequences**:
- Breaks circular import chain
- DB connection logic lives in `db/` where it belongs
- `cli/helpers.py` becomes purely presentation-layer code
- Test mocking becomes simpler (no need to mock CLI code to test DB logic)

---

### DD-031: Module-by-module review findings

**Date**: 2025-06-15
**Status**: Decided (findings documented; individual refactor items tracked separately)

**Context**: Module-by-module review of the current codebase to identify code debt, overlaps, and architectural gaps that need addressing in v2.

> **Phase 1 update:** The module inventory below preserves the 2025 review
> context. The `tokens.py` entry and related action are updated to current
> `TokenStore`/`LocalTokenStore` behavior; legacy `.env`, keyring, and module
> references remain as historical rationale for the future secrets migration.

**1. `simulation/` — Mode-aware redesign needed**

Current state (10 files, ~3,500 lines):
- `engine.py` — BacktestEngine with its own `_Position.compute_pnl()`, `SlippageModel`, `BacktestResult`
- `paper_trader.py` — PaperTrader with `PaperFill`, `PaperPosition`, `PaperPortfolio`, `PaperSlippageModel`, and inline P&L calculation
- `settlement.py` — SettlementVerifier with weather settlement via Open-Meteo and Kalshi settlement
- `performance.py` — Strategy comparison metrics (Sharpe, drawdown, Brier, edge capture, Calmar)
- `profiles.py` — Backtest strategy profiles (CONSERVATIVE/MODERATE/AGGRESSIVE) that map to `TradingProfile`
- `adaptation.py` — Bayesian adaptation engine (Beta-Binomial, Dirichlet-Multinomial, Normal-Normal, Gamma-Exponential)
- `adapter_state.py` — State persistence for adaptation engine
- `data_loader.py` — Historical data loading for backtests
- `strategies/` — Backtest strategy implementations

Issues:
- P&L direction logic is duplicated in `engine.py`, `paper_trader.py`, and `settlement.py` (DD-029 addresses this)
- `TradingProfile` in `profiles/models.py` has `mode: Literal["paper", "live"]` — needs "backtesting" mode added for v2
- `simulation/profiles.py` duplicates `TradingProfile` creation logic with `to_trading_profile()` — this should be unified with the v2 profile system
- `PaperSlippageModel` and `SlippageModel` are two separate implementations — should be unified
- Settlement has three separate implementations (paper, weather, Kalshi) — DD-029 consolidates
- Backtesting mode (DD-019) requires `simulation/` to support time-lapse behavioral simulation, not just statistical replay
- The adaptation engine is sophisticated but currently disconnected from the self-improvement framework (DD-018) — it should be wired into the agent-debate cycle

Actions:
- P&L consolidation → DD-029
- Add "backtesting" mode to `TradingProfile` mode enum
- Unify `PaperSlippageModel` and `SlippageModel`
- Wire adaptation engine into self-improvement Layer 2 pipeline
- Retire `simulation/profiles.py` preset strategy system — v2 uses per-category agent profiles, not static presets

**2. `profiles/` — Auth overhaul required, isolation is solid**

Current state (12 files, ~2,334 lines):
- `models.py` — `TradingProfile` with risk parameters and category filters
- `auth.py` — Profile-auth using keyring + env (to be replaced by Infisical, DD-037)
- `tokens.py` — `TokenStore` interface plus `LocalTokenStore` generation, resolution, listing, rotation, and atomic `tokens.json` persistence; no Fernet encryption
- `isolation.py` — Per-profile DB/ChromaDB/audit path isolation
- `injection.py` — Workspace file injection (fenced merge strategies)
- `injection_strategies.py` — Merge strategy definitions (FENCED_MERGE, INIT_IF_MISSING, ASK_THEN_MERGE)
- `registry.py` — Profile CRUD (create, list, get, delete)
- `discovery.py` — Profile discovery from OpenClaw config
- `config.py` — Credential resolution with profile-aware fallback chains
- `runtime.py` — Current profile resolution (env var, .env file, CLI flag)
- `sysadmin.py` — SysAdmin profile creation helper
- `openclaw_config.py` — OpenClaw configuration reader/writer

Issues:
- Legacy `auth.py` credential handling remains scheduled for DD-037; `TokenStore` stays as the abstraction while Phase 1.5 may replace only its local backend with Infisical
- `config.py` has historical profile-aware credential resolution (keyring → env → .env) that needs rewriting for the future Infisical-backed secrets flow
- `TradingProfile.mode` is `Literal["paper", "live"]` — needs "backtesting" added
- `injection_strategies.py` uses "ASK_THEN_MERGE" strategy which is incompatible with v2's prebuilt agent design (DD-020 says agents are no longer customizable)
- `discovery.py` resolves agents from `openclaw.json` — needs updating for v2 deploy flow where agents are created by `traderbot deploy`
- `sysadmin.py` is a thin helper — needs expansion for v2 SysAdmin lifecycle management

Actions:
- Replace legacy `auth.py` credential handling with the future secrets package and add an Infisical-backed `TokenStore` implementation (DD-037)
- Add "backtesting" to `TradingProfile.mode`
- Remove ASK_THEN_MERGE strategy (agents are prebuilt, no user prompting)
- Update `discovery.py` for v2 deploy-created agents
- Expand `sysadmin.py` for v2 SysAdmin lifecycle

**3. `kalshi/` — WebSocket-first redesign needed**

Current state (19 files, ~3,960 lines):
- `client.py` — REST API client with auth
- `websocket.py` — WebSocket client (subscribe, unsubscribe, receive)
- `ws_daemon.py` — Persistent daemon that caches all market data to JSON file
- `ws_cache.py` — Cache data models for WebSocket data
- `cache.py` — Market data cache (REST-backed)
- `provider.py` — MarketDataProvider combining REST + cache
- `markets.py` — Market discovery and filtering (617 lines)
- `models.py` — Pydantic models for markets, trades, positions, orders
- `trading.py` — Order placement and management
- `portfolio.py` — Portfolio queries
- `history.py` — Historical market data service
- `signing.py` — RSA-PSS request signing
- `pinning.py` — TLS certificate pinning
- `rate_limit.py` — Rate limiter
- `events.py` — Event queries
- `exchange.py` — Exchange info
- `_normalize.py` — Response normalization helpers
- `config.py` — Kalshi configuration

Issues:
- `ws_daemon.py` is a standalone script that writes to a JSON cache file — under v2 (always-on service, DD-016), this should be an integrated service component, not a separate daemon
- `cache.py` and `ws_cache.py` overlap — `cache.py` is REST-backed market data cache, `ws_cache.py` is WebSocket cache models. Under v2, WebSocket cache should be the primary source (DD-016), with REST only for fallback and historical data
- No candlestick API implementation exists yet — needed for backtesting (DD-019) and historical data. The Kalshi API does have `Get Event Candlesticks` endpoint
- `history.py` is minimal (144 lines) — needs expansion for backtesting historical data needs
- `trading.py` (151 lines) handles live order placement — under MCP architecture, agents don't call this directly; the MCP tool calls it on their behalf
- P&L settlement logic should move here from `simulation/settlement.py` (DD-029)

Actions:
- Integrate `ws_daemon.py` into the always-on TraderBot service
- Unify `cache.py` and `ws_cache.py` — WebSocket cache is primary, REST is fallback
- Implement Kalshi candlestick API client for historical data
- Expand `history.py` for backtesting data requirements
- Add `kalshi/settlement.py` for Kalshi-specific settlement logic (DD-029)
- Wrap `trading.py` as MCP tool endpoint

**4. `analysis/` — Solid but needs expansion for v2**

Current state (6 files, ~1,041 lines):
- `portfolio.py` — P&L analytics, Sharpe ratio, drawdown, calibration curve, edge realization
- `odds.py` — Implied probability from orderbook
- `indicators.py` — Market indicators
- `signals.py` — Trading signal aggregation
- `registry.py` — Signal registry pattern
- `__init__.py` — Re-exports `evaluate_trade`

Issues:
- `portfolio.py` P&L calculation overlaps with `simulation/performance.py` and `simulation/paper_trader.py` — consolidated into unified `trading.py` (DD-029)
- Signal registry pattern (`analysis/registry.py`) is well-structured but currently only has weather signals — needs expansion for all 9 categories
- `indicators.py` and `signals.py` are thin wrappers — need substantive expansion for v2 statistical analysis engine
- No statistical analysis engine exists yet — v2 requires this for the self-improvement pipeline (DD-018)

Actions:
- Consolidate P&L calculation into `trading.py` (DD-029)
- Expand signal registry for all categories
- Build statistical analysis engine for self-improvement pipeline (deferred to weather signal engine discussion)

**5. `risk/` — Solid, minor updates needed**

Current state (6 files, ~700 lines):
- `limits.py` — Hard limits (immutable by design per AGENTS.md)
- `circuit_breaker.py` — Trading halt on drawdown/loss thresholds
- `sizing.py` — Position sizing calculation
- `agent_limits.py` — Per-agent risk limits
- `audit.py` — Trade audit logging
- `__init__.py` — Re-exports `evaluate_trade`

Issues:
- `risk/` is well-structured and respects the "risk module is immutable" constraint
- `circuit_breaker.py` stores state in JSON file (`cb_backtest.json`) — under v2 always-on service, this should use the per-agent profile DB
- `agent_limits.py` is thin (107 lines) — needs expansion for per-category risk profiles
- `sizing.py` is very thin (46 lines) — should be expanded with v2 position sizing strategies

Actions:
- Update circuit breaker to use per-agent profile DB for state
- Expand `agent_limits.py` for per-category risk parameters
- Expand `sizing.py` with v2 position sizing logic

**6. `cli/` — Thin MCP wrappers after v2**

Current state (13 files):
- `__init__.py`, `helpers.py`, `admin.py`, `auth.py`, `cron.py`, `data.py`, `market.py`, `news.py`, `profile.py`, `sandbox.py`, `setup.py`, `trade.py`, `ws.py`

Issues:
- `helpers.py` contains DB code (circular import issue, DD-030)
- `cli/news.py` and `cli/data.py` overlap (DD-028)
- `cli/trade.py` and `cli/market.py` contain business logic that should move to service layer
- Under v2 MCP architecture, CLI commands become thin wrappers around MCP tool calls
- `cli/auth.py` uses keyring — replaced by 1Password (DD-026)
- `cli/sandbox.py` manages Docker — integrated into deploy flow (DD-003)
- `cli/cron.py` manages cron jobs — replaced by SysAdmin-managed heartbeat (DD-023)
- `cli/setup.py` is the existing setup wizard — replaced by `traderbot deploy` (DD-005)
- `cli/ws.py` manages the WebSocket daemon — integrated into always-on service (DD-016)

Actions:
- Extract DB code from `helpers.py` (DD-030)
- Merge `cli/news.py` and `cli/data.py` (DD-028)
- Convert business logic commands to thin MCP wrappers
- Replace `cli/auth.py` with 1Password integration
- Replace `cli/setup.py` with deploy flow
- Remove `cli/cron.py`, `cli/sandbox.py`, `cli/ws.py` (absorbed by service/deploy)

**7. `experiment/` — Needs v2 alignment**

Current state (19 files):
- `harness.py` — Experiment execution harness
- `results.py` — Result collection and comparison
- `registry.py` — Experiment registry
- `shared.py` — Shared utilities (MarketData, etc.)
- `populate.py` — DB population for experiments
- `cli.py` — CLI entry point
- `treatments/` — Treatment implementations (control, calibration_bundle)
- `methodologies/` — Methodology definitions
- `tests/` — Experiment tests

Issues:
- The experiment framework is well-structured but currently focused on A/B testing of strategy profiles
- Under v2, this aligns with self-improvement Layer 2 (DD-018) — the test-lab environment
- `experiment/shared.py` defines `MarketData` used by signal engines — this is the right abstraction but needs expansion for all categories
- Needs to be connected to the agent-debate cycle (DD-018) for Round 4 (experiment design)
- Currently only has weather-related treatments — needs expansion

Actions:
- Align experiment framework with self-improvement Layer 2 (DD-018)
- Connect to agent-debate cycle for Round 4 experiment design
- Expand beyond weather to all categories
- The `test-lab/` concept from agent workspaces becomes the experiment execution environment

**8. `db/` — Needs per-mode isolation**

Current state (9 files):
- `__init__.py` — Connection management
- `positions.py` — Position tracking
- `decisions.py` — Decision logging
- `forecast_bias.py` — Weather forecast bias tracking
- `vectors.py` — ChromaDB vector store
- `reconciliation.py` — Position reconciliation
- `experiment_schema.py` — Experiment DB schema
- `sync.py` — DB sync utilities
- `learnings.py` — Agent learnings tracking

Issues:
- `positions.py` has a single `positions` table — under v2, positions must be per-agent per-mode (backtesting/paper/live)
- `decisions.py` similarly needs per-agent per-mode isolation
- `forecast_bias.py` is weather-specific — each category needs equivalent bias tracking
- `vectors.py` manages ChromaDB collections — already has category filtering but needs audit (pending item)
- `reconciliation.py` is for paper-vs-live reconciliation — solid for v2
- No per-mode DB naming convention exists yet
- Under v2 (DD-019/021), each agent gets 3 databases: `backtesting-{name}/db/`, `paper-{name}/db/`, `live-{name}/db/`

Actions:
- Implement per-agent per-mode DB isolation (backtesting/paper/live)
- Create bias tracking tables per category (not just weather)
- ChromaDB metadata audit (existing pending item)
- Remove DB code from `cli/helpers.py` (DD-030)

**9. Kalshi WebSocket — primary data source for real-time data (DD-016 amendment)**

**Decision**: Under v2, the Kalshi WebSocket connection is the primary source for all real-time Kalshi data. REST API is only for:
- Historical data queries (backtesting, settlement verification)
- Fallback when WebSocket connection is lost
- One-time setup queries (market discovery, event listing)

The `ws_daemon.py` pattern of a standalone daemon writing to a JSON cache file is replaced by an integrated WebSocket service within the always-on TraderBot process that maintains an in-memory cache with optional persistence.

**Consequences**:
- `ws_daemon.py` is retired as a standalone CLI command
- WebSocket connection is managed by the TraderBot service process
- `ws_cache.py` models remain as the in-memory cache structure
- REST `cache.py` is downgraded to fallback-only
- `kalshi/history.py` gains candlestick API and expanded historical data queries for backtesting


---

### DD-032: Database restructuring for v2 multi-agent, multi-mode architecture

**Date**: 2025-06-15
**Status**: Decided

**Context**: The current database layer has several structural problems that conflict with v2 requirements:
1. No per-mode isolation — all trading modes (backtesting, paper, live) share a single DB per profile
2. No "backtesting" mode in `TradingProfile.mode` — only "paper" and "live" exist
3. `decisions` table has no `category` column — SysAdmin can't query across agents
4. `forecast_bias` is weather-specific — other categories need their own bias tracking
5. ChromaDB collections are globally shared — no category metadata on `decisions`, `market_patterns`, `market_conditions`
6. `learnings` table not in `init_schema()` — may not exist in all DB paths
7. `paper_positions` table (in `paper_trader.py`) duplicates `positions` table structure
8. No historical forecast snapshot storage — backtesting needs "forecast as of day X-4 for day X"
9. `experiment_schema` tables are separate from standard schema

**Decision**:

**1. Per-agent, per-mode database isolation**

Each agent gets 3 separate database directories, one per trading mode:

```
~/.traderbot/
├── backtesting-{agent}/
│   ├── db/
│   │   ├── decisions.db      # Trade decisions + positions + settlements
│   │   ├── bias.db           # Category-specific forecast accuracy
│   │   └── learnings.db      # Agent learnings
│   ├── chromadb/             # Vector store (category-filtered)
│   └── audit/                # Audit logs
├── paper-{agent}/
│   ├── db/
│   │   └── decisions.db
│   ├── chromadb/
│   └── audit/
└── live-{agent}/
    ├── db/
    │   └── decisions.db
    ├── chromadb/
    └── audit/
```

SysAdmin gets read access to all agent databases across all modes. This is enforced by the MCP server (DD-015), not by database-level permissions.

**2. Unified `decisions.db` schema**

Each `decisions.db` contains:

```sql
-- Positions (merged from db/positions.py and paper_trader.py's paper_positions)
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT UNIQUE NOT NULL,
    side TEXT NOT NULL DEFAULT 'yes',
    quantity INTEGER NOT NULL DEFAULT 0,
    avg_price_cents INTEGER NOT NULL DEFAULT 0,
    settlement_result INTEGER,  -- bool or NULL for open
    pnl_cents INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open',  -- open, settled, closed
    mode TEXT NOT NULL DEFAULT 'paper',   -- backtesting, paper, live
    category TEXT NOT NULL,                -- weather, economics, etc.
    agent TEXT NOT NULL,                   -- agent name
    updated_at TEXT NOT NULL
);

-- Decisions (from db/decisions.py, with category column added)
CREATE TABLE decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    ticker TEXT NOT NULL,
    direction TEXT NOT NULL,    -- yes, no, neutral
    quantity INTEGER NOT NULL,
    price INTEGER NOT NULL,     -- cents
    signal_strength REAL NOT NULL,
    confidence REAL NOT NULL,
    edge_estimate REAL NOT NULL,
    risk_checks TEXT NOT NULL,   -- JSON
    outcome TEXT NOT NULL,       -- executed, rejected, held
    rejection_reason TEXT,
    actual_result INTEGER,
    mode TEXT NOT NULL,          -- backtesting, paper, live
    category TEXT NOT NULL,
    agent TEXT NOT NULL
);
```

**3. Category-specific bias tables**

Instead of a single weather-specific `forecast_bias` table, create a generalized `bias_tracking` table:

```sql
CREATE TABLE bias_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,       -- weather, economics, crypto, etc.
    source TEXT NOT NULL,         -- nws, gfs, ecmwf, fred, etc.
    metric TEXT NOT NULL,         -- high_temp, gdp, btc_price, etc.
    predicted_value REAL NOT NULL,
    actual_value REAL,
    predicted_at TEXT NOT NULL,   -- when the prediction was made
    actual_at TEXT,               -- when the actual value was observed
    lead_time_hours INTEGER,      -- how far in advance the prediction was made
    error REAL,                   -- actual - predicted
    created_at TEXT NOT NULL
);
```

This replaces `forecast_bias` and works for all categories:
- Weather: source=nws, metric=high_temp, predicted_value=72, actual_value=68
- Economics: source=fred, metric=gdp_growth, predicted_value=2.1, actual_value=1.8
- Crypto: source=coingecko, metric=btc_price, predicted_value=65000, actual_value=62000

**4. Forecast snapshot storage for backtesting**

New table for storing time-series forecast snapshots (what was the forecast on day X-4 for day X):

```sql
CREATE TABLE forecast_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    category TEXT NOT NULL,
    source TEXT NOT NULL,
    metric TEXT NOT NULL,
    predicted_value REAL NOT NULL,
    predicted_for_date TEXT NOT NULL,  -- the date being forecast
    snapshot_date TEXT NOT NULL,       -- when this forecast was made
    lead_time_days INTEGER NOT NULL,   -- days between snapshot and target date
    confidence REAL,
    model_consensus_score REAL,
    metadata TEXT,                      -- JSON for source-specific data
    created_at TEXT NOT NULL
);
```

This enables backtesting (DD-019) to query "what was the forecast for June 15 as of June 11" — critical for time-lapse simulation.

**5. ChromaDB per-agent isolation**

Under v2, ChromaDB is shared (DD-009 discussion noted that duplicating 6 months of news per agent is wasteful), but access is controlled by the MCP server:

- **Shared collections** (written by TraderBot data pipeline, read by all agents via MCP):
  - `news` — with `category` metadata filter
  - `data_points` — with `category` metadata filter
  - `market_conditions` — with `category` metadata filter
  - `market_patterns` — with `category` metadata filter

- **Per-agent collections** (written by and read by single agent):
  - `{agent}_decisions` — agent-specific decision embeddings
  - `{agent}_learnings` — agent-specific learnings
  - `news_signals` — processed signals (category-filtered)

The MCP server (DD-015) enforces that category agents only query shared collections with `where={"category": "<their_category>"}` and only access their own per-agent collections.

**6. `paper_positions` merged into `positions`**

The `paper_positions` table in `paper_trader.py` is merged into the unified `positions` table with a `mode` column. This eliminates duplication (DD-029) and ensures all position data lives in one schema.

**7. `init_schema()` includes all tables**

`db/__init__.py::init_schema()` must create all standard tables: `positions`, `decisions`, `bias_tracking`, `forecast_snapshots`, and `learnings`. No more separate initialization.

**8. Learnings table gains category column**

```sql
CREATE TABLE learnings (
    ...existing columns...,
    category TEXT NOT NULL DEFAULT 'general',
    agent TEXT NOT NULL DEFAULT 'unknown'
);
```

**Consequences**:
- Each agent gets 3 DB directories (backtesting, paper, live) with full isolation
- SysAdmin reads across agents via MCP — no direct DB access
- Category-specific bias tracking works for all 9 categories
- Forecast snapshots enable proper backtesting with "forecast as of time T"
- ChromaDB shared collections use category metadata filtering for access control
- `paper_positions` table eliminated (merged into `positions` with mode column)
- `forecast_bias` table replaced by generalized `bias_tracking`
- Migration path needed: existing `paper-{name}/db/decisions.db` databases get `mode` and `category` columns added

**9. Additional DB efficiency and alignment issues found**

**a) No database indexes**

None of the primary SQLite tables (`positions`, `decisions`, `forecast_bias`, `learnings`) have indexes beyond the primary key. The `decisions` table is routinely queried by `ticker` and `timestamp` — these need indexes. The `positions` table is queried by `ticker` (unique, so covered) and `settlement_result`. Under v2, with per-agent per-mode databases, each DB will be smaller, but indexes are still essential for:

```sql
CREATE INDEX idx_decisions_ticker ON decisions(ticker);
CREATE INDEX idx_decisions_timestamp ON decisions(timestamp);
CREATE INDEX idx_decisions_ticker_timestamp ON decisions(ticker, timestamp);
CREATE INDEX idx_decisions_category ON decisions(category);
CREATE INDEX idx_decisions_mode ON decisions(mode);
CREATE INDEX idx_positions_ticker ON positions(ticker);
CREATE INDEX idx_positions_status ON positions(status);
CREATE INDEX idx_bias_tracking_category_source ON bias_tracking(category, source);
CREATE INDEX idx_bias_tracking_metric ON bias_tracking(category, metric, predicted_for_date);
CREATE INDEX idx_forecast_snapshots_lookup ON forecast_snapshots(ticker, predicted_for_date, snapshot_date);
```

The `DataLoader` in `simulation/data_loader.py` correctly creates indexes on its cache tables (`idx_cached_markets_dates`, `idx_cached_trades_ticker`), but the main operational tables don't have them.

**b) Scattered SQLite connections with no connection pooling**

`get_connection()` in `db/__init__.py` creates a new SQLite connection for every operation. Under v2's always-on service, this means:
- Every MCP tool call opens and closes a SQLite connection
- No WAL mode or connection pooling for concurrent access
- Paper trading balance computation opens a connection per position iteration

Under v2, the MCP server will be handling concurrent agent requests. SQLite needs a single-writer connection pool or an async wrapper to avoid "database is locked" errors. Options:
- Use `aiosqlite` for async access from the MCP server
- Or use a dedicated writer thread with a queue (simpler, avoids async dependency)

**c) `paper_positions` table duplicates `positions` table schema**

`simulation/paper_trader.py` creates its own `paper_positions` table with nearly identical columns to `db/positions.py`:
- `positions`: id, ticker (unique), side, quantity, avg_price, settlement_result, pnl_cents, updated_at
- `paper_positions`: ticker (unique), side, avg_price_cents, quantity, status, updated_at

These should be unified into one table with a `mode` column (DD-029, DD-032). The `paper_trader.py` module currently creates and manages its own table, bypassing the `db/` layer entirely.

**d) `paper.py` computes balance directly from SQL**

`paper.py` has `compute_paper_balance()` which manually iterates positions and computes `remaining = initial - total_cost + total_payout`. This logic should be in the `db/` layer or a `trading.py` module — not in a standalone module that directly imports `list_all()` and iterates. Under v2, this calculation needs to be profile-aware and mode-aware.

**e) `settlement_cache.db` is per-profile but separate from `decisions.db`**

`kalshi/cache.py` creates a `settlement_cache.db` in the profile's base directory alongside `decisions.db`. Under v2, settlement data should be in the main `decisions.db` — there's no reason for a separate database file for settlement results when the `positions` table already has `settlement_result` and `pnl_cents` columns.

**f) JSON file caches should migrate to the always-on service's data pipeline**

Multiple JSON file caches exist for ephemeral data:
- `event_category_cache.json` (WebSocket daemon market data) — becomes in-memory under v2 always-on service
- `news_cache/` (news cache directory per profile) — becomes the data pipeline's storage
- `.update_check_cache.json` (update check) — stays as-is
- `circuit_breaker_state.json` (risk state) — should move to per-agent DB
- NWS forecast cache (JSON file in `data/weather/nws_client.py`) — should move to SQLite or in-memory under v2

Under v2, the always-on service manages an in-memory WebSocket cache with optional persistence. The NWS cache should be in the data pipeline (not a JSON file). News cache moves to ChromaDB.

**g) ChromaDB `market_patterns` and `market_conditions` collections are never written to**

These two collections are defined in `DEFAULT_COLLECTIONS` in `db/vectors.py` but no code in the current codebase writes to them. They appear to be aspirational placeholders. Under v2, they should either be:
- Written to by the data pipeline (if we plan to store market pattern embeddings)
- Removed from `DEFAULT_COLLECTIONS` until they're actually needed

The `news_signals` collection IS written to by `news/ingest.py` and read by `cli/news.py`.

**h) `experiment_schema.py` creates separate tables in separate databases**

The experiment framework creates `markets`, `forecast_snapshots`, `market_prices`, `settlement_actuals`, and `agent_decisions` tables. These are populated by `experiment/populate.py` and used during backtesting. Under v2, `forecast_snapshots` becomes a first-class table in the main schema (DD-032), and `agent_decisions` should align with the `decisions` table schema (add `mode` and `category` columns).

**i) `DataLoader` caches should use the always-on service instead of separate SQLite**

`simulation/data_loader.py` creates `cached_markets` and `cached_trades` tables for backtesting. Under v2, this data should come from the always-on data pipeline's database, not a separate backtest cache. The data pipeline proactively collects and stores market data — the backtest engine queries it, not the Kalshi API directly.

**j) `learnings` table not in `init_schema()`**

The `learnings` table (from `db/learnings.py`) is not created by `db/__init__.py::init_schema()`. It's only created on-demand when `learning.py` calls `init_table()`. This means if `init_schema()` is called on a fresh database, the `learnings` table won't exist until `learning.py` is first used. Under v2, `init_schema()` should create all standard tables.

**k) `forecast_bias` is weather-specific and should be generalized**

As documented in DD-032 section 3, the current `forecast_bias` table has weather-specific columns (`city`, `model`, `forecast_high_f`, `actual_high_f`). This needs to become a generalized `bias_tracking` table that works for all categories.


---

**10. Additional database efficiency and design improvements**

**a) No database migration system**

Schema changes are currently applied via ad-hoc `_migrate_*()` and `_ensure_column()` functions scattered across modules:
- `positions.py` — `_ensure_column()` for `pnl_cents` and `side`
- `paper_trader.py` — `_migrate_add_status_column()` for `status`
- `learnings.py` — `_migrate_feature_request_columns()` for `pattern_key`, `recurrence_count`, `justification`, `impact`, `priority`

These are not versioned, not tracked, and not reversible. Under v2, we need a proper migration system that:
- Tracks schema version in a `schema_version` table
- Applies migrations in order and skips already-applied ones
- Supports rollback for development
- Is called by `init_schema()` as part of first-time setup

**b) Circuit breaker state in JSON file instead of per-agent DB**

`risk/circuit_breaker.py` stores state in `circuit_breaker_state.json` with HMAC integrity verification. Under v2:
- Circuit breaker state should be in the per-agent per-mode database (a paper agent's risk state differs from a live agent's)
- The `.breaker_secret` file adds another credential-like artifact to manage
- State should be queryable via MCP for SysAdmin oversight

**c) ChromaDB embedding dimension hardcoded**

`db/vectors.py` hardcodes `EMBEDDING_DIMENSION = 1024` for `voyage-4-large`. If the embedding model changes (e.g., to a future `voyage-5` with a different dimension), all existing embeddings become incompatible with no migration path. Under v2:
- The embedding dimension should be stored as ChromaDB collection metadata
- A migration utility should support re-embedding when the model changes
- The `VoyageClient` model name should be configurable, not hardcoded

**d) No data retention or cleanup policy**

Under v2's always-on data collection (DD-016, DD-027), databases will grow indefinitely. There is no mechanism for:
- Pruning old news articles beyond a retention window
- Archiving settled positions older than N months
- Cleaning up stale ChromaDB vectors
- Removing expired forecast snapshots

Need a retention policy per data type:
- News articles: retain 6 months (matching backfill window), archive older
- Positions: retain all for active modes, archive after settlement + 90 days
- Decisions: retain all (audit trail)
- Forecast snapshots: retain 6 months for backtesting, archive older
- ChromaDB vectors: retain per collection policy, archive stale embeddings

**e) No SQLite PRAGMA optimization**

The only PRAGMA set is `journal_mode=WAL`. Under v2's concurrent access from the MCP server, we need:
```sql
PRAGMA journal_mode=WAL;          -- Already set
PRAGMA synchronous=NORMAL;        -- Faster writes, safe with WAL
PRAGMA busy_timeout=5000;          -- Wait up to 5s for locks
PRAGMA cache_size=-64000;          -- 64MB cache
PRAGMA temp_store=MEMORY;          -- In-memory temp tables
PRAGMA mmap_size=268435456;        -- 256MB memory-mapped I/O
PRAGMA foreign_keys=ON;            -- Already set
```

**f) No foreign key constraints between tables**

The `decisions` table has no foreign key to `positions`. Under v2, with per-agent per-mode isolation this is less critical (cross-agent contamination is prevented by directory structure), but referential integrity within a single agent's DB would help catch data corruption:
```sql
-- Example FK for v2 schema
FOREIGN KEY (ticker) REFERENCES positions(ticker) ON DELETE CASCADE
```

**g) Settlement cache uses separate SQLite database**

`kalshi/cache.py` creates `settlement_cache.db` as a standalone SQLite file per profile. Under v2, this should be a table in the main `decisions.db`:
```sql
CREATE TABLE settlement_cache (
    ticker TEXT PRIMARY KEY,
    outcome INTEGER NOT NULL,
    settled_at TEXT NOT NULL
);
```
This eliminates the separate DB file and lets settlement queries join with positions data.

**h) Paper trading balance computation needs MCP endpoint**

`paper.py` computes balance by iterating all positions from the DB. Under v2, the MCP server needs a fast balance query endpoint that doesn't require loading all positions. Options:
- Maintain a running `portfolio_summary` table that's updated on each trade
- Or a materialized view / computed column approach
- The MCP tool `get_balance` should return in <10ms even with thousands of positions

**i) `paper.py` should be retired**

The `paper.py` module is a thin wrapper around direct DB queries. Under v2, paper balance computation moves to `trading.py` (DD-029), and the MCP server provides the endpoint. `paper.py` can be retired.

**j) Heartbeat integrity check is the only DB health check**

`heartbeat.py` runs `PRAGMA integrity_check` as part of its health cycle. Under v2, the always-on service should:
- Run `PRAGMA integrity_check` on startup
- Run `PRAGMA wal_checkpoint(TRUNCATE)` periodically to keep WAL size bounded
- Monitor DB file sizes and alert when they exceed thresholds
- Run VACUUM on agent databases when they're promoted from backtesting to paper (the backtesting DB may have a lot of transient data)


---

### DD-033: GRIB2 processing pipeline for historical weather forecast data

**Date**: 2025-06-15
**Status**: Decided

**Context**: Realistic weather backtesting (DD-019) requires "forecast as of day X-4 for day X" data — multi-day lead time forecasts that show what the agent would have actually seen at each point in time. Without this, backtesting uses same-day forecasts (day-0), which inflates accuracy because same-day forecasts are significantly more accurate than 4-day-ahead forecasts.

Open-Meteo's Historical Forecast API provides day-0 forecasts only. NOAA GFS and ECMWF store full lead-time model output in GRIB2 format on AWS S3, freely available.

**Decision**: Build a GRIB2 processing pipeline as part of the unified data module (DD-028), in two phases:

**Phase 1 — Tier 1 data (ship with initial v2)**

Use Open-Meteo Archive API (actual observations) + Historical Forecast API (day-0 model consensus) + Kalshi historical market data. This is sufficient to:
- Validate MCP architecture, deploy flow, and agent behavior end-to-end
- Start backtesting with approximate conditions
- Begin the self-improvement cycle (DD-018)
- Populate `forecast_snapshots` and `bias_tracking` tables with day-0 data

Known limitation: backtesting results for weather agents will be slightly inflated because the agent always sees same-day forecast accuracy, not the degraded accuracy of multi-day lead times. This is acceptable for initial development.

**Phase 2 — Tier 2 data (build after core v2 is stable)**

Implement GRIB2 processing for true multi-day lead time forecasts:

1. **Provider modules** — `data/providers/gfs.py` and `data/providers/ecmwf.py` under the unified data pipeline (DD-028)
2. **Dependency** — `cfgrib` (Python GRIB2 reader, uses eccodes) as optional dependency via `pip install traderbot[weather-backtest]`. Falls back to `wgrib2` CLI if available.
3. **Processing flow**:
   - Download only the grid points for our 15 Kalshi cities from NOAA GFS S3 bucket (`noaa-gfs-bdp-pds.s3.amazonaws.com`) and ECMWF S3 bucket
   - GFS path: `gfs.YYYYMMDD/HH/atmos/gfs.tHHz.pgrb2.0p25.fNNN` (forecast hours f000-f384, 4 runs/day)
   - ECMWF path: `YYYYMMDD/HHz/aifs/0p25/oper/YYYYMMDDHH0000-{N}h-oper-fc.grib2` (0h-144h+, 2 runs/day)
   - Extract temperature (2m max/min), precipitation, wind speed, wind gusts at our 15 city coordinates
   - Store in `forecast_snapshots` table with `(ticker, category, source, metric, predicted_value, predicted_for_date, snapshot_date, lead_time_days, confidence, model_consensus_score, metadata)`
4. **Deploy integration** — During `traderbot deploy`, offer optional 6-month backfill of GFS/ECMWF data (~5-10 GB compressed). Skip by default.
5. **Ongoing collection** — The always-on data pipeline archives GFS runs every 6 hours and ECMWF runs every 12 hours going forward

**Data source summary for weather backtesting**:

| Source | What it provides | Lead time data? | Phase | Access |
|---|---|---|---|---|
| Open-Meteo Archive API | Actual observed temperatures for past dates | N/A (observations, not forecasts) | Phase 1 | Free, no API key |
| Open-Meteo Historical Forecast API | Day-0 model consensus (GFS, ECMWF, GEM) for past dates | No — day-0 only | Phase 1 | Free, no API key |
| Kalshi Historical Candlesticks | OHLC bid/ask + trade prices for settled markets | N/A (market data) | Phase 1 | Requires API key |
| Kalshi Forecast Percentile History | Historical forecast percentiles for events | N/A (market consensus) | Phase 1 | Requires API key |
| NOAA GFS on AWS S3 | Raw GRIB2 model output, full lead times f000-f384 | Yes — "forecast on date X for date X+N" | Phase 2 | Free, public S3 |
| ECMWF on AWS S3 | Raw GRIB2 model output, full lead times 0h-144h+ | Yes — "forecast on date X for date X+N" | Phase 2 | Free, public S3 |

**forecast_snapshots table** (from DD-032):

```sql
CREATE TABLE forecast_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    category TEXT NOT NULL,
    source TEXT NOT NULL,           -- 'nws', 'gfs', 'ecmwf', 'gem', 'open-meteo'
    metric TEXT NOT NULL,           -- 'high_temp', 'low_temp', 'precip_prob', 'wind_speed'
    predicted_value REAL NOT NULL,
    predicted_for_date TEXT NOT NULL,  -- the date being forecast
    snapshot_date TEXT NOT NULL,       -- when this forecast was made
    lead_time_days INTEGER NOT NULL,   -- days between snapshot and target date
    confidence REAL,
    model_consensus_score REAL,
    metadata TEXT,                     -- JSON for source-specific data
    created_at TEXT NOT NULL
);

CREATE INDEX idx_forecast_snapshots_lookup
    ON forecast_snapshots(ticker, predicted_for_date, snapshot_date);
CREATE INDEX idx_forecast_snapshots_source_lead
    ON forecast_snapshots(source, lead_time_days);
CREATE INDEX idx_forecast_snapshots_category
    ON forecast_snapshots(category, predicted_for_date);
```

**Tier 3 — Ongoing archival (start immediately)**

Begin archiving current data for future backtests regardless of Phase 1/2:
- NWS forecast snapshots: every hour
- Open-Meteo model consensus: every 6 hours
- Kalshi orderbook snapshots: via WebSocket (complements historical candlestick API)
- These archives become the ground truth for future backtest cycles

**Consequences**:
- Phase 1 ships without GRIB2 processing — acceptable for initial development
- `forecast_snapshots` table schema already supports both day-0 and multi-day lead time data
- Phase 2 adds `cfgrib` as optional dependency — no impact on core installation
- Estimated storage: ~5-10 GB compressed for 6 months of GFS data at 15 cities
- Phase 2 makes weather backtesting realistic — the agent sees exactly what it would have seen in live trading at each point in time
- The bias tracking system (DD-032 `bias_tracking` table) gains lead-time context: "how accurate was our 4-day-ahead forecast vs our 1-day-ahead forecast?"
- All other categories (economics, crypto, politics, etc.) don't need GRIB2 — their data sources are API-based and historical data is readily available

### DD-034: Dev-Liaison — TraderBot subject matter expert and AutoDev liaison

**Date**: 2026-06-15
**Status**: Decided

**Context**: The Dev-Liaison (formerly "Coding Agent") is the interface between the TraderBot agent team and the AutoDev team (OpenCode + OmO) responsible for all engineering and development of TraderBot, including v2 implementation. DD-018 originally described a "Coding Agent" role as a Watcher in the agent-debate process and a bridge to a Layer 3 autonomous dev team. The role has been clarified and expanded: the Dev-Liaison is NOT a member of an autonomous dev team and does NOT modify TraderBot source code directly. It acts as a liaison between the TraderBot agent team and the AutoDev team — a subject matter expert on TraderBot internals that ships with complete knowledge of how the toolkit is designed and how everything works, and a communication bridge that coordinates work between the two systems.

The original description in DD-018 ("Built on VoyageAI + database infrastructure") was partially correct — VoyageAI embeddings power the knowledge retrieval layer, and a dedicated database collection stores the indexed reference material. The Dev-Liaison's role encompasses: creating test modules, diagnosing bugs, verifying deployments, and now also coordinating with the AutoDev team via webhook communication to ensure TraderBot engineering work is picked up and completed. It does not write production code, does not participate in the autonomous dev team, and does not modify TraderBot source.

**Decision:**

#### 1. Role and Responsibilities

The Dev-Liaison is an OpenClaw agent — managed by the OpenClaw gateway, running in the same infrastructure as all other agents. It is a **liaison** between the TraderBot agent team and the AutoDev team** between the TraderBot agent team and the human dev team. While SysAdmin manages the mechanics of agent orchestration (cron jobs, heartbeats, lifecycle transitions), the Dev-Liaison manages the actual building and developing part of the backend.

**Three core responsibilities:**

1. **Test authoring** — Takes design output from the agent-debate process (DD-018) and creates actual test modules that plug into the test-lab. This means writing Python classes that implement the `TreatmentInterface` ABC, producing new treatment modules for the experiment harness.

2. **Error diagnosis** — Reads agent ERRORS.md, system logs, and state; diagnoses root causes; writes structured GitHub issues with reproduction steps, root cause analysis, and proposed solution. Uses the OpenClaw built-in GitHub skill for issue creation.

3. **Update verification** — When deployments land, runs validation and provides feedback. The specifics vary by update type (experiment harness validation, regression testing, integration checks), but the Dev-Liaison is responsible for confirming that updates work as intended and surfacing any regressions.

**Explicit non-responsibilities:**

- Does NOT modify TraderBot source code directly
- Does NOT participate in the Layer 3 autonomous dev team
- Does NOT make trading decisions or access trading tools
- Does NOT modify other agents' workspace files
- Does NOT approve its own knowledge base updates without SysAdmin review

#### 2. Division of Labor with SysAdmin

| Domain | SysAdmin | Dev-Liaison |
|---|---|---|
| Agent orchestration | Cron jobs, heartbeats, lifecycle transitions | — |
| Fleet monitoring | Health checks, circuit breaker oversight | — |
| Experiment deployment | Runs backtests, deploys profile changes | Designs and writes the test modules |
| Error escalation | Surfaces anomalies to human | Diagnoses root causes, writes GitHub issues |
| Codebase knowledge | Uses TraderBot CLI as a toolkit user | Deep understanding of internals, architecture, and contracts |
| Update validation | Triggers validation cycle | Executes validation, reports findings |
| Improvement cycle (DD-018) | Orchestrator role | Watcher role (feasibility perspective) |

#### 3. Agent Configuration

The Dev-Liaison runs as an OpenClaw agent with the following configuration:

```
Agent ID: dev-liaison
Sandbox mode: off (runs on host, like SysAdmin — needs access to source and logs)
Skills: github, traderbot-reference (custom skill for knowledge retrieval)
Heartbeat: 30m, isolated session, light context
```

The Dev-Liaison runs unsandboxed (like SysAdmin) because it needs access to the TraderBot source tree for test module authoring, system logs for error diagnosis, and the experiment database for validation. It does NOT need access to trading credentials or the Kalshi API.

**OpenClaw tool allowlist:**

The Dev-Liaison is unsandboxed in this target design, so the sandbox
`bundle-mcp` gate does not apply. Its normal policy uses one explicit
restrictive `allow` list; planned TraderBot tools remain names in the target
policy, not claims that they are currently implemented.

```json5
{
  tools: {
    allow: [
      "read", "write", "exec", "github",
      "traderbot__reference",     // Knowledge retrieval (DD-034 §4)
      "traderbot__experiment",    // Experiment harness tools
      "traderbot__auth_check",    // Profile-token validation and access context
    ],
    deny: [
      "traderbot__trade",         // No trading
      "traderbot__scan",          // No market scanning
      "traderbot__analyze",       // No analysis
    ],
  },
}
```

#### 4. Knowledge Architecture

The Dev-Liaison's knowledge architecture is a four-layer system designed for **complete coverage with zero context waste** — the agent always has the shape of the system in context and retrieves specifics on demand.

**Research basis:** Five categories of dev-liaison agent memory solutions were evaluated and documented in `AutoDev.md`: Markdown Memory Banks, Agent Operational Layers (AgentOps), Team-Ratified Knowledge Bases (Loreguard), Semantic Code Search MCP Servers (codesearch/code-context-v2), and Documentation-as-Context Services (Context7). The architecture below synthesizes the strongest patterns from each category while avoiding their limitations for our specific use case. See `AutoDev.md` for full research details.

**Layer 1: Bootstrap files (always in context, ~5–8K chars)**

Four OpenClaw bootstrap files that give the Dev-Liaison enough shape to know what to search for, without dumping exhaustive detail into context:

- **`IDENTITY.md`** — Role, name, personality. "You are the Dev-Liaison. You are a subject matter expert on TraderBot internals. You create test modules, diagnose errors, and verify updates."
- **`AGENTS.md`** — Operating rules, hard rules, boundaries. Responsibilities, escalation protocol, what NOT to do. Architecture map: module names, their responsibilities, key data models, and the design decisions that shape the system. This is the table of contents, not the book.
- **`TOOLS.md`** — Available commands: `traderbot experiment` CLI, `traderbot auth`, GitHub skill, the `traderbot__reference` MCP tool for knowledge retrieval.
- **`HEARTBEAT.md`** — Periodic task cadence: check for new experiment proposals from SysAdmin, review agent ERRORS.md files, verify recent deployments.

**Layer 2: Purpose-built reference retrieval MCP tool (`traderbot__reference`)**

An MCP tool exposed by the TraderBot MCP server that provides on-demand retrieval of technical specifications. The Dev-Liaison calls this when it needs specifics — "show me the TreatmentInterface contract" or "what does the Kalshi WebSocket subscription model look like?" — and gets back exactly the relevant chunk, not a whole file.

**Retrieval design** (informed by codesearch, code-context-v2, and loreguard patterns):

| Feature | Approach | Source |
|---|---|---|
| Chunking | AST-aware (tree-sitter) for source code, section-aware for docs | codesearch, code-context-v2 |
| Embeddings | `voyage-4-large` (documents), `voyage-4-lite` (queries) — same vector space, asymmetric retrieval | code-context-v2 |
| Vector store | ChromaDB `traderbot_reference` collection (already in codebase) | Existing `VectorStore` |
| Search | Hybrid: vector similarity + BM25 keyword, fused with Reciprocal Rank Fusion | codesearch |
| Reranking | `rerank-2.5` for precision on top candidates | code-context-v2 |
| Retrieval | Metadata first, full content on demand | codesearch, loreguard |
| Scoping | Filter by `scope` parameter: `source`, `docs`, `api`, `decisions`, `all` | loreguard, codesearch |

**MCP tool interface:**

```python
# Search for reference material
traderbot__reference(
    query="TreatmentInterface contract and ValidatedDecision schema",
    scope="source",        # source | docs | api | decisions | all
    max_results=5,
    tokens=2000,            # token budget for response
) → list[ReferenceResult]

# Each result contains:
# - chunk_id: stable identifier for the chunk
# - source: file path or document title
# - module: traderbot module path (e.g., "traderbot.experiment.shared")
# - type: "source" | "doc" | "api_spec" | "decision" | "convention"
# - summary: brief description (always returned)
# - content: full chunk text (returned only when depth="full")
# - line_start / line_end: for source code chunks
# - score: relevance score
# - metadata: version, class_name, function_name, etc.

# Fetch full content for a specific chunk
traderbot__reference_get(
    chunk_id="src/traderbot/experiment/shared.py:TreatmentInterface",
    depth="full",          # summary | full
) → ReferenceResult
```

**What gets indexed:**

| Source | Chunking method | Metadata fields |
|---|---|---|
| `docs/*.md` | Section-aware (by markdown headers) | `{module, type: "doc", version}` |
| `src/traderbot/**/*.py` | AST-aware (tree-sitter: functions, classes, methods) | `{module, class, function, type: "source", version}` |
| `Dep_Docs/*.txt` | Section-aware | `{service, type: "api_spec"}` |
| `v2roadmap.md` | By DD section | `{dd_number, type: "decision"}` |
| `CHANGELOG.md` | By version entry | `{version, type: "changelog"}` |
| `AGENTS.md` (project-level) | By section | `{type: "convention"}` |

**Indexing pipeline:**

1. **On deploy** — `traderbot setup` (or a new `traderbot index` command) walks the sources, parses, chunks, embeds with VoyageAI, and stores in ChromaDB
2. **Incremental** — on `traderbot update`, re-index only changed files (hash comparison)
3. **Version-tagged** — every chunk's metadata includes the VERSION at index time, so queries can be scoped to a specific version

**Why not memory-wiki?** OpenClaw's `memory-wiki` plugin was evaluated as the primary knowledge store. It was rejected for this purpose because:
- Its claim/evidence/provenance model adds ceremony without value for specifications that are either correct or incorrect
- It has no code-level indexing (can't retrieve function signatures, type annotations, or import graphs)
- Its freshness tracking by wall clock doesn't match versioned documentation
- It treats content as prose to be curated, not reference material to be retrieved precisely
- Per-agent workspace scoping means the knowledge isn't shared or version-aware

Memory-wiki may still be used for the Dev-Liaison's accumulated diagnostic knowledge (error patterns, experiment outcomes) where claim/evidence tracking genuinely adds value.

**Layer 3: Context7 for external dependency documentation**

The `mcp__context7` tool (already available in the environment) provides on-demand, version-specific documentation for third-party libraries. This eliminates the need to pre-index Dep_Docs/ for well-known libraries (Pydantic, httpx, typer, ChromaDB, SQLite, etc.).

For TraderBot-specific external APIs that Context7 doesn't cover (Kalshi, OpenClaw, Open-Meteo, FRED, NewsAPI, Voyage AI), Dep_Docs/ content is indexed into the `traderbot_reference` ChromaDB collection (Layer 2).

**Layer 4: OpenClaw memory-wiki for accumulated diagnostic knowledge (optional)**

The Dev-Liaison may use `memory-wiki` for knowledge it accumulates through its work — patterns it discovers, error signatures, experiment results. These are genuine claims with evolving confidence, where the claim/evidence model adds real value:

- "WebSocket disconnection at market close correlates with `market_lifecycle_v2` subscription timing" (evidence: 3 occurrences, resolved in v0.15.42)
- "Treatment modules that skip `validate_response()` produce invalid decisions in 12% of cases" (evidence: experiment run EXP-007)
- "Paper trading P&L diverges from live by 2-3 cents on high-spread markets" (evidence: comparison of 47 trades)

This layer is optional and can be added after the core knowledge architecture (Layers 1–3) is stable.

**Knowledge access summary:**

| Knowledge type | Layer | Storage | Retrieval | Maintenance |
|---|---|---|---|---|
| System architecture overview | 1 | Bootstrap files (AGENTS.md) | Always in context | Updated on deploy |
| Code contracts & signatures | 2 | ChromaDB `traderbot_reference` (source chunks) | `traderbot__reference(scope="source")` | Re-indexed on deploy |
| Architecture docs & design decisions | 2 | ChromaDB `traderbot_reference` (doc chunks) | `traderbot__reference(scope="docs")` | Re-indexed on deploy |
| External API docs (third-party) | 3 | Context7 hosted service | `resolve-library-id` + `get-library-docs` | Automatic, on-demand |
| External API docs (TraderBot-specific) | 2 | ChromaDB `traderbot_reference` (api_spec chunks) | `traderbot__reference(scope="api")` | Re-indexed on deploy |
| Design decision records | 2 | ChromaDB `traderbot_reference` (decision chunks) | `traderbot__reference(scope="decisions")` | Re-indexed on deploy |
| Changelog entries | 2 | ChromaDB `traderbot_reference` (changelog chunks) | `traderbot__reference(scope="all", filter="changelog")` | Re-indexed on deploy |
| Diagnostic patterns | 4 (optional) | OpenClaw memory-wiki | `wiki_search`, `wiki_get` | Agent-maintained |
| Session-level operational notes | — | OpenClaw `memory/YYYY-MM-DD.md` | `memory_search` | Agent-maintained |

#### 5. Test Module Authoring Flow

When SysAdmin prompts the Dev-Liaison to create a test module based on agent-debate output, the flow is:

1. **Receive experiment design** — SysAdmin sends the white paper, hypothesis, and success criteria from the improvement cycle (DD-018 Round 4)
2. **Query reference knowledge** — Call `traderbot__reference` to understand the existing `TreatmentInterface` contract, the `TreatmentContext` data model, and the `ValidatedDecision` schema
3. **Query source code** — Call `traderbot__reference(scope="source")` to understand how existing treatments (ControlTreatment, CalibrationBundleTreatment) are implemented
4. **Author treatment module** — Write a new Python class implementing `TreatmentInterface` with the experiment-specific prompt design and validation logic
5. **Register treatment** — Add the new class to the treatment registry
6. **Report to SysAdmin** — Notify SysAdmin that the test module is ready for backtesting

**Treatment discovery evolution:** The current treatment registry (`treatments/__init__.py` → `TREATMENT_REGISTRY` list) requires editing Python source to register new treatments. The Dev-Liaison should not need to modify core source files. A dynamic discovery path should be implemented: the harness scans a `treatments/` directory for `.py` files and auto-registers any class that subclasses `TreatmentInterface`. This lets the Dev-Liaison drop new treatment files without touching existing code. This is a pre-requisite for the Dev-Liaison's test authoring responsibility and should be implemented before the Dev-Liaison is deployed.

#### 6. Error Diagnosis Flow

When the Dev-Liaison detects or is notified of an error:

1. **Read error context** — Read the originating agent's `.learnings/ERRORS.md` and any relevant logs
2. **Query reference knowledge** — Call `traderbot__reference` to understand the module where the error occurred, its contracts, and dependencies
3. **Trace through source** — Call `traderbot__reference(scope="source")` to examine the actual implementation, following the error path through the code
4. **Diagnose root cause** — Determine whether this is a TraderBot problem (broken function, data quality, infrastructure) or an agent problem (missing instructions, bad automation)
5. **File GitHub issue** — Use the OpenClaw GitHub skill to create a structured issue with:
   - Reproduction steps
   - Root cause analysis (TraderBot vs agent, per DD-018 root cause classification)
   - Proposed solution
   - Relevant labels (bug, infrastructure, enhancement)
   - References to affected design decisions if applicable
6. **Notify SysAdmin** — Surface the issue via session message so SysAdmin can track it

#### 7. Update Verification Flow

When a deployment lands, the Dev-Liaison's verification varies by update type:

- **Experiment harness changes** — Run `traderbot experiment verify` and `traderbot experiment run` against existing treatments to confirm no regressions
- **Data pipeline changes** — Verify data freshness with `traderbot data-points` and `traderbot ws status`
- **CLI changes** — Run treatment modules end-to-end and compare results against prior runs
- **Profile/risk changes** — Verify that profile parameters match the intended configuration

The Dev-Liaison re-indexes `traderbot_reference` after each deploy so its knowledge base stays current.

#### 8. Workspace File Structure

```
~/.openclaw/workspace/dev-liaison/
├── AGENTS.md           # Operating rules, architecture map
├── IDENTITY.md         # Role, name, personality
├── TOOLS.md            # Available commands and MCP tools
├── HEARTBEAT.md        # Periodic task cadence
├── SOUL.md             # Agent identity principles
├── USER.md            # Empty, reserved
├── MEMORY.md          # Long-term curated memory
├── SESSION-STATE.md   # WAL protocol (current tasks, pending diagnoses)
├── memory/
│   └── YYYY-MM-DD.md  # Daily operational notes
└── .learnings/
    ├── ERRORS.md       # Errors encountered during diagnosis
    ├── LEARNINGS.md    # Patterns discovered
    └── FEATURE_REQUESTS.md  # Capability gaps identified
```

The workspace follows the same structure as other TraderBot agent workspaces (SysAdmin, weather), but with content specific to the Dev-Liaison role. The `AGENTS.md` contains the architecture map that gives the Dev-Liaison its always-in-context system shape, and the `TOOLS.md` documents the `traderbot__reference` MCP tool and experiment CLI commands.

#### 9. Implementation Prerequisites

Before the Dev-Liaison can be deployed, the following must be built:

1. **Dynamic treatment discovery** — The experiment harness must support auto-discovering treatment modules from a directory, not just manual registration in `__init__.py`. This is required for the Dev-Liaison to author treatments without modifying core source.

2. **`traderbot__reference` MCP tool** — The reference retrieval tool and its ChromaDB `traderbot_reference` collection must be implemented. This includes:
   - Tree-sitter based AST chunking for Python source code
   - Section-aware chunking for markdown documentation
   - Voyage AI embedding pipeline (`voyage-4-large` for documents, `voyage-4-lite` for queries)
   - Hybrid search (vector + BM25) with Rerank-2.5
   - Scope filtering (source, docs, api, decisions, all)
   - `traderbot index` CLI command for initial and incremental indexing

3. **Dev-Liaison workspace templates** — The four bootstrap files (AGENTS.md, IDENTITY.md, TOOLS.md, HEARTBEAT.md) must be authored with TraderBot-specific content.

4. **OpenClaw agent configuration** — The `dev-liaison` agent entry in `openclaw.json` with the correct tool allowlist and sandbox settings.

5. **Voyage AI query embedding** — `VoyageClient` currently only supports `voyage-4-large` for document embeddings. Query-side embedding with `voyage-4-lite` (same vector space, lower latency) needs to be added for the asymmetric retrieval pattern.

**Consequences:**
- Dev-Liaison is an OpenClaw agent, not a standalone tool — integrates with the same gateway, cron, and heartbeat infrastructure as all other agents
- The `traderbot__reference` MCP tool is shared infrastructure — SysAdmin and future agents can also use it for knowledge retrieval
- VoyageAI embeddings power both the existing news pipeline and the new reference retrieval pipeline — same infrastructure, different collections
- Context7 covers third-party library documentation, eliminating the need to pre-index Dep_Docs/ for well-known libraries
- Memory-wiki is optional for the Dev-Liaison's accumulated knowledge — the core architecture (Layers 1–3) does not depend on it
- Dynamic treatment discovery is a pre-requisite — without it, the Dev-Liaison cannot author test modules without modifying core source code
- The Dev-Liaison does not trade, does not modify source code, and does not approve its own knowledge base updates without SysAdmin review
- DD-018's original description of the Dev-liaison ("Built on VoyageAI + database infrastructure", "Also serves in Layer 3 autonomous dev team") is superseded by this decision — the Dev-Liaison is a liaison, not an autonomous developer
- The pending discussion item "Dev-Liaison build: Architecture for the Dev-Liaison on VoyageAI + database infrastructure" is resolved by this decision

#### 10. AutoDev Webhook Communication

The Dev-Liaison (formerly "Coding Agent") interfaces with the AutoDev team (OpenCode + OmO), which is responsible for all engineering and development of TraderBot going forward, including the implementation of v2. The two systems communicate via a low-latency webhook layer with GitHub as the shared source of truth.

**Communication channels:**

| Channel | Direction | Mechanism | What it carries | Latency |
|---------|-----------|-----------|-----------------|---------|
| Wake signal | Either direction | OpenClaw webhooks / Discord bot | "Hey, check GitHub" | Seconds |
| GitHub | Both directions | Issues, PRs, labels, comments | All state and data | 30 min (heartbeat) |

The wake signal never carries business data — it is just a tap on the shoulder. All detail lives on GitHub. If the wake signal is lost, nothing breaks — the next heartbeat catches everything.

**AutoDev → Dev-Liaison (via OpenClaw webhooks):**

AutoDev sends webhook POST requests to the OpenClaw gateway. The OpenClaw webhook server is configured with mappings that route each webhook path to the `dev-liaison` agent:

- `/hooks/autodev-completed` → Dev-Liaison is notified that work is finished. It verifies on GitHub, then notifies the requesting TraderBot agent.
- `/hooks/autodev-blocked` → Dev-Liaison is notified that AutoDev is stuck. It escalates to the operator immediately.
- `/hooks/autodev-deployed` → Dev-Liaison is notified that a change was deployed. It asks the relevant TraderBot agent to validate health.

**Dev-Liaison → AutoDev (via shared Discord channel):**

When a TraderBot agent files an issue or needs AutoDev to start work, the Dev-Liaison posts a wake signal on a shared Discord channel:

```
🤖 autodev:wake | Issue #42 | high | bug | Weather agent backtest failing on settlement
```

Event types the Dev-Liaison can send: `autodev:wake` (new work), `autodev:cancel` (work no longer needed), `autodev:priority` (critical bug).

**Agent configuration:**

The target AgentEntry below uses only the pinned schema fields `id`, `sandbox`,
and `tools`. Because this role is unsandboxed, no sandbox `bundle-mcp` gate is
required. Workspace/name details remain role documentation rather than fields
in this config object.

```json5
{
  id: "dev-liaison",
  sandbox: { mode: "off" },
  tools: {
    allow: [
      "read", "write", "exec", "github",
      "traderbot__reference",
      "traderbot__experiment",
      "traderbot__auth_check",
      "traderbot__health",
      "sessions_spawn", "sessions_send", "sessions_yield",
      "sessions_list", "sessions_history", "subagents",
    ],
    deny: [
      "traderbot__trade", "traderbot__scan", "traderbot__analyze",
      "traderbot__weather_*", "traderbot__market_edge", "traderbot__market_prices",
    ],
  },
}
```

**OpenClaw webhook configuration (`openclaw.json`):**

> **Conceptual routing pseudocode, not deployable configuration:** The hook
> field names below have not been validated against pinned `d1c96302`. This
> block records event-routing intent only and must not be pasted into
> `openclaw.json` without a separate schema review.

```json5
{
  hooks: {
    enabled: true,
    token: "<AUTODEV_HOOK_TOKEN>",
    path: "/hooks",
    allowedAgentIds: ["dev-liaison"],
    mappings: [
      {
        match: { path: "autodev-completed" },
        action: "agent",
        agentId: "dev-liaison",
        instruction: "AutoDev completed work. Verify on GitHub, then notify the requesting Traderbot agent.",
        deliver: true
      },
      {
        match: { path: "autodev-blocked" },
        action: "agent",
        agentId: "dev-liaison",
        instruction: "AutoDev is blocked and needs human input. Escalate to the operator immediately.",
        deliver: true,
        channel: "telegram",
        to: "traderbot-ops"
      },
      {
        match: { path: "autodev-deployed" },
        action: "agent",
        agentId: "dev-liaison",
        instruction: "AutoDev deployed a change. Ask the relevant Traderbot agent to validate health.",
        deliver: true
      }
    ]
  }
}
```

**Fallback and reliability:** GitHub is always the source of truth. Wake signals are acceleration, not critical path. If any channel fails, the heartbeat eventually catches everything. Both systems buffer locally and retry with exponential backoff on GitHub failures.

**Environment variables:**

```bash
AUTODEV_HOOK_TOKEN=<dedicated-token>        # Not the gateway auth token
AUTODEV_DISCORD_BOT_TOKEN=<bot-token>        # For Dev-Liaison → AutoDev wake signals
AUTODEV_DISCORD_CHANNEL_ID=<channel-id>      # Shared AutoDev/Dev-Liaison channel
GITHUB_TOKEN=<token>                          # Both systems need repo access
GITHUB_REPOSITORY=<owner/repo>                # Shared repo
```



### DD-035: Category-specific analysis toolkits — analysis, not trading signals

**Date**: 2026-06-15
**Status**: Decided

**Context**: The current analysis pipeline has two signal systems:

1. `WeatherSignalEngine` (`data/weather/signals.py`) — Uses a logistic function with hardcoded `sigma=5.0` to convert forecast temperatures to yes/no probabilities. Returns a `TradingSignal` with direction, confidence, and edge.

2. `generate_signal()` (`analysis/signals.py`) — A generic weighted combiner mixing RSI, Bollinger Bands, EMA momentum, and optional news sentiment with hardcoded weights. Returns a `CombinedSignal` with direction and confidence.

3. `AnalysisRegistry` (`analysis/registry.py`) — Has a `CategoryAnalyzer` protocol but only implements `GenericAnalyzer`. No category-specific analyzer exists.

**Problems with the current approach:**

- **Violates the division of labor.** TraderBot's role is data, analysis, and guardrails. The agent's role is decisions. Both signal systems produce `direction: Literal["yes", "no", "neutral"]` — that is a trading recommendation, which is the agent's responsibility.

- **One size fits none.** Weather markets depend on forecast accuracy, seasonal distributions, and lead-time decay. Election markets depend on polling aggregates, demographic models, and event timing. Crypto markets depend on volatility, on-chain metrics, and order flow. The `GenericAnalyzer` applies the same RSI/Bollinger/EMA logic to every category, which is inappropriate for most of them. Each category needs its own analysis toolkit designed for its domain.

- **Hardcoded and opaque.** The logistic sigma=5.0 treats Minneapolis in January (σ≈12°F) the same as Miami in August (σ≈3°F). Fixed weights (indicators: 0.3, odds: 0.5, momentum: 0.2) are invisible to the agent. Under MCP, the agent should receive raw analytical outputs and make its own weighting decisions.

- **No calibration or uncertainty.** Confidence is a weighted average of "strength" values, not a calibrated probability. The agent has no way to know whether "0.72 confidence" actually resolves YES 72% of the time. Each category needs its own calibration framework.

- **No time-series depth.** The engine evaluates a single point in time. Weather needs lead-time decay; elections need polling trend analysis; crypto needs volatility regime detection. Each category has its own temporal dynamics.

- **Experiment harness disconnected from production.** The `TreatmentInterface` operates on a separate code path from the production signal engine. Under v2, MCP tools should be the same interface used in backtesting and live trading, so improvements tested in the lab translate directly to production.

**Decision**: Redesign the analysis layer as **category-specific analysis toolkits** exposed as MCP tools. Each category gets a custom toolkit designed for its domain. TraderBot provides *interpretive statistical outputs*, not directional trading calls. The agent receives structured analytical data and makes its own decisions.

#### 1. Architecture: Category Analysis Toolkits

Each category agent receives a bespoke set of MCP tools reflecting its domain's analytical needs. Tools are namespaced by category, and the OpenClaw `alsoAllow` mechanism (DD-025) ensures each agent only sees its own toolkit.

This is not a generic framework with pluggable modules — each toolkit is **custom-designed** for its category. Weather needs calibrated probability estimates from forecast distributions. Elections need polling aggregates and demographic modeling. Crypto needs volatility analysis and order flow metrics. The analysis pipeline, data sources, statistical models, and tool outputs are all category-specific.

The `AnalysisRegistry` pattern is preserved as an internal dispatch mechanism — each toolkit calls into its category's registered analyzer. But the agent never sees the analyzer directly. It only sees MCP tool responses.

**General-purpose tools** (available to all categories):
```
traderbot__market_edge      — Market-implied probability, spread, liquidity, edge assessment
traderbot__market_prices    — Current and historical price data from Kalshi WebSocket/cache
```

**Weather toolkit** (weather agent only):
```
traderbot__weather_forecast_prob    — Calibrated probability estimate with confidence interval
traderbot__weather_accuracy         — Historical forecast accuracy by source, city, lead time
traderbot__weather_seasonal_context — Historical temperature distributions and recent anomalies
traderbot__weather_decision_brief   — Assembled analytical brief for a specific market/ticker
```

**Election toolkit** (election agent only, design pending):
```
traderbot__election_poll_aggregate  — Polling averages with methodology weighting
traderbot__election_demographic     — Demographic composition and voting pattern data
traderbot__election_accuracy        — Historical polling accuracy by type, lead time, source
traderbot__election_decision_brief  — Assembled analytical brief for an election market
```

**Crypto toolkit** (crypto agent only, design pending):
```
traderbot__crypto_volatility       — Implied and realized volatility metrics
traderbot__crypto_onchain           — On-chain flow and holder distribution data
traderbot__crypto_accuracy          — Historical signal accuracy for crypto markets
traderbot__crypto_decision_brief    — Assembled analytical brief for a crypto market
```

Other categories (sports, economics, etc.) follow the same pattern. Each toolkit is designed from scratch for its domain. There is no requirement that toolkits share structure beyond the `*_decision_brief` aggregation tool and the general `market_edge`/`market_prices` tools.

#### 2. Weather Toolkit — Detailed Design (First Implementation)

Weather is the first category to get a full toolkit implementation. The design here is specific to weather markets and should not be assumed to generalize to other categories.

**`traderbot__weather_forecast_prob`**

Replaces the hardcoded logistic function. Takes a ticker and returns a calibrated probability estimate with uncertainty bounds.

Input: `ticker`, `snapshot_date` (optional, defaults to now)
Output:
```json
{
  "ticker": "KXHIGHCHI-26JUN02-T81",
  "city": "Chicago",
  "target_date": "2026-06-02",
  "lead_time_days": 4,
  "forecast_temp_f": 83.2,
  "strike_type": "less",
  "threshold": 81,
  "estimated_prob": 0.68,
  "confidence_interval": {"low": 0.52, "high": 0.82},
  "calibration_score": 0.74,
  "sources": [
    {"source": "nws", "forecast_f": 84.0, "weight": 0.4},
    {"source": "gfs", "forecast_f": 82.5, "weight": 0.3},
    {"source": "ecmwf", "forecast_f": 83.0, "weight": 0.3}
  ],
  "model_consensus": {
    "mean_temp_f": 83.2,
    "std_dev_f": 1.8,
    "spread_f": 4.0,
    "agreement_score": 0.85,
    "models_used": ["nws", "gfs", "ecmwf"]
  },
  "method": "calibrated_logistic",
  "note": "Probability calibrated against historical accuracy for this city/month/lead_time combination"
}
```

Implementation:
- City-month-specific σ values derived from historical temperature distributions in `forecast_snapshots` and `bias_tracking` — no more hardcoded sigma=5.0
- Calibration curves (Brier score decomposition) adjust raw logistic probability based on historical accuracy for this city/month/lead_time combination
- Confidence intervals computed from ensemble spread and historical calibration
- Lead-time decay: probability estimates widen and confidence decreases as lead time increases
- When multi-day forecast data is available (DD-033 Phase 2), use the actual forecast available at `snapshot_date` rather than the current forecast

**`traderbot__weather_accuracy`**

Replaces the simple `_query_bias_adjustment()` method. Provides the full statistical picture so the agent can assess forecast reliability.

Input: `city`, `source` (optional, defaults to all), `lead_time_days` (optional), `lookback_days` (optional, default 90)
Output:
```json
{
  "city": "Chicago",
  "source": "all",
  "lookback_days": 90,
  "sample_size": 87,
  "brier_score": 0.142,
  "calibration_error": 0.068,
  "mean_error_f": 1.3,
  "mean_abs_error_f": 3.1,
  "std_error_f": 4.2,
  "by_lead_time": {
    "0": {"brier_score": 0.08, "mean_abs_error_f": 1.8, "sample_size": 87},
    "1": {"brier_score": 0.12, "mean_abs_error_f": 2.4, "sample_size": 85},
    "2": {"brier_score": 0.19, "mean_abs_error_f": 3.5, "sample_size": 82},
    "3": {"brier_score": 0.24, "mean_abs_error_f": 4.1, "sample_size": 78},
    "4": {"brier_score": 0.31, "mean_abs_error_f": 5.1, "sample_size": 72}
  },
  "recent_trend": "improving",
  "note": "Brier scores below 0.25 indicate useful forecasts; below 0.15 indicates strong forecasts"
}
```

The agent receives the full statistical picture and decides how much weight to give the forecast. Interpretive notes help the agent understand what the numbers mean, but the tool does not tell the agent what to do.

**`traderbot__weather_seasonal_context`**

New capability — provides the statistical context that weather trading requires.

Input: `city`, `target_date` (optional)
Output:
```json
{
  "city": "Chicago",
  "month": "June",
  "historical_distribution": {
    "mean_high_f": 82.3,
    "std_dev_f": 6.8,
    "percentile_10": 72.0,
    "percentile_25": 77.0,
    "percentile_50": 82.0,
    "percentile_75": 87.0,
    "percentile_90": 92.0,
    "sample_size": 30
  },
  "recent_anomaly": {
    "last_7_days_mean_f": 79.5,
    "departure_from_normal_f": -2.8,
    "trend": "cooling",
    "trend_days": 3
  },
  "climate_patterns": {
    "enso_status": "neutral",
    "enso_impact": "minimal predictable effect on Chicago June temperatures"
  },
  "note": "Chicago June highs have σ≈6.8°F. A threshold of 81°F is near the median — roughly even odds without any forecast information."
}
```

- Historical distributions come from `forecast_snapshots` actuals and Open-Meteo Archive API
- Seasonal context is pre-computed monthly and cached — not recomputed on every request
- Anomaly tracking uses last 7-14 days of actual observations
- ENSO/climate patterns are aspirational for Phase 1
- The `note` field provides interpretive context about the market structure

**`traderbot__weather_decision_brief`**

The aggregation tool. Calls the other three weather tools plus `market_edge` and assembles a single structured brief. This is the primary tool the weather agent calls during its trading cycle.

Input: `ticker`
Output: Combined analytical brief with forecast probability, accuracy data, market edge, and seasonal context. Interpretive notes throughout. **No directional call.**

This replaces `generate_signal()` and `WeatherSignalEngine.compute_signals()`. Instead of:
```python
# OLD: TraderBot decides direction
signal = generate_signal(ticker, prices, orderbook, estimated_prob)
direction = signal.direction  # "yes", "no", or "neutral"
```

The agent calls:
```python
# NEW: TraderBot provides analysis, agent decides
brief = traderbot__weather_decision_brief(ticker="KXHIGHCHI-26JUN02-T81")
# brief contains probability estimates, accuracy data, market context, seasonal context
# The LLM reads the brief and makes its own directional decision
```

#### 3. General-Purpose Tools

Some analysis is category-agnostic and shared across all toolkits. These are exposed as general MCP tools available to all category agents:

**`traderbot__market_edge`** — Replaces the current `detect_edge()` and `_get_market_prob()`. Provides market-implied probability, bid-ask spread, liquidity assessment, fill probability, and edge classification (negligible/moderate/strong). The `direction` field describes which side the math favors — this is a mathematical observation, not a trading recommendation. The agent decides whether to act on it.

**`traderbot__market_prices`** — Current and historical price data from the Kalshi WebSocket cache (DD-016). Provides price history, volume, and candlestick data. Used by most categories but especially important for crypto and sports where price action patterns matter.

Technical indicators (RSI, Bollinger Bands, EMA, volume-weighted price) remain as internal computation utilities in `analysis/indicators.py`. They may be referenced inside category-specific tools (e.g., crypto's volatility toolkit might use EMA internally) but are not exposed as standalone MCP tools. Each category decides whether and how to use them.

#### 4. Calibrated Probability Model (Weather)

The current logistic function is replaced with a calibrated model specific to weather markets:

```python
def calibrated_probability(
    forecast_temp_f: float,
    threshold_f: float,
    strike_type: str,
    city: str,
    month: int,
    lead_time_days: int,
) -> tuple[float, float, float]:
    """Compute calibrated probability estimate with confidence interval.

    Returns (estimated_prob, ci_low, ci_high).
    """
    # 1. City-month-specific sigma from historical distribution
    sigma = get_city_month_sigma(city, month)  # from forecast_snapshots/bias_tracking

    # 2. Raw logistic probability
    z = (forecast_temp_f - threshold_f) / sigma
    if strike_type == "greater":
        prob = 1.0 / (1.0 + math.exp(-z))
    elif strike_type == "less":
        prob = 1.0 / (1.0 + math.exp(z))
    else:
        prob = 0.5  # bucket markets need different handling

    # 3. Lead-time decay factor
    lead_time_factor = get_lead_time_accuracy(city, lead_time_days)

    # 4. Confidence interval from sigma and ensemble spread
    ci_spread = 1.96 * (sigma / max(abs(forecast_temp_f - threshold_f), 0.01)) * lead_time_factor
    ci_low = max(0.0, prob - ci_spread)
    ci_high = min(1.0, prob + ci_spread)

    # 5. Calibration correction from historical Brier scores
    prob = apply_calibration(prob, city, month, lead_time_days)

    return (prob, ci_low, ci_high)
```

Key differences from current approach:
- City-month-specific σ instead of hardcoded 5.0
- Confidence intervals instead of a single point estimate
- Lead-time decay factor
- Calibration correction based on historical accuracy
- Bucket markets handled differently (not just defaulting to 0.5)

Each category will need its own calibrated model — elections use polling margins, crypto uses volatility surfaces, etc. The weather implementation above is specific to weather and should not be assumed to generalize.

#### 5. Internal Architecture Changes

**Retire `analysis/signals.py`** — The `generate_signal()` function, `CombinedSignal`, and `SignalSource` models are removed. TraderBot no longer produces directional trading signals.

**Retire `data/weather/signals.py`** — The `WeatherSignalEngine` class is replaced by `WeatherAnalyzer`, which implements the five weather MCP tools as methods. Internal computation methods are preserved but refactored into tool implementations.

**Retire `TradingSignal.direction`** — The `TradingSignal` model is refactored. The `direction` field is removed. `estimated_prob` gains confidence interval fields. New fields for calibration, source breakdown, and method identification are added. The model becomes a structured analytical output, not a recommendation.

**Extend `AnalysisRegistry`** — Each category registers its own analyzer implementing a revised `CategoryAnalyzer` protocol. The protocol no longer returns `CategorySignals` (which includes direction). Instead, each analyzer returns a domain-specific analytical brief. The registry dispatches to the correct analyzer based on category.

**`GenericAnalyzer`** — Kept as a fallback for categories without a custom analyzer. Stops producing directional calls. Returns a `TechnicalIndicators` data structure (RSI value, Bollinger position, EMA crossover, volume-weighted price) that the agent can interpret. Categories like weather that don't benefit from price momentum indicators simply don't use it.

**Keep `analysis/odds.py`** — `implied_probability()`, `detect_edge()`, and `compute_kelly_inputs()` are pure statistical functions. They're absorbed into `traderbot__market_edge` and remain as internal utilities. `EdgeEstimate.direction` changes semantics from "trading direction" to "mathematical edge direction" — it describes which side the math favors, not what the agent should do.

**Keep `analysis/indicators.py`** — Technical indicators remain as internal computation tools. Category-specific toolkits may use them internally (e.g., crypto volatility) but they are not exposed as standalone MCP tools.

#### 6. Experiment Harness Alignment

Under the new design, the experiment harness (DD-034) tests *treatments* — different analytical configurations, prompt variations, or decision frameworks. The harness:

- Uses the same MCP tools in backtesting that the agent uses in live trading
- Tests variations in the analysis pipeline (different sigma models, calibration approaches) by swapping analyzer implementations
- Measures outcomes (P&L, Brier score, calibration) without changing the tool interface
- `TreatmentInterface` and `Harness` are preserved, but treatments manipulate *analyzer configuration* rather than *output format*

#### 7. Migration Path

1. **Phase A (v2 core)** — Implement the weather toolkit with calibrated logistic model. Use existing data sources (NWS, Open-Meteo day-0, Kalshi WebSocket). Accuracy tool starts with `bias_tracking` and `forecast_snapshots` data. Seasonal context uses historical distributions from Open-Meteo Archive. General-purpose `market_edge` and `market_prices` tools are implemented alongside.

2. **Phase B (post-v2, with GRIB2)** — DD-033 Phase 2 unlocks true multi-day lead time data. `forecast_prob` upgrades from day-0 approximation to actual lead-time-dependent forecasts. `accuracy` gains per-lead-time Brier scores. Additional category toolkits (election, crypto, etc.) are designed and implemented.

3. **Phase C (self-improvement)** — DD-018 Layer 2 can propose and test improvements to any category's calibrated models, phantom edge detection thresholds, confidence interval calculations, etc. These are tested in the experiment harness and, if proven effective, promoted to production.

**Consequences**:
- TraderBot no longer produces trading directions — `direction` fields on signal models are removed or redefined as mathematical edge direction
- Each category gets a custom analysis toolkit designed for its domain, not a one-size-fits-all signal generator
- The agent receives structured analytical data and makes all directional decisions itself
- Weather analysis gains city-specific calibration, lead-time decay, confidence intervals, seasonal context, and market structure awareness
- `generate_signal()`, `CombinedSignal`, and `SignalSource` are retired
- `WeatherSignalEngine` becomes `WeatherAnalyzer` with tool-specific methods
- `AnalysisRegistry` supports per-category analyzers with a revised protocol
- Technical indicators preserved as internal utilities; not exposed as MCP tools
- `TradingSignal` model refactored: `direction` removed, confidence interval added, calibration fields added
- New `SeasonalContext` model for historical distributions and anomaly tracking
- New `MarketEdgeBrief` model replaces `EdgeEstimate` in MCP responses
- Experiment harness aligns with MCP tools — backtesting and live trading use the same interface
- Election, crypto, and other category toolkits are pending designs — weather is the first implementation
- The `GenericAnalyzer` is a fallback for categories without custom toolkits, producing technical indicator data without directional calls

### DD-036: SysAdmin sandbox decision — unsandboxed with principled restrictions

**Date**: 2026-06-15
**Status**: Decided

> **Phase 1 implementation update:** `profiles/sysadmin.py` currently creates a
> paper-mode SysAdmin profile that enumerates every `MarketCategory` and applies
> deny rules for trading, scanning, analysis, market data, and weather tools.
> Only `health`, `auth_check`, `profile_list`, and `market_edge` exist in the MCP
> server; SysAdmin denies `market_edge`, and `auth_check` validates the profile
> token and reports access context rather than provider credentials. The broader
> confirmations below remain target design. OpenClaw hardening config is
> committed, and secure profile-token injection is deployment-verified via
> the `before_tool_call` plugin hook (Phase 1.1, issue #187 closed).

**Context**: DD-010 mandates Docker sandboxing for all category agents, but explicitly leaves SysAdmin unsandboxed (`mode: off`). The pending discussion item "SysAdmin sandbox decision" asks whether this is appropriate given SysAdmin's enormous power — fleet orchestration, lifecycle management, self-improvement coordination, and cross-agent data access.

SysAdmin's responsibilities (DD-017) include:
- Monitoring fleet health and circuit breakers
- Managing agent lifecycle transitions (backtesting → paper → live → suspended)
- Coordinating the self-improvement cycle
- Sending investigation prompts to category agents via session-send
- Reviewing and promoting learnings
- Managing cron/heartbeat activation (DD-023)
- Authenticating agents with TraderBot
- Coordinating with the Dev-Liaison

The concern: SysAdmin has access to all agent workspaces, all TraderBot management tools, and all cross-agent data. If compromised (via prompt injection, LLM attack, or other vector), this access could be catastrophic.

**Investigation of threat model:**

| Threat | Docker sandboxing SysAdmin helps? | MCP tool restriction helps? |
|---|---|---|
| External actor gains system access | No — they have host access regardless | Partially — limits what can be done via MCP |
| Rogue category agent | Already handled by per-agent Docker isolation | N/A — not SysAdmin's threat |
| Compromised SysAdmin (prompt injection) | Marginal — sandboxed SysAdmin still has all MCP tools | Yes — restricts what compromised SysAdmin can do |
| SysAdmin misconfiguration or error | Marginal — sandbox doesn't prevent misconfig via tools | Yes — guardrails on critical actions |

Key insight: Docker sandboxing SysAdmin provides minimal security benefit because SysAdmin's power comes from its MCP tool access, not filesystem access. A sandboxed SysAdmin with all management tools would still be equally dangerous if compromised. The real security boundary is the tool layer, not the container boundary.

However, SysAdmin needs legitimate host-level access:
- OpenClaw CLI for cron/heartbeat management requires host access
- Reading all agent workspaces for oversight requires filesystem access or complex bind mounts
- Coordinating with Dev-Liaison (also unsandboxed per DD-034)
- Reading system logs and TraderBot state

**Decision**: SysAdmin remains **unsandboxed on the host**, with three additional safeguard layers that the current design lacks:

#### 1. Target MCP tool allowlist

The target design gives SysAdmin a broad but specific tool allowlist. It has oversight of everything but direct control of trading. The principle: SysAdmin monitors, coordinates, and manages, but does not trade. Names beyond the four current Phase 1 tools are planned, not implemented.

```
SysAdmin tool allowlist:
  ALLOWED (oversight and management):
    traderbot__health          — System and pipeline health checks
    traderbot__auth_check      — Profile-token validation and access-context reporting
    traderbot__profile_list    — List all agent profiles and their status
    traderbot__profile_update  — Update agent profiles (mode, parameters)
    traderbot__performance     — Performance metrics for any agent
    traderbot__audit           — Audit trail for any agent
    traderbot__learnings       — Read/write learning patterns
    traderbot__cron_setup      — Manage OpenClaw cron/heartbeat jobs
    traderbot__session_send    — Send messages to any agent
    traderbot__experiment      — Run and evaluate experiments
    traderbot__data_status     — Data pipeline freshness and status
    traderbot__ws_status       — WebSocket daemon status
    traderbot__backfill        — Trigger data backfill

  DENIED (trading and direct API access):
    traderbot__trade           — No trade placement
    traderbot__scan            — No market scanning (category agents do this)
    traderbot__analyze         — No analysis (category agents do this)
    traderbot__weather_*       — No category-specific tools (category agents do this)
    traderbot__market_edge     — No market edge analysis
    traderbot__market_prices   — No direct market data
```

Once the full target surface exists, these restrictions are intended to let a compromised SysAdmin monitor the fleet, manage lifecycle transitions, and coordinate agents without placing trades or using category-specific analysis. In current Phase 1, the profile deny rules block the implemented `market_edge` tool; the broader management controls remain unimplemented.

#### 2. Target workspace file immutability enforcement (not implemented in Phase 1)

SysAdmin can read all agent workspace files (AGENTS.md, SOUL.md, TOOLS.md, MEMORY.md, .learnings/) but can only *write* to:
- `.learnings/` — for promoting learning patterns
- `MEMORY.md` — for operational notes
- `SESSION-STATE.md` — for current task state

All other workspace files (AGENTS.md, SOUL.md, TOOLS.md, IDENTITY.md, HEARTBEAT.md) are read-only for SysAdmin. This is enforced at the MCP tool level, not just by convention. These files are prebuilt (DD-008) and should only be modified through the deploy/update process, not by SysAdmin directly.

This prevents a compromised SysAdmin from altering agent operating procedures, identity, or tool definitions.

#### 3. Target critical-action confirmation for lifecycle transitions (not implemented in Phase 1)

The most powerful actions SysAdmin can take are lifecycle transitions: promoting an agent from backtesting to paper, from paper to live, or suspending an agent. These should require a confirmation mechanism:

- **Promoting to live trading**: SysAdmin must provide a verification summary that includes the agent's performance metrics, the deployment bar criteria, and a confirmation that all criteria are met. The MCP tool validates this summary against actual metrics before executing the transition.
- **Suspending an agent**: SysAdmin can suspend immediately (emergency stop) but must log the reason and trigger an investigation.
- **Demoting an agent**: SysAdmin can demote with a logged reason, no additional confirmation required.

This prevents a compromised SysAdmin from unilaterally moving an agent to live trading without evidence that it meets the deployment bar.

#### 4. SysAdmin vs. Dev-Liaison sandbox comparison

| Dimension | SysAdmin | Dev-Liaison |
|---|---|---|
| Sandbox mode | `off` (host) | `off` (host) |
| Reason for host access | Workspace oversight, cron management, fleet coordination | Source tree access, logs, experiment DB |
| Trading tools | Denied | Denied |
| Category analysis tools | Denied | Denied |
| Management tools | Full suite | None (only reference + experiment + auth_check) |
| Can modify source code | No | No (explicitly forbidden in DD-034) |
| Can modify workspace files | Only .learnings/, MEMORY.md, SESSION-STATE.md | Only test modules in experiment directory |
| Can place trades | No | No |
| Can manage agent lifecycle | Yes (with confirmation for live promotion) | No |
| Can read all agent data | Yes (oversight role) | No (only experiment data) |
| Can write GitHub issues | No (not its role) | Yes (via GitHub skill) |

**Target consequences**:
- SysAdmin remains unsandboxed — host-level access is required for legitimate operational needs
- The real security boundary is the MCP tool layer, not the container layer
- SysAdmin cannot place trades, access market data, or modify agent operating procedures — even if compromised, it can only monitor, coordinate, and manage lifecycle transitions
- Critical lifecycle transitions (promoting to live) require verified confirmation, preventing unilateral action
- Workspace file immutability prevents a compromised SysAdmin from altering agent behavior through workspace modification
- The Dev-Liaison precedent (unsandboxed with curated tool allowlist) is consistent with this approach
- If SysAdmin's MCP tool access is compromised, the damage is limited to fleet management actions — not trading, not market data exfiltration, not agent behavior modification


### DD-037: Secrets management — Infisical as primary vault

**Date**: 2026-06-15
**Status**: Decided

> **Implementation status:** Phase 1.5 implemented (commits leading to
> 2.0.0a38). `SecretsStore` (Infisical primary + `LocalEncryptedStore`
> fallback), `TokenStoreAdapter`, `SecretsResolver`, token rotation/scheduler,
> the `openclaw-infisical-resolver` exec provider, plugin SecretRef migration
> (vault → infisical), and the local-token migration script are all committed
> and tested. Profile-token storage now defaults to Infisical-backed
> `TokenStoreAdapter`; `LocalTokenStore`/`tokens.json` remains readable for
> migration only.

**Context**: DD-026 established 1Password as the primary secrets vault, but 1Password Connect requires a Business/Teams subscription ($7.99+/month), which is a significant barrier for TraderBot's target users. This decision replaces 1Password with Infisical, a free open-source (MIT) secrets management platform that provides the same capabilities — vaults, access control, secret rotation, audit logging, and a Python SDK — at no cost, with self-hosted deployment alongside TraderBot's existing Docker infrastructure.

All other aspects of DD-026 (architecture, token provisioning, division of secrets responsibility) remain unchanged. Only the vault backend changes.

**Why Infisical:**

| Requirement | Infisical | 1Password Connect |
|---|---|---|
| Cost | Free (MIT license) | $7.99/user/month minimum |
| Self-hosted | Yes, Docker Compose alongside TraderBot | Connect server is a cache; data in 1Password cloud |
| Python SDK | `infisicalsdk` (current official SDK, OS-independent) | Official API, but requires Business plan |
| Secret versioning | Yes | Yes |
| Token rotation | Yes (API-driven) | Yes (API-driven) |
| Access control | Projects + environments | Vaults + items |
| Audit logging | Yes | Yes |
| End-to-end encryption | Yes (AES-256-GCM) | Yes |
| Docker deployment | Single image, linux/amd64 + linux/arm64 | Single image, but cloud-dependent |
| CLI tool | `infisical` CLI (npm/pip/binary) | `op` CLI |
| Headless Linux | Full support (API-based, no GUI) | Full support |
| macOS | Full support (Docker + SDK) | Full support |
| Windows | Full support (Docker + SDK) | Full support |
| Maintenance | User manages the container (alongside TraderBot's existing Docker) | 1Password manages cloud; user manages Connect container |

Infisical's architecture maps naturally to our vault structure:
- **Infisical projects** = our vaults ("TraderBot" for API keys, "TraderBot Agent Tokens" for profile tokens)
- **Infisical environments** = our namespaces ("global", "weather", "economics", etc.)
- **Infisical machine identities** = our service tokens (TraderBot service, each agent)
- **`site_url` SDK parameter** = self-hosted instance URL (default `http://localhost:8080`)

**Decision:**

#### 1. Infisical as the sole external secrets vault

1Password support is removed. Infisical is the sole external secrets backend. The three-tier storage model becomes:

| Tier | When to use | Storage | Key management |
|---|---|---|---|
| **Infisical** (primary, default) | Recommended for all deployments | Self-hosted Infisical server (Docker) | Infisical manages |
| **Local encrypted store** (fallback) | Air-gapped systems, testing | `~/.traderbot/secrets/secrets.json` (0600) | Machine-derived encryption key |

Users choose the backend during `traderbot deploy`. Infisical is the default and recommended option.

#### 2. Infisical deployment

Infisical runs as a Docker container on the TraderBot host, alongside the agent sandbox containers (DD-010). Since Docker is already required, adding one more container is minimal overhead.

```yaml
# docker-compose.infisical.yml (managed by TraderBot)
services:
  infisical:
    image: infisical/infisical:latest
    ports:
      - "8080:8080"
    environment:
      - ENCRYPTION_KEY=<auto-generated>
      - AUTH_SECRET=<auto-generated>
    volumes:
      - ~/.traderbot/infisical/data:/var/lib/infisical/data
      - ~/.traderbot/infisical/config:/var/lib/infisical/config
    restart: unless-stopped
```

The TraderBot service connects to `http://localhost:8080` to retrieve secrets. No external cloud dependency.

**Platform compatibility:**
- **Linux (including headless):** Infisical Docker image supports linux/amd64 and linux/arm64. The Python SDK is OS-independent. The CLI is available via pip, npm, or binary download. Headless Linux is fully supported — all interaction is via API/SDK/CLI, no GUI required.
- **macOS:** Same Docker container via Docker Desktop. The Python SDK and CLI work natively.
- **Windows:** Same Docker container via Docker Desktop (WSL2 backend). The Python SDK works natively on Windows.

#### 3. Secret resolution flow (updated from DD-026)

```python
class SecretsStore:
    """Unified secrets store with Infisical primary and local fallback."""

    def get(self, service: str, key: str, namespace: str = "global") -> str | None: ...
    def set(self, service: str, key: str, value: str, namespace: str = "global") -> None: ...
    def get_namespace(self, namespace: str) -> dict[str, dict[str, str]]: ...
    def delete(self, service: str, key: str, namespace: str = "global") -> None: ...

    # Infisical backend
    def _infisical_get(self, project: str, env: str, key: str) -> str | None: ...
    def _infisical_set(self, project: str, env: str, key: str, value: str) -> None: ...
    def _infisical_delete(self, project: str, env: str, key: str) -> None: ...

    # Local fallback backend
    def _local_get(self, service: str, key: str, namespace: str) -> str | None: ...
    def _local_set(self, service: str, key: str, value: str, namespace: str) -> None: ...
    def _local_delete(self, service: str, key: str, namespace: str) -> None: ...
```

The `SecretsStore` interface is identical regardless of backend. The Infisical backend maps:
- `namespace="global"` → Infisical project "TraderBot", environment "prod"
- `namespace="weather"` → Infisical project "TraderBot", environment "weather"
- `namespace="tokens"` → Infisical project "TraderBot Agent Tokens", environment "prod"

#### 4. Vault structure

```
Infisical Project: "TraderBot"
  Environment: "prod" (global keys)
    ├── kalshi_api_key
    ├── kalshi_private_key_pem
    ├── voyage_api_key
    ├── newsapi_key
    ├── twitter_api_key
    ├── twitter_api_secret
    ├── twitter_bearer_token
    ├── reddit_client_id
    └── reddit_client_secret
  Environment: "weather"
    ├── openweathermap_api_key
    └── (Open-Meteo: free, no key)
  Environment: "economics"
    └── fred_api_key
  Environment: "crypto"
    └── coingecko_api_key

Infisical Project: "TraderBot Agent Tokens"
  Environment: "prod"
    ├── sysadmin_token (field: token, profile, agent, categories, permissions)
    ├── weather_token (field: token, profile, agent, categories, permissions)
    └── dev-liaison_token (field: token, profile, agent, categories, permissions)
```

The two-project structure separates API keys from agent tokens, enabling granular access control. The TraderBot service authenticates with a machine identity that has read/write access to both projects. Each agent's machine identity has read access only to its own token.

#### 5. Deploy flow — Infisical setup

**Step 4a: Infisical health check**
```
traderbot deploy Step 4a: Checking Infisical...

  ✓ Infisical server is running at http://localhost:8080
  ✓ Machine identity authenticated
  ✓ Project access confirmed
```

If Infisical isn't running:
```
traderbot deploy Step 4a: Checking Infisical...
  ✗ Infisical server not found at http://localhost:8080

  Would you like to:
    1) Start Infisical (requires Docker) — recommended
    2) Configure an existing Infisical server
    3) Use local encrypted storage (no Infisical, no audit logging, no automatic rotation)
```

Option 1 starts the Infisical Docker container using `docker compose -f docker-compose.infisical.yml up -d`, creates the projects and machine identity, and configures the TraderBot service to connect.

Option 2 connects to an existing Infisical instance (for users who already run Infisical).

Option 3 falls back to local encrypted storage (see §9).

**Step 4b: API token entry**

API tokens are prompted per category and stored directly in Infisical:
```
traderbot deploy Step 4b: API tokens

  Common tokens (required for all agents):
    Kalshi API key: ************************************
    Kalshi private key: (paste PEM or path) ************************************
    VoyageAI API key: ************************************
    NewsAPI key: ************************************
    Twitter bearer token: ************************************
    Reddit client ID: ************************************
    Reddit client secret: ************************************

  Weather-specific tokens (weather category enabled):
    Open-Meteo: (free, no key required) — skipping
    OpenWeatherMap API key: ************************************

  Each token is validated against the service before storing.
  ✓ All tokens stored in Infisical project "TraderBot"
```

Validation happens immediately — if a Kalshi key doesn't authenticate, deploy pauses and asks for a corrected key.

**Step 4c: Machine identity configuration**

The TraderBot service authenticates with Infisical using a machine identity (service token):
```
traderbot deploy Step 4c: Configuring Infisical machine identity...

  ✓ Created machine identity "traderbot-service" with read/write access
  ✓ Service token stored in OpenClaw SecretRef (env: INFISICAL_TOKEN)
  ✓ TraderBot service will authenticate with Infisical on startup
```

This is the single bootstrap secret: `INFISICAL_TOKEN` → TraderBot authenticates with Infisical → retrieves all other secrets.

#### 6. Agent profile token provisioning (unchanged from DD-026/037)

> **Resolved:** The `before_tool_call` plugin hook (Phase 1.1, issue #187
> closed) now handles per-agent token injection host-side. The config-only
> injection sequence shown below is replaced by the plugin, which resolves
> per-agent tokens from Infisical-backed SecretRefs and injects them into
> tool call params. The OpenClaw config does not need per-agent env fields.

The token provisioning flow is identical to the 1Password design, just using Infisical as the backend:

1. TraderBot generates a profile token (cryptographically random, 256-bit)
2. Profile token is stored as an Infisical secret in the "TraderBot Agent Tokens" project
3. OpenClaw SecretRef is configured to inject this token into the agent's environment:
   ```
   openclaw config set secrets.providers.traderbot_weather \
     --provider-type env \
     --provider-command "infisical secrets get weather_token --project traderbot-agent-tokens" \
     --env-var TRADERBOT_PROFILE_TOKEN
   ```
4. The token is passed to the agent via `TRADERBOT_PROFILE_TOKEN` environment variable
5. When the agent calls an MCP tool, the TraderBot MCP server resolves the token to a profile

The security properties are identical: the profile token is the only secret that enters the container, it's scoped to a specific agent, and it rotates every 4 hours.

#### 7. Token rotation

The 4-hour rotation cycle (DD-026 §5):

1. TraderBot service maintains a rotation timer
2. Every 4 hours, for each active profile:
   a. Generate a new 256-bit random token
   b. Store the new token in Infisical (replacing the old one)
   c. Signal OpenClaw to refresh the SecretRef for that agent
   d. The old token is immediately invalidated
3. SysAdmin heartbeat includes a token staleness check (30-minute warning before expiry)
4. If Infisical is unavailable during rotation:
   - The current token remains valid until rotation succeeds
   - SysAdmin is alerted that rotation failed
   - Retry occurs every 15 minutes
   - After 24 hours of failed rotation, the fleet is suspended

Manual rotation via CLI:
```
traderbot token rotate --agent weather    # Rotate one agent's token
traderbot token rotate --all              # Rotate all tokens
traderbot token rotate --force             # Force immediate rotation
```

#### 8. TraderBot service startup sequence

When the TraderBot service (MCP server + always-on daemon) starts:

1. Read `INFISICAL_TOKEN` from environment (provided by OpenClaw SecretRef)
2. Authenticate with Infisical at `http://localhost:8080` (or configured URL)
3. Load all secrets from the "TraderBot" project into memory
4. Load all profile tokens from the "TraderBot Agent Tokens" project into memory
5. Start the MCP server
6. Start the token rotation timer
7. Start the data pipeline (DD-016)

If Infisical is unreachable:
- Retry with exponential backoff (1s, 2s, 4s, 8s, 16s, 30s max)
- After 5 minutes of failed retries, fall back to local `secrets.json` if available
- Log a warning that secrets are being loaded from fallback storage
- Continue retrying Infisical in the background
- When Infisical becomes available, switch to it and reload all secrets

#### 9. Local encrypted store — fallback

For users who don't want to run Infisical (air-gapped systems, minimal setups, testing):

```
~/.traderbot/secrets/secrets.json (0600 permissions)
```

Structure is identical to DD-026 §9 (namespaced JSON). The local store adds security beyond simple file permissions:

- **Machine-derived encryption**: The file is encrypted at rest using a key derived from the host machine's identity (hostname + username + machine ID hash). This means the file is unreadable if copied to another machine, but decrypts automatically on the original machine without a user-supplied password.
- **File integrity monitoring**: A SHA-256 hash of the file contents is stored alongside it (`secrets.json.sha256`). At startup, TraderBot verifies the hash and alerts if tampering is detected.
- **Audit logging**: Last-read and last-write timestamps per secret are tracked in `secrets.json.meta` for basic audit trail.

The local fallback:
- Uses the same `SecretsStore` interface as Infisical
- Has audit logging (basic) and integrity monitoring, but no automatic token rotation
- Token rotation must be done manually via `traderbot token rotate --agent <name>`
- Is clearly marked during deploy: `⚠ Local storage provides basic security but no automatic token rotation or Infisical's audit logging. Infisical is recommended for production deployments.`

#### 10. OpenClaw SecretRef configuration

> **Historical design sketch, not valid current config:** OpenClaw agent entries
> do not accept the per-agent `env` field shown below. The sketch is retained to
> document the intended secret mapping, not as deployable syntax.

OpenClaw SecretRef entries for each agent:

```json5
{
  secrets: {
    providers: {
      // Infisical service token for TraderBot
      traderbot_infisical: {
        type: "env",
        env: "INFISICAL_TOKEN"
      },
      // Per-agent profile tokens — resolved via Infisical CLI
      traderbot_weather_token: {
        type: "exec",
        command: "infisical",
        args: ["secrets", "get", "weather_token", "--project", "traderbot-agent-tokens", "--env", "prod"]
      },
      traderbot_sysadmin_token: {
        type: "exec",
        command: "infisical",
        args: ["secrets", "get", "sysadmin_token", "--project", "traderbot-agent-tokens", "--env", "prod"]
      },
      traderbot_dev-liaison_token: {
        type: "exec",
        command: "infisical",
        args: ["secrets", "get", "dev-liaison_token", "--project", "traderbot-agent-tokens", "--env", "prod"]
      }
    }
  }
}
```

Each agent's OpenClaw configuration injects the corresponding token:

> **Schema-invalid historical continuation:** Per-agent `env` is rejected by
> pinned `d1c96302`; this object is retained only to show the intended mapping
> and is not deployable. Per-agent token injection is now handled by the
> `before_tool_call` plugin hook (Phase 1.1, issue #187 closed).

```json5
{
  id: "weather",
  sandbox: { mode: "all" },
  env: {
    TRADERBOT_PROFILE_TOKEN: { secretRef: "traderbot_weather_token" }
  }
}
```

#### 11. Deployment verification

After deploy completes:
```
traderbot deploy: Verifying Infisical integration...

  ✓ Infisical server is healthy (http://localhost:8080)
  ✓ TraderBot project is accessible (9 items)
  ✓ TraderBot Agent Tokens project is accessible (3 items)
  ✓ All API keys validated against their services
  ✓ All profile tokens are accessible
  ✓ OpenClaw SecretRef entries configured (4 providers)
  ✓ Token rotation timer started (4-hour interval)

  Infisical integration: ✓ Ready
```

Failed checks produce actionable guidance:
```
  ✗ Kalshi API key validation failed: 401 Unauthorized
    → Check your Kalshi API key in Infisical project "TraderBot"
    → Environment: "prod", Secret: "kalshi_api_key"
    → Update with: infisical secrets update kalshi_api_key --project traderbot --env prod
```

#### 12. Division of secrets responsibility (updated from DD-026)

| Secret type | Manager | Storage | Access |
|---|---|---|---|
| OpenClaw LLM keys, gateway auth, channel tokens | OpenClaw SecretRef | Infisical project "OpenClaw" (or OpenClaw's own provider) | OpenClaw gateway on host only |
| TraderBot API keys (Kalshi, Voyage, NewsAPI, etc.) | Infisical | Infisical project "TraderBot" | TraderBot service on host only |
| Agent profile tokens | Infisical | Infisical project "TraderBot Agent Tokens" | TraderBot service (resolution) + OpenClaw SecretRef (injection into containers) |
| Infisical machine identity token | OpenClaw SecretRef | OpenClaw config (env provider) | TraderBot service only |
| TraderBot service auth token | Infisical | Infisical project "TraderBot" | TraderBot service only |

#### 13. What gets retired (updated from DD-026)

| Component | Lines | Replacement |
|---|---|---|
| `auth.py` | 376 | `SecretsStore` with Infisical backend |
| `profiles/auth.py` | 185 | `SecretsStore` with namespace parameter |
| `profiles/tokens.py` | 358 | Simplified — tokens stored in Infisical, resolution stays |
| `master_password.py` | 284 | Eliminated (Infisical manages auth) |
| `keyring` dependency | — | Eliminated (Infisical replaces keyring) |
| `~/.traderbot/.env` | — | Eliminated |
| `~/.traderbot/tokens.enc` | — | Eliminated (Infisical stores tokens) |
| `~/.traderbot/keys/token.key` | — | Eliminated |
| `~/.traderbot/.master_key` | — | Eliminated |

#### 14. What gets added (updated from DD-026)

| Component | Purpose |
|---|---|
| `src/traderbot/secrets/__init__.py` | Package init |
| `src/traderbot/secrets/store.py` | `SecretsStore` interface with Infisical and local backends |
| `src/traderbot/secrets/store.py` | `SecretsStore` facade — Infisical SDK integration and local fallback selection |
| `src/traderbot/secrets/local_encrypted.py` | `LocalEncryptedStore` — Fernet-encrypted `secrets.json`, machine-derived key, integrity monitoring |
| `src/traderbot/mcp/__init__.py` | Package init |
| `src/traderbot/mcp/server.py` | MCP server entry point (`traderbot-mcp-server` command) |
| `src/traderbot/mcp/tools.py` | MCP tool definitions |
| `src/traderbot/mcp/auth.py` | Profile token resolution, category validation, permission checks |
| `docker-compose.infisical.yml` | Infisical self-hosted deployment configuration |
| `src/traderbot/secrets/rotation.py` | Token rotation timer and management |

#### 15. Relationship to previous DDs

- **DD-026** (1Password as primary vault): Superseded by this decision. Infisical replaces 1Password as the primary vault. All other aspects of DD-026 (architecture, token provisioning, division of secrets responsibility, what gets retired) remain unchanged with Infisical as the backend.
- **DD-015** (MCP server): The MCP server reads secrets from Infisical at startup. Profile tokens are resolved from OpenClaw session context. The `SecretsStore` interface is the same whether backed by Infisical or local storage.
- **DD-025** (MCP identity resolution): Profile tokens are stored in Infisical and injected via OpenClaw SecretRef. The resolution flow (token → profile → categories → permissions) is unchanged.
- **DD-010** (mandatory Docker sandbox): Infisical runs as a Docker container alongside agent sandboxes. No additional Docker overhead beyond one more container.
- **DD-006** (OS-aware capability detection): The deploy flow checks for Infisical on all three platforms. On headless Linux, the Infisical container starts via Docker Compose with no GUI required.
- **DD-036** (SysAdmin sandbox): SysAdmin's profile token is stored in Infisical and accessed via SecretRef, same as other agents.
- **DD-034 (Dev-Liaison): Same token provisioning pattern.

**Consequences**:
- 1Password is removed as a secrets backend option — Infisical is the sole external vault
- Infisical is free, open source (MIT), and self-hosted alongside TraderBot's existing Docker infrastructure
- All three platforms (macOS, Linux including headless, Windows) are fully supported — Infisical runs in Docker, the Python SDK is OS-independent, and all interaction is API-based with no GUI required
- The `SecretsStore` interface is backend-agnostic — same API for Infisical and local storage
- Local encrypted storage remains as a fallback for air-gapped or minimal setups, with machine-derived encryption and integrity monitoring
- The deploy flow gains an Infisical health check, project creation, and machine identity setup step
- API key validation is immediate — keys that don't authenticate are rejected before deploy completes
- Profile tokens are never stored on disk in containers, only in memory via SecretRef
- Token rotation is automated with 4-hour intervals, with manual override available
- The single bootstrap secret is the Infisical machine identity token, stored in OpenClaw SecretRef
- All other secrets chain from that token: Infisical token → Infisical projects → API keys + profile tokens
- Deploy verification provides clear, actionable error messages for any failed checks
- The two-project structure (API keys vs. agent tokens) enables future granular access control

### DD-038: Agent-debate integration, OpenClaw sub-agent configuration, and TEMPLATE.md modifications

**Date**: 2026-06-15
**Status**: Decided

**Context**: DD-018 established the three-layer self-improvement architecture and adopted the agent-debate framework (gumbel-ai/agent-debate) as the procedural structure for Layer 2. Three pending items need resolution: (1) how to integrate agent-debate into OpenClaw's infrastructure, (2) how to configure OpenClaw to spawn sub-agents with different models for debate, and (3) what modifications the TEMPLATE.md and guardrails need for TraderBot-specific use.

Investigation of the agent-debate framework and OpenClaw's capabilities reveals:

- **agent-debate** is a markdown-based debate protocol, not a runtime. It provides TEMPLATE.md (debate document structure), agent-guardrails.md (editing rules, evidence requirements, convergence criteria), and orchestrate.sh (a bash orchestrator for manual/CLI-driven debates). The protocol is agent-agnostic — any LLM provider can participate.
- **OpenClaw `sessions_spawn`** creates isolated sub-agent sessions for background work. It returns a `runId` and `childSessionKey`. Each spawn can specify a different model, sandbox configuration, and tool profile. This is exactly what we need for multi-model debate agents.
- **OpenClaw `sessions_send`** sends messages to specific agent sessions, enabling SysAdmin to coordinate rounds, deliver debate prompts, and collect responses.
- **OpenClaw `sessions_yield`** ends the current turn and waits for follow-up sub-agent results, enabling synchronous round coordination.

**Decision:**

#### 1. Agent-debate integration architecture

We do NOT use the agent-debate `orchestrate.sh` bash script. SysAdmin orchestrates the debate natively through OpenClaw's tool interface. The agent-debate framework provides the *protocol* (document structure, guardrails, convergence mechanics), and we implement the *orchestration* through OpenClaw.

**Debate flow (Layer 2 improvement cycle):**

```
Round 1: Identify Suboptimal Outcomes
  SysAdmin spawns 4 debate agents via sessions_spawn:
    - debate-weather-1 (category agent sub, model: e.g., Claude Opus)
    - debate-weather-2 (category agent sub, model: e.g., GPT-5)
    - debate-sysadmin-1 (SysAdmin sub, model: e.g., Claude Opus)
    - debate-sysadmin-2 (SysAdmin sub, model: e.g., Gemini)

  Each agent receives a prompt containing:
    - The debate template (modified for TraderBot, see §3)
    - Their role assignment (adversarial agent x4)
    - The debate topic (from SysAdmin's daily evaluation)
    - Access to relevant data (decisions.db, forecast_snapshots, market data)

  Each agent independently analyzes the pipeline and identifies 10 suboptimal outcomes.
  SysAdmin collects all 40 outcomes, deduplicates, and posts the consolidated list.

Round 2: White Paper Development & Cross-Examination
  Each agent produces a white paper for each of their 10 suggestions.
  SysAdmin coordinates sequential cross-examination:
    - Agent A presents, Agent B examines, Agent C examines, Agent D examines
    - Each examination is a sessions_send with the current proposal state
    - The defendant responds via sessions_send
  Dev-Liaison (Watcher) provides feasibility perspective on each.

Round 3: Blind Vote to Select Top Proposals
  SysAdmin collects blind votes from all 6 participants (4 debate + 1 watcher + 1 orchestrator).
  Votes are cast privately — SysAdmin does not reveal running totals until all votes are in.
  Top 5 proposals advance.

Round 4: In-Depth White Paper & Experiment Design
  Each surviving proposal gets a deep dive with:
    - Current code state review (via traderbot__reference MCP tool)
    - Deep conceptual research (web search tools)
    - Existing implementation search (GitHub)
    - Statistical experimental design
  Dev-Liaison provides detailed feasibility assessment for each.

Round 5: Final Selection & Implementation
  SysAdmin selects the top proposal based on:
    - Statistical rigor of the hypothesis
    - Feasibility (Dev-Liaison assessment)
    - Expected improvement in decision quality relative to implementation effort
    - Expected increase in overall profitability
  Implementation depends on root cause classification:
    - TraderBot code change → SysAdmin files a GitHub issue with full experiment design
    - Agent workspace change → SysAdmin updates workspace files and re-propagates
    - Both → Separate GitHub issues for each side, coordinated deployment
  Dev-Liaison writes the test module for the experiment harness.
  SysAdmin deploys to test-lab and monitors results.
```

**Key design choices:**

- SysAdmin orchestrates, it does not debate. As orchestrator, SysAdmin manages the process flow, coordinates rounds, collects votes, and makes final selection. It participates through its subs, not directly.
- The debate document is a shared markdown file in the test-lab workspace. Each agent edits in-place using the strikethrough-and-counter protocol from agent-guardrails.md.
- Convergence is determined by the debate protocol: all agents must mark `STATUS: CONVERGED` and all disputes must be `CLOSED` or `PARKED`.
- The Dev-Liaison participates as Watcher across all rounds, providing feasibility perspective but not voting on Round 3.

#### 2. OpenClaw multi-model sub-agent configuration

OpenClaw's `sessions_spawn` tool supports model overrides per spawn. The configuration for a debate cycle:

> **Conceptual orchestration notes:** The comments-only JSON5 fence below is
> pseudocode, not an `openclaw.json` object.

```json5
// Debate agent configuration (spawned by SysAdmin via sessions_spawn)
// Each debate cycle creates 4 temporary sub-agents with different models

// Debate sub-agents inherit their parent's tool profile but with modifications:
// - Category agent subs get their category's tool allowlist (DD-025, DD-035)
// - SysAdmin subs get the SysAdmin tool allowlist (DD-036)
// - All debate subs get sessions_spawn, sessions_send, sessions_yield for coordination
// - All debate subs get traderbot__reference for codebase knowledge (DD-034)
// - All debate subs get web search for research

// Model diversity configuration (recommended starting point):
// 2x category agent subs:
//   - Sub 1: Claude Opus (strong analytical reasoning)
//   - Sub 2: GPT-5 or GPT-5.5 (strong pattern recognition)
// 2x SysAdmin subs:
//   - Sub 3: Claude Opus (deep architectural understanding)
//   - Sub 4: Gemini 2.5 Pro or equivalent (different reasoning style)

// Dev-Liaison (Watcher) — uses its standard configuration (DD-034)
//   - Model: same as Dev-Liaison's standard model
//   - Tools: traderbot__reference, traderbot__experiment, traderbot__auth_check
```

**Model selection principles:**

- Use models from at least 2 different providers to maximize perspective diversity
- Favor models with strong analytical reasoning and statistical capabilities
- Rotate model assignments across cycles to prevent systematic bias
- The debate topic (category) determines which category agent subs are spawned — a weather improvement cycle spawns weather agent subs, an economics cycle spawns economics subs

**Debate sub-agent lifecycle:**

1. SysAdmin creates a debate workspace in `~/.openclaw/workspace/test-lab/debate-{cycle-id}/`
2. SysAdmin spawns 4 sub-agents via `sessions_spawn` with model overrides and tool profiles
3. Each sub-agent receives the debate prompt via `sessions_send`
4. Sub-agents write their analysis and proposals into the shared debate document
5. After convergence, SysAdmin collects results and terminates the sub-agents
6. Sub-agents are ephemeral — they exist only for the duration of the debate cycle

**OpenClaw configuration for debate sub-agents:**

The existing agent configurations are extended with a `debate` profile that SysAdmin can activate:

> **Historical non-deployable pseudocode:** This sketch uses additive
> `alsoAllow` as though it were restrictive, omits the required sandbox
> `bundle-mcp` gate, and includes fields not validated against pinned
> `d1c96302`. It is retained only to document the debate-agent intent.

```json5
// In openclaw.json, each debate sub-agent gets:
{
  id: "debate-weather-1",
  model: "claude-opus",  // or whatever model SysAdmin selects for this cycle
  sandbox: { mode: "all" },  // same sandbox as the parent category agent
  tools: {
    deny: ["group:runtime", "group:fs"],
    alsoAllow: [
      // Category-specific tools (inherited from parent)
      "traderbot__weather_forecast_prob",
      "traderbot__weather_accuracy",
      "traderbot__weather_seasonal_context",
      "traderbot__weather_decision_brief",
      "traderbot__market_edge",
      "traderbot__market_prices",
      "traderbot__positions",
      "traderbot__heartbeat",
      "traderbot__performance",
      "traderbot__audit",
      "traderbot__learnings",
      // Debate coordination tools
      "sessions_spawn",
      "sessions_send",
      "sessions_yield",
      "subagents",
      // Research tools
      "traderbot__reference",
    ],
  },
  // Workspace files for the debate cycle
  workspace: {
    dir: "~/.openclaw/workspace/test-lab/debate-{cycle-id}/",
  },
}
```

#### 3. TEMPLATE.md modifications for TraderBot

The agent-debate TEMPLATE.md is used as the base document structure, but requires TraderBot-specific modifications. The key changes:

**A. Context section — TraderBot-specific context requirements:**

Replace the generic `{PROBLEM_DESCRIPTION}` with a structured context block:

```markdown
## Context

**Category:** {weather|economics|crypto|sports|politics|...}
**Cycle ID:** {CYCLE_ID}
**Evaluation Period:** {DATE_RANGE}
**Agent Performance:** {PERFORMANCE_SUMMARY}

### Suboptimal Outcomes
{OBSERVED_LOSSES_OR_SUBOPTIMAL_DECISIONS_WITH_FULL_EVIDENCE_CHAINS}

### Relevant Files
{TRADERBOT_SOURCE_FILES_AND_DATA_PATHS}

### Constraints
- One concept per cycle (DD-018 guardrail)
- Statistical rigor as foundational philosophy (DD-018 guardrail)
- Kalshi market specificity: the goal is better performance on Kalshi markets, not general prediction improvement
- TraderBot provides analysis and guardrails; the agent makes decisions
- Evidence must reference specific data sources: decisions.db, forecast_snapshots, market data, agent logs
```

**B. Guardrails — TraderBot-specific additions:**

The agent-guardrails.md from the framework is used as-is, with these TraderBot-specific additions injected:

```markdown
## TraderBot-Specific Guardrails

### Statistical Rigor (Non-Negotiable)

1. **Every probability claim must be calibrated.** "70% confident" must mean the event resolves YES 70% of the time. Reference calibration data from `traderbot__weather_accuracy` or equivalent category tools.

2. **Every recommendation must include a confidence interval.** Point estimates without uncertainty bounds are rejected. Reference the `confidence_interval` field from `traderbot__weather_forecast_prob` or equivalent.

3. **Correlation is not causation.** When claiming a data source improves outcomes, provide evidence of causal relationship, not just statistical correlation. Consider confounding variables.

4. **Historical performance is not future performance.** Backtesting results must include sample size, time period, and market conditions. A strategy that worked in a bull market may fail in a bear market.

5. **Sample size matters.** Conclusions drawn from fewer than 30 observations are flagged as low-confidence. Flag them explicitly: `[LOW-CONFIDENCE: n=12 observations]`.

### Kalshi Market Specificity

1. **The goal is Kalshi performance, not general prediction accuracy.** A weather model that's better at predicting temperature in general but worse at predicting Kalshi settlement prices is not an improvement.

2. **Market structure matters.** Consider how Kalshi questions are structured (T-type threshold, B-type bucket), how liquidity affects fill probability, and how the timing of trades relative to settlement affects profitability.

3. **Edge is relative to market price, not absolute accuracy.** A forecast that's right 60% of the time when the market says 50% has more edge than a forecast that's right 90% of the time when the market says 88%.

### Division of Responsibilities

1. **TraderBot provides analysis, not decisions.** Proposals that move TraderBot toward making trading decisions (direction, confidence thresholds) are out of scope. The agent decides; TraderBot provides data.

2. **Workspace files are prebuilt (DD-008).** Proposals that require agent customization are out of scope. Improvements must be on the TraderBot side (data, analysis, tools, guardrails).

3. **One concept per cycle.** "Implement machine learning models to improve analysis performance" is one concept even if it applies across multiple pipeline layers. Break it into separate cycles.
```

**C. Success Criteria — TraderBot-specific verification:**

```markdown
## Success Criteria

Define how we know the improvement worked. Required before the proposal can converge.
Each criterion must be verifiable — a command to run, output to expect, or condition to check.

Format:
- [ ] Criterion description — `command or check` → expected result

Required criteria for every proposal:
- [ ] Backtest over 6-month period shows improvement → `traderbot experiment run --treatments control,variant --category {CATEGORY}` → Sharpe ratio ≥ 1.0, win rate ≥ 55%
- [ ] No regression in other categories → `traderbot experiment run --treatments control,variant --category {ALL_ENABLED_CATEGORIES}` → no category shows degradation > 5%
- [ ] Improvement is statistically significant → paired t-test or Wilcoxon signed-rank test on trade-level P&L → p-value < 0.05
```

**D. Dispute Log — unchanged from agent-debate:**

The dispute log format is used as-is. The TraderBot-specific guardrails above define what counts as evidence, but the dispute mechanics (strikethrough, counter, status tracking) are protocol-level and don't need modification.

#### 4. Improvement Framework Round 5 — Final Selection and Implementation

DD-018 left Round 5 undefined. Based on the full architecture now in place, Round 5 is:

**Round 5: Final Selection and Implementation**

1. **SysAdmin selects the top proposal** based on:
   - Statistical rigor of the hypothesis (Round 4 assessment)
   - Feasibility (Dev-Liaison assessment from Round 4)
   - Expected improvement in decision quality relative to implementation effort
   - Expected increase in Kalshi profitability for the relevant category

2. **Root cause classification determines the implementation path:**

   | Root cause | Implementation path | Owner |
   |---|---|---|
   | TraderBot code (data pipeline, analysis model, tool design) | GitHub issue with experiment design | SysAdmin files, Dev-Liaison writes test module |
   | Agent workspace (instructions, decision framework) | Update workspace template files | SysAdmin updates, re-propagates to agents |
   | Both (new module + new instructions) | Two coordinated GitHub issues | SysAdmin coordinates, Dev-Liaison implements TraderBot side |

3. **Dev-Liaison writes the test module** implementing the proposal as a `TreatmentInterface` subclass for the experiment harness. The test module is placed in the test-lab workspace.

4. **SysAdmin deploys to test-lab** via `traderbot experiment run --treatments control,variant --category {CATEGORY} --replicates 3`.

5. **Results are evaluated** against the success criteria defined in Round 4. If criteria are met, the improvement is promoted:
   - TraderBot code changes → GitHub issue for human review and merge
   - Workspace template changes → SysAdmin updates and re-propagates
   - Both → Coordinated deployment after both sides pass review

6. **If criteria are not met**, the cycle iterates: SysAdmin documents the failure in `test-lab/RESULTS.md`, the Dev-Liaison analyzes why, and the debate cycle restarts with the new information (one concept per cycle).

**Consequences**:
- Agent-debate provides the *protocol* (TEMPLATE.md, guardrails, dispute mechanics) — not the orchestration
- SysAdmin orchestrates debates natively through OpenClaw's `sessions_spawn`, `sessions_send`, and `sessions_yield`
- The bash orchestrate.sh script is NOT used — SysAdmin replaces it
- Multi-model debate is achieved through OpenClaw's per-spawn model configuration
- Debate sub-agents are ephemeral — created for a cycle, terminated after convergence
- TEMPLATE.md is modified with TraderBot-specific context requirements, guardrails, and success criteria
- Round 5 is now fully defined: final selection by SysAdmin, implementation path determined by root cause classification, Dev-Liaison writes test modules, SysAdmin deploys and evaluates
- The Dev-Liaison's role as Watcher is preserved across all rounds, providing feasibility perspective without voting on Round 3
- Model diversity is ensured by using models from at least 2 different providers per debate cycle
- The debate workspace is in `~/.openclaw/workspace/test-lab/debate-{cycle-id}/` — ephemeral and isolated from agent production workspaces

#### 5. OpenClaw sessions tool validation

Investigation of OpenClaw's `sessions_spawn`, `sessions_send`, and `sessions_yield` confirms the agent-debate integration is feasible as designed. Key findings:

**`sessions_spawn` — confirmed capabilities:**

- **Model overrides per spawn**: `model` and `thinking` parameters allow different models per sub-agent. SysAdmin can spawn 4 debate sub-agents each with a different model (e.g., Claude Opus, GPT-5, Gemini).
- **`agentId` targeting**: Sub-agents can be spawned targeting a specific configured agent, inheriting that agent's tool allowlist and sandbox settings. This means `sessions_spawn({ agentId: "weather", model: "gpt-5" })` creates a weather agent sub with GPT-5 that has the weather category's tool allowlist.
- **`sandbox: "require"`**: Forces sandboxing on the spawned child. This is critical for debate sub-agents — even SysAdmin subs should be sandboxed during debates to prevent resource access outside the debate workspace.
- **`context: "isolated"`**: Creates a clean session with no inherited transcript. This is the correct mode for debate sub-agents — each debate cycle starts fresh.
- **Non-blocking**: Returns immediately with `runId` and `childSessionKey`. SysAdmin can spawn all 4 sub-agents and then coordinate via `sessions_send`.

**`sessions_send` — confirmed capabilities:**

- **Fire-and-forget** (`timeoutSeconds: 0`): Enqueue a message and return immediately. This is how SysAdmin delivers debate prompts and collects responses.
- **Wait for reply**: Set a timeout and get the response inline. Useful for synchronous round coordination.
- **A2A follow-up loop**: `maxPingPongTurns` (0-20, default 5) allows bounded agent-to-agent exchanges. For debate cross-examination, we use fire-and-forget with manual coordination rather than the ping-pong loop, because debate rounds need more control over the flow.
- **Messages are marked as inter-session data**: The receiving agent sees `[Inter-session message ... isUser=false]` in its prompt, which clearly distinguishes debate input from user commands.

**`sessions_yield` — confirmed capabilities:**

- Ends the current turn and waits for follow-up sub-agent results. SysAdmin uses this after spawning all 4 debate agents to wait for their responses.
- Prevents polling loops — the recommended pattern for coordinating sub-agent results.

**Depth and tool access:**

- `maxSpawnDepth` defaults to 1 (leaf sub-agents only, no recursive spawning). For the debate pattern, depth 1 is sufficient — SysAdmin spawns debate sub-agents, they don't spawn further children.
- If `maxSpawnDepth >= 2`, depth-1 orchestrator sub-agents get `sessions_spawn`, `subagents`, `sessions_list`, `sessions_history`. For our design, SysAdmin is already at the orchestrator level and has these tools. Debate sub-agents are leaf agents (depth 1) and do NOT get session orchestration tools.
- Debate sub-agents need `sessions_send` for cross-examination, but this is a messaging tool, not an orchestration tool. A deployable restrictive policy must include it in the explicit `allow` list and, for sandboxed agents, in the nested sandbox gate.

**Configuration for debate sub-agents:**

> **Historical non-deployable combined pseudocode:** The block below mixes
> `allow` and additive `alsoAllow`, includes unvalidated agent fields, and embeds
> a `sessions_spawn(...)` call inside a JSON5 fence. It records orchestration
> intent only; it is not valid `openclaw.json` syntax.

```json5
// SysAdmin agent configuration (orchestrator)
{
  id: "sysadmin",
  sandbox: { mode: "off" },  // DD-036
  tools: {
    allow: ["read", "write", "exec", "github"],
    alsoAllow: [
      // SysAdmin management tools (DD-036)
      "traderbot__health", "traderbot__auth_check", "traderbot__profile_list",
      "traderbot__profile_update", "traderbot__performance", "traderbot__audit",
      "traderbot__learnings", "traderbot__cron_setup", "traderbot__session_send",
      "traderbot__experiment", "traderbot__data_status", "traderbot__ws_status",
      "traderbot__backfill",
      // Session orchestration for debate coordination
      "sessions_spawn", "sessions_send", "sessions_yield",
      "sessions_list", "sessions_history", "subagents",
      // Knowledge retrieval
      "traderbot__reference",
    ],
    deny: [
      "traderbot__trade", "traderbot__scan", "traderbot__analyze",
      "traderbot__weather_*", "traderbot__market_edge", "traderbot__market_prices",
    ],
  },
  subagents: {
    allowAgents: ["weather", "economics", "crypto", "sports", "politics", "sysadmin", "dev-liaison"],
    requireAgentId: true,  // Force explicit agent selection for debate subs
  },
}

// Debate sub-agent spawn configuration (SysAdmin spawns these dynamically)
// Each sub-agent gets the TARGET agent's tool allowlist + debate-specific tools
// Example: spawning a weather agent sub with GPT-5 for a debate cycle
sessions_spawn({
  agentId: "weather",          // Inherit weather agent's tool allowlist
  model: "openai/gpt-5",       // Model override for perspective diversity
  sandbox: "require",            // Force sandboxing even for sysadmin subs
  context: "isolated",          // Clean session, no inherited transcript
  prompt: "You are participating in a TraderBot improvement debate...",
  // Debate sub-agents are ephemeral — terminated after convergence
})
```

**Important constraints confirmed:**

1. **Sandbox inheritance guard**: If the requester (SysAdmin) is unsandboxed and spawns a sub-agent targeting a sandboxed agent (weather), the sub-agent WILL be sandboxed (inherit the target agent's sandbox settings). This is the correct behavior for debate subs.

2. **Tool profile inheritance**: Sub-agents spawned with `agentId` inherit the target agent's tool allowlist AND deny list. A weather debate sub-agent gets `traderbot__weather_*` tools but NOT `traderbot__trade` or SysAdmin management tools. This enforces the same category isolation (DD-011, DD-036) during debates.

3. **Cross-examination communication**: Debate sub-agents need `sessions_send` to communicate during cross-examination rounds. This must be added to their `alsoAllow` list since leaf sub-agents don't get messaging tools by default. SysAdmin adds this when spawning each debate sub-agent.

4. **Ephemeral sessions**: Debate sub-agents are created for a single cycle and terminated after convergence. OpenClaw's sub-agent lifecycle supports this — `sessions_spawn` creates isolated sessions, and they can be terminated via the `subagents` tool when the cycle completes.

5. **No recursive spawning**: Debate sub-agents are leaf agents (depth 1). They cannot spawn further children. This prevents debate sub-agents from spawning their own sub-agents, which maintains the orchestrated debate structure.
