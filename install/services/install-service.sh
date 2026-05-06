#!/bin/bash
# Usage: install-service.sh <agent_name> <profile_token>
set -euo pipefail

AGENT_NAME="$1"
PROFILE_TOKEN="$2"

if [[ -z "$AGENT_NAME" ]] || [[ -z "$PROFILE_TOKEN" ]]; then
    echo "Usage: install-service.sh <agent_name> <profile_token>" >&2
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

TEMPLATE_FILE="$(dirname "$0")/traderbot-agent@.service"

if [[ ! -f "$TEMPLATE_FILE" ]]; then
    echo "Error: template file not found: $TEMPLATE_FILE" >&2
    exit 1
fi

ENV_FILE="${HOME}/.traderbot/.env"
mkdir -p "${HOME}/.traderbot"
touch "$ENV_FILE"
chmod 600 "$ENV_FILE"

if grep -q "^TRADERBOT_PROFILE_TOKEN=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^TRADERBOT_PROFILE_TOKEN=.*|TRADERBOT_PROFILE_TOKEN=${PROFILE_TOKEN}|" "$ENV_FILE"
else
    echo "TRADERBOT_PROFILE_TOKEN=${PROFILE_TOKEN}" >> "$ENV_FILE"
fi

VENV_BIN="${HOME}/traderbot/.venv/bin/traderbot"
sed -e "s|/home/%i/traderbot/.venv/bin/traderbot|$VENV_BIN|g" "$TEMPLATE_FILE" > "/tmp/traderbot-agent@$AGENT_NAME.service"

if command -v systemd-analyze &>/dev/null; then
    if ! systemd-analyze verify "/tmp/traderbot-agent@$AGENT_NAME.service" 2>/dev/null; then
        echo "Warning: systemd-analyze verify reported issues." >&2
    fi
fi

sudo cp "/tmp/traderbot-agent@$AGENT_NAME.service" "/etc/systemd/system/traderbot-agent@$AGENT_NAME.service"
rm -f "/tmp/traderbot-agent@$AGENT_NAME.service"
sudo systemctl daemon-reload
sudo systemctl enable "traderbot-agent@$AGENT_NAME.service"
sudo systemctl start "traderbot-agent@$AGENT_NAME.service"
echo "System service installed, enabled at boot, and started for agent: $AGENT_NAME"
