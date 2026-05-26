# TraderBot Installation Guide

This directory contains installation resources for deploying TraderBot agents as persistent system services.

## Systemd Service Template (Linux)

The `services/traderbot-agent@.service` file is a systemd template unit that allows you to run multiple TraderBot agents as independent system services.

### Understanding Systemd Templates

The `@` symbol in the filename makes this a **template unit**. When you enable or start the service, you provide an **instance name** (the agent ID), and systemd replaces all occurrences of `%i` in the template with that instance name.

For example:
- `traderbot-agent@molty.service` → `%i` becomes `molty`
- `traderbot-agent@alice.service` → `%i` becomes `alice`

This allows you to run multiple agents with a single template file.

### Prerequisites

1. **TraderBot installed**: The `traderbot` command must be available in `/usr/local/bin/` (or adjust the `ExecStart` path in the service file)
2. **Profile token**: Each agent needs a valid profile token
3. **System user** (optional): If using `User=%i`, create a system user for each agent
4. **Working directory**: Ensure the working directory exists and is writable by the service user

### Installation Steps

#### 1. Prepare the Service File

Copy the template to the systemd directory:

```bash
sudo cp install/services/traderbot-agent@.service /etc/systemd/system/
```

#### 2. Customize for Your Agent

Edit the service file to replace the placeholder token:

```bash
sudo nano /etc/systemd/system/traderbot-agent@.service
```

Replace `<PROFILE_TOKEN>` with your actual profile token:

```ini
Environment=TRADERBOT_PROFILE_TOKEN=your_actual_token_here
```

**Important**: Future versions will include an installer script that automates this step.

#### 3. Adjust Paths (if needed)

If your installation differs from the defaults, adjust these settings:

- **User**: Change from `%i` to a specific user (e.g., `traderbot`)
- **WorkingDirectory**: Change from `/home/%i/traderbot` to your installation path
- **ExecStart**: Change from `/usr/local/bin/traderbot` if installed elsewhere

#### 4. Reload Systemd

After making changes, reload systemd to recognize the new service:

```bash
sudo systemctl daemon-reload
```

### Managing Services

#### Enable a Service (Start on Boot)

```bash
sudo systemctl enable traderbot-agent@molty.service
```

#### Start a Service

```bash
sudo systemctl start traderbot-agent@molty.service
```

#### Enable and Start in One Command

```bash
sudo systemctl enable --now traderbot-agent@molty.service
```

#### Stop a Service

```bash
sudo systemctl stop traderbot-agent@molty.service
```

#### Restart a Service

```bash
sudo systemctl restart traderbot-agent@molty.service
```

#### Disable a Service (Prevent Start on Boot)

```bash
sudo systemctl disable traderbot-agent@molty.service
```

#### Check Service Status

```bash
sudo systemctl status traderbot-agent@molty.service
```

Example output:
```
● traderbot-agent@molty.service - TraderBot Agent (molty)
     Loaded: loaded (/etc/systemd/system/traderbot-agent@.service; enabled; vendor preset: enabled)
     Active: active (running) since Wed 2026-04-22 13:00:00 UTC; 5min ago
   Main PID: 12345 (traderbot)
      Tasks: 3 (limit: 4915)
     Memory: 45.2M
        CPU: 2.345s
     CGroup: /system.slice/system-traderbot\x2dagent.slice/traderbot-agent@molty.service
             └─12345 /usr/local/bin/traderbot scan --continuous
```

### Viewing Logs

#### Follow Live Logs

```bash
sudo journalctl -u traderbot-agent@molty.service -f
```

#### View Recent Logs

```bash
sudo journalctl -u traderbot-agent@molty.service -n 100
```

#### View Logs Since Boot

```bash
sudo journalctl -u traderbot-agent@molty.service -b
```

#### View Logs for a Specific Time Range

```bash
sudo journalctl -u traderbot-agent@molty.service --since "2026-04-22 12:00:00" --until "2026-04-22 13:00:00"
```

#### Filter by Priority

```bash
# Errors only
sudo journalctl -u traderbot-agent@molty.service -p err

# Warnings and above
sudo journalctl -u traderbot-agent@molty.service -p warning
```

### Running Multiple Agents

To run multiple agents, simply enable and start multiple instances:

```bash
# Agent 1: molty
sudo systemctl enable --now traderbot-agent@molty.service

# Agent 2: alice
sudo systemctl enable --now traderbot-agent@alice.service

# Agent 3: bob
sudo systemctl enable --now traderbot-agent@bob.service
```

Each agent runs independently with its own:
- Profile token
- Working directory
- Log stream
- Process ID

### Troubleshooting

#### Service Won't Start

1. Check the service status for error messages:
   ```bash
   sudo systemctl status traderbot-agent@molty.service
   ```

2. Check the logs:
   ```bash
   sudo journalctl -u traderbot-agent@molty.service -n 50
   ```

3. Verify the profile token is correct
4. Verify the working directory exists and is writable
5. Verify the `traderbot` binary is executable

#### Service Keeps Restarting

The service is configured to restart on failure with a 10-second delay. If it keeps restarting:

1. Check logs for the error causing the crash
2. Verify the profile token is valid
3. Check network connectivity
4. Verify Kalshi API credentials

#### Permission Denied Errors

1. Verify the service user has access to the working directory
2. Check file permissions: `ls -la /home/molty/traderbot`
3. Adjust the `User` setting in the service file if needed

### Security Hardening

The service file includes optional security settings (commented out by default). To enable them, uncomment these lines:

```ini
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/%i/traderbot
```

These settings:
- Prevent privilege escalation
- Isolate temporary files
- Make system directories read-only
- Restrict home directory access
- Allow writes only to the working directory

### Uninstallation

To remove a service:

```bash
# Stop and disable the service
sudo systemctl stop traderbot-agent@molty.service
sudo systemctl disable traderbot-agent@molty.service

# Remove the service file (optional)
sudo rm /etc/systemd/system/traderbot-agent@.service

# Reload systemd
sudo systemctl daemon-reload
```

## Launchd Service Template (macOS)

The `services/com.traderbot.agent.plist` file is a launchd property list template that allows you to run TraderBot agents as persistent user services on macOS.

### Understanding Launchd Agents

Launchd is macOS's service management framework. User agents run in the user's session and start automatically when the user logs in. Each agent instance requires its own plist file with a unique label.

For example:
- `com.traderbot.agent.molty.plist` → runs the molty agent
- `com.traderbot.agent.alice.plist` → runs the alice agent

### Prerequisites

1. **TraderBot installed**: The `traderbot` command must be available in `/usr/local/bin/` (or adjust the `ProgramArguments` path in the plist file)
2. **Profile token**: Each agent needs a valid profile token
3. **Working directory**: Ensure the working directory exists and is writable by your user
4. **Logs directory**: The `~/Library/Logs/` directory is used for agent logs

### Installation Steps

#### 1. Prepare the Plist File

Copy the template and customize it for your agent:

```bash
# Copy template for agent "molty"
cp install/services/com.traderbot.agent.plist ~/Library/LaunchAgents/com.traderbot.agent.molty.plist
```

#### 2. Customize for Your Agent

Edit the plist file to replace placeholders:

```bash
nano ~/Library/LaunchAgents/com.traderbot.agent.molty.plist
```

Replace these placeholders:
- **AGENT_ID**: Replace with your agent ID (e.g., `molty`)
- **TOKEN_PLACEHOLDER**: Replace with your actual profile token
- **USERNAME**: Replace with your macOS username (e.g., `djtchill`)

Example replacements:
```xml
<!-- Before -->
<key>Label</key>
<string>com.traderbot.agent.AGENT_ID</string>

<!-- After -->
<key>Label</key>
<string>com.traderbot.agent.molty</string>
```

**Important**: Future versions will include an installer script that automates this step.

#### 3. Adjust Paths (if needed)

If your installation differs from the defaults, adjust these settings:

- **ProgramArguments**: Change `/usr/local/bin/traderbot` if installed elsewhere
- **WorkingDirectory**: Change `/Users/USERNAME/traderbot` to your installation path
- **StandardOutPath/StandardErrorPath**: Adjust log paths if desired

#### 4. Load the Service

Load the service into launchd:

```bash
launchctl load ~/Library/LaunchAgents/com.traderbot.agent.molty.plist
```

The service will start automatically and run continuously.

### Managing Services

#### Load a Service (Enable and Start)

```bash
launchctl load ~/Library/LaunchAgents/com.traderbot.agent.molty.plist
```

#### Start a Service (if loaded but stopped)

```bash
launchctl start com.traderbot.agent.molty
```

#### Stop a Service

```bash
launchctl stop com.traderbot.agent.molty
```

#### Unload a Service (Disable)

```bash
launchctl unload ~/Library/LaunchAgents/com.traderbot.agent.molty.plist
```

#### Check Service Status

```bash
launchctl list | grep traderbot
```

Example output:
```
12345   0   com.traderbot.agent.molty
```

The first column is the PID (process ID), the second is the exit status (0 = running), and the third is the label.

#### Get Detailed Service Info

```bash
launchctl print gui/$(id -u)/com.traderbot.agent.molty
```

### Viewing Logs

#### Follow Live Logs (Standard Output)

```bash
tail -f ~/Library/Logs/traderbot-molty.log
```

#### Follow Live Logs (Errors)

```bash
tail -f ~/Library/Logs/traderbot-molty-error.log
```

#### View Recent Logs

```bash
# Last 100 lines of standard output
tail -n 100 ~/Library/Logs/traderbot-molty.log

# Last 100 lines of errors
tail -n 100 ~/Library/Logs/traderbot-molty-error.log
```

#### Search Logs

```bash
# Search for specific text
grep "market scan" ~/Library/Logs/traderbot-molty.log

# Search with context
grep -C 5 "error" ~/Library/Logs/traderbot-molty-error.log
```

### Running Multiple Agents

To run multiple agents, create and load multiple plist files:

```bash
# Agent 1: molty
cp install/services/com.traderbot.agent.plist ~/Library/LaunchAgents/com.traderbot.agent.molty.plist
# Edit molty plist with agent-specific settings
launchctl load ~/Library/LaunchAgents/com.traderbot.agent.molty.plist

# Agent 2: alice
cp install/services/com.traderbot.agent.plist ~/Library/LaunchAgents/com.traderbot.agent.alice.plist
# Edit alice plist with agent-specific settings
launchctl load ~/Library/LaunchAgents/com.traderbot.agent.alice.plist

# Agent 3: bob
cp install/services/com.traderbot.agent.plist ~/Library/LaunchAgents/com.traderbot.agent.bob.plist
# Edit bob plist with agent-specific settings
launchctl load ~/Library/LaunchAgents/com.traderbot.agent.bob.plist
```

Each agent runs independently with its own:
- Profile token
- Working directory
- Log files
- Process ID

### Troubleshooting

#### Service Won't Start

1. Check if the service is loaded:
   ```bash
   launchctl list | grep traderbot
   ```

2. Check the error log:
   ```bash
   tail -n 50 ~/Library/Logs/traderbot-molty-error.log
   ```

3. Verify the plist file is valid XML:
   ```bash
   plutil -lint ~/Library/LaunchAgents/com.traderbot.agent.molty.plist
   ```

4. Verify the profile token is correct
5. Verify the working directory exists and is writable
6. Verify the `traderbot` binary is executable

#### Service Keeps Restarting

The service is configured to restart on failure (KeepAlive with SuccessfulExit=false). If it keeps restarting:

1. Check error logs for the crash reason
2. Verify the profile token is valid
3. Check network connectivity
4. Verify Kalshi API credentials

#### Permission Denied Errors

1. Verify you own the working directory: `ls -la ~/traderbot`
2. Verify log directory is writable: `ls -la ~/Library/Logs/`
3. Check file permissions on the plist: `ls -la ~/Library/LaunchAgents/com.traderbot.agent.molty.plist`

#### Service Not Starting on Login

1. Verify the plist is in `~/Library/LaunchAgents/` (not `/Library/LaunchAgents/`)
2. Verify `RunAtLoad` is set to `true` in the plist
3. Check Console.app for launchd errors (filter by "launchd")

### Uninstallation

To remove a service:

```bash
# Unload the service
launchctl unload ~/Library/LaunchAgents/com.traderbot.agent.molty.plist

# Remove the plist file
rm ~/Library/LaunchAgents/com.traderbot.agent.molty.plist

# Remove log files (optional)
rm ~/Library/Logs/traderbot-molty.log
rm ~/Library/Logs/traderbot-molty-error.log
```

## Data Pipeline Timers

New deployments auto-wire two recurring data pipeline timers via `install/services/install-data-pipeline.sh` (called automatically by the main installer).

| Timer | Frequency | What It Does |
|---|---|---|
| `traderbot-news-ingest@.timer` | Every 30 min | Fetch, classify, embed, store news + data points to ChromaDB |
| `traderbot-backfill-data@.timer` | Daily | Incremental historical data backfill (Open-Meteo, FRED, CoinGecko) |

On install, `install-data-pipeline.sh` also runs an initial **6-month historical backfill** to seed the ChromaDB `data_points` collection so agents have context immediately.

### Standalone installation

```bash
bash install/services/install-data-pipeline.sh
```

### Verify timers

```bash
systemctl list-timers | grep traderbot
```

### View pipeline logs

```bash
journalctl -u traderbot-news-ingest@$(whoami).service -n 50
journalctl -u traderbot-backfill-data@$(whoami).service -n 50
```

### Troubleshooting

If `traderbot data-points weather --json` returns 0 items:
1. Check timers: `systemctl list-timers | grep traderbot`
2. If timers are running but data_points is empty (< 24h since install), the initial backfill is in progress
3. If timers are NOT running, run `bash install/services/install-data-pipeline.sh`
4. For immediate results: `traderbot backfill --months 6` (runs synchronously, ~1-3 min)

## Future Enhancements

- Automated installer script (Tasks 14-16)
- macOS launchd template (Task 13)
- Windows service support
- Docker/container deployment
- Kubernetes manifests

## Support

For issues or questions:
- Check the logs first: `sudo journalctl -u traderbot-agent@<agent-id>.service`
- Review the systemd service file: `/etc/systemd/system/traderbot-agent@.service`
- Consult the main TraderBot documentation