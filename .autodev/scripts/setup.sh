#!/usr/bin/env bash
# AutoDev Framework Setup
# Run once to initialize the AutoDev team on your machine.
# Prerequisites: bun, opencode, gh (authenticated), git
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
AUTODEV_DIR="$REPO_ROOT/.autodev"

echo "=== AutoDev Framework Setup ==="
echo ""

# 1. Install oh-my-openagent (Ultimate edition for OpenCode)
echo "1. Installing oh-my-openagent..."
if bunx oh-my-openagent doctor --json 2>/dev/null | grep -q '"status":"ok"'; then
  echo "   Already installed."
else
  bunx oh-my-openagent install --platform=opencode --no-tui \
    --claude=no --openai=no --gemini=no --copilot=no --skip-auth
  echo "   Installed. Model auth will need manual configuration for Ollama Cloud."
fi

# 2. Copy AutoDev config into OpenCode config
echo "2. Configuring oh-my-openagent..."
OPENCODE_CONFIG="$HOME/.config/opencode/oh-my-openagent.jsonc"
if [ -f "$OPENCODE_CONFIG" ]; then
  echo "   Existing config found at $OPENCODE_CONFIG"
  echo "   Merge .autodev/config/oh-my-openagent.jsonc settings manually."
else
  echo "   No existing config. Copying AutoDev defaults..."
  mkdir -p "$(dirname "$OPENCODE_CONFIG")"
  cp "$AUTODEV_DIR/config/oh-my-openagent.jsonc" "$OPENCODE_CONFIG"
fi

# 3. Install Magic Context
echo "3. Installing Magic Context..."
if npx @cortexkit/magic-context@latest doctor --harness opencode 2>/dev/null | grep -q "PASS"; then
  echo "   Already installed."
else
  npx @cortexkit/magic-context@latest setup --harness opencode
  echo "   Installed. Compaction should be disabled by setup."
fi

# 4. Install Loreguard
echo "4. Installing Loreguard..."
if command -v loreguard &>/dev/null; then
  echo "   Already installed."
else
  npm i -g loreguard-mcp
  echo "   Installed."
fi

# 5. Initialize Loreguard DB
echo "5. Initializing Loreguard..."
if [ -f "$REPO_ROOT/.loreguard/lore.db" ]; then
  echo "   Loreguard DB already exists."
else
  cd "$REPO_ROOT"
  loreguard init
  echo "   Initialized."
fi

# 6. Create GitHub labels
echo "6. Setting up GitHub labels..."
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "")
if [ -n "$REPO" ]; then
  bash "$AUTODEV_DIR/scripts/setup-github-labels.sh"
else
  echo "   No GitHub repo detected. Run setup-github-labels.sh manually after creating the repo."
fi

# 7. Copy GitHub issue/PR templates
echo "7. Installing GitHub templates..."
mkdir -p "$REPO_ROOT/.github"
cp "$AUTODEV_DIR/templates/autodev-request.md" "$REPO_ROOT/.github/ISSUE_TEMPLATE/" 2>/dev/null || {
  mkdir -p "$REPO_ROOT/.github/ISSUE_TEMPLATE"
  cp "$AUTODEV_DIR/templates/autodev-request.md" "$REPO_ROOT/.github/ISSUE_TEMPLATE/"
}
echo "   Done."

# 8. Create .loreguard directory for team sync
echo "8. Setting up Loreguard sync..."
mkdir -p "$REPO_ROOT/.loreguard"
echo "   Done."

# 9. Verify setup
echo ""
echo "=== Verification ==="
echo "OpenCode + OmO:"
bunx oh-my-openagent doctor --json 2>/dev/null | head -5 || echo "  Run 'bunx oh-my-openagent doctor' manually"
echo ""
echo "Magic Context:"
npx @cortexkit/magic-context@latest doctor --harness opencode 2>/dev/null | head -5 || echo "  Run 'npx @cortexkit/magic-context@latest doctor' manually"
echo ""
echo "Loreguard:"
loreguard doctor 2>/dev/null || echo "  Run 'loreguard doctor' manually"
echo ""
echo "=== Next Steps ==="
echo "1. Configure Ollama Cloud model auth in OpenCode config"
echo "2. Point OpenCode at the Traderbot repo when ready"
echo "3. Configure the liaison webhook URL when the OpenClaw gateway is ready"
echo "4. Seed Loreguard with existing Traderbot decisions (see .autodev/KNOWLEDGE-ARCHITECTURE.md)"
echo "5. Populate .autodev/reference/ with Traderbot technical docs when available"
echo "6. Run a test: 'opencode' in the Traderbot repo, then type 'ultrawork'"
