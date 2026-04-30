#!/bin/bash
# Usage: install-service.sh <agent_name> <profile_token>
# Creates instance-specific systemd service file and enables it

set -euo pipefail

AGENT_NAME="$1"
PROFILE_TOKEN="$2"

# Validate arguments
if [[ -z "$AGENT_NAME" ]] || [[ -z "$PROFILE_TOKEN" ]]; then
    echo "Usage: install-service.sh <agent_name> <profile_token>" >&2
    exit 1
fi

# Validate AGENT_NAME matches safe pattern (no path traversal or shell metacharacters)
if [[ ! "$AGENT_NAME" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo "Error: AGENT_NAME contains invalid characters. Only alphanumeric, hyphens, and underscores allowed." >&2
    exit 1
fi

# Validate PROFILE_TOKEN is alphanumeric (prevents sed injection and shell metacharacter injection)
if [[ ! "$PROFILE_TOKEN" =~ ^[a-zA-Z0-9]+$ ]]; then
    echo "Error: PROFILE_TOKEN contains invalid characters. Only alphanumeric characters allowed." >&2
    exit 1
fi

# Create instance-specific service file
SERVICE_DIR="$HOME/.config/systemd/user"
mkdir -p "$SERVICE_DIR"

TEMPLATE_FILE="$(dirname "$0")/traderbot-agent@.service"
if [[ ! -f "$TEMPLATE_FILE" ]]; then
    echo "Error: template file not found: $TEMPLATE_FILE" >&2
    exit 1
fi

# Copy template and replace placeholders
sed "s/<PROFILE_TOKEN>/$PROFILE_TOKEN/g" "$TEMPLATE_FILE" > "$SERVICE_DIR/traderbot-agent@$AGENT_NAME.service"

# Enable the service
if systemctl --user enable "traderbot-agent@$AGENT_NAME.service" 2>/dev/null; then
    systemctl --user start "traderbot-agent@$AGENT_NAME.service"
    echo "Service installed and started for agent: $AGENT_NAME"
else
    # If user doesn't have systemd running (e.g., not logged in with systemd), just install
    echo "Service file installed for agent: $AGENT_NAME (manual start required: systemctl --user start traderbot-agent@$AGENT_NAME.service)"
fi