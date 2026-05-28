# TraderBot Installer

The installer (`traderbot-installer.sh`) automates the full deployment of TraderBot including OpenClaw lifecycle management, agent creation, workspace deployment, systemd services, and data pipeline timers.

## Quick Start

```bash
# 1. Prerequisites (one-time)
npm install -g @openclaw/cli

# 2. Clone and run installer
git clone git@github.com:JsonDaRula69/TraderBot.git ~/traderbot
cd ~/traderbot
bash install/traderbot-installer.sh
```

The installer handles everything — OpenClaw gateway setup, agent creation, hooks, profile creation, service installation, and data pipeline timers.

## What the Installer Does

### Phase 1 — OpenClaw Bootstrap

| Step | Action | Auto? |
|---|---|---|
| Detect `openclaw` CLI | `which openclaw` | ✅ Yes |
| Install if missing | `npm install -g @openclaw/cli` | ✅ Prompted |
| Detect gateway status | `openclaw gateway status` | ✅ Yes |
| Install gateway service | `openclaw gateway install` | ✅ Prompted |
| Start gateway | `openclaw gateway start` | ✅ Prompted |
| Wait for readiness | Polls up to 20s | ✅ Yes |

### Phase 2 — Agent Creation + Hooks

| Step | Action | Purpose |
|---|---|---|
| Create `main` agent | `openclaw agents add main` | Sysadmin agent |
| Enable `command-logger` | `openclaw hooks enable command-logger` | Audit trail for all commands |
| Enable `session-memory` | `openclaw hooks enable session-memory` | Auto-saves last 15 messages |
| Enable `compaction-notifier` | `openclaw hooks enable compaction-notifier` | Shows "compacting history..." |
| Enable `agent-bootstrap` | `openclaw hooks enable agent-bootstrap` | Pre-session status injection |

### Phase 3 — Interactive Configuration

The installer prompts for:
1. **Sysadmin setup** — creates sysadmin profile (0.001 risk, all categories), assigns to `main` agent, registers 7 isolated cron jobs
2. **Trading profile** — creates a profile with:
   - **Name**: user-provided
   - **Mode**: paper (default) or live
   - **Categories**: multi-select (↑/↓ SPACE to toggle, ENTER to confirm)
3. **Agent assignment** — auto-creates OpenClaw agent via `openclaw agents add <name>` if it doesn't exist, then assigns profile and injects workspace files
4. **Service installation** — creates systemd service for the agent
5. **Data pipeline timers** — installs news-ingest (30min) + backfill-data (daily) timers

## Systemd Service Files

| Service | Type | Purpose |
|---|---|---|
| `traderbot-agent@.service` | Template unit | Runs one traderbot agent per instance |
| `traderbot-news-ingest@.timer` | Timer, 30min | News ingestion + ChromaDB embedding |
| `traderbot-backfill-data@.timer` | Timer, daily | Incremental historical data backfill |

## Data Pipeline Timers

New deployments auto-wire two recurring data pipeline timers:

| Timer | Frequency | What It Does |
|---|---|---|
| `traderbot-news-ingest@.timer` | Every 30 min | Fetch, classify, embed, store news + data points to ChromaDB |
| `traderbot-backfill-data@.timer` | Daily | Incremental historical data backfill (Open-Meteo, FRED, CoinGecko) |

On install, also runs an initial **6-month historical backfill** to seed the ChromaDB `data_points` collection.

### Verify timers

```bash
systemctl list-timers | grep traderbot
```

### View pipeline logs

```bash
journalctl -u traderbot-news-ingest@$(whoami).service -n 50
journalctl -u traderbot-backfill-data@$(whoami).service -n 50
```

## Isolated Cron Jobs (Per Agent)

Each agent gets 7 isolated OpenClaw cron jobs. All run via `--session isolated` so they never collide with trading:

| Job | Interval | What It Runs |
|---|---|---|
| circuit-breaker-check | 30m | `traderbot halt --json` |
| data-forecast-check | 30m | `traderbot data forecasts` |
| news-scan | 30m | `traderbot news-context` |
| position-health | 1h | `traderbot positions --json` |
| performance-review | 6h | `traderbot heartbeat --json` |
| learning-promotion | 6h | `.learnings/` recurrence >= 3 check |
| pipeline-health | 6h | Pipeline timer status, data_points count |

Plus 7 sysadmin cron jobs for fleet oversight (registered for the `main` agent).

### View cron jobs

```bash
openclaw cron list
```

## Uninstalling

```bash
bash install/traderbot-installer.sh --uninstall
```

Or via the CLI:
```bash
traderbot uninstall --remove-data
```

The uninstall flow removes:
- All `traderbot-*@*.service` + `traderbot-*@*.timer` systemd units
- Orphaned systemd wants symlinks
- `com.traderbot.*.plist` launch daemons (macOS)
- OpenClaw cron jobs (traderbot-related)
- All profiles, databases, and user data (`--remove-data`)
- The repository (`--remove-repo`)

## Files In This Directory

```
install/
├── traderbot-installer.sh      # Main installer
├── README.md                   # This file
└── services/
    ├── traderbot-agent@.service           # Agent systemd service template
    ├── traderbot-news-ingest@.service     # News ingestion service
    ├── traderbot-news-ingest@.timer       # News ingestion timer (30min)
    ├── traderbot-backfill-data@.service   # Data backfill service
    ├── traderbot-backfill-data@.timer     # Data backfill timer (daily)
    ├── install-data-pipeline.sh           # Pipeline installer (autowired)
    └── com.traderbot.agent.plist         # Launchd template (macOS)
```
