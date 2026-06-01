#!/bin/bash
# install-ws-daemon.sh — Install TraderBot WebSocket daemon systemd user service
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
UNIT_NAME="traderbot-ws-daemon.service"
UNIT_SRC="$SCRIPT_DIR/$UNIT_NAME"
UNIT_DST="$HOME/.config/systemd/user/$UNIT_NAME"

echo "Installing WS daemon systemd service..."
mkdir -p "$HOME/.config/systemd/user"
cp "$UNIT_SRC" "$UNIT_DST"

systemctl --user daemon-reload
systemctl --user enable "$UNIT_NAME"
systemctl --user start "$UNIT_NAME"

echo "✓ WS daemon installed and started."
echo "  Status: systemctl --user status $UNIT_NAME"
echo "  Stop:   traderbot ws stop"
echo "  Status: traderbot ws status"