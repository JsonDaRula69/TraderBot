# Deployment

This guide covers installing TraderBot on Ubuntu (Debian-based Linux), setting up profiles, assigning agents, and configuring persistence.

## Installer

`install/traderbot-installer.sh` handles the full installation flow on both platforms.

```bash
bash install/traderbot-installer.sh              # Interactive install
bash install/traderbot-installer.sh --uninstall  # Remove services
bash install/traderbot-installer.sh --update      # Pull latest and restart
```

The installer runs three phases:

1. **OS detection** — detects Ubuntu/Debian or unsupported
2. **Dependency installation** — platform-specific package setup
3. **TraderBot install** — downloads from GitHub, installs via pip/uv
4. **Interactive config** — profile creation, API keys, agent assignment

### Prerequisites

The installer checks for OpenClaw before proceeding:

- `~/.openclaw/` directory must exist
- `openclaw` binary must be in PATH

If OpenClaw is not found, the installer exits with code 1 and instructions.

## Ubuntu Installation

### 1. Run the installer

```bash
bash install/traderbot-installer.sh
```

The installer will:
- Detect `linux-debian` (Ubuntu/Debian) or `linux-other`
- Install dependencies: `build-essential`, `python3-dev`, `python3-venv`
- Download and install TraderBot
- Launch interactive config

### 2. Create a profile

```bash
traderbot profile create paper-aggressive --mode paper \
    --categories Economics,Politics \
    --risk-multiplier 0.8 \
    --max-daily-loss-pct 1.5
```

### 3. Assign an agent

```bash
traderbot profile discover-agents
# Returns: [{"agent_id": "molty", "name": "Molty the Trader", "path": ".openclaw/workspace/molty"}]

traderbot profile assign molty paper-aggressive
# Token: xK9mQ2pL7nR4
# Token injected into molty/TOOLS.md
```

### 4. Set API credentials

```bash
traderbot profile set-auth paper-aggressive kalshi
# Prompts for API key ID and secret
```

### 5. Enable persistence

For each assigned agent, the installer calls `install/services/install-service.sh`:

```bash
bash install/services/install-service.sh molty xK9mQ2pL7nR4
```

This:
- Generates a systemd service instance: `traderbot-agent@molty.service`
- Sets `TRADERBOT_PROFILE_TOKEN=xK9mQ2pL7nR4` in the service environment
- Enables linger for the user (allows services to start at boot without login)
- Starts the service

```bash
# Check status
systemctl --user status traderbot-agent@molty.service

# View logs
journalctl --user -u traderbot-agent@molty.service -f
```

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

## Uninstall

```bash
bash install/traderbot-installer.sh --uninstall
```

This:
- Stops all running TraderBot services
- Removes systemd unit files (Linux) or launchd plist files (macOS)
- Preserves data at `~/.traderbot/` (all profiles and data)

## Update

```bash
bash install/traderbot-installer.sh --update
```

This:
- Stops all services
- Pulls latest from GitHub
- Restarts services

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
