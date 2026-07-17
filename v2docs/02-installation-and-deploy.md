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
| Keyring | Available | Available | Not available — skip keyring questions | Available |
| Docker | Offered | Offered | Offered (required for agents) | Offered |
| Infisical | Offered | Offered | Offered (Docker required) | Offered |
| Service manager | launchd | systemd | systemd | Task Scheduler |
| Service template resolution | `shutil.which('traderbot')` + `.resolve()` | Same | Same | Same |

Service template paths use `{placeholder}` syntax resolved at install time via `shutil.which('traderbot')` + `.resolve()` (DD-007). This handles pipx virtualenv backend variations (venv vs uv) and user-customizable `PIPX_BIN_DIR` locations. Templates are stored as package data in `src/traderbot/services/` and read via `importlib.resources`.

---

## Deploy Flow (8 Steps)

The first-time configuration process is called **"deploy"** (not "bootstrap") to avoid confusion with OpenClaw's unrelated bootstrap function (DD-005).

### Step 1: OpenClaw Config

- Detect `openclaw` on PATH
- If missing: install via `npm install -g @openclaw/cli` (requires Node.js)
- Run `openclaw setup` — creates the `main` agent and configures gateway, model provider, web search, comms channels
- Verify: `openclaw gateway status`

### Step 2: SysAdmin Setup

- Inject sysadmin workspace files (AGENTS.md, SOUL.md, TOOLS.md, IDENTITY.md, HEARTBEAT.md, USER.md, SESSION-STATE.md, .learnings/) into the chosen agent's workspace
- Register one-shot bootstrap job: `openclaw cron add --at "5m" --session isolated --agent main --delete-after-run` (DD-023)
- No other cron or heartbeat jobs registered at deploy time — SysAdmin activates them during its startup protocol
- Create sysadmin profile: `traderbot profile create sysadmin --mode paper --risk-multiplier 0.001 --all-categories`
- Assign profile token to sysadmin agent via OpenClaw SecretRef
- Verify: `traderbot auth check --json`

### Step 3: Category Selection

- Present available categories: Weather, Economics, Politics, Sports, Crypto, Entertainment, Science & Technology, Health, Social
- User selects one or more
- For each selected category:
  - `openclaw agents add <category>` (creates OpenClaw agent)
  - Inject category workspace files (AGENTS.md, SOUL.md, TOOLS.md, IDENTITY.md, etc.)
  - Configure agent heartbeat: `heartbeat.every: "0m"` (dormant — SysAdmin activates during startup)
  - No cron jobs registered at deploy time
  - Create profile: `traderbot profile create <category> --mode backtest --categories <category>`
  - Assign profile token to category agent via OpenClaw SecretRef
- After all agents: `openclaw doctor`

### Step 4: Infisical and API Tokens

**Step 4a: Infisical health check**
- Check Infisical server at `http://localhost:8080`
- If not running: offer to start (Docker), connect to existing, or fall back to local encrypted storage
- Verify machine identity is authenticated

**Step 4b: API token entry** (per category, validated immediately)
- Global tokens (all agents): Kalshi API key + PEM, VoyageAI, NewsAPI, Twitter, Reddit
- Category-specific tokens (only if category enabled):
  - Weather: OpenWeatherMap
  - Economics: FRED
  - Crypto: CoinGecko (with tier detection)
  - Sports: TheSportsDB
- Each token validated against its service before storing

**Step 4c: Machine identity configuration**
- Create Infisical machine identity "traderbot-service" with read/write access
- Store service token in OpenClaw SecretRef (`INFISICAL_TOKEN`)
- Verify TraderBot can authenticate with Infisical

### Step 5: Database Creation

- Create `~/.traderbot/traderbot.db` (global, schema init)
- Create `~/.traderbot/sysadmin/db/decisions.db`
- For each category: create `~/.traderbot/paper-{category}/db/decisions.db` (note: directory is `paper-{category}` even though mode is `backtest` — the directory name doesn't change when mode changes)
- Initialize ChromaDB collections (news, data_points, market_patterns, news_signals, market_conditions)
- Verify: all DB paths writable, ChromaDB accessible

### Step 6: Backfill

- Run `traderbot backfill --months 6 --json`
- **All data sources begin collection at install time** (DD-027), not just enabled categories
- This ensures backtesting data is available for any category the user might enable later
- Progress reporting during backfill

### Step 7: Simulation Start

- All agents begin in **backtesting mode** (not paper trading) — DD-017, DD-019
- SysAdmin is activated with its bootstrap job
- SysAdmin follows its activation protocol (DD-023):
  1. Verify TraderBot service is running
  2. Verify data streams are fresh
  3. Register essential cron jobs (health-check, error-logger)
  4. Enable own heartbeat
  5. For each category (one at a time):
     a. Verify category data available
     b. Activate agent in backtesting mode
     c. Register backtesting oversight jobs
     d. Monitor progress
     e. Promote when deployment bar is met
- Docker sandbox started for each category agent (mandatory, DD-010)

### Step 8: Verification

- OpenClaw gateway reachable
- All agent tokens resolve correctly
- Kalshi credentials valid (`traderbot auth check --json`)
- All cron jobs visible via `openclaw cron list`
- All DB paths writable
- ChromaDB accessible and collections initialized
- Docker sandbox running
- Infisical integration verified (all projects accessible, tokens valid, rotation timer started)
- Print summary with agent names, profiles, tokens, and status

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

All deploy operations are idempotent — safe to run twice without side effects (per AGENTS.md). Before creating a resource (cron job, service, agent, profile), remove or replace any existing one with the same name. Use `--replace` semantics for cron job registration.
