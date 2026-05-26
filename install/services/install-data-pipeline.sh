#!/bin/bash
# install-data-pipeline.sh — Install TraderBot data pipeline timers
#
# Deploys and enables two recurring data pipeline services:
#   1. traderbot-news-ingest@.timer     — every 30m (existing)
#   2. traderbot-backfill-data@.timer    — daily (new)
#
# Also runs an initial 6-month backfill to seed the ChromaDB data_points
# collection so the agent has historical context immediately.
#
# USAGE:
#   install-data-pipeline.sh                    # current user
#   sudo install-data-pipeline.sh <username>    # run as root for another user
#
# Prerequisites:
#   - traderbot CLI must be installed and on PATH
#   - .env file must exist at ~/.traderbot/.env or /home/<user>/.traderbot/.env
#   - ChromaDB persist directory must be writable
set -euo pipefail

# ── Resolve user ──────────────────────────────────────────────────────────
if [[ $# -ge 1 ]]; then
    TARGET_USER="$1"
else
    TARGET_USER="$(whoami)"
fi

if [[ "$TARGET_USER" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    :  # valid
elif [[ "$(whoami)" == "root" && -n "${SUDO_USER:-}" ]]; then
    TARGET_USER="$SUDO_USER"
else
    echo "Error: invalid username '$TARGET_USER'. Use alphanumeric, hyphens, underscores only." >&2
    exit 1
fi

# ── Paths ─────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_DIR="$SCRIPT_DIR/services"

if [[ "$TARGET_USER" == "$(whoami)" ]] || [[ "$(whoami)" == "root" ]]; then
    TRADERBOT_HOME=$(eval echo "~${TARGET_USER}")/traderbot
    VENV_BIN="${TRADERBOT_HOME}/.venv/bin/traderbot"
else
    TRADERBOT_HOME="/home/${TARGET_USER}/traderbot"
    VENV_BIN="${TRADERBOT_HOME}/.venv/bin/traderbot"
fi

# ── Check prerequisites ───────────────────────────────────────────────────
if [[ ! -f "$VENV_BIN" ]]; then
    echo "Error: traderbot CLI not found at $VENV_BIN" >&2
    echo "Install TraderBot first, then run this script." >&2
    exit 1
fi

# ── Run initial seed backfill ─────────────────────────────────────────────
echo "--- Running initial 6-month data backfill ---"
echo "  This fetches historical weather (Open-Meteo), economic (FRED),"
echo "  and crypto (CoinGecko) data into the ChromaDB data_points collection."
echo "  First run may take 1-3 minutes depending on API speed."
echo ""

# Run as the target user via sudo if needed
if [[ "$(whoami)" == "root" ]]; then
    sudo -u "$TARGET_USER" "$VENV_BIN" backfill --months 6 --json || {
        echo "Warning: initial backfill failed. Timers will still be installed." >&2
        echo "  Run manually: sudo -u $TARGET_USER $VENV_BIN backfill --months 6" >&2
    }
else
    "$VENV_BIN" backfill --months 6 --json || {
        echo "Warning: initial backfill failed. Timers will still be installed." >&2
        echo "  Run manually: $VENV_BIN backfill --months 6" >&2
    }
fi
echo ""

# ── Deploy systemd services + timers ─────────────────────────────────────
if command -v systemctl &>/dev/null; then
    echo "--- Installing systemd service files ---"

    # News ingest — every 30 minutes
    echo "  Deploying traderbot-news-ingest@${TARGET_USER}.service (30min interval)..."
    sudo cp "$SERVICE_DIR/traderbot-news-ingest@.service" "/etc/systemd/system/traderbot-news-ingest@${TARGET_USER}.service" 2>/dev/null || \
        echo "  Skipping — service already exists or template not found."
    sudo cp "$SERVICE_DIR/traderbot-news-ingest@.timer" "/etc/systemd/system/traderbot-news-ingest@${TARGET_USER}.timer"

    # Data backfill — daily
    echo "  Deploying traderbot-backfill-data@${TARGET_USER}.service (daily)..."
    sudo cp "$SERVICE_DIR/traderbot-backfill-data@.service" "/etc/systemd/system/traderbot-backfill-data@${TARGET_USER}.service" 2>/dev/null || \
        echo "  Skipping — service already exists or template not found."
    sudo cp "$SERVICE_DIR/traderbot-backfill-data@.timer" "/etc/systemd/system/traderbot-backfill-data@${TARGET_USER}.timer"

    sudo systemctl daemon-reload

    # Enable and start timers
    echo "  Enabling traderbot-news-ingest@${TARGET_USER}.timer..."
    sudo systemctl enable --now "traderbot-news-ingest@${TARGET_USER}.timer" 2>/dev/null && \
        echo "    OK" || echo "    (already enabled)"

    echo "  Enabling traderbot-backfill-data@${TARGET_USER}.timer..."
    sudo systemctl enable --now "traderbot-backfill-data@${TARGET_USER}.timer" 2>/dev/null && \
        echo "    OK" || echo "    (already enabled)"

    echo ""
    echo "Systemd timers installed:"
    echo "  traderbot-news-ingest@${TARGET_USER}.timer     — every 30 min"
    echo "  traderbot-backfill-data@${TARGET_USER}.timer   — daily at midnight"

# ── Deploy launchd plists (macOS) ─────────────────────────────────────────
elif command -v launchctl &>/dev/null; then
    echo "--- macOS detected — installing LaunchDaemons ---"

    PLIST_NEWS="/Library/LaunchDaemons/com.traderbot.news-ingest.${TARGET_USER}.plist"
    PLIST_BACKFILL="/Library/LaunchDaemons/com.traderbot.backfill-data.${TARGET_USER}.plist"

    # Generate news-ingest plist from template
    echo "  Creating $PLIST_NEWS..."
    sed -e "s/AGENT_ID/${TARGET_USER}/g" \
        -e "s/USERNAME/${TARGET_USER}/g" \
        "$SERVICE_DIR/com.traderbot.news-ingest.plist" > "/tmp/com.traderbot.news-ingest.${TARGET_USER}.plist" 2>/dev/null || {
        echo "  Warning: com.traderbot.news-ingest.plist template not found. Skipping." >&2
    }
    if [[ -f "/tmp/com.traderbot.news-ingest.${TARGET_USER}.plist" ]]; then
        sudo cp "/tmp/com.traderbot.news-ingest.${TARGET_USER}.plist" "$PLIST_NEWS"
        sudo launchctl bootstrap system "$PLIST_NEWS" 2>/dev/null || sudo launchctl load "$PLIST_NEWS" 2>/dev/null || true
        rm -f "/tmp/com.traderbot.news-ingest.${TARGET_USER}.plist"
    fi

    # Generate backfill plist
    echo "  Creating $PLIST_BACKFILL..."
    cat > "/tmp/com.traderbot.backfill-data.${TARGET_USER}.plist" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.traderbot.backfill-data.${TARGET_USER}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${VENV_BIN}</string>
        <string>backfill</string>
        <string>--months</string>
        <string>1</string>
        <string>--json</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>${TRADERBOT_HOME}/.venv/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
    <key>RunAtLoad</key>
    <false/>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>3</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/traderbot-backfill-${TARGET_USER}.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/traderbot-backfill-${TARGET_USER}.log</string>
    <key>UserName</key>
    <string>${TARGET_USER}</string>
</dict>
</plist>
PLISTEOF
    sudo cp "/tmp/com.traderbot.backfill-data.${TARGET_USER}.plist" "$PLIST_BACKFILL"
    sudo launchctl bootstrap system "$PLIST_BACKFILL" 2>/dev/null || sudo launchctl load "$PLIST_BACKFILL" 2>/dev/null || true
    rm -f "/tmp/com.traderbot.backfill-data.${TARGET_USER}.plist"

    echo ""
    echo "LaunchDaemons installed:"
    echo "  com.traderbot.news-ingest.${TARGET_USER}    — every 30 min"
    echo "  com.traderbot.backfill-data.${TARGET_USER}  — daily at 3:00 AM"

else
    echo "Warning: neither systemctl nor launchctl found." >&2
    echo "  Timers not installed. To complete setup manually:" >&2
    echo "    Run: $VENV_BIN backfill --months 6" >&2
    echo "    Then configure a cron job: 0 */6 * * * $VENV_BIN news-ingest --json" >&2
    echo "    And: 0 3 * * * $VENV_BIN backfill --months 1 --json" >&2
fi

# ── Summary ───────────────────────────────────────────────────────────────
echo ""
echo "=== Data Pipeline Install Complete ==="
echo ""
echo "Live data feeds (agent handles via CLI):"
echo "  - NWS official forecast    — every decision cycle (web_fetch)"
echo "  - Kalshi orderbook/prices  — per trade (traderbot analyze)"
echo ""
echo "Background pipeline (systemd/launchd handles):"
echo "  - News ingestion           — every 30 min"
echo "  - Data historical backfill — daily"
echo ""
echo "Verify with:"
echo "  systemctl status traderbot-news-ingest@${TARGET_USER}.timer"
echo "  systemctl status traderbot-backfill-data@${TARGET_USER}.timer"
