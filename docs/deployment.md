# Deployment

## Installer

The main entry point is `install/traderbot-installer.sh`. It handles OpenClaw bootstrap, TraderBot installation, and interactive configuration in three phases.

### Linux/macOS

```bash
curl -fsSL https://raw.githubusercontent.com/JsonDaRula69/TraderBot/main/install/traderbot-installer.sh \
  -o /tmp/traderbot-installer.sh && bash /tmp/traderbot-installer.sh
```

### Windows

```powershell
.\install\Install-TraderBot.ps1                 # Interactive install
.\install\Install-TraderBot.ps1 -Uninstall       # Remove scheduled tasks
.\install\Install-TraderBot.ps1 -Update           # Pull latest and restart
```

The installers run four phases:

1. **OS detection** — detects the platform and version
2. **Dependency installation** — platform-specific package setup (Python 3.12, git, uv)
3. **TraderBot install** — tries `pip install traderbot` first (PyPI), falls back to `git clone` + `uv sync`
4. **Interactive config** — profile creation, API keys, agent assignment

### Prerequisites

**OpenClaw Required**

TraderBot agents run as OpenClaw agents. The installer will install OpenClaw via `npm install -g openclaw` if not found:

- `~/.openclaw/` directory created by `openclaw setup`
- `openclaw` binary installed globally and in PATH
- OpenClaw gateway runs as a systemd user service

## Ubuntu Installation

### 1. Run the installer

```bash
bash install/traderbot-installer.sh
```

The installer will:
- Detect `linux-debian` (Ubuntu/Debian) or `linux-other`
- Check/install OpenClaw via `npm install -g openclaw` if not found
- Start OpenClaw gateway service (systemd user service)
- Run `openclaw setup --workspace ~/.openclaw/workspace`
- Install dependencies: `build-essential`, `python3.12-dev`, `python3.12-venv`, Docker (optional)
- Clone TraderBot from GitHub
- Create Python venv and install package
- Launch interactive config: API credentials, sysadmin profile, category agents

### 2. Docker sandbox (optional, interactive prompt)

If Docker is available, the installer prompts to build and configure the sandbox:

```bash
bash install/docker/build-sandbox.sh
```

This builds `traderbot-sandbox:bookworm-slim` (Python 3.12 base) and applies OpenClaw config:

| Setting | Value |
|---|---|
| `agents.defaults.sandbox.mode` | `non-main` |
| `agents.defaults.sandbox.backend` | `docker` |
| `agents.defaults.sandbox.docker.binds` | `["~/traderbot:/traderbot:ro", "~/.traderbot:/home/traderbot/.traderbot:rw"]` |
| `agents.defaults.sandbox.docker.dangerouslyAllowExternalBindSources` | `true` |
| `agents.list[0].sandbox.mode` | `off` (main/sysadmin runs on host) |

Agent activity data (credentials, ChromaDB, SESSION-STATE.md, MEMORY.md, .learnings/) is **preserved** across sandbox image rebuilds — it lives on the host filesystem and is bind-mounted into the container.

### 3. Update

Two update paths execute the full pipeline:

```bash
# CLI update (Python)
traderbot update            # git pull → pip install → workspace refresh → sandbox rebuild → config reapply → cron re-register → gateway restart
traderbot update --force    # Apply even if versions match

# Installer update (bash)
bash install/traderbot-installer.sh --update
```

Both rebuild the Docker sandbox image and re-apply OpenClaw config keys.

### 6. Install data pipeline timers

New deployments now auto-wire the data pipeline via `install/services/install-data-pipeline.sh`. This is called automatically by the installer after agent setup, or can be run standalone:

```bash
bash install/services/install-data-pipeline.sh
```

This:
- Runs an initial 6-month data backfill to seed ChromaDB data_points (weather, economic, crypto history)
- Deploys `traderbot-news-ingest@.timer` — every 30 minutes (fetches news + data points from 9 sources)
- Deploys `traderbot-backfill-data@.timer` — daily at midnight (incremental historical data enrichment)

```bash
# Check timer status
systemctl list-timers | grep traderbot

# View news ingestion logs
journalctl -u traderbot-news-ingest@$(whoami).service -n 50

# View data backfill logs
journalctl -u traderbot-backfill-data@$(whoami).service -n 50

# Check data_points collection was seeded
traderbot data-points weather --json
```

> **Note for existing deployments**: If you deployed TraderBot before the pipeline timers existed, run `bash install/services/install-data-pipeline.sh` manually to backfill historical data and enable the timers.

## macOS Installation

### 1. Run the installer

```bash
bash install/traderbot-installer.sh
```

The installer will:
- Detect `macos`
- Check for Xcode CLI tools (install if missing)
- Verify Python 3.12+ is installed
- Download and install TraderBot
- Launch interactive config

### 2. Create a profile

Same as Ubuntu.

### 3. Assign an agent

Same as Ubuntu.

### 4. Enable persistence

For each assigned agent, the installer calls `install/services/install-launchd.sh`:

```bash
bash install/services/install-launchd.sh molty xK9mQ2pL7nR4
```

This:
- Copies the plist template to `~/Library/LaunchAgents/com.traderbot.agent.molty.plist`
- Fills in the agent ID and token
- Loads the service via `launchctl`

```bash
# Check status
launchctl list | grep traderbot

# View logs
tail -f ~/Library/Logs/traderbot-molty.log
```

### 5. Install data pipeline timers

The installer runs `install/services/install-data-pipeline.sh` automatically after agent setup. On macOS, this deploys LaunchDaemons instead of systemd timers:

```bash
bash install/services/install-data-pipeline.sh
```

This:
- Runs an initial 6-month data backfill to seed ChromaDB data_points (weather, economic, crypto history)
- Deploys `com.traderbot.news-ingest` LaunchDaemon — every 30 minutes (fetches news + data points from 9 sources)
- Deploys `com.traderbot.backfill-data` LaunchDaemon — daily at midnight (incremental historical data enrichment)

```bash
# Check LaunchDaemon status
sudo launchctl list | grep traderbot

# Run initial backfill manually if needed
traderbot backfill --months 6
```

## Windows Installation

### Prerequisites

- **Windows 10/11** or Windows Server 2019+
- **PowerShell 5.1+** (pre-installed on Windows 10+)
- **Administrator privileges** (for Task Scheduler registration)
- **OpenClaw** installed (recommended; installer will warn if missing)

### 1. Run the installer

Open PowerShell as Administrator and run:

```powershell
.\install\Install-TraderBot.ps1
```

If you see an execution policy error, first allow script execution:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

The installer will:
- Detect Windows version
- Install Python 3.12 via winget (or python.org fallback)
- Install git via winget (or direct download)
- Install uv (Python package manager)
- Clone and install TraderBot
- Launch interactive config for profiles, API keys, and agent assignment

### 2. Create a profile

Same as Ubuntu — handled interactively by the installer or run manually:

```powershell
traderbot profile create paper-aggressive --mode paper `
    --categories Economics,Politics `
    --risk-multiplier 0.8 `
    --max-daily-loss-pct 1.5
```

### 3. Assign an agent

The installer prompts for agent name and profile token during Phase 4.
To assign manually:

```powershell
traderbot profile discover-agents
# Returns: [{"agent_id": "molty", "name": "Molty the Trader", ...}]

traderbot profile assign molty paper-aggressive
# Token: xK9mQ2pL7nR4
```

### 4. Enable persistence

The installer registers three Windows Task Scheduler tasks:

| Task | Schedule | Description |
|------|----------|-------------|
| `TraderBot-agent-{name}` | Hourly | Main agent scan loop |
| `TraderBot-heartbeat-{name}` | Every 15 min | Agent heartbeat/health check |
| `TraderBot-news-ingest` | Hourly | News content ingestion (shared) |

> **Note**: The Windows installer does not currently register a daily backfill timer (`traderbot-backfill-data@.timer` — Linux only). To seed historical data on Windows, run `traderbot backfill --months 6` manually after installation. Daily data enrichment occurs via the news-ingest task's data points fetching.

Tasks run in the background and survive reboots via Task Scheduler settings
(`AllowStartIfOnBatteries`, `StartWhenAvailable`, restart on failure).

```powershell
# View all scheduled tasks
Get-ScheduledTask -TaskPath "\TraderBot\"

# Check task status
Get-ScheduledTaskInfo -TaskName "TraderBot-agent-molty" -TaskPath "\TraderBot\"

# View task history in Event Viewer or Task Scheduler GUI:
taskschd.msc  → navigate to \TraderBot\
```

### Installation Paths

| Directory | Purpose |
|-----------|---------|
| `%USERPROFILE%\traderbot\` | Git repo + venv |
| `%USERPROFILE%\.traderbot\` | .env credentials, profiles DB |
| `%USERPROFILE%\.local\bin\` | traderbot.exe symlink |
| `%USERPROFILE%\Library\Logs\` | Agent log files |

## Uninstall

### Linux/macOS

```bash
bash install/traderbot-installer.sh --uninstall
```

### Windows

```powershell
.\install\Install-TraderBot.ps1 -Uninstall
```

This:
- Stops and removes all TraderBot scheduled tasks
- Preserves data at `%USERPROFILE%\.traderbot\` (all profiles and data)
- To remove completely, delete `%USERPROFILE%\traderbot\` and `%USERPROFILE%\.traderbot\` manually

## Update

### Linux/macOS

```bash
bash install/traderbot-installer.sh --update
```

### Windows

```powershell
.\install\Install-TraderBot.ps1 -Update
```

This:
- Stops all scheduled tasks
- Pulls latest from GitHub
- Re-installs dependencies
- Restarts scheduled tasks

## Profile Creation Flow

The installer interactive config flow:

```
=== TraderBot Configuration ===

Create a trading profile? (y/n): y
Profile name: my-paper
Mode (paper/live): paper
Categories (comma-separated): Economics,Politics,Sports

=== API Key Setup ===

Kalshi API Key ID: your_key_id

=== Agent Assignment ===

Available agents:
  molty — Molty the Trader

Agent name to assign: molty

=== Verification ===

Heartbeat verification: PASSED
```

After the installer completes, `traderbot profile list` shows the new profile and `traderbot profile assignments` shows the agent binding.

## Persistence Architecture

### Linux (systemd)

A systemd template unit `traderbot-agent@.service` runs one agent per instance. The installer generates instance-specific unit files with the token injected.

```
~/.config/systemd/user/
├── traderbot-agent@molty.service
├── traderbot-agent@alice.service
└── traderbot-agent@bob.service
```

Each service reads `TRADERBOT_PROFILE_TOKEN` from its environment and uses `loginctl enable-linger` to start at boot.

### macOS (launchd)

A plist template runs one agent per plist. The installer generates instance-specific plist files with the token injected.

```
~/Library/LaunchAgents/
├── com.traderbot.agent.molty.plist
├── com.traderbot.agent.alice.plist
└── com.traderbot.agent.bob.plist
```

Each plist has `RunAtLoad=true` and `KeepAlive=true` for automatic start and restart on failure.

### Windows (Task Scheduler)

Tasks run under `\TraderBot\` in the Task Scheduler hierarchy. The installer registers per-agent tasks with hourly scan triggers, 15-minute heartbeats, and a shared news ingest task.

```
\TraderBot\
├── TraderBot-agent-molty       (hourly scan loop)
├── TraderBot-heartbeat-molty   (every 15 min)
├── TraderBot-agent-alice       (hourly scan loop)
├── TraderBot-heartbeat-alice   (every 15 min)
└── TraderBot-news-ingest       (hourly, shared)
```

Each task runs `traderbot scan --continuous` from the venv, with the profile token stored in `%USERPROFILE%\.traderbot\.env`. Tasks are configured to survive reboots (`StartWhenAvailable`), run on battery, and retry on failure (up to 5 retries, 10-minute intervals).

## Data Isolation

Each profile has its own data directory under `~/.traderbot/{mode}-{name}/`:

| Profile | Base Directory |
|---|---|
| `paper-weather-agent` | `~/.traderbot/paper-weather-agent/` |
| `live-portfolio` | `~/.traderbot/live-portfolio/` |
| Global (no profile) | `~/.traderbot/` |

Within each profile directory:
- `db/` — SQLite database (decisions, positions, learnings)
- `chroma/` — ChromaDB vector store
- `audit/` — Audit trail logs

When a profile token is set via `TRADERBOT_PROFILE_TOKEN`, TraderBot uses the profile-specific paths. When no profile token is set, it uses the global `~/.traderbot/`.
