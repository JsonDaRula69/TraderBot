# TraderBot v2 — Installation and Deploy

> This document details the complete installation and first-time configuration (deploy) flow for TraderBot v2, grounded in DD-001 through DD-009, DD-022, DD-023, DD-037.

---

## Installation Method

**pipx is the sole supported installation method** (DD-001). All previous methods (plain pip, venv, installer script) are retired.

```bash
pipx install traderbot
```

This command:
1. Checks OS version and dependencies (including OpenClaw)
2. Downloads and installs any missing required dependencies
3. Downloads and installs the TraderBot package (minimal, category-specific modules only for the user's OS)
4. Only installs required dependencies and TraderBot modules for the user's OS — minimizing unnecessary disk usage

**What gets retired** (DD-001):
- `install/traderbot-installer.sh` — removed
- `traderbot bootstrap` command (without `--full`) — removed (DD-005)
- Plain pip and venv installation instructions — removed
- Any code paths for git/source installation — removed

---

## OS-Aware Setup

`traderbot deploy` detects OS capabilities upfront and adjusts prompts and messaging accordingly (DD-006):

| Feature | macOS | Linux (GUI) | Linux (headless) | Windows |
|---|---|---|---|---|
| Phase 5 Docker sandbox | Deferred; no Phase 4 operation | Same | Same | Same |
| Infisical | Existing loopback instance or encrypted fallback | Same | Same | Same |
| Service manager detection | launchd | systemd | systemd | Task Scheduler |
| Service template resolution | `shutil.which('traderbot')` + `.resolve()` | Same | Same | Same |

Service template paths use `{placeholder}` syntax resolved at install time via `shutil.which('traderbot')` + `.resolve()` (DD-007). This handles pipx virtualenv backend variations (venv vs uv) and user-customizable `PIPX_BIN_DIR` locations. Templates are stored as package data in `src/traderbot/services/` and read via `importlib.resources`.

---

## Deploy Flow (8 Steps)

The first-time configuration process is called **"deploy"** (not "bootstrap") to avoid confusion with OpenClaw's unrelated bootstrap function (DD-005).

### Step 1: OpenClaw Config

- Detect `openclaw` on PATH; installation requires an explicit interactive/config approval
- Inventory every configured agent/workspace, selected config/SecretRef, token metadata, injection plan, heartbeat desired state, and bootstrap cron before category/user-state mutation
- Require existing `main`; run `openclaw setup --baseline --json` only when it is genuinely absent and setup is explicitly approved, then restart complete preflight
- Verify Gateway RPC read-only with `openclaw gateway status --json --require-rpc`; never use setup or doctor as a probe

### Step 2: SysAdmin Setup

- Use existing agent `main` only; never call `agents add main`. Its inventory workspace is authoritative, and an optional user path is only an equality assertion.
- Preflight, then inject the SysAdmin `AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `USER.md`, `SESSION-STATE.md`, and `.learnings/` conventions into that exact workspace. The canonical five-tool guidance is in `AGENTS.md ## Tools`; TraderBot does not create/update `TOOLS.md` or `HEARTBEAT.md` and preserves legacy files exactly.
- Preflight the one-shot bootstrap contract, but delay `openclaw cron add --name traderbot-main-at-5m --at "5m" --session isolated --agent main --message "<SysAdmin activation intent>" --delete-after-run --json` until every selected agent/config postcondition passes (DD-023)
- Current OpenClaw inventory stores `agentId`, `enabled`, typed `schedule`, `sessionTarget`, `wakeMode`, typed `payload`, and `deleteAfterRun`. The submitted relative `5m` may be normalized to an absolute `at` timestamp; deploy validates that it semantically represents the managed five-minute one-shot delay. Exact managed contracts are reused, conflicts fail closed, and new jobs are re-read before success.
- This is the only agent scheduling automation requested at deploy time. OpenClaw Gateway owns it; all recurring cron/heartbeat schedules remain dormant until explicitly approved for activation.
- Create sysadmin profile: `traderbot profile create sysadmin --mode paper --risk-multiplier 0.001 --all-categories`
- Assign the `main_token` profile-token document to agent `main` via OpenClaw SecretRef
- Verify: `traderbot auth check --json`

### Step 3: Category Selection

- Present the exact categories: `weather`, `economics`, `crypto`, `sports`, `politics`, `entertainment`, `financial`, `world`, `other`
- User selects one or more
- Config mode supports only `mode: "backtest"` until Phase 7 lifecycle transitions; paper/live are rejected before mutation
- Existing selected agents adopt their configured inventory workspace unchanged; an explicit path mismatch fails global preflight
- Missing selected agents require an explicit absolute path plus `approvals.create_agents: true`; inventory is re-read after every add exit, including nonzero/malformed output
- This original-plan creation contract is current for Phase 4. Existing-agents-only installation plus per-agent paper/live, channel binding, and same-name Telegram accounts are deferred to Phase 4b.
- Reject linked, same-file, normalized-equal, and overlapping workspace roots across every configured agent, including unselected agents
- For each selected category:
  - For missing selected agents only: `openclaw agents add <category> --workspace <approved-absolute-path> --non-interactive --json`
  - Inject category workspace files (`AGENTS.md`, `SOUL.md`, and `IDENTITY.md`); exact-five-tool guidance is in `AGENTS.md ## Tools`
  - Preserve user heartbeat cadence by default; an explicitly approved dormant state writes `heartbeat.every: "0m"` through OpenClaw config only
  - Create profile: `traderbot profile create <category> --mode backtest --categories <category>`
  - Preserve an exact profile-token SecretRef, atomically create an absent mapping, and fail closed on any mismatch
- Do not invoke doctor implicitly; repair or migration of user-owned OpenClaw state requires a separate explicit operator action
- Steps 1-3 complete before secret or database mutation; failures stop later steps

### Step 4: Infisical and API Tokens

- Probe a configurable loopback HTTP Infisical origin at `GET /api/status` with an explicit one-second timeout and `trust_env=False`; lower-level requests reject remote origins before network access. Production `http://localhost:8080` is local to macpro-linux, where Infisical runs beside TraderBot. Isolated development fakes do not prove that integration; Final-Wave QA validates it on the target host.
- Refuse SDK use when any HTTP/HTTPS/ALL proxy environment variable is nonempty, because the supported SDK has no public proxy-free transport
- After universal-auth login with `cache_ttl=None`, check both required project roots with non-value `list_secrets`; denial closes the SDK client and reports machine-bound `LocalEncryptedStore` through `SecretsStore`
- Reuse a complete valid stored Kalshi pair without rewriting it
- Otherwise obtain only `kalshi_api_key` and `kalshi_private_key_pem`: hidden prompts in interactive mode or environment-variable-name references in config mode
- Keep secret-bearing values redacted on repr, string, serialization, exception, and logging surfaces
- Reject raw secret fields, incomplete references, empty API keys, and non-RSA/malformed PEM before the first secret write; incomplete state requires `reconcile_incomplete`, while malformed or differing state separately requires `replace_existing`
- Validate locally only; do not sign or send a live Kalshi request
- Post-read every set; preserve first/second/no-op partial state, report only verified canonical written/pending names, and skip durable matching fields on rerun
- Reject linked, escaping, wrong-type, or foreign-owned encrypted-local paths; harden accepted POSIX directories/files to `0700`/`0600` and revalidate before atomic publication
- Do not start Docker, create a machine identity, or prompt/store inactive and keyless provider credentials

### Step 5: Database Creation

- Run `init_schema()` with every currently registered global migration, then construct one `SQLiteConnectionPool`
- Provision only selected category databases through `DatabaseAccess.writable_decisions` at `{mode}-{name}/db/decisions.db`; initial deploy mode is `backtest`
- Verify each selected database has the current seven-table domain schema and accepts a committed writable transaction
- Use canonical SysAdmin only with `all_agent_decisions` for read-only enumeration; never create a SysAdmin decisions database
- Create or validate the owner-only embedded Chroma root, acquire the ownership lock, and verify the pinned Rust client/backend
- Validate and report the exact five-name shared manifest, but create no collection until a real embedding write supplies an explicit dimension
- Attempt Chroma close before pool shutdown on every path, retain both cleanup identities if both fail, and release the ownership lock even if client close fails
- Step 5 completion permits the wizard to continue through typed Steps 6-8; only all eight complete produces `deployment_complete: true`

### Step 6: Backfill

- Run `traderbot backfill --months 6 --json`
- **All data sources begin collection at install time** (DD-027), not just enabled categories
- This ensures backtesting data is available for any category the user might enable later
- The optional legacy collector source is opened read-only and copied in idempotent 1,000-row transactions; a missing default source is a warning
- Kalshi weather data spans current and archive tiers around one runtime cutoff, with tier-correct candles and one forecast call per unique event
- JSON stdout is one typed result line; progress and Rich output use stderr
- Exit codes are 0 complete, 1 partial/runtime failure, and 2 invalid input
- The deploy wizard invokes the same typed `run_backfill` request/dependency boundary and embeds the result without a second JSON stream
- Explicit collector input is prepared once before secrets/runtime construction, consumed from the immutable snapshot, and never reopened by Step 6

### Step 7: Phase 5 Sandbox Stub

- Step 7 is a read-only Phase 5 sandbox stub. Phase 4 starts no Docker sandbox, simulation, backtest, trading lifecycle, or agent schedule.
- Agent backtesting activation and the SysAdmin lifecycle protocol are future behavior, not Phase 4 execution.
- The stub performs one read-only strict inventory of the exact Gateway-owned bootstrap job. It never adds, updates, deletes, runs, or recreates a cron.
- A persisted exact job passes. Post-execution absence from `deleteAfterRun: true` is recorded as an action-required partial state, not silently passed or recreated.
- Owner-only deploy state records prior registration and per-step fingerprints; unchanged completed late steps are reused, while incomplete or affected downstream steps rerun.
- Before factories, the selected data root is checked without creation for absolute containment, linked ancestors, directory type, current owner, and exact `0700`; resumability state additionally requires a no-follow owner-owned regular `0600` file no larger than 1 MiB.
- Retained completed and authoritatively deleted one-shots are distinct lifecycle states that reach the read-only Step 7 partial outcome without recreation; unknown absence and disabled/error/conflicting inventory fail closed.
- Persisted `bootstrap_registered: false` plus missing inventory is unknown absence, not a fresh install. Descriptor metadata is revalidated after no-follow open before any resumability state is trusted.

### Step 8: Verification

- `traderbot verify --categories ...` runs a stable, dependency-aware read-only graph.
- Gateway health uses `gateway status --json --require-rpc`; selected inventory, workspaces, config, exact bootstrap cron, and persisted heartbeat `0m` state reuse the typed OpenClaw read seams.
- Exact real-auth mode and selected five-field token documents are read from the currently selected durable SecretsStore without installing adapters or revealing token values.
- Kalshi authentication uses signed `GET /portfolio/balance`; public market data is not authentication proof.
- Global and current-mode category databases use no-follow owner checks, SQLite URI `mode=ro`, `query_only`, `quick_check`, and exact schema/table/index manifests. A SysAdmin decisions database is forbidden; writability is never probed.
- Active daemon health requires a bounded loopback streamable-http MCP handshake and actual `health` call. Daemon-owned Chroma is proved from this health response and is never opened by the verifier.
- Infisical status and both non-value project-root access checks share one owned selection; encrypted local fallback is reported as degraded. Production loopback is macpro-linux-local, not the development host.
- JSON output is exactly one stdout line; the Rich table is stderr-only. Exit codes are 0 for OK, 1 for failed/degraded, and 2 for invalid input.
- The deploy wizard composes the same `VerificationRequest` and read-only graph, embeds every typed check in its one JSON result, and still runs safe verification after a partial backfill.
- The explicit data root is shared unchanged across database creation, backfill, verification, and deploy state; Kalshi reads are canonical read-only production requests.

---

## What Gets Retired

| Component | What | Reason |
|---|---|---|
| `install/traderbot-installer.sh` | Entire installer script | pipx-only install (DD-001) |
| `traderbot bootstrap` (without `--full`) | Legacy command | Replaced by `traderbot deploy` (DD-005) |
| `src/traderbot/auth.py` | Keyring-based credential management | Replaced by Infisical + SecretsStore (DD-037) |
| `src/traderbot/master_password.py` | Master password system | Retired — paper mode auto-authenticates (DD-024) |
| `src/traderbot/profiles/tokens.py` | Fernet token storage | Simplified — Infisical manages tokens (DD-037) |
| `src/traderbot/profiles/auth.py` | Keyring resolution | Replaced by SecretsStore (DD-037) |
| `keyring` dependency | pip dependency | Removed from pyproject.toml |
| `~/.traderbot/.env` | Plaintext credentials | Migrated to Infisical, then deleted |
| `~/.traderbot/.master_key` | Master key file | No longer needed for paper mode auth |

---

## Idempotency

All deploy operations are idempotent and resumable. Inventory resources before mutation, reuse matching agents, profiles, tokens, and cron identities, and heal only missing selected-agent state. A conflicting user-owned resource fails closed; deploy never deletes agents, workspaces, tokens, cron jobs, or user content as rollback.
