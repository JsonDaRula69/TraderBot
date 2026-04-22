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

## macOS Support (launchd)

macOS support via launchd will be added in a future release. See Task 13 in the roadmap.

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