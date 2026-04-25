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

PLIST_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$PLIST_DIR"

PLIST_FILE="$PLIST_DIR/com.traderbot.agent.$AGENT_NAME.plist"

TEMPLATE_FILE="$(dirname "$0")/com.traderbot.agent.plist"
if [[ ! -f "$TEMPLATE_FILE" ]]; then
    echo "Error: template file not found: $TEMPLATE_FILE" >&2
    exit 1
fi

USER_NAME="$(whoami)"
sed -e "s/AGENT_ID/$AGENT_NAME/g" -e "s/TOKEN_PLACEHOLDER/$PROFILE_TOKEN/g" -e "s/USERNAME/$USER_NAME/g" \
    "$TEMPLATE_FILE" > "$PLIST_FILE"

if launchctl load "$PLIST_FILE" 2>/dev/null; then
    echo "Service installed and loaded for agent: $AGENT_NAME"
else
    echo "Service file installed for agent: $AGENT_NAME (manual load required: launchctl load $PLIST_FILE)"
fi