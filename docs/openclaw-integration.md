# OpenClaw Integration

How TraderBot integrates with the OpenClaw agent framework — lifecycle management, workspace files, isolated cron tasks, hooks, and the full install flow.

## Installation Lifecycle

The TraderBot installer (`install/traderbot-installer.sh`) manages the full OpenClaw lifecycle in three phases:

### Phase 1 — OpenClaw Bootstrap
1. **Detect** if `openclaw` CLI is installed
2. If missing: prompt to install via `npm install -g openclaw`; runs `npm approve-scripts openclaw` for bundled plugins; rehashes PATH if npm global bin is not on PATH
3. **Detect** if gateway is running
4. If not running: prompt to install service (`openclaw gateway install` with error surfacing) and start (`openclaw gateway start`)
5. Wait for gateway readiness (polls up to 30s)
6. **Run baseline setup** (mandatory): `openclaw setup --workspace ~/.openclaw/workspace` — initializes config defaults and workspace

### Phase 2 — Agent Creation + Hooks + Validation + Guided Setup
1. **Create default agent**: `openclaw agents add main --non-interactive --workspace ~/.openclaw/workspace`
2. **Enable bundled hooks**:
   - `openclaw hooks enable command-logger`
   - `openclaw hooks enable session-memory`
3. **Run repair**: `openclaw doctor --fix`
4. **Validate config**: `openclaw config validate`
5. **Optional — LLM provider**: `openclaw configure --section models` (interactive wizard)
6. **Optional — runtime health**: `openclaw doctor`

### Phase 3 — Interactive Config (API Credentials → Profiles → Category Agents)
API credentials are collected first, then:

1. **Sysadmin setup**: sysadmin profile created and assigned to agent `main`
2. **Category agent loop** (per selected category):
   - Agent auto-created via `openclaw agents add <name> --non-interactive --workspace ~/.openclaw/workspace`
   - Profile created with `--mode paper|live` and `--categories <cat>`
   - Profile assigned to agent via `traderbot profile assign`
   - Systemd service installed
   - Isolated cron jobs registered via `traderbot cron setup-heartbeat-tasks --agent <name>`
3. **Data pipeline timers installed** via `install-data-pipeline.sh`
4. **Sysadmin cron jobs registered** via `traderbot cron setup-heartbeat-tasks --agent main`
5. **Optional — Docker sandbox**: prompt to build and configure sandbox for category agents

### Docker Sandbox

Category agents run inside OpenClaw's Docker sandbox for filesystem isolation. Sysadmin (main) is NOT sandboxed.

Config at `agents.defaults.sandbox`:

| Setting | Value |
|---|---|
| `mode` | `non-main` |
| `backend` | `docker` |
| `scope` | `agent` |
| `workspaceAccess` | `rw` |
| `docker.image` | `traderbot-sandbox:bookworm-slim` |
| `docker.network` | `bridge` |
| `docker.readOnlyRoot` | `true` |
| `docker.capDrop` | `["ALL"]` |
| `docker.memory` | `1g` |

Build image: `bash install/docker/build-sandbox.sh`

### Uninstallation

`traderbot uninstall` interactively prompts for each removal category:

1. **System services** (always removed): systemd services, timers, wants symlinks, `daemon-reload`
2. **User-level systemd**: OpenClaw gateway service
3. **OpenClaw cron jobs**: each job removed by ID
4. **User data** (prompted): `~/.traderbot/` including profiles, credentials, logs
5. **Repository** (prompted): `~/traderbot/`

Flags: `--json` for machine-readable output. No `--remove-data` or `--remove-repo` flags needed — prompts handle it.

## OpenClaw Configuration

### Heartbeat Configuration

Each agent has `isolatedSession: true` and `lightContext: true` configured in their heartbeat settings. This means every heartbeat turn runs in a fresh session with minimum bootstrap context (only `HEARTBEAT.md`).

Configured via `cli/cron.py:_write_heartbeat_config()` which writes directly to `openclaw.json`. Heartbeat settings are not exposed through the `openclaw` CLI, so this is the only method.

```json
{
  "heartbeat": {
    "every": "30m",
    "isolatedSession": true,
    "lightContext": true
  }
}
```

### Bootstrap Hook

Deployed at `~/.openclaw/hooks/traderbot-bootstrap/` and enabled via `openclaw hooks enable agent-bootstrap`. Fires on `agent:bootstrap` before workspace files are injected. Checks:

1. SESSION-STATE.md for PENDING/ESCALATE entries
2. HEARTBEAT_DATA.md for circuit breaker state (HALT/FULL_STOP)
3. Injects a Pre-Session Status block when issues are found

## Workspace File Architecture

### Auto-Injected Bootstrap Files (all 8 recognized basenames)

| File | Strategy | Purpose |
|---|---|---|
| `AGENTS.md` | Fenced merge | Trading rules, market types, decision loop |
| `SOUL.md` | Fenced merge | Agent personality, principles, autonomy |
| `TOOLS.md` | Fenced merge | CLI reference, auth tiers, tool autonomy |
| `IDENTITY.md` | Fenced merge | Prebuilt name, creature, vibe, emoji |
| `USER.md` | Init if missing | Human preferences (name, pronouns, style) |
| `HEARTBEAT.md` | Init if missing | Task schedule reference (cron handles execution) |
| ~~`BOOTSTRAP.md`~~ | Not used | Removed — all agents are prebuilt frozen identities |
| `MEMORY.md` | Init if missing | Long-term curated operational memory |

### Non-Bootstrap Files (explicitly referenced by agents)

| File | Loaded By | Purpose |
|---|---|---|
| `SESSION-STATE.md` | AGENTS.md (boot sequence) | WAL protocol — active positions, pending actions |
| `HEARTBEAT_DATA.md` | AGENTS.md (boot sequence) | Latest 7-step review, circuit breaker state |
| `.learnings/` | AGENTS.md (learning tasks) | Discovered patterns, errors, feature requests |

### Template Selection

`propagate_workspace_files()` selects templates by profile category:
1. Sysadmin (`categories=[ALL]` with min risk) → `workspace/` root templates
2. Weather agent (`categories=[WEATHER]`) → `workspace/weather/` templates if they exist
3. Other categories → `workspace/agent/` fallback

## Isolated Cron Architecture

Each agent gets 7 isolated cron jobs registered during install. Every job runs in a dedicated `cron:<jobId>` session — zero collision with trading or other tasks:

### Per-Agent Jobs (registered for every trading agent)

| Job | Interval | Purpose |
|---|---|---|
| `circuit-breaker-check` | 30m | `traderbot halt --json` |
| `data-forecast-check` | 30m | `traderbot data forecasts` |
| `news-scan` | 30m | `traderbot news-context` |
| `position-health` | 1h | `traderbot positions --json` |
| `performance-review` | 6h | `traderbot heartbeat --json` |
| `learning-promotion` | 6h | `.learnings/` recurrence >= 3 check |
| `pipeline-health` | 6h | Pipeline timers, data_points count |

### Sysadmin Jobs (registered for "main" agent)

| Job | Interval | Purpose |
|---|---|---|
| `fleet-health` | 30m | Agent circuit breakers, fleet status |
| `experiment-check` | 30m | New experiment designs from agents |
| `experiment-execution` | 30m | Process queued experiments |
| `learning-review` | 1h | Cross-agent learning patterns |
| `news-scan` | 2h | High-impact signals > 0.7 |
| `pipeline-health` | 3h | Timer status, data pipeline |

## Update Flow

Both `traderbot update` (Python) and `update_services()` (bash) refresh workspace files after pulling new code:

- **Replaced**: AGENTS.md, SOUL.md, TOOLS.md, IDENTITY.md, HEARTBEAT.md
- **Preserved**: USER.md, MEMORY.md, HEARTBEAT_DATA.md, SESSION-STATE.md, .learnings/ (configurable via `--heartbeat-every`).

The heartbeat loop also includes capability gap detection — scanning `.learnings/FEATURE_REQUESTS.md` for recurring feature requests that warrant human review. Entries with `Recurrence-Count >= 3` are promoted to `PENDING_REVIEW` status and surfaced for human evaluation.

### `systemEvent` — Interactive Alerts

Used for: **News/Sentiment Loop** (actionable events only)

When the news pipeline detects a high-impact event, it surfaces to the main session so the human can intervene if desired.

```json
{
  "sessionTarget": "main",
  "payload": {
    "kind": "systemEvent",
    "message": "ALERT: Fed emergency rate cut detected. This may affect 8 tracked markets. Run `traderbot sentiment rate-cut` for analysis."
  }
}
```

## Workspace Files

OpenClaw uses a file-based memory system. These workspace files are injected into every session by the Gateway:

### AGENTS.md

Operating rules and constraints for the TraderBot agent. Includes:
- Risk guard rails (immutable limits)
- Trading constraints (no shorting, binary outcomes)
- Market categories to track
- Preferred analysis approaches
- What requires human approval vs. what's autonomous
- Session startup instructions and memory management
- Self-learning protocol with human approval gates

### IDENTITY.md

Agent name, role, and vibe. Short and declarative.

### SOUL.md

Persona, boundaries, and behavioral principles. Defines how the agent communicates, what it values, and what it never does. TraderBot-specific principles include data-driven decisions, risk discipline, and transparency.

### TOOLS.md

Environment-specific tool notes — local paths, gotchas, CLI command reference, setup specifics. Skills define _how_ tools work; this file captures _our_ specifics.

### SESSION-STATE.md (WAL Protocol target)

Active working memory — the Write-Ahead Log. The agent writes critical state here **before** taking action, ensuring context survives crashes or context loss.

Updated by the Decision Loop with:
- Currently tracked markets
- Active positions and pending orders
- Recent signal summary
- Last heartbeat timestamp

### HEARTBEAT.md

Agent checklist — **instructions** for the OpenClaw agent to follow during heartbeat runs. The Gateway reads this file and injects it into the heartbeat prompt. The agent follows the checklist and either surfaces alerts or replies `HEARTBEAT_OK`.

Per the OpenClaw spec, HEARTBEAT.md is a **prompt file** (agent instructions), NOT a data output file. It supports `tasks:` blocks with per-task intervals for structured periodic checks.

Example:

```markdown
tasks:

- name: circuit-breaker-check
  interval: 30m
  prompt: "Run `traderbot halt` to check circuit breaker status."
- name: performance-review
  interval: 6h
  prompt: "Run `traderbot heartbeat --json` for the 7-step self-review cycle."

## General Instructions

- If circuit breaker is HALT or FULL_STOP, do NOT place new trades.
- If nothing needs attention, reply HEARTBEAT_OK.
```

### HEARTBEAT_DATA.md

7-step self-review output written by `traderbot heartbeat`. Contains performance metrics, adaptation results, circuit breaker state, system health, and alerts. This is the data file — separate from the instruction file (HEARTBEAT.md).

```markdown
## Last Heartbeat: 2026-04-20T12:00:00Z

### Performance
- Win rate: 64% (45 trades)
- Daily P&L: +23.00 USD

### Adaptation
- Edge threshold: increase (magnitude 0.0234, confidence 0.78)

### Circuit Breaker
- Level: NORMAL
- Daily loss: 0.45%

### System Health
- API: available
- DB: ok
```

### USER.md

Human profile — name, preferred address, timezone, and personal context. Trading preferences (risk tolerance, market interests) are included as a subsection since they are specific to this human's trading style.

### .learnings/ Directory

Self-improvement logs, following the pattern from `peterskoett/self-improving-agent`:

- **LEARNINGS.md**: Corrections, insights, better approaches discovered
- **ERRORS.md**: API errors, failed orders, unexpected states
- **FEATURE_REQUESTS.md**: Capabilities the agent discovers it needs

Entries use structured metadata:
```markdown
## Entry: KALSHI-001
**Logged**: 2026-04-20T14:30:00Z
**Pattern-Key**: illiquid-market-slippage
**Recurrence-Count**: 4
**Priority**: high
**Status**: active
### Learning
Markets with open_interest < 500 experience significant slippage on orders > 5 contracts.
### Action
Added liquidity threshold to risk/limits.py
```

When Recurrence-Count >= 3 across 2+ tasks within 30 days, the agent promotes the learning to PENDING_REVIEW status. PENDING_REVIEW entries are flagged for human review during heartbeat — they are never auto-committed to AGENTS.md.

### Feature Requests (Capability Gaps)

The `FEATURE_REQUESTS.md` file tracks capabilities the agent discovers it needs during operation. When the agent encounters a gap (e.g., no data feed for a market category, missing tool, insufficient signal), it logs a `feature_request` entry:

```markdown
## Entry: FEAT-001
**Logged**: 2026-04-20T14:30:00Z
**Category**: feature_request
**Pattern-Key**: missing-sports-data
**Recurrence-Count**: 5
**Priority**: high
**Status**: PENDING_REVIEW
### Request
The agent frequently encounters sports markets but lacks real-time sports data feeds.
### Proposed Solution
Add sports data integration to improve sports market classification.
### Impact
Improved classification accuracy for ~15% of tracked markets.
```

Feature requests follow the same recurrence-based promotion model:
1. Each capability gap occurrence increments `Recurrence-Count`
2. When count >= 3 across 2+ tasks within 30 days, status → `PENDING_REVIEW`
3. PENDING_REVIEW entries surface in heartbeat reviews for human evaluation
4. Humans approve (implement), defer (lower priority), or reject (close entry)
5. Feature requests are NEVER auto-implemented

## WAL Protocol (Write-Ahead Log)

Borrowed from `proactive-agent`. Before the agent executes any trade:

1. **STOP** — do not place the order yet
2. **WRITE** — log the intended action to `SESSION-STATE.md` with reasoning
3. **THEN** — execute the order

This ensures every action is recoverable. If the agent crashes mid-trade, `SESSION-STATE.md` contains the intent and can be reconciled with actual positions on restart.

### WAL Promotion Flow

When a learning entry meets promotion criteria (Recurrence-Count >= 3, seen across 2+ tasks, within 30 days):

1. Entry status changes from `active` → `PENDING_REVIEW`
2. PENDING_REVIEW entries are surfaced in the next heartbeat review
3. Human reviews the proposed change and either:
   - **Approves**: Implements the change (code, config, or operating rule)
   - **Defers**: Lowers priority, keeps in PENDING_REVIEW
   - **Rejects**: Closes the entry with a reason
4. Auto-editing of AGENTS.md is NEVER performed — all promotions require explicit human approval

This PENDING_REVIEW status replaces the previous pattern of auto-promoting learnings directly to AGENTS.md. The WAL protocol ensures human review for all operating rule changes.

## Skill Loading Precedence

OpenClaw loads skills in this order (later overrides earlier):
1. Built-in / plugin skills
2. OpenClaw-shipped skills
3. User-installed skills (ClawHub or manual)
4. Project-level skills (in workspace)

TraderBot is installed at the project level: `skills/traderbot/SKILL.md`. This means it takes highest precedence and can override generic financial skills if any exist.

## Simulation Mode

During development, the agent reads real market data from Kalshi's production API but simulates all orders locally. No trades are submitted to the exchange. This is controlled via the simulation engine:

```bash
traderbot paper --strategy momentum  # runs strategy with local order simulation
```