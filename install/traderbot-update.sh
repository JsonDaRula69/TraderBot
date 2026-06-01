#!/bin/bash
# traderbot-update.sh — Standalone bootstrap update script
#
# Runs the full update pipeline via shell, independent of the Python package.
# Use this when `traderbot update` is unreachable due to a broken module.
#
# USAGE:
#   bash install/traderbot-update.sh [--dev]
set -euo pipefail

TRADERBOT_REPO="${TRADERBOT_REPO:-JsonDaRula69/TraderBot}"
_BRANCH="main"
if [[ "${1:-}" == "--dev" ]]; then
    _BRANCH="dev"
fi

echo "=== TraderBot Bootstrap Update ==="
echo "  Branch: $_BRANCH"
echo ""

REPO_DIR="${HOME}/traderbot"
VENV_BIN="${REPO_DIR}/.venv/bin"
PYTHON="${VENV_BIN}/python3"
TRADERBOT_CLI="${VENV_BIN}/traderbot"

# ── Step 1: git pull ─────────────────────────────────────────────────────
cd "$REPO_DIR"
echo "  Pulling latest code from $_BRANCH..."
git stash --include-untracked 2>/dev/null || true
git pull origin "$_BRANCH" 2>&1

# ── Step 2: pip install ──────────────────────────────────────────────────
echo "  Reinstalling traderbot package..."
"$PYTHON" -m pip install -e . 2>&1

# ── Step 3: Refresh workspace files ──────────────────────────────────────
echo "  Refreshing agent workspace files..."
if [[ -d ".openclaw/workspace" ]]; then
    WS_ROOT="${HOME}/.openclaw/workspace"
    TEMPLATE_ROOT="${REPO_DIR}/.openclaw/workspace"
    for agent_dir in "$WS_ROOT"/*/; do
        [ -d "$agent_dir" ] || continue
        ag_name="$(basename "$agent_dir")"
        # Determine template source
        tdir=""
        if [[ "$ag_name" == "main" ]] || grep -q "system administrator\|sysadmin\|fleet oversight" "$agent_dir/AGENTS.md" 2>/dev/null; then
            tdir="$TEMPLATE_ROOT"
        elif [[ -d "$TEMPLATE_ROOT/$ag_name" ]]; then
            tdir="$TEMPLATE_ROOT/$ag_name"
        elif [[ -d "$TEMPLATE_ROOT/agents/$ag_name" ]]; then
            tdir="$TEMPLATE_ROOT/agents/$ag_name"
        else
            tdir="$TEMPLATE_ROOT/agent"
        fi
        if [[ -d "$tdir" ]]; then
            for f in AGENTS.md SOUL.md TOOLS.md IDENTITY.md HEARTBEAT.md; do
                [[ -f "$tdir/$f" ]] && cp "$tdir/$f" "$agent_dir/$f" 2>/dev/null || true
            done
        fi
    done
fi

# ── Step 4: Rebuild Docker sandbox image ─────────────────────────────────
if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    if [[ -x "install/docker/build-sandbox.sh" ]]; then
        echo "  Rebuilding Docker sandbox image..."
        bash "install/docker/build-sandbox.sh" 2>&1 || echo "  Warning: sandbox rebuild failed." >&2
    fi
fi

# ── Step 5: Re-apply OpenClaw sandbox config ─────────────────────────────
if command -v openclaw &>/dev/null; then
    echo "  Re-applying OpenClaw sandbox configuration..."
    openclaw config set agents.defaults.sandbox.mode non-main 2>/dev/null || true
    openclaw config set agents.defaults.sandbox.backend docker 2>/dev/null || true
    openclaw config set agents.defaults.sandbox.scope agent 2>/dev/null || true
    openclaw config set agents.defaults.sandbox.workspaceAccess rw 2>/dev/null || true
    openclaw config set agents.defaults.sandbox.docker.image traderbot-sandbox:bookworm-slim 2>/dev/null || true
    openclaw config set agents.defaults.sandbox.docker.network bridge 2>/dev/null || true
    openclaw config set agents.defaults.sandbox.docker.readOnlyRoot true 2>/dev/null || true
    openclaw config set agents.defaults.sandbox.docker.capDrop '["ALL"]' 2>/dev/null || true
    openclaw config set agents.defaults.sandbox.docker.memory 1g 2>/dev/null || true
    openclaw config set agents.defaults.sandbox.docker.dangerouslyAllowExternalBindSources true 2>/dev/null || true
    openclaw config set 'agents.defaults.sandbox.docker.extraHosts' '["api.elections.kalshi.com:127.0.0.1","api.kalshi.com:127.0.0.1","trading-api.kalshi.com:127.0.0.1"]' --strict-json 2>/dev/null || true
    openclaw config set 'agents.defaults.sandbox.docker.binds' "[\"${HOME}/traderbot:/traderbot:ro\",\"${HOME}/.traderbot:/home/traderbot/.traderbot:rw\"]" --strict-json 2>/dev/null || true
    openclaw config set 'agents.list[0].sandbox.mode' off 2>/dev/null || true
fi

# ── Step 6: Re-register cron jobs ────────────────────────────────────────
if [[ -x "$TRADERBOT_CLI" ]]; then
    echo "  Re-registering cron jobs..."
    "$TRADERBOT_CLI" cron setup-heartbeat-tasks --agent main --role sysadmin --replace 2>/dev/null || true
    for agent_dir in "$HOME/.openclaw/agents"/main/agent "$HOME/.openclaw/agents"/weather/agent; do
        if [[ -d "$agent_dir" ]]; then
            ag_id="$(basename "$(dirname "$agent_dir")")"
            "$TRADERBOT_CLI" cron setup-heartbeat-tasks --agent "$ag_id" --replace 2>/dev/null || true
        fi
    done
fi

# ── Step 7: Restart OpenClaw gateway ─────────────────────────────────────
if command -v openclaw &>/dev/null; then
    echo "  Restarting OpenClaw gateway..."
    openclaw gateway restart 2>/dev/null || true
fi

echo ""
echo "=== Update complete ==="
echo "  If you installed via symlink at /usr/local/bin/traderbot,"
echo "  it has been updated. Run 'traderbot --version' to verify."