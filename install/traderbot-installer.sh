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
    if [[ "$level" == "ERROR" ]]; then
        echo "[ERROR] ${message}" >&2
    elif [[ "$level" == "WARN" ]]; then
        echo "[WARN]  ${message}" >&2
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
trap '_log_error "Interrupted."; cleanup; exit 130' SIGINT
trap '_log_error "Terminated."; cleanup; exit 143' SIGTERM

_sed_inplace() {
    # Portable sed -i across GNU and BSD/macOS
    if [[ "$OSTYPE" == darwin* ]]; then
        sed -i '' "$@"
    else
        sed -i "$@"
    fi
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
        _log_error "Failed to install OpenClaw. Install manually and re-run."
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
        _log_error "Gateway install failed: $gw_install_out. Fix the issue then rerun."
        return 1
    }
    echo "  $gw_install_out"
    echo "  Starting OpenClaw gateway..."
    openclaw gateway start 2>&1 || {
        _log_error "Failed to start gateway. Start manually: openclaw gateway start"
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
    echo "  Gateway start timed out after 30s. Check: openclaw gateway status"
    _log_error "Gateway start timed out after 30s."
    return 1
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
            _log_warn "Some packages failed to install (python3.12 may need deadsnakes PPA)."
            _log_info "Attempting to add deadsnakes PPA..."
            sudo apt install -y software-properties-common 2>/dev/null
            sudo add-apt-repository -y ppa:deadsnakes/ppa 2>/dev/null
            sudo apt update
            sudo apt install -y python3.12 python3.12-venv python3.12-dev || {
                _log_error "Could not install Python 3.12. Install it manually and re-run."
                exit 3
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
            _log_error "Xcode CLI tools installation timed out."
            exit 3
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
            _log_error "Homebrew installation failed."
            exit 3
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
        _log_warn "brew install python@3.12 failed."
        _log_info "Checking for python.org installer of Python 3.12..."
        local py_bin
        py_bin="$(find_compatible_python 2>/dev/null)" || true
        if [[ -z "$py_bin" ]]; then
            _log_error "Python 3.12 not available. Install from https://www.python.org/downloads/ and re-run."
            exit 3
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
        _log_warn "uv installed but not found in PATH. You may need to restart your shell."
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
            _log_error "$INSTALL_DIR is not a git repository. Cannot update."
            exit 2
        fi
        cd "$INSTALL_DIR"
        if ! git pull origin main 2>/dev/null && ! git pull origin master 2>/dev/null; then
            _log_error "git pull failed for both 'main' and 'master' branches."
            exit 4
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
                    _log_error "git pull failed."
                    exit 4
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
                        _log_error "git pull failed. Try removing ~/traderbot and re-running the installer."
                        exit 4
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
                    _log_error "Failed to download TraderBot"
                    exit 4
                fi

                unzip -q "${temp_dir}/traderbot.zip" -d "${temp_dir}"
                local extracted_dir
                extracted_dir="$(find "${temp_dir}" -mindepth 1 -maxdepth 1 -type d -name 'TraderBot-*' | head -1)"
                if [[ -z "$extracted_dir" ]]; then
                    _log_error "Failed to extract TraderBot archive"
                    exit 3
                fi
                mv "$extracted_dir" "$INSTALL_DIR"
                echo "Warning: Installed via ZIP (no .git). Auto-update will not work."
                _log_warn "Installed via ZIP (no .git). Auto-update will not work."
                echo "To enable updates, run: cd ~/traderbot && git init && git remote add origin https://github.com/${TRADERBOT_ORG}/TraderBot.git && git fetch && git checkout main"
            fi
        fi
    fi

    cd "$INSTALL_DIR"
    echo "Installing Python dependencies into venv..."
    
    install_uv

    PYTHON_BIN=""
    if ! PYTHON_BIN="$(find_compatible_python)"; then
        _log_error "Python 3.12 is required but not found."
        _log_error "chroma-hnswlib (a dependency) has no pre-built wheels for Python 3.13+."
        _log_error "Install Python 3.12 and re-run this installer."
        _log_error "On Ubuntu/Debian: sudo apt install python3.12 python3.12-venv"
        exit 3
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
            _log_error "pip install failed. Retrying with verbose output..."
            pip install -e . 2>&1 | tail -20
            exit 3
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
        _log_error "traderbot binary not found at ${venv_bin}/traderbot"
        _log_error "Contents of ${venv_bin}/:"
        find "${venv_bin}/" -maxdepth 1 -type f -executable 2>/dev/null | head -20 >&2
        _log_error "pip install log:"
        cat "${INSTALL_DIR}/.venv/pip_install.log" 2>/dev/null || _log_error "(no log available)"
        exit 3
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

    # Detect pipx-installed TraderBot
    if command -v traderbot &>/dev/null && pipx list --short 2>/dev/null | grep -q "traderbot"; then
        echo "Pipx installation detected. Upgrading via pipx..."
        pipx upgrade traderbot
        if [[ $? -ne 0 ]]; then
            _log_error "pipx upgrade failed."
            return 1
        fi
        # Re-apply configuration via traderbot setup
        echo "Re-applying configuration..."
        if command -v traderbot &>/dev/null; then
            TRADERBOT_NON_INTERACTIVE=1 traderbot setup --non-interactive
        fi
        # Re-apply OpenClaw visibility config
        if command -v openclaw &>/dev/null; then
            openclaw config set tools.sessions.visibility agent 2>/dev/null || true
            openclaw config set tools.agentToAgent.enabled true --strict-json 2>/dev/null || true
        fi
        echo "Update complete (pipx)."
        return 0
    fi

    # Git/source install — existing flow
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
        _log_error "Failed to stop services."
        exit 3
    }
    install_traderbot "" "update" || {
        _log_error "Failed to update TraderBot."
        exit 4
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
            bash "$docker_dir/build-sandbox.sh" 2>&1 || _log_warn "sandbox image rebuild failed."
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
        _log_error "Failed to start services."
        exit 3
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

# Delegate interactive configuration to `traderbot setup`.
# The installer handles install; `traderbot setup` handles credential prompts,
# keyring setup, master password, and profile creation.
interactive_config_flow() {
    # Determine which traderbot binary to use:
    # - pip-installed: on PATH
    # - git/source install: INSTALL_DIR/.venv/bin/traderbot
    local tb_bin=""
    if command -v traderbot &>/dev/null; then
        tb_bin="traderbot"
    elif [[ -x "${INSTALL_DIR}/.venv/bin/traderbot" ]]; then
        tb_bin="${INSTALL_DIR}/.venv/bin/traderbot"
    else
        _log_warn "TraderBot binary not found. Skipping configuration."
        echo "Run 'traderbot setup' manually after installing."
        return 1
    fi

    # Build flags from installer environment variables
    local setup_flags=()
    if [[ "${TRADERBOT_NON_INTERACTIVE:-0}" == "1" ]]; then
        setup_flags+=("--non-interactive")
    fi
    if [[ "${TRADERBOT_NO_CREDS:-0}" == "1" ]]; then
        setup_flags+=("--no-creds")
    fi
    if [[ "${TRADERBOT_DRY_RUN:-0}" == "1" ]]; then
        setup_flags+=("--dry-run")
    fi
    if [[ "${TRADERBOT_JSON:-0}" == "1" ]]; then
        setup_flags+=("--json")
    fi

    echo "Running TraderBot configuration wizard..."
    if [[ ${#setup_flags[@]} -eq 0 ]]; then
        if ! "$tb_bin" setup; then
            _log_warn "traderbot setup exited with an error."
            echo "Run '$tb_bin setup' manually to complete configuration."
            return 1
        fi
    else
        if ! "$tb_bin" setup "${setup_flags[@]}"; then
            _log_warn "traderbot setup exited with an error."
            echo "Run '$tb_bin setup' manually to complete configuration."
            return 1
        fi
    fi

    # Post-setup: data pipeline and WS daemon (outside traderbot setup scope)
    local post_install_dir="${INSTALL_DIR}"
    # For pip installs, data pipeline scripts may not be available
    if [[ -x "${post_install_dir}/install/services/install-data-pipeline.sh" ]]; then
        echo "Installing data pipeline timers..."
        bash "${post_install_dir}/install/services/install-data-pipeline.sh"
    fi

    if [[ -x "${post_install_dir}/install/services/install-ws-daemon.sh" ]]; then
        echo "Installing WS daemon..."
        bash "${post_install_dir}/install/services/install-ws-daemon.sh"
    fi

    if command -v openclaw &>/dev/null && openclaw gateway status &>/dev/null; then
        echo "Restarting OpenClaw gateway to apply configuration..."
        openclaw gateway restart 2>/dev/null || true
        echo "  Gateway restart issued."
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
        _log_error "Unsupported OS. TraderBot requires macOS or Debian-based Linux (Ubuntu/Debian/Raspbian)."
        exit 2
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
