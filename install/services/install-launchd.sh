#!/bin/bash
# Usage: install-launchd.sh <agent_name> <profile_token>
# Installs a LaunchDaemon (boot-time, no login required) for macOS
set -euo pipefail

AGENT_NAME="$1"
PROFILE_TOKEN="$2"

if [[ -z "$AGENT_NAME" ]] || [[ -z "$PROFILE_TOKEN" ]]; then
    echo "Usage: install-launchd.sh <agent_name> <profile_token>" >&2
    exit 1
fi

if [[ ! "$AGENT_NAME" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo "Error: AGENT_NAME contains invalid characters. Only alphanumeric, hyphens, and underscores allowed." >&2
    exit 1
fi

if [[ ! "$PROFILE_TOKEN" =~ ^[a-zA-Z0-9]+$ ]]; then
    echo "Error: PROFILE_TOKEN contains invalid characters. Only alphanumeric characters allowed." >&2
    exit 1
fi

USER_NAME="$(whoami)"
if [[ "$USER_NAME" =~ AGENT_ID ]] || [[ "$USER_NAME" =~ USERNAME ]]; then
    echo "Error: Username '$USER_NAME' conflicts with plist template placeholders." >&2
    exit 1
fi

TEMPLATE_FILE="$(dirname "$0")/com.traderbot.agent.plist"
if [[ ! -f "$TEMPLATE_FILE" ]]; then
    echo "Error: template file not found: $TEMPLATE_FILE" >&2
    exit 1
fi

ENV_FILE="${HOME}/.traderbot/.env"
mkdir -p "${HOME}/.traderbot"
touch "$ENV_FILE"
chmod 600 "$ENV_FILE"

if grep -q "^TRADERBOT_PROFILE_TOKEN=" "$ENV_FILE" 2>/dev/null; then
    sed -i "" "s|^TRADERBOT_PROFILE_TOKEN=.*|TRADERBOT_PROFILE_TOKEN=${PROFILE_TOKEN}|" "$ENV_FILE"
else
    echo "TRADERBOT_PROFILE_TOKEN=${PROFILE_TOKEN}" >> "$ENV_FILE"
fi

PLIST_FILE="/Library/LaunchDaemons/com.traderbot.agent.$AGENT_NAME.plist"
USER_NAME="$(whoami)"

sed -e "s/AGENT_ID/$AGENT_NAME/g" \
    -e "s/USERNAME/$USER_NAME/g" \
    "$TEMPLATE_FILE" > "/tmp/com.traderbot.agent.$AGENT_NAME.plist"

if command -v plutil &>/dev/null; then
    if ! plutil -lint "/tmp/com.traderbot.agent.$AGENT_NAME.plist" &>/dev/null; then
        echo "Error: Generated plist file is invalid." >&2
        rm -f "/tmp/com.traderbot.agent.$AGENT_NAME.plist"
        exit 1
    fi
fi

sudo cp "/tmp/com.traderbot.agent.$AGENT_NAME.plist" "$PLIST_FILE"
rm -f "/tmp/com.traderbot.agent.$AGENT_NAME.plist"
sudo launchctl bootstrap "system/com.traderbot.agent.$AGENT_NAME" 2>/dev/null || \
    sudo launchctl load "$PLIST_FILE" 2>/dev/null || true
echo "LaunchDaemon installed and loaded for agent: $AGENT_NAME (starts at boot, no login required)"