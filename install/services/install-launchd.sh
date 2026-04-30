#!/bin/bash
# Usage: install-launchd.sh <agent_name> <profile_token>
# Creates instance-specific plist file and loads it

set -euo pipefail

AGENT_NAME="$1"
PROFILE_TOKEN="$2"

if [[ -z "$AGENT_NAME" ]] || [[ -z "$PROFILE_TOKEN" ]]; then
    echo "Usage: install-launchd.sh <agent_name> <profile_token>" >&2
    exit 1
fi

# Validate AGENT_NAME matches safe pattern (prevents path traversal in plist filename)
if [[ ! "$AGENT_NAME" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo "Error: AGENT_NAME contains invalid characters. Only alphanumeric, hyphens, and underscores allowed." >&2
    exit 1
fi

# Validate PROFILE_TOKEN is alphanumeric (prevents sed injection into plist)
if [[ ! "$PROFILE_TOKEN" =~ ^[a-zA-Z0-9]+$ ]]; then
    echo "Error: PROFILE_TOKEN contains invalid characters. Only alphanumeric characters allowed." >&2
    exit 1
fi

PLIST_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$PLIST_DIR"

PLIST_FILE="$PLIST_DIR/com.traderbot.agent.$AGENT_NAME.plist"

TEMPLATE_FILE="$(dirname "$0")/com.traderbot.agent.plist"
if [[ ! -f "$TEMPLATE_FILE" ]]; then
    echo "Error: template file not found: $TEMPLATE_FILE" >&2
    exit 1
fi

USER_NAME="$(whoami)"
TRADERBOT_BIN="$(command -v traderbot || echo '/usr/local/bin/traderbot')"
sed -e "s/AGENT_ID/$AGENT_NAME/g" -e "s/TOKEN_PLACEHOLDER/$PROFILE_TOKEN/g" -e "s/USERNAME/$USER_NAME/g" -e "s|TRADERBOT_BIN_PATH|$TRADERBOT_BIN|g" \
    "$TEMPLATE_FILE" > "$PLIST_FILE"

if launchctl load "$PLIST_FILE" 2>/dev/null; then
    echo "Service installed and loaded for agent: $AGENT_NAME"
else
    echo "Service file installed for agent: $AGENT_NAME (manual load required: launchctl load $PLIST_FILE)"
fi