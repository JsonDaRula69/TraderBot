#!/bin/bash
# TraderBot Installer — Linux (systemd) and macOS (launchd)
set -euo pipefail

TRADERBOT_REPO="${TRADERBOT_REPO:-JsonDaRula69/TraderBot}"
TRADERBOT_ORG="${TRADERBOT_ORG:-JsonDaRula69}"
INSTALL_DIR="${HOME}/traderbot"
SUPPORTED_DISTROS="ubuntu|debian|raspbian"
_CLEANUP_TEMP_DIR=""

# ── Installer Logging ─────────────────────────────────────────────────────
TRADERBOT_LOG_DIR="${HOME}/.traderbot/logs"
TRADERBOT_INSTALL_LOG="${TRADERBOT_LOG_DIR}/install-$(date +%Y%m%d-%H%M%S).log"
mkdir -p "$TRADERBOT_LOG_DIR" 2>/dev/null || true

_log() {
    local level="$1"
    local message="$2"
    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "[${timestamp}] [${level}] ${message}" >> "$TRADERBOT_INSTALL_LOG"
    if [[ "$level" == "ERROR" ]] || [[ "$level" == "WARN" ]]; then
        echo "  ${message}" >&2
    fi
}

_log_info()  { _log "INFO" "$1"; }
_log_warn()  { _log "WARN" "$1"; }
_log_error() { _log "ERROR" "$1"; }

# Drain leftover stdin so subsequent read -r prompts don't consume stale newlines
# from piped OpenClaw commands (e.g. config validate | head)
_flush_stdin() {
    local _fs_extra=""
    read -rt 0.01 _fs_extra 2>/dev/null || true
}

_log_info "Installer started. Log: $TRADERBOT_INSTALL_LOG"

cleanup() {
    if [[ -n "$_CLEANUP_TEMP_DIR" ]] && [[ -d "$_CLEANUP_TEMP_DIR" ]]; then
        rm -rf "$_CLEANUP_TEMP_DIR"
    fi
}
trap cleanup EXIT
trap 'echo "Interrupted."; cleanup; exit 130' SIGINT
trap 'echo "Terminated."; cleanup; exit 143' SIGTERM

_sed_inplace() {
    # Portable sed -i across GNU and BSD/macOS
    if [[ "$OSTYPE" == darwin* ]]; then
        sed -i '' "$@"
    else
        sed -i "$@"
    fi
}

_read_tier() {
    local prompt="$1"
    local min="$2"
    local max="$3"
    local default="${4:-1}"
    local choice=""
    while true; do
        read -r -p "$prompt" choice
        if [[ -z "$choice" ]]; then
            echo "$default"
            return
        fi
        if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= min && choice <= max )); then
            echo "$choice"
            return
        fi
        echo "  Invalid selection. Enter a number between $min and $max." >&2
    done
}

_validate_key() {
    local key="$1"
    local name="$2"
    local min_len="${3:-8}"
    if [[ ${#key} -lt "$min_len" ]]; then
        read -r -p "  Warning: $name seems too short (${#key} chars, expected at least $min_len). Continue? [y/N]: " confirm
        if [[ ! "$confirm" =~ ^[Yy] ]]; then
            return 1
        fi
    fi
    return 0
}

_validate_prefix() {
    local key="$1"
    local prefix="$2"
    local name="$3"
    if [[ "$key" != "$prefix"* ]]; then
        read -r -p "  Warning: $name typically starts with '$prefix'. Continue? [y/N]: " confirm
        if [[ ! "$confirm" =~ ^[Yy] ]]; then
            return 1
        fi
    fi
    return 0
}

_detect_kalshi_tier() {
    local env_file="$1"
    local python_bin
    python_bin=$(command -v python3 || command -v python || echo "")
    if [[ -z "$python_bin" ]]; then
        return 1
    fi
    echo "  Auto-detecting Kalshi API tier..."
    local tier_info
    tier_info=$("$python_bin" -c "
import sys, json, traceback
from pathlib import Path

env_path = Path.home() / '.traderbot' / '.env'
env_vars = {}
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            env_vars[k.strip()] = v.strip().strip('\"\"')

api_key = env_vars.get('KALSHI_API_KEY', '')
pem_path = env_vars.get('KALSHI_PRIVATE_KEY_PATH', '')

if not api_key or not pem_path:
    print('MISSING')
    sys.exit(1)

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    import base64, time, urllib.request, urllib.error

    private_key = serialization.load_pem_private_key(
        Path(pem_path).read_bytes(), password=None
    )
    ts_ms = int(time.time() * 1000)
    msg = f'{ts_ms}GET/trade-api/v2/account/limits'
    sig = private_key.sign(
        msg.encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256()
    )
    sig_b64 = base64.b64encode(sig).decode()

    req = urllib.request.Request(
        'https://api.elections.kalshi.com/trade-api/v2/account/limits',
        headers={
            'KALSHI-ACCESS-KEY': api_key,
            'KALSHI-ACCESS-TIMESTAMP': str(ts_ms),
            'KALSHI-ACCESS-SIGNATURE': sig_b64,
            'Accept': 'application/json'
        }
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
        tier = data.get('usage_tier', 'basic').lower()
        rate = data.get('read', {}).get('refill_rate', 20)
        print(f'{tier}:{rate}')
except urllib.error.HTTPError as e:
    print(f'HTTP_ERROR:{e.code}:{e.reason}')
    sys.exit(1)
except Exception:
    traceback.print_exc()
    sys.exit(1)
") || tier_info=""

    if [[ -z "$tier_info" ]] || [[ "$tier_info" == MISSING ]]; then
        echo "  Auto-detection failed."
        return 1
    fi
    if [[ "$tier_info" == HTTP_ERROR:* ]]; then
        local err_code="${tier_info##HTTP_ERROR:}"
        err_code="${err_code%%:*}"
        if [[ "$err_code" == "401" ]] || [[ "$err_code" == "403" ]]; then
            echo "  Auto-detection failed: Authentication error (HTTP $err_code)"
        elif [[ "$err_code" == "404" ]]; then
            echo "  Auto-detection failed: API endpoint not found (HTTP 404) — tier unknown"
        else
            echo "  Auto-detection failed: HTTP error $err_code"
        fi
        return 1
    fi

    local detected_tier="${tier_info%%:*}"
    local detected_rate="${tier_info##*:}"
    echo "  Detected tier: ${detected_tier} (${detected_rate} req/sec)"
    _env_set "$env_file" "KALSHI_RATE_LIMIT_RPS" "$detected_rate"
    return 0
}

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

TraderBot Installer - installs and configures TraderBot agents

OPTIONS:
    --uninstall     Uninstall all TraderBot services and remove service files
    --update       Pull latest from GitHub and restart services
    --help          Show this help message

EXAMPLES:
    $(basename "$0")                  Interactive install
    $(basename "$0") --uninstall      Uninstall all services
    $(basename "$0") --update         Update and restart services
EOF
}

detect_os() {
    if [[ "$OSTYPE" == darwin* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == linux-gnu* ]]; then
        if grep -qE "$SUPPORTED_DISTROS" /etc/os-release 2>/dev/null || grep -qE "$SUPPORTED_DISTROS" /etc/debian_version 2>/dev/null; then
            echo "linux-debian"
        else
            echo "linux-other"
        fi
    else
        echo "unsupported"
    fi
}

# Find a compatible Python (3.12.x only — chroma-hnswlib has no wheels for 3.13+).
# Prefer system Python over linuxbrew/homebrew versions which may be too new.
find_compatible_python() {
    local candidates=()

    # Prioritise system Python on Debian/Ubuntu
    if [[ -f "/usr/bin/python3.12" ]]; then
        candidates+=("/usr/bin/python3.12")
    fi
    # Homebrew Python 3.12 — Apple Silicon
    if [[ -f "/opt/homebrew/opt/python@3.12/bin/python3" ]]; then
        candidates+=("/opt/homebrew/opt/python@3.12/bin/python3")
    fi
    # Homebrew Python 3.12 — Intel Mac
    if [[ -f "/usr/local/opt/python@3.12/bin/python3" ]]; then
        candidates+=("/usr/local/opt/python@3.12/bin/python3")
    fi
    # pyenv / other user-local installs
    if [[ -f "$HOME/.local/bin/python3" ]]; then
        candidates+=("$HOME/.local/bin/python3")
    fi
    # General system python3 (may be 3.12 on recent Ubuntu)
    if [[ -f "/usr/bin/python3" ]]; then
        candidates+=("/usr/bin/python3")
    fi
    # Homebrew/linuxbrew Python — checked last (often too new)
    if command -v python3 &>/dev/null; then
        candidates+=("python3")
    fi

    for py in "${candidates[@]}"; do
        local ver
        ver="$("$py" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)" || continue
        if [[ "$ver" == "3.12" ]]; then
            echo "$py"
            return 0
        fi
    done

    # No compatible Python found
    return 1
}

check_openclaw() {
    _log_info "Checking for OpenClaw..."
    if command -v openclaw &>/dev/null; then
        local oc_ver
        oc_ver="$(openclaw --version 2>/dev/null || echo 'installed')"
        echo "  OpenClaw found: $oc_ver"
        _log_info "OpenClaw found: $oc_ver"
        return 0
    fi
    echo "  OpenClaw not found."
    echo ""
    echo "┌─────────────────────────────────────────────────────────┐"
    echo "│  OpenClaw Gateway Required                             │"
    echo "│                                                         │"
    echo "│  TraderBot agents run as OpenClaw agents. The gateway  │"
    echo "│  manages agent sessions, cron jobs, and hooks.         │"
    echo "│                                                         │"
    echo "│  Install OpenClaw now? (requires npm, ~30s)            │"
    echo "└─────────────────────────────────────────────────────────┘"
    local install_openclaw=""
    read -r -p "Install OpenClaw via npm? (y/n): " install_openclaw
    if [[ ! "${install_openclaw:-}" =~ ^[Yy]$ ]]; then
        echo ""
        echo "OpenClaw is required. Install manually:"
        echo "  npm install -g openclaw"
        echo "Or use the official installer:"
        echo "  curl -fsSL https://openclaw.ai/install.sh | bash"
        echo "Then re-run this installer."
        return 1
    fi
    if ! command -v npm &>/dev/null; then
        echo "npm not found. Install Node.js first:"
        echo "  Linux: curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs"
        echo "  macOS: brew install node"
        echo ""
        echo "Or use OpenClaw's standalone installer (no npm needed):"
        echo "  curl -fsSL https://openclaw.ai/install.sh | bash"
        return 1
    fi
    echo "  Installing OpenClaw via npm..."
    npm install -g openclaw 2>&1 || {
        echo "  Failed to install OpenClaw. Install manually and re-run." >&2
        return 1
    }
    # Approve postinstall scripts for bundled plugins (Telegram, Discord, etc.)
    echo "  Approving OpenClaw plugin scripts..."
    npm approve-scripts openclaw 2>/dev/null || true
    # Rehash PATH — npm global bin may not be in current shell's PATH
    if ! command -v openclaw &>/dev/null; then
        hash -r 2>/dev/null || true
        local npm_prefix
        npm_prefix="$(npm config get prefix 2>/dev/null || echo "$HOME/.npm-global")"
        if [[ -x "$npm_prefix/bin/openclaw" ]]; then
            export PATH="$npm_prefix/bin:$PATH"
            echo "  Added $npm_prefix/bin to PATH."
        fi
    fi
    echo "  OpenClaw installed successfully."
    return 0
}

ensure_gateway_running() {
    _log_info "Checking gateway status..."
    if openclaw gateway status &>/dev/null; then
        echo "  OpenClaw gateway is running."
        _log_info "Gateway already running."
        return 0
    fi
    echo ""
    echo "OpenClaw gateway is not running."
    local setup_gw=""
    read -r -p "Install gateway service and start now? (y/n): " setup_gw
    if [[ ! "${setup_gw:-}" =~ ^[Yy]$ ]]; then
        echo "  Gateway required for agent creation and cron. Start manually: openclaw gateway start"
        return 1
    fi
    echo "  Installing OpenClaw gateway service..."
    local gw_install_out
    gw_install_out=$(openclaw gateway install 2>&1) || {
        echo "  Gateway install failed:" >&2
        echo "  $gw_install_out" >&2
        echo "  Fix the issue then rerun." >&2
        return 1
    }
    echo "  $gw_install_out"
    echo "  Starting OpenClaw gateway..."
    openclaw gateway start 2>&1 || {
        echo "  Failed to start gateway. Start manually: openclaw gateway start" >&2
        return 1
    }
    # Wait for gateway to be ready
    for i in $(seq 1 15); do
        if openclaw gateway status &>/dev/null; then
            echo "  Gateway is ready."
            return 0
        fi
        sleep 2
    done
    echo "  Gateway start timed out after 30s. Check: openclaw gateway status" >&2
    return 1
}

agent_exists() {
    local name="$1"
    local list_out
    list_out=$(openclaw agents list --json 2>/dev/null) || return 1
    echo "$list_out" | grep -q "\"id\":\"${name}\"" && return 0
    return 1
}

create_openclaw_agent() {
    local name="$1"
    if agent_exists "$name"; then
        echo "  Agent '$name' already exists."
        return 0
    fi
    echo "  Creating OpenClaw agent '$name'..."
    # Category agents get their own workspace subdirectory under the root
    local agent_ws="$HOME/.openclaw/workspace"
    if [[ "$name" != "main" ]]; then
        agent_ws="$HOME/.openclaw/workspace/$name"
    fi
    openclaw agents add "$name" --non-interactive --workspace "$agent_ws" 2>&1 || {
        echo "  Warning: Failed to create agent '$name'. Create manually: openclaw agents add $name" >&2
        return 1
    }
}

enable_openclaw_hooks() {
    local hooks_to_enable=("$@")
    for hook in "${hooks_to_enable[@]}"; do
        echo "  Enabling hook: $hook..."
        if openclaw hooks list 2>/dev/null | grep -q "$hook"; then
            openclaw hooks enable "$hook" 2>/dev/null || \
                echo "  Warning: failed to enable hook '$hook'."
        else
            echo "  Warning: hook '$hook' not found in available hooks. Skipping."
        fi
    done
}

check_docker() {
    if command -v docker &>/dev/null; then
        # Verify Docker daemon is running
        if docker info &>/dev/null; then
            return 0
        else
            echo "Warning: Docker is installed but the daemon is not running." >&2
            echo "  Start Docker Desktop or the Docker service." >&2
            return 1
        fi
    fi
    return 1
}

install_dependencies_debian() {
    local pkgs=(build-essential g++ python3-dev python3-venv python3.12 python3.12-venv python3.12-dev unzip curl git file python3-pip jq)

    # Install Docker if not present (optional)
    if ! command -v docker &>/dev/null; then
        echo "Installing Docker..."
        if command -v apt &>/dev/null; then
            # Add Docker's official GPG key and repository
            sudo apt-get update
            sudo apt-get install -y ca-certificates curl
            sudo install -m 0755 -d /etc/apt/keyrings
            sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
            sudo chmod a+r /etc/apt/keyrings/docker.asc
            local arch="$(dpkg --print-architecture)"
            local codename="$(. /etc/os-release && echo "$VERSION_CODENAME")"
            echo "deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${codename} stable" |                 sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
            sudo apt-get update
            sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
            sudo usermod -aG docker "$USER" 2>/dev/null || true
            echo "Docker installed. You may need to log out and back in for group changes to take effect."
        fi
    else
        echo "Docker already installed."
    fi
    if command -v apt &>/dev/null; then
        echo "Installing dependencies with apt..."
        sudo apt update
        sudo apt install -y "${pkgs[@]}" || {
            echo "Warning: Some packages failed to install (python3.12 may need deadsnakes PPA)." >&2
            echo "Attempting to add deadsnakes PPA..." >&2
            sudo apt install -y software-properties-common 2>/dev/null
            sudo add-apt-repository -y ppa:deadsnakes/ppa 2>/dev/null
            sudo apt update
            sudo apt install -y python3.12 python3.12-venv python3.12-dev || {
                echo "Error: Could not install Python 3.12. Install it manually and re-run." >&2
                exit 1
            }
        }
    fi
}

install_dependencies_macos() {
    if ! command -v xcode-select &>/dev/null || [[ ! -d "$(xcode-select -p 2>/dev/null)" ]]; then
        echo "Installing Xcode CLI tools..."
        xcode-select --install 2>/dev/null || true
        local timeout=30
        while [[ ! -d "$(xcode-select -p 2>/dev/null)" ]] && [[ $timeout -gt 0 ]]; do
            sleep 1
            ((timeout--))
        done
        if [[ ! -d "$(xcode-select -p 2>/dev/null)" ]]; then
            echo "Error: Xcode CLI tools installation timed out." >&2
            exit 1
        fi
    fi

    if ! command -v brew &>/dev/null; then
        echo "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        # Add brew to PATH (Apple Silicon vs Intel)
        if [[ -f "/opt/homebrew/bin/brew" ]]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [[ -f "/usr/local/bin/brew" ]]; then
            eval "$(/usr/local/bin/brew shellenv)"
        fi
        if ! command -v brew &>/dev/null; then
            echo "Error: Homebrew installation failed." >&2
            exit 1
        fi
    fi

    # Install Docker Desktop if not present (optional)
    if ! command -v docker &>/dev/null; then
        echo "Installing Docker Desktop via Homebrew..."
        brew install --cask docker
        echo "Docker Desktop installed. You may need to launch it from Applications."
        echo "  Open Docker Desktop and wait for it to start before running TraderBot."
    else
        echo "Docker already installed."
    fi

    echo "Installing python@3.12, git, jq via Homebrew..."
    if ! brew install python@3.12 git jq; then
        echo "Warning: brew install python@3.12 failed." >&2
        echo "Checking for python.org installer of Python 3.12..." >&2
        local py_bin
        py_bin="$(find_compatible_python 2>/dev/null)" || true
        if [[ -z "$py_bin" ]]; then
            echo "Error: Python 3.12 not available. Install from https://www.python.org/downloads/ and re-run." >&2
            exit 1
        fi
    fi
}

install_uv() {
    if command -v uv &>/dev/null; then
        return 0
    fi
    echo "Installing uv (Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Ensure uv is available in current session
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        echo "Warning: uv installed but not found in PATH. You may need to restart your shell." >&2
    fi
}

install_traderbot() {
    local install_type="${1:-install}"
    local update_mode="${2:-false}"

    if [[ "$install_type" == "update" ]] || [[ "$update_mode" == "true" ]]; then
        echo "Updating TraderBot..."
        # Try pip upgrade first (preferred for pip-installed packages)
        if command -v traderbot &>/dev/null; then
            local is_pip
            is_pip="$(which traderbot 2>/dev/null | grep -v '.venv' || true)"
            if [[ -n "$is_pip" ]]; then
                echo "  pip-installed version detected — upgrading via pip..."
                if command -v uv &>/dev/null; then
                    uv pip install --upgrade traderbot 2>&1 || true
                fi
                pip install --upgrade traderbot 2>&1 && {
                    echo "  TraderBot updated via pip."
                    return 0
                }
            fi
        fi
        # Fall back to git pull (git-installed or .venv)
        if [[ ! -d "$INSTALL_DIR/.git" ]]; then
            echo "Error: $INSTALL_DIR is not a git repository. Cannot update." >&2
            exit 1
        fi
        cd "$INSTALL_DIR"
        if ! git pull origin main 2>/dev/null && ! git pull origin master 2>/dev/null; then
            echo "Error: git pull failed for both 'main' and 'master' branches." >&2
            exit 1
        fi
    else
        # ── pip-install path (clean install, no git repo needed) ─────────
        if ! command -v traderbot &>/dev/null && ! [[ -d "$INSTALL_DIR" ]]; then
            echo "Installing TraderBot via pip from PyPI..."
            install_uv
            if command -v uv &>/dev/null; then
                uv pip install traderbot 2>&1 || true
            fi
            pip install traderbot 2>&1 && {
                echo "TraderBot installed via pip."
                return 0
            }
            echo "pip install failed — falling back to git clone."
        fi

        if [[ -d "$INSTALL_DIR" ]]; then
            if command -v traderbot &>/dev/null; then
                echo "TraderBot is already installed at $INSTALL_DIR"
                local REPLY=""
                read -r -p "Update to latest? (y/n): " REPLY
                if [[ ! ${REPLY:-} =~ ^[Yy]$ ]]; then
                    echo "Skipping installation."
                    return 0
                fi
                cd "$INSTALL_DIR"
                if ! git pull origin main 2>/dev/null && ! git pull origin master 2>/dev/null; then
                    echo "Error: git pull failed." >&2
                    exit 1
                fi
            else
                echo "Directory exists but traderbot not in PATH. Checking git state..."
                cd "$INSTALL_DIR"
                if [[ ! -d ".git" ]]; then
                    echo "Not a git repository — backing up and re-cloning..."
                    local backup_dir
                    backup_dir="${INSTALL_DIR}_backup_$(date +%s)"
                    mv "$INSTALL_DIR" "$backup_dir"
                    git clone "https://github.com/${TRADERBOT_ORG}/TraderBot.git" "$INSTALL_DIR"
                else
                    git checkout -- . 2>/dev/null || true
                    git clean -fd 2>/dev/null || true
                    if ! git pull origin main 2>&1 && ! git pull origin master 2>&1; then
                        echo "Error: git pull failed. Try removing ~/traderbot and re-running the installer." >&2
                        exit 1
                    fi
                fi
            fi
        else
            echo "Downloading TraderBot..."
            if ! git clone "https://github.com/${TRADERBOT_ORG}/TraderBot.git" "$INSTALL_DIR" 2>&1; then
                echo "git clone failed, trying ZIP fallback..."
                local temp_dir
                temp_dir="$(mktemp -d)"
                _CLEANUP_TEMP_DIR="$temp_dir"

                local http_code
                http_code="$(curl --max-time 30 --connect-timeout 10 -sSL -w '%{http_code}' -o "${temp_dir}/traderbot.zip" \
                    "https://github.com/${TRADERBOT_ORG}/TraderBot/archive/refs/heads/main.zip")"
                if [[ "$http_code" != "200" ]] || ! file "${temp_dir}/traderbot.zip" | grep -q "Zip archive"; then
                    rm -f "${temp_dir}/traderbot.zip"
                    echo "Public repo not found, checking for private repo access..."
                    read -r -p "Enter GitHub PAT for private repo (or press Enter to skip): " -s PAT
                    echo
                    if [[ -n "$PAT" ]]; then
                        curl --max-time 30 --connect-timeout 10 -sSL -H "Authorization: Bearer $PAT" \
                            "https://api.github.com/repos/${TRADERBOT_ORG}/TraderBot/zipball/main" \
                            -o "${temp_dir}/traderbot.zip"
                    fi
                fi

                if [[ ! -f "${temp_dir}/traderbot.zip" ]]; then
                    echo "Error: Failed to download TraderBot" >&2
                    exit 1
                fi

                unzip -q "${temp_dir}/traderbot.zip" -d "${temp_dir}"
                local extracted_dir
                extracted_dir="$(find "${temp_dir}" -mindepth 1 -maxdepth 1 -type d -name 'TraderBot-*' | head -1)"
                if [[ -z "$extracted_dir" ]]; then
                    echo "Error: Failed to extract TraderBot archive" >&2
                    exit 1
                fi
                mv "$extracted_dir" "$INSTALL_DIR"
                echo "Warning: Installed via ZIP (no .git). Auto-update will not work." >&2
                echo "To enable updates, run: cd ~/traderbot && git init && git remote add origin https://github.com/${TRADERBOT_ORG}/TraderBot.git && git fetch && git checkout main" >&2
            fi
        fi
    fi

    cd "$INSTALL_DIR"
    echo "Installing Python dependencies into venv..."
    
    install_uv

    PYTHON_BIN=""
    if ! PYTHON_BIN="$(find_compatible_python)"; then
        echo "Error: Python 3.12 is required but not found." >&2
        echo "  chroma-hnswlib (a dependency) has no pre-built wheels for Python 3.13+." >&2
        echo "  Install Python 3.12 and re-run this installer." >&2
        echo "  On Ubuntu/Debian: sudo apt install python3.12 python3.12-venv" >&2
        exit 1
    fi
    echo "Using Python: $PYTHON_BIN ($("$PYTHON_BIN" --version 2>&1))"

    if [[ ! -d .venv ]]; then
        "$PYTHON_BIN" -m venv .venv
    fi
    source .venv/bin/activate

    if command -v uv &>/dev/null; then
        uv pip install -e .
    else
        pip install --upgrade pip --quiet
        pip install -e . --quiet 2>&1 || {
            echo "Error: pip install failed. Retrying with verbose output..." >&2
            pip install -e . 2>&1 | tail -20
            exit 1
        }
    fi

    local venv_bin="${INSTALL_DIR}/.venv/bin"
    if [[ -f "${venv_bin}/traderbot" ]]; then
        # Try system-wide first (needs sudo), then fall back to user-local
        if sudo ln -sf "${venv_bin}/traderbot" /usr/local/bin/traderbot 2>/dev/null; then
            :
        else
            mkdir -p "${HOME}/.local/bin"
            ln -sf "${venv_bin}/traderbot" "${HOME}/.local/bin/traderbot"
            # Ensure ~/.local/bin is in PATH for this session
            export PATH="${HOME}/.local/bin:${PATH}"
            # Persist for future sessions
            if ! grep -q '.local/bin' "${HOME}/.bashrc" 2>/dev/null; then
                echo "export PATH=\"\${HOME}/.local/bin:\${PATH}\"" >> "${HOME}/.bashrc"
            fi
            if ! grep -q '.local/bin' "${HOME}/.profile" 2>/dev/null; then
                echo "export PATH=\"\${HOME}/.local/bin:\${PATH}\"" >> "${HOME}/.profile"
            fi
        fi
    fi

    # Verify using the venv binary directly (more reliable than PATH lookup)
    if [[ -x "${venv_bin}/traderbot" ]]; then
        echo "TraderBot installed successfully: $("${venv_bin}/traderbot" --version 2>/dev/null || echo 'unknown')"
    else
        echo "Error: traderbot binary not found at ${venv_bin}/traderbot" >&2
        echo "Contents of ${venv_bin}/:" >&2
        find "${venv_bin}/" -maxdepth 1 -type f -executable 2>/dev/null | head -20 >&2
        echo "pip install log:" >&2
        cat "${INSTALL_DIR}/.venv/pip_install.log" 2>/dev/null || echo "(no log available)" >&2
        exit 1
    fi
}

stop_services() {
    local os_type="$1"
    if [[ "$os_type" == "macos" ]]; then
        sudo launchctl list 2>/dev/null | grep 'com.traderbot.agent' | awk '{print $3}' | while read -r label; do
            sudo launchctl bootout "system/${label}" 2>/dev/null || \
                sudo launchctl unload "/Library/LaunchDaemons/${label}.plist" 2>/dev/null || true
        done
    else
        sudo systemctl list-units --type=service --state=running 2>/dev/null | grep 'traderbot-agent@' | awk '{print $1}' | while read -r unit; do
            sudo systemctl stop "$unit" 2>/dev/null || true
        done
    fi
}

uninstall_services() {
    local os_type="$1"

    local tb_bin="${INSTALL_DIR}/.venv/bin/traderbot"
    if [[ -x "$tb_bin" ]]; then
        echo "Uninstalling via traderbot CLI..."
        if "$tb_bin" uninstall --json &>/dev/null; then
            echo "TraderBot uninstalled."
            return 0
        fi
        echo "  Warning: CLI uninstall had issues, falling back to manual cleanup."
    else
        tb_bin="$(command -v traderbot 2>/dev/null || true)"
        if [[ -x "$tb_bin" ]]; then
            echo "Uninstalling via traderbot CLI..."
            if "$tb_bin" uninstall --json &>/dev/null; then
                echo "TraderBot uninstalled."
                return 0
            fi
        fi
    fi

    echo "Performing manual cleanup..."
    if [[ "$os_type" == "macos" ]]; then
        local daemon_dir="/Library/LaunchDaemons"
        if [[ -d "$daemon_dir" ]]; then
            find "$daemon_dir" -maxdepth 1 -name 'com.traderbot.*.plist' 2>/dev/null | while read -r plist; do
                local label
                label="$(basename "$plist" .plist)"
                sudo launchctl bootout "system/${label}" 2>/dev/null || \
                    sudo launchctl unload "$plist" 2>/dev/null || true
                sudo rm -f "$plist"
                echo "  Removed: $plist"
            done
        fi
    else
        local service_dir="/etc/systemd/system"
        if [[ -d "$service_dir" ]]; then
            find "$service_dir" -maxdepth 1 -name 'traderbot-*@*.service' 2>/dev/null | while read -r service; do
                local unit
                unit="$(basename "$service")"
                local timer="${unit%.service}.timer"
                sudo systemctl stop "$unit" 2>/dev/null || true
                sudo systemctl disable "$unit" 2>/dev/null || true
                sudo rm -f "$service"
                sudo rm -f "$service_dir/$timer" 2>/dev/null || true
                echo "  Removed: $unit"
            done
            for wants_dir in "/etc/systemd/system/multi-user.target.wants" "/etc/systemd/system/timers.target.wants"; do
                if [[ -d "$wants_dir" ]]; then
                    find "$wants_dir" -maxdepth 1 -name 'traderbot-*' -type l 2>/dev/null | while read -r link; do
                        sudo rm -f "$link"
                        echo "  Removed symlink: $(basename "$link")"
                    done
                fi
            done
            sudo systemctl daemon-reload 2>/dev/null || true
        fi

        local user_svc_dir="${HOME}/.config/systemd/user"
        if [[ -d "$user_svc_dir" ]]; then
            find "$user_svc_dir" -maxdepth 1 \( -name 'openclaw-*gateway*' -o -name 'traderbot-*' \) 2>/dev/null | while read -r svc; do
                local unit
                unit="$(basename "$svc")"
                systemctl --user stop "$unit" 2>/dev/null || true
                systemctl --user disable "$unit" 2>/dev/null || true
                rm -f "$svc"
                echo "  Removed user service: $unit"
            done
        fi
    fi

    if [[ -L "/usr/local/bin/traderbot" ]]; then
        sudo rm -f /usr/local/bin/traderbot
        echo "  Removed: /usr/local/bin/traderbot"
    fi
    if [[ -L "${HOME}/.local/bin/traderbot" ]]; then
        rm -f "${HOME}/.local/bin/traderbot"
        echo "  Removed: ${HOME}/.local/bin/traderbot"
    fi

    local modified=false
    if grep -q '.local/bin' "${HOME}/.bashrc" 2>/dev/null; then
        sed -i.bak '/\.local\/bin/d' "${HOME}/.bashrc" && rm -f "${HOME}/.bashrc.bak"
        modified=true
    fi
    if grep -q '.local/bin' "${HOME}/.profile" 2>/dev/null; then
        sed -i.bak '/\.local\/bin/d' "${HOME}/.profile" && rm -f "${HOME}/.profile.bak"
        modified=true
    fi
    if [[ "$modified" == "true" ]]; then
        echo "  Cleaned shell config (.bashrc/.profile PATH additions)"
    fi

    if [[ -d "${HOME}/.openclaw" ]]; then
        rm -rf "${HOME}/.openclaw"
        echo "  Removed: ~/.openclaw"
    fi
    if [[ -d "${INSTALL_DIR}" ]]; then
        rm -rf "${INSTALL_DIR}"
        echo "  Removed: ${INSTALL_DIR}"
    fi
    if [[ -d "${HOME}/.traderbot" ]]; then
        rm -rf "${HOME}/.traderbot"
        echo "  Removed: ~/.traderbot"
    fi

    local _oc_sbx
    _oc_sbx="$(docker ps -aq --filter name=openclaw-sbx 2>/dev/null || true)"
    if [[ -n "$_oc_sbx" ]]; then
        docker rm -f $_oc_sbx 2>/dev/null || true
        echo "  Removed orphan sandbox containers"
    fi

    if docker images -q traderbot-sandbox:bookworm-slim &>/dev/null; then
        docker rmi -f traderbot-sandbox:bookworm-slim 2>/dev/null || true
        echo "  Removed Docker image: traderbot-sandbox:bookworm-slim"
    fi

    docker builder prune --all --force 2>/dev/null || true
    echo "  Pruned Docker build cache"

    echo "TraderBot uninstalled."
}

update_services() {
    local os_type="$1"
    local tb_bin="${INSTALL_DIR}/.venv/bin/traderbot"

    if [[ -x "$tb_bin" ]]; then
        echo "Verifying Ed25519 update trust anchor..."
        if "$tb_bin" update --check 2>/dev/null; then
            echo "  Ed25519 trust anchor verified."
        else
            echo "  Warning: No Ed25519 trust anchor found. Initialising..."
            "$tb_bin" update --init-trust 2>/dev/null || echo "  Warning: --init-trust failed. Proceeding without trust verification."
        fi

        echo "Refreshing Kalshi TLS pin..."
        "$tb_bin" auth check 2>/dev/null || echo "  Warning: TLS pin refresh failed."
    fi

    stop_services "$os_type" || {
        echo "Error: Failed to stop services." >&2
        exit 1
    }
    install_traderbot "" "update" || {
        echo "Error: Failed to update TraderBot." >&2
        exit 1
    }
    # Refresh data pipeline timers
    if [[ -x "$INSTALL_DIR/install/services/install-data-pipeline.sh" ]]; then
        echo "Refreshing data pipeline timers..."
        bash "$INSTALL_DIR/install/services/install-data-pipeline.sh"
    fi

    # Re-register sysadmin and agent cron jobs after update
    if [[ -x "$tb_bin" ]]; then
        echo "Re-registering sysadmin cron jobs..."
        "$tb_bin" cron setup-heartbeat-tasks --agent main --role sysadmin --replace 2>/dev/null || true
        # Re-register cron for category agents only (not main — that's sysadmin)
        for agent_dir in "$HOME/.openclaw/agents"/weather/agent; do
            if [[ -d "$agent_dir" ]]; then
                local ag_id
                ag_id="$(basename "$(dirname "$agent_dir")")"
                echo "Re-registering cron jobs for $ag_id..."
                "$tb_bin" cron setup-heartbeat-tasks --agent "$ag_id" --replace 2>/dev/null || true
            fi
        done
    fi

    # Rebuild Docker sandbox image (new image tags, Python version bumps)
    if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
        local docker_dir="$INSTALL_DIR/install/docker"
        if [[ -x "$docker_dir/build-sandbox.sh" ]]; then
            echo "Rebuilding Docker sandbox image..."
            bash "$docker_dir/build-sandbox.sh" 2>&1 || echo "  Warning: sandbox image rebuild failed." >&2
        fi
echo "Re-applying OpenClaw sandbox configuration..."
        openclaw config set agents.defaults.sandbox.docker.binds "[\"${HOME}/traderbot:/traderbot:ro\",\"${HOME}/.traderbot:/home/traderbot/.traderbot:rw\"]" --strict-json 2>/dev/null || true
        openclaw config set agents.defaults.sandbox.docker.dangerouslyAllowExternalBindSources true 2>/dev/null || true
        openclaw config set 'agents.list[0].sandbox.mode' off 2>/dev/null || true
    fi

    # Refresh agent workspace files (replace templates, preserve user data)
    echo "Refreshing agent workspace files..."
    local ws_root="$HOME/.openclaw/workspace"
    local template_root="$INSTALL_DIR/.openclaw/workspace"
    for agent_dir in "$ws_root"/*/; do
        [ -d "$agent_dir" ] || continue
        local ag_name
        ag_name="$(basename "$agent_dir")"

        # Determine template source
        local tdir=""
        if [[ "$ag_name" == "main" ]] || grep -q "system administrator\|sysadmin\|fleet oversight" "$agent_dir/AGENTS.md" 2>/dev/null; then
            tdir="$template_root"
        elif [[ -d "$template_root/$ag_name" ]]; then
            tdir="$template_root/$ag_name"
        elif [[ -d "$template_root/agents/$ag_name" ]]; then
            tdir="$template_root/agents/$ag_name"
        else
            tdir="$template_root/agent"
        fi

        if [[ ! -d "$tdir" ]]; then
            echo "  Skipping $ag_name — no template dir ($tdir)"
            continue
        fi

        # Template files to replace (overwrite)
        local replaced=0
        local preserved=0
        for f in AGENTS.md SOUL.md TOOLS.md IDENTITY.md HEARTBEAT.md; do
            if [[ -f "$tdir/$f" ]]; then
                cp "$tdir/$f" "$agent_dir/$f" 2>/dev/null && ((replaced++)) || true
            fi
        done
        # Preserved files (never overwrite)
        for f in USER.md HEARTBEAT_DATA.md SESSION-STATE.md MEMORY.md; do
            if [[ -f "$agent_dir/$f" ]]; then
                ((preserved++))
            fi
        done
        # Preserved directories
        for d in .learnings; do
            if [[ -d "$agent_dir/$d" ]]; then
                ((preserved++))
            fi
        done
        if [[ $replaced -gt 0 || $preserved -gt 0 ]]; then
            echo "  $ag_name: $replaced files replaced, $preserved files preserved"
        fi
    done
    start_services "$os_type" || {
        echo "Error: Failed to start services." >&2
        exit 1
    }
}

stop_services() {
    local os_type="$1"
    if [[ "$os_type" == "macos" ]]; then
        sudo launchctl bootout system/com.traderbot.news-ingest.* 2>/dev/null || true
        sudo launchctl bootout system/com.traderbot.backfill-data.* 2>/dev/null || true
        find /Library/LaunchDaemons -maxdepth 1 -name 'com.traderbot.agent.*.plist' 2>/dev/null | while read -r plist; do
            local label
            label="$(basename "$plist" .plist)"
            sudo launchctl bootout "system/${label}" 2>/dev/null || \
                sudo launchctl unload "$plist" 2>/dev/null || true
        done
    else
        sudo systemctl stop 'traderbot-agent@*' 2>/dev/null || true
        sudo systemctl stop 'traderbot-news-ingest@*' 2>/dev/null || true
        sudo systemctl stop 'traderbot-backfill-data@*' 2>/dev/null || true
    fi
}

start_services() {
    local os_type="$1"
    if [[ "$os_type" == "macos" ]]; then
        find /Library/LaunchDaemons -maxdepth 1 -name 'com.traderbot.*.plist' 2>/dev/null | while read -r plist; do
            local label
            label="$(basename "$plist" .plist)"
            sudo launchctl kickstart -p "system/${label}" 2>/dev/null || \
                sudo launchctl load "$plist" 2>/dev/null || true
        done
    else
        sudo systemctl start 'traderbot-agent@*' 2>/dev/null || true
        sudo systemctl enable --now 'traderbot-news-ingest@*.timer' 2>/dev/null || true
        sudo systemctl enable --now 'traderbot-backfill-data@*.timer' 2>/dev/null || true
    fi
}

install_service_for_agent() {
    local agent_name="$1"
    local profile_token="$2"
    local os_type="$3"
    local script_dir="${INSTALL_DIR}"
    if [[ "$os_type" == "macos" ]]; then
        bash "${script_dir}/install/services/install-launchd.sh" "$agent_name" "$profile_token"
    else
        bash "${script_dir}/install/services/install-service.sh" "$agent_name" "$profile_token"
    fi
}

_env_set() {
    local env_file="$1"
    local key="$2"
    local value="$3"
    if grep -q "^${key}=" "$env_file" 2>/dev/null; then
        local tmp_file
        tmp_file="$(mktemp)"
        while IFS= read -r line || [[ -n "$line" ]]; do
            if [[ "$line" == "${key}="* ]]; then
                echo "${key}=${value}"
            else
                echo "$line"
            fi
        done < "$env_file" > "$tmp_file"
        mv "$tmp_file" "$env_file"
    else
        echo "${key}=${value}" >> "$env_file"
    fi
}

setup_api_credentials() {
    local tb_cmd="${INSTALL_DIR}/.venv/bin/traderbot"
    if [[ ! -x "$tb_cmd" ]]; then
        echo "TraderBot binary not found. Skipping API credential setup." >&2
        return 1
    fi

    if [[ "${TRADERBOT_NON_INTERACTIVE:-0}" == "1" ]]; then
        echo "Non-interactive mode — skipping API credential prompts."
        echo "Set credentials later with: traderbot auth set-key"
        return 0
    fi

    echo
    echo "=== API Credentials ==="
    echo "Kalshi credentials are required. Other services are optional."
    echo

    mkdir -p "${HOME}/.traderbot"
    local env_file="${HOME}/.traderbot/.env"
    touch "$env_file"
    chmod 600 "$env_file"

    local REPLY=""

    # --- Kalshi (required) ---
    echo "--- Kalshi (required) ---"
    local kalshi_key=""
    local kalshi_secret=""
    local retry_mode="both"
    while true; do
        if [[ "$retry_mode" == "both" ]]; then
            kalshi_key=""
            kalshi_secret=""
        elif [[ "$retry_mode" == "key" ]]; then
            kalshi_key=""
        elif [[ "$retry_mode" == "pem" ]]; then
            kalshi_secret=""
        fi
        retry_mode="both"

        if [[ -z "$kalshi_key" ]]; then
            while true; do
                read -r -p "Kalshi API key: " kalshi_key
                if [[ -z "$kalshi_key" ]]; then
                    echo "  Kalshi API key is required. Enter it or press Ctrl+C to abort." >&2
                    continue
                fi
                if _validate_key "$kalshi_key" "Kalshi API key" 20; then
                    break
                fi
            done
        fi
        if [[ -z "$kalshi_secret" ]]; then
            echo "Kalshi API secret (paste the full PEM key including BEGIN...END markers):"
            local pem_started=false
            kalshi_secret=""
            while IFS= read -r line || [[ -n "$line" ]]; do
                if [[ "$line" == *"-----BEGIN"* ]]; then
                    pem_started=true
                fi
                if $pem_started; then
                    kalshi_secret+="$line"$'\n'
                fi
                if [[ "$line" == *"-----END"* ]]; then
                    break
                fi
                if [[ -z "$line" ]] && ! $pem_started; then
                    break
                fi
            done
            local _drain
            while IFS= read -r -t 0.3 _drain; do : ; done 2>/dev/null || true
            echo
            kalshi_secret="${kalshi_secret%$'\n'}"
            if [[ -n "$kalshi_secret" ]]; then
                local line_count
                line_count=$(printf '%s' "$kalshi_secret" | grep -c .)
                echo "  PEM key received ($line_count lines, ${#kalshi_secret} bytes)"
            fi
            if [[ -n "$kalshi_secret" ]] && [[ "$kalshi_secret" != *"BEGIN"* ]]; then
                echo "  Warning: PEM key should contain BEGIN/END markers. The key may be invalid." >&2
            fi
        fi
        _env_set "$env_file" "KALSHI_API_KEY" "$kalshi_key"
        if [[ -n "$kalshi_secret" ]]; then
            local pem_path="${HOME}/.traderbot/kalshi_key.pem"
            printf '%s' "$kalshi_secret" > "$pem_path"
            chmod 600 "$pem_path"
            _env_set "$env_file" "KALSHI_PRIVATE_KEY_PATH" "$pem_path"
        fi
        echo "Kalshi credentials stored."
        echo
        if _detect_kalshi_tier "$env_file"; then
            break
        fi
        echo
        echo "  [ERROR] Could not auto-detect Kalshi API tier. Common causes:"
        echo "    1. Incorrect API key or PEM key"
        echo "    2. No internet connectivity"
        echo "    3. Kalshi API is temporarily unavailable"
        echo
        echo "  Options:"
        echo "    r) Re-enter API key"
        echo "    p) Re-enter PEM key"
        echo "    b) Re-enter both"
        echo "    a) Abort installation"
        echo
        local fix_choice=""
        while true; do
            read -r -p "Choose option [r/p/b/a]: " fix_choice
            case "$fix_choice" in
                r|R)
                    retry_mode="key"
                    break
                    ;;
                p|P)
                    retry_mode="pem"
                    break
                    ;;
                b|B)
                    break
                    ;;
                a|A)
                    echo "Installation aborted by user."
                    exit 1
                    ;;
                *)
                    echo "  Invalid option. Choose r, p, b, or a."
                    ;;
            esac
        done
    done

    # --- NewsAPI (optional) ---
    echo
    echo "--- NewsAPI (optional) ---"
    local newsapi_key=""
    while true; do
        read -r -p "NewsAPI key (press Enter to skip): " newsapi_key
        if [[ -z "$newsapi_key" ]]; then
            break
        fi
        if ! _validate_key "$newsapi_key" "NewsAPI key" 20; then
            newsapi_key=""
            continue
        fi
        echo "  Validating NewsAPI key..."
        local newsapi_status
        newsapi_status=$(curl --max-time 10 --connect-timeout 5 -fsS -o /dev/null -w "%{http_code}" "https://newsapi.org/v2/top-headlines/sources?apiKey=${newsapi_key}" 2>/dev/null) || newsapi_status="000"
        if [[ "$newsapi_status" == "200" ]]; then
            echo "  NewsAPI key is valid."
            break
        elif [[ "$newsapi_status" == "401" ]]; then
            echo "  Invalid NewsAPI key (HTTP 401). Please re-enter."
            newsapi_key=""
            continue
        elif [[ "$newsapi_status" == "429" ]]; then
            echo "  NewsAPI key is valid but rate-limited (HTTP 429). Continuing..."
            break
        else
            echo "  Could not validate key (HTTP ${newsapi_status}). Proceeding anyway."
            break
        fi
    done
    if [[ -n "$newsapi_key" ]]; then
        _env_set "$env_file" "NEWSAPI_API_KEY" "$newsapi_key"
        echo "NewsAPI key stored."
        echo
        echo "Select NewsAPI tier:"
        echo "  1) Free      (100 requests/day)"
        echo "  2) Business  (2,500 requests/day)"
        newsapi_tier=$(_read_tier "Tier [1]: " 1 2 1)
        case "$newsapi_tier" in
            2) _env_set "$env_file" "NEWSAPI_DAILY_BUDGET" "2500" ;;
            *) _env_set "$env_file" "NEWSAPI_DAILY_BUDGET" "100" ;;
        esac
    fi
    if [[ -z "$newsapi_key" ]]; then
        echo "Skipped. Set later with: traderbot auth set-key newsapi api_key"
    fi

    # --- Voyage (optional) ---
    echo
    echo "--- Voyage (optional) ---"
    local voyage_key=""
    while true; do
        read -r -p "Voyage API key (press Enter to skip): " voyage_key
        if [[ -z "$voyage_key" ]]; then
            break
        fi
        if ! _validate_prefix "$voyage_key" "pa-" "Voyage API key"; then
            voyage_key=""
            continue
        fi
        if ! _validate_key "$voyage_key" "Voyage API key" 20; then
            voyage_key=""
            continue
        fi
        echo "  Validating Voyage API key..."
        local voyage_status
        voyage_status=$(curl --max-time 10 --connect-timeout 5 -fsS -o /dev/null -w "%{http_code}" \
            -H "Authorization: Bearer ${voyage_key}" \
            -H "Content-Type: application/json" \
            -d '{"input": ["hello"], "model": "voyage-3"}' \
            "https://api.voyageai.com/v1/embeddings" 2>/dev/null) || voyage_status="000"
        if [[ "$voyage_status" == "200" ]]; then
            echo "  Voyage API key is valid."
            break
        elif [[ "$voyage_status" == "401" ]]; then
            echo "  Invalid Voyage API key (HTTP 401). Please re-enter."
            voyage_key=""
            continue
        elif [[ "$voyage_status" == "429" ]]; then
            echo "  Voyage API key is valid but rate-limited (HTTP 429). Continuing..."
            break
        else
            echo "  Could not validate key (HTTP ${voyage_status}). Proceeding anyway."
            break
        fi
    done
    if [[ -n "$voyage_key" ]]; then
        _env_set "$env_file" "VOYAGE_API_KEY" "$voyage_key"
        echo "Voyage key stored."
    fi
    if [[ -z "$voyage_key" ]]; then
        echo "Skipped. Set later with: traderbot auth set-key voyage api_key"
    fi

    # --- Twitter/X (optional) ---
    echo
    echo "--- Twitter/X (optional) ---"
    local twitter_key=""
    while true; do
        read -r -p "Twitter API key (Bearer token, press Enter to skip): " twitter_key
        if [[ -z "$twitter_key" ]]; then
            break
        fi
        if ! _validate_key "$twitter_key" "Twitter API key" 20; then
            twitter_key=""
            continue
        fi
        echo "  Validating Twitter API key..."
        local twitter_status
        twitter_status=$(curl --max-time 10 --connect-timeout 5 -fsS -o /dev/null -w "%{http_code}" \
            -H "Authorization: Bearer ${twitter_key}" \
            "https://api.twitter.com/2/users/me" 2>/dev/null) || twitter_status="000"
        if [[ "$twitter_status" == "200" ]]; then
            echo "  Twitter API key is valid."
            break
        elif [[ "$twitter_status" == "401" ]] || [[ "$twitter_status" == "403" ]]; then
            echo "  Invalid Twitter API key (HTTP ${twitter_status}). Please re-enter."
            twitter_key=""
            continue
        elif [[ "$twitter_status" == "429" ]]; then
            echo "  Twitter API key is valid but rate-limited (HTTP 429). Continuing..."
            break
        else
            echo "  Could not validate key (HTTP ${twitter_status}). Proceeding anyway."
            break
        fi
    done
    if [[ -n "$twitter_key" ]]; then
        _env_set "$env_file" "TWITTER_API_KEY" "$twitter_key"
        echo "Twitter key stored."
    fi
    if [[ -z "$twitter_key" ]]; then
        echo "Skipped. Set later with: traderbot auth set-key twitter api_key"
    fi

    # --- Reddit (optional) ---
    echo
    echo "--- Reddit (optional) ---"
    local reddit_id=""
    local reddit_secret=""
    while true; do
        read -r -p "Reddit client ID (press Enter to skip): " reddit_id
        if [[ -z "$reddit_id" ]]; then
            break
        fi
        if ! _validate_key "$reddit_id" "Reddit client ID" 10; then
            reddit_id=""
            continue
        fi
        read -r -p "Reddit client secret: " -s reddit_secret
        echo
        if [[ -z "$reddit_secret" ]]; then
            echo "  Reddit client secret is required. Please re-enter both."
            reddit_id=""
            continue
        fi
        echo "  Validating Reddit credentials..."
        local reddit_token
        reddit_token=$(curl --max-time 10 --connect-timeout 5 -fsS -u "${reddit_id}:${reddit_secret}" \
            -d "grant_type=client_credentials" \
            -A "TraderBot/1.0" \
            "https://www.reddit.com/api/v1/access_token" 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('access_token', 'INVALID'))
except Exception:
    print('INVALID')
" 2>/dev/null) || reddit_token=""
        if [[ -n "$reddit_token" ]] && [[ "$reddit_token" != "INVALID" ]] && [[ "$reddit_token" != "null" ]]; then
            echo "  Reddit credentials are valid."
            break
        fi
        echo "  Invalid Reddit credentials. Please re-enter."
        reddit_id=""
        reddit_secret=""
    done
    if [[ -n "$reddit_id" ]]; then
        _env_set "$env_file" "REDDIT_CLIENT_ID" "$reddit_id"
        if [[ -n "$reddit_secret" ]]; then
            _env_set "$env_file" "REDDIT_CLIENT_SECRET" "$reddit_secret"
        fi
        echo "Reddit credentials stored."
    fi
    if [[ -z "$reddit_id" ]]; then
        echo "Skipped. Set later with: traderbot auth set-key reddit client_id"
    fi

    # --- OpenWeatherMap (optional) ---
    echo
    echo "--- OpenWeatherMap (optional) ---"
    echo "Free tier: 1,000 calls/day. Register at https://openweathermap.org/api"
    local owm_key=""
    while true; do
        read -r -p "OpenWeatherMap API key (press Enter to skip): " owm_key
        if [[ -z "$owm_key" ]]; then
            break
        fi
        echo "  Validating OpenWeatherMap API key..."
        local owm_status
        owm_status=$(curl --max-time 10 --connect-timeout 5 -fsS -o /dev/null -w "%{http_code}" \
            "https://api.openweathermap.org/data/2.5/weather?q=London&appid=${owm_key}" 2>/dev/null) || owm_status="000"
        if [[ "$owm_status" == "200" ]]; then
            echo "  OpenWeatherMap API key is valid."
            break
        elif [[ "$owm_status" == "401" ]]; then
            echo "  Invalid OpenWeatherMap API key (HTTP 401). Please re-enter."
            owm_key=""
            continue
        elif [[ "$owm_status" == "429" ]]; then
            echo "  OpenWeatherMap API key is valid but rate-limited (HTTP 429). Continuing..."
            break
        else
            echo "  Could not validate key (HTTP ${owm_status}). Proceeding anyway."
            break
        fi
    done
    if [[ -n "$owm_key" ]]; then
        _env_set "$env_file" "OPENWEATHER_API_KEY" "$owm_key"
        echo "OpenWeatherMap key stored."
    else
        echo "Skipped. Set later with: traderbot auth set-key openweathermap api_key"
    fi

    # --- CoinGecko (optional) ---
    echo
    echo "--- CoinGecko (optional) ---"
    echo "Free tier works without a key (30 req/min). API key increases rate limits."
    echo "Register at https://www.coingecko.com/en/api"
    local cg_key=""
    local cg_tier="demo"
    while true; do
        read -r -p "CoinGecko API key (press Enter to skip): " cg_key
        if [[ -z "$cg_key" ]]; then
            break
        fi
        echo
        echo "  Account type:"
        echo "    1) Demo     (free/public API — api.coingecko.com)"
        echo "    2) Pro      (paid plans — pro-api.coingecko.com)"
        read -r -p "  Select [1]: " cg_tier_choice
        case "$cg_tier_choice" in
            2) cg_tier="pro" ;;
            *) cg_tier="demo" ;;
        esac
        local cg_base_url="https://api.coingecko.com/api/v3"
        local cg_header_name="x-cg-demo-api-key"
        if [[ "$cg_tier" == "pro" ]]; then
            cg_base_url="https://pro-api.coingecko.com/api/v3"
            cg_header_name="x-cg-pro-api-key"
        fi
        echo "  Validating CoinGecko API key..."
        local cg_status
        cg_status=$(curl --max-time 10 --connect-timeout 5 -fsS -o /dev/null -w "%{http_code}" \
            -H "${cg_header_name}: ${cg_key}" \
            "${cg_base_url}/ping" 2>/dev/null) || cg_status="000"
        if [[ "$cg_status" == "200" ]]; then
            echo "  CoinGecko API key is valid."
            break
        elif [[ "$cg_status" == "401" ]] || [[ "$cg_status" == "403" ]]; then
            echo "  Invalid CoinGecko API key (HTTP ${cg_status}). Please re-enter."
            cg_key=""
            continue
        elif [[ "$cg_status" == "429" ]]; then
            echo "  CoinGecko API key is valid but rate-limited (HTTP 429). Continuing..."
            break
        else
            echo "  Could not validate key (HTTP ${cg_status}). Proceeding anyway."
            break
        fi
    done
    if [[ -n "$cg_key" ]]; then
        _env_set "$env_file" "COINGECKO_API_KEY" "$cg_key"
        _env_set "$env_file" "COINGECKO_TIER" "$cg_tier"
        echo "CoinGecko key stored (tier: ${cg_tier})."
    else
        echo "Skipped. Set later with: traderbot auth set-key coingecko api_key"
    fi

    # --- FRED (optional) ---
    echo
    echo "--- FRED (optional) ---"
    echo "Free tier: 120 req/min. Register at https://fred.stlouisfed.org/docs/api/api_key.html"
    local fred_key=""
    while true; do
        read -r -p "FRED API key (press Enter to skip): " fred_key
        if [[ -z "$fred_key" ]]; then
            break
        fi
        echo "  Validating FRED API key..."
        local fred_status
        fred_status=$(curl --max-time 10 --connect-timeout 5 -fsS -o /dev/null -w "%{http_code}" \
            "https://api.stlouisfed.org/fred/series?series_id=GNPCA&api_key=${fred_key}&file_type=json" 2>/dev/null) || fred_status="000"
        if [[ "$fred_status" == "200" ]]; then
            echo "  FRED API key is valid."
            break
        elif [[ "$fred_status" == "400" ]]; then
            local fred_body
            fred_body=$(curl -fsS "https://api.stlouisfed.org/fred/series?series_id=GNPCA&api_key=${fred_key}&file_type=json" 2>/dev/null | head -c 200)
            if [[ "$fred_body" == *"Bad Request"* ]] || [[ "$fred_body" == *"Invalid"* ]]; then
                echo "  Invalid FRED API key. Please re-enter."
                fred_key=""
                continue
            fi
            echo "  Could not validate key (HTTP 400). Proceeding anyway."
            break
        elif [[ "$fred_status" == "429" ]]; then
            echo "  FRED API key is valid but rate-limited (HTTP 429). Continuing..."
            break
        else
            echo "  Could not validate key (HTTP ${fred_status}). Proceeding anyway."
            break
        fi
    done
    if [[ -n "$fred_key" ]]; then
        _env_set "$env_file" "FRED_API_KEY" "$fred_key"
        echo "FRED key stored."
    else
        echo "Skipped. Set later with: traderbot auth set-key fred api_key"
    fi

    echo
    echo "API credential setup complete."
    echo "Credentials written to ${env_file}"
    return 0
}

prompt_os_keyring() {
    local tb_cmd="${INSTALL_DIR}/.venv/bin/traderbot"
    if [[ ! -x "$tb_cmd" ]]; then
        echo "TraderBot binary not found. Skipping keyring prompt." >&2
        return 1
    fi
    if [[ "${TRADERBOT_NON_INTERACTIVE:-0}" == "1" ]]; then
        echo "Non-interactive mode — skipping keyring setup."
        return 0
    fi

    local keyring_ok=false
    local python_bin
    python_bin=$(command -v python3 || command -v python || echo "")
    if [[ -n "$python_bin" ]]; then
        if "$python_bin" -c "
import keyring, keyring.backends.SecretService
from keyring.backends.SecretService import Keyring
kr = Keyring()
try:
    kr.get_preferred_collection()
    print('OK')
except Exception:
    print('FAIL')
" 2>/dev/null | grep -q "OK"; then
            keyring_ok=true
        fi
    fi

    if [[ "$keyring_ok" != "true" ]]; then
        echo
        echo "=== OS Keyring ==="
        echo "OS keyring (D-Bus / Secret Service) is not available on this system."
        echo "Credentials remain in ~/.traderbot/.env (already secured with chmod 600)."
        echo "To enable keyring later, install a desktop session or run:"
        echo "  traderbot auth set-kalshi"
        return 0
    fi

    echo
    echo "=== OS Keyring ==="
    echo "Kalshi credentials have been written to .env."
    read -r -p "Store in OS keyring for encrypted storage? [Y/n]: " keyring_choice
    if [[ -z "$keyring_choice" ]] || [[ "$keyring_choice" =~ ^[Yy]$ ]]; then
        echo "Running traderbot auth set-kalshi..."
        "$tb_cmd" auth set-kalshi 2>&1 || echo "Warning: traderbot auth set-kalshi failed." >&2
    else
        echo "Skipped. Run later with: traderbot auth set-kalshi"
    fi
}

setup_master_password() {
    local tb_cmd="${INSTALL_DIR}/.venv/bin/traderbot"
    if [[ ! -x "$tb_cmd" ]]; then
        echo "TraderBot binary not found. Skipping master password setup." >&2
        return 1
    fi
    if [[ "${TRADERBOT_NON_INTERACTIVE:-0}" == "1" ]]; then
        echo "Non-interactive mode — skipping master password setup."
        echo "Set later with: traderbot auth setup-master-password"
        return 0
    fi
    echo
    echo "=== Master Password ==="
    echo "A master password is required to gate trade/simulate commands."
    echo "This uses PBKDF2 key derivation to secure your master key."
    echo
    if "$tb_cmd" auth check-master-password --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('configured') else 1)" 2>/dev/null; then
        echo "Master password already configured."
        return 0
    fi
    echo "Running traderbot auth setup-master-password (interactive)..."
    if "$tb_cmd" auth setup-master-password 2>&1; then
        echo "Master password created. Session authenticated for 30 minutes."
    else
        echo "Warning: Master password setup failed."
        echo "Run manually: traderbot auth setup-master-password"
    fi
}

prompt_sandbox_docker() {
    if [[ "${TRADERBOT_NON_INTERACTIVE:-0}" == "1" ]]; then
        return
    fi
    echo
    echo "=== Docker Sandbox for Category Agents ==="
    echo "OpenClaw's Docker sandbox isolates category agents from the host."
    echo "Sysadmin (main) is NOT sandboxed."
    if ! command -v docker &>/dev/null; then
        echo "Docker is not installed. The sandbox image must be built manually."
        echo "  Build: bash install/docker/build-sandbox.sh"
        return
    fi
    local do_sandbox=""
    read -r -p "Build sandbox Docker image and configure OpenClaw? (y/n): " do_sandbox
    if [[ ! "${do_sandbox:-}" =~ ^[Yy]$ ]]; then
        echo "Sandbox skipped. Configure later:"
        echo "  bash install/docker/build-sandbox.sh"
        return
    fi
    local docker_dir="${INSTALL_DIR}/install/docker"
    if [[ -x "$docker_dir/build-sandbox.sh" ]]; then
        echo "  Building traderbot sandbox image..."
        bash "$docker_dir/build-sandbox.sh" 2>&1 || {
            echo "  Warning: sandbox image build failed." >&2
            return
        }
    else
        echo "  Warning: build-sandbox.sh not found." >&2
        return
    fi
    echo "  Configuring OpenClaw sandbox for category agents..."
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
        openclaw config set 'agents.list[0].sandbox.mode' off 2>/dev/null || true
    # Set tools.profile=coding for all agents (provides sessions, exec, fs tools)
    openclaw config set 'agents.list[0].tools.profile' coding 2>/dev/null || true
    # Category agents get bind mounts for CLI access and data persistence
    # Use defaults.sandbox so all sandboxed agents inherit (main has mode:off)
    openclaw config set 'agents.defaults.sandbox.docker.binds' "[\"${HOME}/traderbot:/traderbot:ro\",\"${HOME}/.traderbot:/home/traderbot/.traderbot:rw\"]" --strict-json 2>/dev/null || true
    echo "  Sandbox configured. Restart gateway: openclaw gateway restart"
}

prompt_tls_pinning() {
    local tb_cmd="${INSTALL_DIR}/.venv/bin/traderbot"
    if [[ ! -x "$tb_cmd" ]]; then
        echo "TraderBot binary not found. Skipping TLS pinning." >&2
        return 1
    fi
    if [[ "${TRADERBOT_NON_INTERACTIVE:-0}" == "1" ]]; then
        echo "Non-interactive mode — skipping TLS pinning."
        return 0
    fi
    echo
    echo "=== TLS Pinning ==="
    echo "Pin the current Kalshi API TLS certificate for added security."
    read -r -p "Update Kalshi TLS pin? [y/N]: " tls_choice
    if [[ "$tls_choice" =~ ^[Yy]$ ]]; then
        echo "Checking Kalshi TLS pin..."
        "$tb_cmd" auth check 2>&1 || echo "Warning: TLS pin update failed."
    else
        echo "Skipped. Run later with: traderbot auth check"
    fi
}

prompt_sysadmin_setup() {
    local tb_cmd="${INSTALL_DIR}/.venv/bin/traderbot"
    if [[ ! -x "$tb_cmd" ]]; then
        echo "TraderBot binary not found. Skipping sysadmin setup." >&2
        return 1
    fi
    if [[ "${TRADERBOT_NON_INTERACTIVE:-0}" == "1" ]]; then
        echo "Non-interactive mode — skipping sysadmin setup."
        return 0
    fi
    echo
    echo "=== Sysadmin Setup ==="
    echo "The sysadmin profile provides non-trading oversight, test lab management,"
    echo "and serves as the human point of contact."
    local sysadmin_reply=""
    read -r -p "Set up a sysadmin agent? (y/n): " sysadmin_reply
    if [[ ! ${sysadmin_reply:-} =~ ^[Yy]$ ]]; then
        echo "Skipping sysadmin setup."
        return 0
    fi

    local sysadmin_agent=""
    echo "  1) main  (default OpenClaw agent)"
    echo "  2) Custom agent name"
    read -r -p "Select [1]: " agent_choice
    case "$agent_choice" in
        2)
            read -r -p "Enter custom agent name: " sysadmin_agent
            ;;
        *)
            sysadmin_agent="main"
            ;;
    esac

    if [[ -z "$sysadmin_agent" ]]; then
        echo "No agent selected. Skipping sysadmin setup."
        return 0
    fi

    echo "Creating sysadmin profile and assigning to agent '$sysadmin_agent'..."
    local tb_python="${INSTALL_DIR}/.venv/bin/python3"
    if [[ -x "$tb_python" ]]; then
        "$tb_python" -c "
from traderbot.profiles.sysadmin import create_sysadmin_profile
from traderbot.profiles.registry import ProfileRegistry
registry = ProfileRegistry()
if not registry.profile_exists('sysadmin'):
    profile = create_sysadmin_profile()
    registry.create_profile(profile)
    print('Created sysadmin profile.')
else:
    print('Sysadmin profile already exists.')
" 2>/dev/null || echo "Warning: sysadmin profile creation failed." >&2
    fi

    if [[ -x "$tb_cmd" ]]; then
        set +e
        local assign_output
        assign_output=$("$tb_cmd" profile assign sysadmin "$sysadmin_agent" --yes --overwrite 2>&1)
        local assign_exit=$?
        set -e
        if [[ $assign_exit -eq 0 ]]; then
            echo "Sysadmin profile assigned to agent '$sysadmin_agent'."
            echo "$assign_output"
            # Register sysadmin cron jobs (isolated heartbeat tasks)
            echo "Registering sysadmin heartbeat cron jobs..."
            "$tb_cmd" cron setup-heartbeat-tasks --agent "$sysadmin_agent" --role sysadmin --replace 2>/dev/null || \
                echo "  Warning: sysadmin cron registration skipped."
        else
            echo "Warning: sysadmin assignment failed (exit $assign_exit)." >&2
            echo "$assign_output" >&2
            echo "Run manually later: $tb_cmd profile assign sysadmin $sysadmin_agent"
        fi
    fi
}

interactive_config_flow() {
    if [[ "${TRADERBOT_NON_INTERACTIVE:-0}" == "1" ]]; then
        echo "=== TraderBot Configuration (non-interactive) ==="
        profile_name="${TRADERBOT_PROFILE_NAME:-default}"
        profile_mode="paper"
        profile_categories="economics,politics,weather,sports,science_and_technology,crypto,commodities,companies,elections,entertainment,financials,health,mentions,social"

        local tb_bin="${INSTALL_DIR}/.venv/bin/traderbot"
        if [[ -x "$tb_bin" ]]; then
            "$tb_bin" profile create "$profile_name" --mode "$profile_mode" --categories "$profile_categories" 2>&1 || echo "Warning: profile create failed." >&2
        fi

        echo "Profile '$profile_name' created (paper mode, all categories)."
        echo "Set API credentials later with: traderbot auth set-key"
        return 0
    fi

    if [[ ! -t 0 ]]; then
        if ! exec < /dev/tty; then
            echo "Error: Interactive terminal required for configuration." >&2
            exit 1
        fi
    fi
    echo
    echo "=== TraderBot Configuration ==="
    echo

    setup_api_credentials
    prompt_os_keyring
    setup_master_password
    prompt_sandbox_docker
    prompt_tls_pinning
    prompt_sysadmin_setup

    echo
    local configure_agents=""
    read -r -p "Configure category agents? (y/n): " configure_agents
    if [[ ! "${configure_agents:-}" =~ ^[Yy]$ ]]; then
        echo "Skipping agent configuration."
        return 0
    fi

    echo "Select market categories to configure agents for (↑/↓ navigate, SPACE to toggle, ENTER to confirm):"
    echo
    local -a CAT_KEYS=(economics politics weather sports science_and_technology crypto commodities companies elections entertainment financials health mentions social)
    local -a CAT_LABELS=("Economics" "Politics" "Climate and Weather" "Sports" "Science and Technology" "Crypto" "Commodities" "Companies" "Elections" "Entertainment" "Financials" "Health" "Mentions" "Social")
    local -a CAT_SELECTED=()
    local _ci=0
    for _ci in "${!CAT_KEYS[@]}"; do
        CAT_SELECTED+=("0")
    done
    unset _ci
    local cur=0
    local profile_categories=""

    if [[ ! -t 0 ]] || [[ -z "${TERM:-}" ]]; then
        profile_categories=$(IFS=,; echo "${CAT_KEYS[*]}")
        echo "Non-interactive mode. Using all categories: $profile_categories"
    elif [[ "$(uname)" == "Darwin" ]] && ! command -v gdate &>/dev/null; then
        echo "Select categories (comma-separated numbers, or 'a' for all):"
        local i=1
        for label in "${CAT_LABELS[@]}"; do
            printf "  %2d) %s\n" "$i" "$label"
            ((i++))
        done
        echo "   a) All categories"
        read -r -p "Choice [a]: " cat_nums
        if [[ -z "$cat_nums" || "$cat_nums" == "a" ]]; then
            profile_categories=$(IFS=,; echo "${CAT_KEYS[*]}")
        else
            profile_categories=""
            local IFS=','
            for num in $cat_nums; do
                num="$(echo "$num" | tr -d ' ')"
                if [[ "$num" -ge 1 ]] && [[ "$num" -le "${#CAT_KEYS[@]}" ]] 2>/dev/null; then
                    [[ -n "$profile_categories" ]] && profile_categories+=","
                    profile_categories+="${CAT_KEYS[$((num-1))]}"
                fi
            done
            [[ -z "$profile_categories" ]] && profile_categories=$(IFS=,; echo "${CAT_KEYS[*]}")
        fi
    else
        local old_tty_settings
        old_tty_settings="$(stty -g 2>/dev/null)" || true
        # Save previous EXIT trap to avoid clobbering main script's cleanup
        local prev_exit_trap
        prev_exit_trap=$(trap -p EXIT | sed 's/^trap -- //')
        trap '[[ -n "$old_tty_settings" ]] && stty "$old_tty_settings" 2>/dev/null; echo' EXIT

        stty -echo -icanon min 1 time 0 2>/dev/null || true

        _render_cat_menu() {
            local i=0
            printf "\r\033[J"
            for label in "${CAT_LABELS[@]}"; do
                if [[ "$i" -eq "$cur" ]]; then
                    printf "\033[1m"
                fi
                if [[ "${CAT_SELECTED[$i]}" == "1" ]]; then
                    printf "  [✓] %s\033[0m\n" "$label"
                else
                    printf "  [ ] %s\033[0m\n" "$label"
                fi
                ((i++)) || true
            done
            printf "\n  ↑/↓: navigate  SPACE: toggle  ENTER: confirm\n"
        }

        _clear_cat_menu() {
            local count=$(( ${#CAT_LABELS[@]} + 2 ))
            printf "\r\033[%dA" "$count"
        }

        _render_cat_menu

        local key
        while true; do
            IFS= read -rn1 key
            if [[ "$key" == $'\x1b' ]]; then
                IFS= read -rn1 -t 0.1 key
                if [[ "$key" == '[' ]]; then
                    IFS= read -rn1 key
                    if [[ "$key" == 'A' ]]; then
                        ((cur > 0)) && ((cur--)) || true
                        _clear_cat_menu
                        _render_cat_menu
                    elif [[ "$key" == 'B' ]]; then
                        ((cur < ${#CAT_KEYS[@]} - 1)) && ((cur++)) || true
                        _clear_cat_menu
                        _render_cat_menu
                    fi
                fi
            elif [[ "$key" == ' ' ]]; then
                if [[ "${CAT_SELECTED[$cur]}" == "1" ]]; then
                    CAT_SELECTED[$cur]="0"
                else
                    CAT_SELECTED[$cur]="1"
                fi
                _clear_cat_menu
                _render_cat_menu
            elif [[ -z "$key" || "$key" == $'\n' || "$key" == $'\r' || "$key" == 'q' ]]; then
                break
            fi
        done

        [[ -n "$old_tty_settings" ]] && stty "$old_tty_settings" 2>/dev/null
        # Restore previous EXIT trap (or clear if there wasn't one)
        if [[ -n "$prev_exit_trap" ]]; then
            eval "trap $prev_exit_trap"
        else
            trap - EXIT
        fi

        profile_categories=""
        for i in "${!CAT_SELECTED[@]}"; do
            if [[ "${CAT_SELECTED[$i]}" == "1" ]]; then
                [[ -n "$profile_categories" ]] && profile_categories+=","
                profile_categories+="${CAT_KEYS[$i]}"
            fi
        done

        if [[ -z "$profile_categories" ]]; then
            echo "No categories selected. Defaulting to all categories."
            profile_categories=$(IFS=,; echo "${CAT_KEYS[*]}")
        fi

        echo
        echo "Selected categories: $profile_categories"
    fi

    # Parse selected categories
    local IFS=','
    local -a selected_cats=()
    local _c=""
    for _c in $profile_categories; do
        selected_cats+=("$_c")
    done
    unset _c
    IFS=' '

    local tb_cmd="${INSTALL_DIR}/.venv/bin/traderbot"

    # Per-category agent configuration loop — auto-configures names from categories
    local _cat=""
    for _cat in "${selected_cats[@]}"; do
        local cat_name="$_cat"

        local cat_mode="paper"
        echo "  Select mode for '$cat_name':"
        echo "    1) paper  (simulated trades, no real money)"
        read -r -p "    2) live   (real money on Kalshi) [1]: " mode_choice
        case "$mode_choice" in
            2) cat_mode="live" ;;
            *) cat_mode="paper" ;;
        esac

        local cat_profile="${cat_name}-${cat_mode}"
        if [[ -x "$tb_cmd" ]]; then
            echo "  Creating profile '$cat_profile' (mode=$cat_mode, category=$_cat)..."
            _log_info "Creating profile $cat_profile for agent $cat_name (mode=$cat_mode)"
            if ! "$tb_cmd" profile create "$cat_profile" --mode "$cat_mode" --categories "$_cat" 2>&1; then
                echo "  Warning: profile creation failed for $cat_name." >&2
                _log_warn "Profile creation failed for $cat_name"
                continue
            fi
        else
            echo "  TraderBot not found. Skipping profile creation." >&2
            continue
        fi

        if command -v openclaw &>/dev/null; then
            create_openclaw_agent "$cat_name" || true
        fi

        if [[ -x "$tb_cmd" ]]; then
            echo "  Assigning profile '$cat_profile' to agent '$cat_name'..."
            _log_info "Assigning $cat_profile to $cat_name"
            set +e
            local cat_assign_out=""
            cat_assign_out=$("$tb_cmd" profile assign "$cat_profile" "$cat_name" --yes --overwrite 2>&1)
            local assign_exit=$?
            set -e
            if [[ $assign_exit -ne 0 ]]; then
                echo "  Warning: assign failed: $cat_assign_out" >&2
                _log_warn "Assign failed for $cat_name: $cat_assign_out"
                continue
            fi
        fi

        local cat_token=""
        if [[ -x "$tb_cmd" ]]; then
            cat_token=$("$tb_cmd" profile get-token "$cat_profile" 2>/dev/null | tail -1) || true
        fi
        if [[ -n "$cat_token" ]]; then
            install_service_for_agent "$cat_name" "$cat_token" "$OS_TYPE"
        if [[ -x "$tb_cmd" ]]; then
            echo "  Registering cron jobs for $cat_name..."
            "$tb_cmd" cron setup-heartbeat-tasks --agent "$cat_name" --skip-heartbeat-config --replace 2>/dev/null || true
        fi
    fi

    if command -v openclaw &>/dev/null; then
        echo ""
        local do_bind=""
        read -r -p "  Bind '$cat_name' to a chat channel? (y/n): " do_bind
        if [[ "${do_bind:-}" =~ ^[Yy]$ ]]; then
            local -a CHAN_KEYS=("telegram" "discord" "slack" "whatsapp" "matrix")
            local -a CHAN_LABELS=("Telegram" "Discord" "Slack" "WhatsApp" "Matrix")
            local chan_cur=0
            local old_tty2
            old_tty2=$(stty -g 2>/dev/null || true)
            local prev_exit_trap2
            [[ -n "$old_tty2" ]] && stty -echo -icanon 2>/dev/null
            _render_chan_menu() {
                local ci=0
                printf "\r\033[J"
                for clabel in "${CHAN_LABELS[@]}"; do
                    if [[ "$ci" -eq "$chan_cur" ]]; then
                        printf "\033[7m  %s\033[0m\n" "$clabel"
                    else
                        printf "  %s\n" "$clabel"
                    fi
                    ((ci++)) || true
                done
                printf "\n  ↑/↓: navigate  ENTER: confirm\n"
            }
            _clear_chan_menu() {
                local ccount=$(( ${#CHAN_LABELS[@]} + 2 ))
                printf "\r\033[%dA" "$ccount"
            }
            _render_chan_menu
            while true; do
                local ckey=""
                IFS= read -rn1 ckey
                if [[ "$ckey" == $'\x1b' ]]; then
                    IFS= read -rn1 -t 0.1 ckey
                    if [[ "$ckey" == '[' ]]; then
                        IFS= read -rn1 ckey
                        if [[ "$ckey" == 'A' ]] && ((chan_cur > 0)); then
                            ((chan_cur--)) || true
                            _clear_chan_menu; _render_chan_menu
                        elif [[ "$ckey" == 'B' ]] && ((chan_cur < ${#CHAN_KEYS[@]} - 1)); then
                            ((chan_cur++)) || true
                            _clear_chan_menu; _render_chan_menu
                        fi
                    fi
                elif [[ -z "$ckey" || "$ckey" == $'\n' || "$ckey" == $'\r' ]]; then
                    break
                fi
            done
            [[ -n "$old_tty2" ]] && stty "$old_tty2" 2>/dev/null
            local bind_channel="${CHAN_KEYS[$chan_cur]}"

            if [[ "$bind_channel" == "telegram" ]]; then
                local telegram_token=""
                while true; do
                    read -r -p "  Telegram bot token (from @BotFather): " telegram_token
                    if [[ -z "$telegram_token" ]]; then
                        echo "  Skipping Telegram bind — no token provided."
                        break
                    fi
                    if ! _validate_key "$telegram_token" "Telegram bot token" 20; then
                        telegram_token=""
                        continue
                    fi
                    echo "  Configuring Telegram channel for $cat_name..."
                    openclaw channels add --channel telegram --account "$cat_name" --token "$telegram_token" 2>&1 || {
                        echo "  Warning: Telegram channel setup failed. Token may be invalid."
                        telegram_token=""
                        continue
                    }
                    echo "  Telegram channel configured."
                    break
                done
                if [[ -z "$telegram_token" ]]; then
                    echo "  Skipping bind — no channel configured."
                    continue
                fi
            fi

            echo "    Binding $cat_name to $bind_channel..."
            openclaw agents bind --agent "$cat_name" --bind "${bind_channel}:${cat_name}" 2>&1 || \
                echo "    Warning: bind failed. Run later: openclaw agents bind --agent $cat_name --bind ${bind_channel}:<id>"
        fi
    fi

    echo "  Agent '$cat_name' configured (paper, $_cat)."
        _log_info "Agent $cat_name configured: profile=$cat_profile mode=paper category=$_cat"
    done
    unset _cat

    if [[ -x "$INSTALL_DIR/install/services/install-data-pipeline.sh" ]]; then
        echo "Installing data pipeline timers..."
        bash "$INSTALL_DIR/install/services/install-data-pipeline.sh"
    fi

    if [[ -x "$tb_cmd" ]]; then
        echo "Registering sysadmin heartbeat cron jobs..."
        "$tb_cmd" cron setup-heartbeat-tasks --agent main --role sysadmin --replace 2>/dev/null || true
    fi

    if command -v openclaw &>/dev/null && openclaw gateway status &>/dev/null; then
        echo "Restarting OpenClaw gateway to apply channel config..."
        openclaw gateway restart 2>/dev/null || true
        echo "  Gateway restart issued."
    fi

    # Install WS daemon (maintains event category cache from Kalshi WebSocket)
    if [[ -x "$INSTALL_DIR/install/services/install-ws-daemon.sh" ]]; then
        echo "Installing WS daemon..."
        bash "$INSTALL_DIR/install/services/install-ws-daemon.sh"
    fi

    echo
    echo "=== Configuration Complete ==="
}


main() {
    if [[ $# -gt 0 ]]; then
        case "$1" in
            --uninstall)
                OS_TYPE="$(detect_os)"
                echo "Uninstalling TraderBot services..."
                uninstall_services "$OS_TYPE"
                exit 0
                ;;
            --update)
                OS_TYPE="$(detect_os)"
                echo "Updating TraderBot..."
                update_services "$OS_TYPE"
                exit 0
                ;;
            --help|-h)
                usage
                exit 0
                ;;
        esac
    fi

    echo "Detecting OS..."
    OS_TYPE="$(detect_os)"
    echo "Detected: $OS_TYPE"

    if [[ "$OS_TYPE" == "unsupported" ]]; then
        echo "Error: Unsupported OS. TraderBot requires macOS or Debian-based Linux (Ubuntu/Debian/Raspbian)." >&2
        exit 1
    fi

    echo "Checking for OpenClaw..."
    if ! check_openclaw; then
        exit 1
    fi

    echo "Setting up OpenClaw gateway..."
    if ensure_gateway_running; then
        echo "  Running OpenClaw baseline setup (config defaults, workspace)..."
        openclaw setup --workspace ~/.openclaw/workspace 2>&1 || \
            echo "  Warning: openclaw setup had issues. Run manually: openclaw setup; openclaw onboard"

        echo "  Creating default agents..."
        # "main" is auto-created by openclaw setup — creating it manually fails
        echo "  (agent 'main' already exists after setup)"

        echo "  Enabling bundled OpenClaw hooks..."
        enable_openclaw_hooks "command-logger" "session-memory" || true

        echo "  Running OpenClaw doctor --fix..."
        openclaw doctor --fix 2>/dev/null || true

        echo "  Validating OpenClaw configuration..."
        openclaw config validate 2>&1 | head -5 || \
            echo "  Warning: config validation found issues. Run 'openclaw config validate' to inspect."

        # Optional LLM provider configuration
        _flush_stdin
        local do_llm=""
        read -r -p "Configure an LLM provider now? (required for agents to function) (y/n): " do_llm
        if [[ "${do_llm:-}" =~ ^[Yy]$ ]]; then
            echo "  Launching LLM provider configuration wizard..."
            echo "  (Follow prompts to set up Ollama, OpenAI, or another provider)"
            openclaw configure --section models 2>&1 || \
                echo "  Warning: LLM config interrupted. Run later: openclaw configure --section models"
        fi

        # Set the default model for all agents to one that supports tools.
        # The LLM provider wizard above adds models to the provider list but
        # does NOT set agents.defaults.model — agents would default to the first
        # model in the list which may not support tool calls (e.g. kimi-k2.5).
        openclaw config set agents.defaults.model ollama/deepseek-v4-flash 2>/dev/null || \
            echo "  Warning: could not set default model. Run: openclaw config set agents.defaults.model ollama/deepseek-v4-flash"

        # Optional runtime health check
        _flush_stdin
        local do_health=""
        read -r -p "Run runtime health check? (verifies LLM endpoint, auth, plugins) (y/n): " do_health
        if [[ "${do_health:-}" =~ ^[Yy]$ ]]; then
            echo "  Running OpenClaw health check..."
            openclaw doctor 2>&1 || \
                echo "  Warning: health check found issues. Run: openclaw doctor"
        fi

        echo "  OpenClaw setup complete."
    else
        echo "  OpenClaw gateway not available. Agent creation and hooks will be manual."
    fi

    echo "Installing dependencies..."
    case "$OS_TYPE" in
        macos)
            install_dependencies_macos
            ;;
        linux-debian)
            install_dependencies_debian
            ;;
        linux-other)
            echo "Warning: Linux distro not fully supported. Manual dependency installation may be required."
            ;;
    esac

    echo "Installing TraderBot..."
    install_traderbot

    # Deploy bootstrap hook (requires traderbot CLI which was just installed)
    local tb_bin="${INSTALL_DIR}/.venv/bin/traderbot"
    if [[ -x "$tb_bin" ]]; then
        if openclaw hooks list 2>/dev/null | grep -q "traderbot-bootstrap"; then
            echo "  Enabling traderbot-bootstrap hook..."
            openclaw hooks enable "traderbot-bootstrap" 2>/dev/null || true
        fi
    fi

    echo "Running interactive configuration..."
    interactive_config_flow

    echo

    echo "Installation complete!"
}

main "$@"
