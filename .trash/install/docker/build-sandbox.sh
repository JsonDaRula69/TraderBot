#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_DIR="$SCRIPT_DIR"
IMAGE_TAG="traderbot-sandbox:bookworm-slim"

echo "Building traderbot sandbox image..."
echo "  Image: $IMAGE_TAG"

docker build \
  -t "$IMAGE_TAG" \
  -f "$DOCKER_DIR/Dockerfile" \
  "$DOCKER_DIR"

echo "Sandbox image built successfully: $IMAGE_TAG"
echo ""
echo "To configure OpenClaw to use this image:"
echo "  openclaw config set agents.defaults.sandbox.mode non-main"
echo "  openclaw config set agents.defaults.sandbox.backend docker"
echo "  openclaw config set agents.defaults.sandbox.scope agent"
echo "  openclaw config set agents.defaults.sandbox.workspaceAccess rw"
echo "  openclaw config set agents.defaults.sandbox.docker.image '$IMAGE_TAG'"
echo "  openclaw config set agents.defaults.sandbox.docker.network bridge"
echo "  openclaw config set agents.defaults.sandbox.docker.readOnlyRoot true"
echo "  openclaw config set agents.defaults.sandbox.docker.binds '[\"\$HOME/traderbot:/traderbot:ro\",\"\$HOME/.traderbot:/home/traderbot/.traderbot:rw\"]'"
echo "  openclaw config set agents.defaults.sandbox.docker.dns '[\"1.1.1.1\",\"8.8.8.8\"]'"
echo "  openclaw config set agents.defaults.sandbox.docker.capDrop '[\"ALL\"]'"
echo "  openclaw config set agents.defaults.sandbox.docker.memory 1g"
echo "  openclaw config set agents.defaults.sandbox.docker.dangerouslyAllowExternalBindSources true"
echo ""
echo "  # Set per-agent sandbox to off for main (sysadmin runs on host)"
echo "  openclaw config set 'agents.list[0].sandbox.mode' off"
echo ""
echo "  # Sandboxed agents inherit bind mounts from agents.defaults.sandbox.docker.binds"
echo "  echo '  (main excluded via mode:off -- set binds via defaults, not agents.list[N])'"
echo ""
echo "Restart gateway: openclaw gateway restart"
