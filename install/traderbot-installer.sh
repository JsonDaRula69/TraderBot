#!/bin/bash
# TraderBot Installer — Linux (systemd) and macOS (launchd)
set -euo pipefail

TRADERBOT_REPO="${TRADERBOT_REPO:-JsonDaRula69/TraderBot}"
TRADERBOT_ORG="${TRADERBOT_ORG:-JsonDaRula69}"
INSTALL_DIR="${HOME}/traderbot"
SUPPORTED_DISTROS="ubuntu|debian|raspbian"
_TRADERBOT_TEMP_FILES=""

_register_temp() {
    _TRADERBOT_TEMP_FILES="${_TRADERBOT_TEMP_FILES:+${_TRADERBOT_TEMP_FILES} }$1"
}

cleanup() {
    for f in $_TRADERBOT_TEMP_FILES; do
        if [[ -d "$f" ]]; then
            rm -rf "$f"
        elif [[ -f "$f" ]]; then
            rm -f "$f"
        fi
    done
    if [[ "${BASH_SOURCE[0]}" == /tmp/* ]]; then
        rm -f "${BASH_SOURCE[0]}"
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

_backup_config() {
    local config_path="$1"
    if [[ -f "$config_path" ]]; then
        local backup="${config_path}.bak.$(date +%Y%m%d%H%M%S)"
        cp "$config_path" "$backup"
        echo "  Backed up $config_path -> $backup"
    fi
}

_wait_for_gateway() {
    local max_attempts="${1:-10}"
    local attempt=0
    local gateway_port=""
    local oc_config="${HOME}/.openclaw/openclaw.json"
    if [[ -f "$oc_config" ]] && command -v jq &>/dev/null; then
        gateway_port=$(jq -r '.gateway.port // 18789' "$oc_config" 2>/dev/null)
    fi
    gateway_port="${gateway_port:-18789}"
    while [[ $attempt -lt $max_attempts ]]; do
        if nc -z 127.0.0.1 "$gateway_port" 2>/dev/null; then
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 2
    done
    return 1
}

_write_heartbeat_to_config() {
    local agent_id="$1"
    local interval="$2"
    local config_path="$3"

    if command -v jq &>/dev/null; then
        local tmp_file
        tmp_file="$(mktemp)"
        _register_temp "$tmp_file"
        local found
        found=$(jq -r --arg agent "$agent_id" 'any(.agents.list // [] | .[]; .id == $agent)' "$config_path" 2>/dev/null || echo "false")
        if [[ "$found" == "true" ]]; then
            jq --arg agent "$agent_id" --arg every "$interval" '
                .agents.list = [.agents.list[] | if .id == $agent then .heartbeat = {"every": $every, "lightContext": true, "isolatedSession": true} else . end]
            ' "$config_path" > "$tmp_file" && mv "$tmp_file" "$config_path"
            echo "  + heartbeat config written to $config_path"
        else
            echo "  - agent '$agent_id' not found in config -- skipping heartbeat write" >&2
        fi
    elif command -v python3 &>/dev/null; then
        python3 -c "
import json
agent_id = '$agent_id'
interval = '$interval'
config_path = '$config_path'
with open(config_path) as f:
    config = json.load(f)
agents = config.setdefault('agents', {})
agent_list = agents.setdefault('list', [])
found = False
for entry in agent_list:
    if entry.get('id') == agent_id:
        entry['heartbeat'] = {'every': interval, 'lightContext': True, 'isolatedSession': True}
        found = True
        break
if not found:
    print(f\"  - agent '{agent_id}' not found in config -- skipping heartbeat write\")
else:
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
        f.write('\n')
    print('  + heartbeat config written')
"
    else
        echo "  Warning: Neither jq nor python3 available. Cannot write heartbeat config." >&2
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
    if [[ -d "${HOME}/.openclaw" ]] && command -v openclaw &>/dev/null; then
        return 0
    fi
    return 1
}

install_dependencies_debian() {
    local pkgs=(build-essential g++ python3-dev python3-venv python3.12 python3.12-venv python3.12-dev gnome-keyring unzip curl git file python3-pip jq)
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
        if [[ -d "$INSTALL_DIR" ]]; then
            if command -v traderbot &>/dev/null; then
                echo "TraderBot is already installed at $INSTALL_DIR"
                local REPLY=""
                read -r -p "Update to latest? (y/n): " -n 1 REPLY
                echo
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
                _register_temp "$temp_dir"

                local http_code
                http_code="$(curl -sSL -w '%{http_code}' -o "${temp_dir}/traderbot.zip" \
                    "https://github.com/${TRADERBOT_ORG}/TraderBot/archive/refs/heads/main.zip")"
                if [[ "$http_code" != "200" ]] || ! file "${temp_dir}/traderbot.zip" | grep -q "Zip archive"; then
                    rm -f "${temp_dir}/traderbot.zip"
                    echo "Public repo not found, checking for private repo access..."
                    read -r -p "Enter GitHub PAT for private repo (or press Enter to skip): " -s PAT
                    echo
                    if [[ -n "$PAT" ]]; then
                        curl -sSL -H "Authorization: Bearer $PAT" \
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
    if [[ "$os_type" == "macos" ]]; then
        local daemon_dir="/Library/LaunchDaemons"
        if [[ -d "$daemon_dir" ]]; then
            find "$daemon_dir" -maxdepth 1 -name 'com.traderbot.agent.*.plist' 2>/dev/null | while read -r plist; do
                local label
                label="$(basename "$plist" .plist)"
                sudo launchctl bootout "system/${label}" 2>/dev/null || \
                    sudo launchctl unload "$plist" 2>/dev/null || true
                sudo rm -f "$plist"
                echo "Removed: $plist"
            done
        fi
    else
        local service_dir="/etc/systemd/system"
        if [[ -d "$service_dir" ]]; then
            find "$service_dir" -maxdepth 1 -name 'traderbot-agent@*.service' 2>/dev/null | while read -r service; do
                local unit
                unit="$(basename "$service")"
                sudo systemctl stop "$unit" 2>/dev/null || true
                sudo systemctl disable "$unit" 2>/dev/null || true
                sudo rm -f "$service"
                echo "Removed: $service"
            done
            sudo systemctl daemon-reload 2>/dev/null || true
        fi
    fi
    echo "Services uninstalled. Data preserved at $INSTALL_DIR and ~/.traderbot/"
}

update_services() {
    local os_type="$1"
    stop_services "$os_type" || {
        echo "Error: Failed to stop services." >&2
        exit 1
    }
    install_traderbot "" "update" || {
        echo "Error: Failed to update TraderBot." >&2
        exit 1
    }
    start_services "$os_type" || {
        echo "Error: Failed to start services." >&2
        exit 1
    }
}

start_services() {
    local os_type="$1"
    if [[ "$os_type" == "macos" ]]; then
        find /Library/LaunchDaemons -maxdepth 1 -name 'com.traderbot.agent.*.plist' 2>/dev/null | while read -r plist; do
            local label
            label="$(basename "$plist" .plist)"
            sudo launchctl kickstart -p "system/${label}" 2>/dev/null || \
                sudo launchctl load "$plist" 2>/dev/null || true
        done
    else
        sudo systemctl list-unit-files --type=service 2>/dev/null | grep 'traderbot-agent@' | awk '{print $1}' | while read -r unit; do
            sudo systemctl start "$unit" 2>/dev/null || true
        done
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
        _register_temp "$tmp_file"
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

    local use_keyring="false"
    if "$tb_cmd" auth list-keys 2>/dev/null | grep -qi 'kalshi'; then
        use_keyring="true"
        echo "Keyring detected. Credentials will be stored securely."
        echo "You can also run 'traderbot auth login' after installation for keyring storage."
        echo
    fi

    mkdir -p "${HOME}/.traderbot"
    local env_file="${HOME}/.traderbot/.env"
    touch "$env_file"
    chmod 600 "$env_file"

    local REPLY=""

    # --- Kalshi (required) ---
    echo "--- Kalshi (required) ---"
    local kalshi_key=""
    local kalshi_secret=""
    read -r -p "Kalshi API key: " kalshi_key
    if [[ -z "$kalshi_key" ]]; then
        echo "Warning: Kalshi API key is required. Set it later with: traderbot auth set-key kalshi api_key" >&2
    else
        echo "Kalshi API secret (PEM private key):"
        echo "Paste the full key including BEGIN/END markers."
        kalshi_secret=""
        while IFS= read -r line; do
            kalshi_secret="${kalshi_secret}${line}"$'\n'
            if [[ "$line" == "-----END RSA PRIVATE KEY-----" ]] || [[ "$line" == "-----END PRIVATE KEY-----" ]]; then
                break
            fi
        done
        echo
        _env_set "$env_file" "KALSHI_API_KEY" "$kalshi_key"
        if [[ "$use_keyring" == "true" ]] && [[ -n "$kalshi_key" ]]; then
            "$tb_cmd" auth set-key kalshi api_key "$kalshi_key" 2>/dev/null || true
        fi
        if [[ -n "$kalshi_secret" ]]; then
            local pem_path="${HOME}/.traderbot/kalshi_key.pem"
            printf '%s' "$kalshi_secret" > "$pem_path"
            chmod 600 "$pem_path"
            _env_set "$env_file" "KALSHI_PRIVATE_KEY_PATH" "$pem_path"
        fi
        echo "Kalshi credentials stored."
        if [[ "${mode_choice:-1}" == "2" ]]; then
            _env_set "$env_file" "KALSHI_DEMO_MODE" "false"
        else
            _env_set "$env_file" "KALSHI_DEMO_MODE" "true"
            echo "Demo mode enabled — using demo-api.kalshi.co."
        fi
        echo
        echo "Select Kalshi API tier:"
        echo "  1) Auto-detect (recommended) — queries GET /account/limits at startup"
        echo "  2) Basic     — free, 200 read / 100 write tokens/sec"
        echo "  3) Advanced  — 300 read / 300 write tokens/sec"
        echo "  4) Premier   — 1000 read / 1000 write tokens/sec"
        echo "  5) Paragon   — 2000 read / 2000 write tokens/sec"
        echo "  6) Prime     — 4000 read / 4000 write tokens/sec"
        read -r -p "Tier [1]: " kalshi_tier
        case "$kalshi_tier" in
            2) _env_set "$env_file" "KALSHI_RATE_LIMIT_RPS" "20" ;;
            3) _env_set "$env_file" "KALSHI_RATE_LIMIT_RPS" "30" ;;
            4) _env_set "$env_file" "KALSHI_RATE_LIMIT_RPS" "100" ;;
            5) _env_set "$env_file" "KALSHI_RATE_LIMIT_RPS" "200" ;;
            6) _env_set "$env_file" "KALSHI_RATE_LIMIT_RPS" "400" ;;
            *) _env_set "$env_file" "KALSHI_RATE_LIMIT_RPS" "0" ;;
        esac
    fi

    # --- NewsAPI (optional) ---
    echo
    echo "--- NewsAPI (optional) ---"
    local newsapi_key=""
    read -r -p "NewsAPI key (press Enter to skip): " newsapi_key
    if [[ -n "$newsapi_key" ]]; then
        _env_set "$env_file" "NEWSAPI_API_KEY" "$newsapi_key"
        echo "NewsAPI key stored."
        echo
        echo "Select NewsAPI tier:"
        echo "  1) Free      (100 requests/day)"
        echo "  2) Business  (2,500 requests/day)"
        read -r -p "Tier [1]: " newsapi_tier
        case "$newsapi_tier" in
            2) _env_set "$env_file" "NEWSAPI_DAILY_BUDGET" "2500" ;;
            *) _env_set "$env_file" "NEWSAPI_DAILY_BUDGET" "100" ;;
        esac
    else
        echo "Skipped. Set later with: traderbot auth set-key newsapi api_key"
    fi

    # --- Voyage (optional) ---
    echo
    echo "--- Voyage (optional) ---"
    local voyage_key=""
    read -r -p "Voyage API key (press Enter to skip): " voyage_key
    if [[ -n "$voyage_key" ]]; then
        _env_set "$env_file" "VOYAGE_API_KEY" "$voyage_key"
        echo "Voyage key stored."
    else
        echo "Skipped. Set later with: traderbot auth set-key voyage api_key"
    fi

    # --- Twitter/X (optional) ---
    echo
    echo "--- Twitter/X (optional) ---"
    local twitter_key=""
    read -r -p "Twitter API key (press Enter to skip): " twitter_key
    if [[ -n "$twitter_key" ]]; then
        _env_set "$env_file" "TWITTER_API_KEY" "$twitter_key"
        echo "Twitter key stored."
    else
        echo "Skipped. Set later with: traderbot auth set-key twitter api_key"
    fi

    # --- Reddit (optional) ---
    echo
    echo "--- Reddit (optional) ---"
    local reddit_id=""
    local reddit_secret=""
    read -r -p "Reddit client ID (press Enter to skip): " reddit_id
    if [[ -n "$reddit_id" ]]; then
        read -r -p "Reddit client secret: " -s reddit_secret
        echo
        _env_set "$env_file" "REDDIT_CLIENT_ID" "$reddit_id"
        if [[ -n "$reddit_secret" ]]; then
            _env_set "$env_file" "REDDIT_CLIENT_SECRET" "$reddit_secret"
        fi
        echo "Reddit credentials stored."
    else
        echo "Skipped. Set later with: traderbot auth set-key reddit client_id"
    fi

    echo
    echo "API credential setup complete."
    echo "Credentials written to ${env_file}"
    if [[ "$use_keyring" == "true" ]]; then
        echo "To migrate credentials to keyring, run: traderbot auth login"
    fi
    return 0
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
    echo "=== TraderBot Configuration ==="
    echo
    local REPLY=""
    read -r -p "Create a trading profile? (y/n): " -n 1 REPLY
    echo
    if [[ ! ${REPLY:-} =~ ^[Yy]$ ]]; then
        echo "Skipping profile creation."
        return 0
    fi

    profile_name=""
    while [[ -z "$profile_name" ]]; do
        read -r -p "Profile name: " profile_name
        if [[ -z "$profile_name" ]]; then
            echo "Profile name cannot be empty."
        fi
    done

    echo "Select trading mode:"
    echo "  1) paper  (recommended — no real money at risk)"
    echo "  2) live   (real money — use with caution)"
    read -r -p "Choice [1]: " mode_choice
    case "$mode_choice" in
        2) profile_mode="live" ;;
        *) profile_mode="paper" ;;
    esac

    echo "Select market categories (↑/↓ navigate, SPACE to toggle, ENTER to confirm):"
    echo
    local -a CAT_KEYS=(economics politics weather sports science_and_technology crypto commodities companies elections entertainment financials health mentions social)
    local -a CAT_LABELS=("Economics" "Politics" "Climate and Weather" "Sports" "Science and Technology" "Crypto" "Commodities" "Companies" "Elections" "Entertainment" "Financials" "Health" "Mentions" "Social")
    local -a CAT_SELECTED=()
    for _ in "${CAT_KEYS[@]}"; do
        CAT_SELECTED+=("0")
    done
    local cur=0

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

        # Drain any buffered input from previous reads
        while read -rsn1 -t 0.01 drain_key 2>/dev/null; [ -n "$drain_key" ]; do :; done

        local key
        while true; do
            IFS='' read -rsn1 key
            if [[ "$key" == $'\x1b' ]]; then
                IFS='' read -rsn1 -t 0.1 key
                if [[ "$key" == '[' ]]; then
                    IFS='' read -rsn1 -t 0.1 key
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
            elif [[ -z "$key" ]] || [[ "$key" == $'\n' ]] || [[ "$key" == $'\r' ]]; then
                break
            fi
        done

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

    if command -v traderbot &>/dev/null; then
        if ! traderbot profile create "$profile_name" --mode "$profile_mode" \
            --categories "$profile_categories" 2>&1; then
            echo "Warning: profile create failed. Try: traderbot profile create $profile_name --mode $profile_mode --categories $profile_categories" >&2
        fi
    else
        local tb_bin="${INSTALL_DIR}/.venv/bin/traderbot"
        if [[ -x "$tb_bin" ]]; then
            if ! "$tb_bin" profile create "$profile_name" --mode "$profile_mode" \
                --categories "$profile_categories" 2>&1; then
                echo "Warning: profile create failed." >&2
            fi
        else
            echo "TraderBot not in PATH. Profile creation skipped." >&2
        fi
    fi

    setup_api_credentials

    echo
    echo "=== Agent Assignment ==="
    echo "TraderBot profiles bind to OpenClaw agents."
    echo "Each agent must have a workspace created via: openclaw agents add <name>"
    echo

    if command -v openclaw &>/dev/null; then
        echo "Available agents (via openclaw agents list --bindings):"
        openclaw agents list --bindings 2>&1 || echo "  (run 'openclaw agents add <name>' to create one)"
    elif command -v traderbot &>/dev/null; then
        echo "Available agents:"
        traderbot profile discover-agents 2>&1 || echo "  (none found)"
    else
        local tb_bin="${INSTALL_DIR}/.venv/bin/traderbot"
        if [[ -x "$tb_bin" ]]; then
            echo "Available agents:"
            "$tb_bin" profile discover-agents 2>&1 || echo "  (none found)"
        else
            echo "  (traderbot not found for agent discovery)"
        fi
    fi

    echo
    read -r -p "Agent name to assign (or press Enter to skip): " agent_name
    if [[ -z "$agent_name" ]]; then
        echo "Skipping agent assignment. Run later:"
        echo "  openclaw agents add $profile_name"
        echo "  traderbot profile assign $profile_name $agent_name"
        return 0
    fi

    local tb_cmd="${INSTALL_DIR}/.venv/bin/traderbot"
    local token_value=""
    if [[ -x "$tb_cmd" ]]; then
        echo "Assigning agent $agent_name to profile $profile_name..."
        set +e
        local assign_err=""
        token_value=$("$tb_cmd" profile assign --non-interactive --token-only "$profile_name" "$agent_name" 2>/tmp/tb_assign_err_$$)
        local assign_exit=$?
        set -e
        if [[ $assign_exit -ne 0 ]]; then
            assign_err=$(cat /tmp/tb_assign_err_$$ 2>/dev/null)
            echo "Error: assign failed (exit code $assign_exit):" >&2
            echo "$assign_err" >&2
            echo "Try manually: $tb_cmd profile assign $profile_name $agent_name" >&2
            token_value=""
        else
            echo "Token: ****${token_value: -4}"
        fi
        rm -f /tmp/tb_assign_err_$$
    else
        echo "Assignment skipped. TraderBot not found."
    fi

    if [[ -n "$token_value" ]]; then
        echo "Installing service for agent $agent_name..."
        install_service_for_agent "$agent_name" "$token_value" "$OS_TYPE"
        export TRADERBOT_PROFILE_TOKEN="$token_value"
    fi

    if [[ -n "$agent_name" ]]; then
        echo
        echo "=== Cron Loop Registration ==="
        echo "Registering decision, heartbeat, and news loops with OpenClaw for agent $agent_name..."

        if command -v openclaw &>/dev/null; then
            local DECISION_MSG="AUTONOMOUS: Run traderbot decision loop. Read SESSION-STATE.md for tracked markets. Execute analysis, risk-check, and trades within guard rails. Log all decisions."
            local HEARTBEAT_MSG="HEARTBEAT: Run traderbot self-improvement cycle. Check circuit breaker, review recent decisions, update Bayesian parameters, promote learnings. Write HEARTBEAT_DATA.md."
            local NEWS_MSG="ALERT: High-impact event detected (impact). Run traderbot sentiment impact for analysis."
            local cron_ok=true

            _wait_for_gateway 15 || { echo "Warning: OpenClaw gateway not responding. Cron registration may fail." >&2; }

            # Resolve delivery target from openclaw config
            local announce_args=""
            local oc_config="${HOME}/.openclaw/openclaw.json"
            if [[ -f "$oc_config" ]]; then
                local owner_chat_id=""
                owner_chat_id=$(python3 -c "
import json
with open('$oc_config') as f:
    cfg = json.load(f)
for entry in cfg.get('commands', {}).get('ownerAllowFrom', []):
    if entry.startswith('telegram:'):
        print(entry.split(':', 1)[1])
        break
" 2>/dev/null || true)
                if [[ -n "$owner_chat_id" ]]; then
                    announce_args="--channel telegram --to $owner_chat_id"
                fi
            fi

            if openclaw cron add \
                --name decision_loop \
                --cron "*/5 * * * *" \
                --session isolated \
                --message "$DECISION_MSG" \
                --agent "$agent_name" \
                --announce $announce_args 2>&1; then
                echo "  + decision_loop registered"
            else
                echo "  x decision_loop failed" >&2
                cron_ok=false
            fi

            if openclaw cron add \
                --name heartbeat_loop \
                --every "30m" \
                --session isolated \
                --message "$HEARTBEAT_MSG" \
                --agent "$agent_name" \
                --announce $announce_args 2>&1; then
                echo "  + heartbeat_loop registered"
            else
                echo "  x heartbeat_loop failed" >&2
                cron_ok=false
            fi

            echo "  i news_loop is event-driven (no cron schedule) -- triggered by impact signals"

            local oc_config="${HOME}/.openclaw/openclaw.json"
            if [[ -f "$oc_config" ]]; then
                _backup_config "$oc_config"
                _write_heartbeat_to_config "$agent_name" "30m" "$oc_config"
            fi

            if [[ "$cron_ok" != "true" ]]; then
                echo "Warning: Some cron loops failed to register." >&2
                echo "Register manually with: openclaw cron add --agent $agent_name --name <loop_name>" >&2
            fi
        else
            echo "Warning: openclaw not found. Cron loop registration skipped." >&2
            echo "Install OpenClaw and register loops manually:" >&2
            echo "  openclaw cron add --name decision_loop --cron '*/5 * * * *' --session isolated --agent $agent_name --announce" >&2
            echo "  openclaw cron add --name heartbeat_loop --every 30m --session isolated --agent $agent_name --announce" >&2
            echo "  openclaw cron add --name news_loop --event impact --session main --agent $agent_name --announce" >&2
        fi
    fi

    echo
    echo "=== Verification ==="
    local tb_bin=""
    if command -v traderbot &>/dev/null; then
        tb_bin="traderbot"
    elif [[ -x "${INSTALL_DIR}/.venv/bin/traderbot" ]]; then
        tb_bin="${INSTALL_DIR}/.venv/bin/traderbot"
    fi

    if [[ -n "${TRADERBOT_PROFILE_TOKEN:-}" ]] && [[ -n "$tb_bin" ]]; then
            if "$tb_bin" heartbeat --dry-run --json 2>/dev/null; then
            echo "Heartbeat verification: PASSED"
        else
            echo "Heartbeat verification: FAILED (check credentials)"
        fi
    else
        if [[ -z "$tb_bin" ]]; then
            echo "TraderBot not found. Verification skipped."
        else
            echo "No profile token set. Verification skipped."
        fi
    fi
}

deploy_workspace_files() {
    local config_path="${HOME}/.openclaw/openclaw.json"
    local workspace_src="${INSTALL_DIR}/.openclaw/workspace"

    if [[ -z "${agent_name:-}" ]]; then
        echo "Warning: No agent name specified. Skipping workspace deployment." >&2
        return 1
    fi

    mkdir -p "${HOME}/.openclaw"

    if [[ ! -f "$config_path" ]]; then
        if command -v openclaw &>/dev/null; then
            echo "Initializing OpenClaw config..."
            openclaw init 2>/dev/null || true
        fi
        if [[ ! -f "$config_path" ]]; then
            python3 -c "
import json, sys
config = {
    'agents': {'defaults': {'workspace': '$HOME/.openclaw/workspace'}, 'list': []},
    'gateway': {'mode': 'local', 'port': 18789, 'bind': 'loopback'},
    'session': {'dmScope': 'per-channel-peer'},
    'tools': {'profile': 'coding'},
    'plugins': {'entries': {}},
}
with open(sys.argv[1], 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')
" "$config_path"
            echo "Created minimal OpenClaw config at $config_path."
        fi
    fi

    # Resolve agent workspace from openclaw.json -- do NOT add or modify agent entries
    local agent_ws_dir=""
    if command -v jq &>/dev/null && [[ -f "$config_path" ]]; then
        local default_ws
        default_ws=$(jq -r '.agents.defaults.workspace // ""' "$config_path" 2>/dev/null)
        agent_ws_dir=$(jq -r --arg id "$agent_name" '
            (.agents.list // [])[] | select(.id == $id) | .workspace // empty
        ' "$config_path" 2>/dev/null | head -1)
        if [[ -z "$agent_ws_dir" ]]; then
            if [[ -n "$default_ws" ]]; then
                agent_ws_dir="${default_ws}/${agent_name}"
            else
                agent_ws_dir="${HOME}/.openclaw/workspace/${agent_name}"
            fi
        fi
    elif command -v python3 &>/dev/null && [[ -f "$config_path" ]]; then
        agent_ws_dir=$(python3 -c "
import json, sys, os
agent_name = sys.argv[1]
config_path = sys.argv[2]
with open(config_path) as f:
    cfg = json.load(f)
default_ws = cfg.get('agents', {}).get('defaults', {}).get('workspace', os.path.expanduser('~/.openclaw/workspace'))
for a in cfg.get('agents', {}).get('list', []):
    if a.get('id') == agent_name:
        print(a.get('workspace', f'{default_ws}/{agent_name}'))
        sys.exit(0)
print(f'{default_ws}/{agent_name}')
" "$agent_name" "$config_path")
    fi
    agent_ws_dir="${agent_ws_dir:-${HOME}/.openclaw/workspace/${agent_name}}"

    # Expand ~ in path
    agent_ws_dir="${agent_ws_dir/#\~/$HOME}"

    echo "Deploying workspace files to $agent_ws_dir"

    if [[ -d "$workspace_src" ]]; then
        mkdir -p "$agent_ws_dir"

        # Fenced-merge files -- always overwrite (AGENTS.md, SOUL.md, TOOLS.md, HEARTBEAT.md, IDENTITY.md)
        for f in AGENTS.md SOUL.md TOOLS.md HEARTBEAT.md IDENTITY.md; do
            if [[ -f "${workspace_src}/${f}" ]]; then
                cp "${workspace_src}/${f}" "${agent_ws_dir}/${f}"
            fi
        done

        # Ask-then-merge files -- skip if target exists (BOOTSTRAP.md, BOOT.md)
        for f in BOOTSTRAP.md BOOT.md; do
            if [[ -f "${workspace_src}/${f}" ]] && [[ ! -f "${agent_ws_dir}/${f}" ]]; then
                cp "${workspace_src}/${f}" "${agent_ws_dir}/${f}"
            fi
        done

        # Init-if-missing files -- only create on fresh deploy
        for f in USER.md MEMORY.md SESSION-STATE.md HEARTBEAT_DATA.md; do
            if [[ -f "${workspace_src}/${f}" ]] && [[ ! -f "${agent_ws_dir}/${f}" ]]; then
                cp "${workspace_src}/${f}" "${agent_ws_dir}/${f}"
            fi
        done

        # .learnings directory -- only on fresh deploy
        if [[ -d "${workspace_src}/.learnings" ]] && [[ ! -d "${agent_ws_dir}/.learnings" ]]; then
            cp -r "${workspace_src}/.learnings" "${agent_ws_dir}/.learnings"
        fi

        echo "Deployed workspace template files to $agent_ws_dir"
    else
        echo "Warning: No workspace templates found at $workspace_src" >&2
    fi
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
        echo "" >&2
        echo "┌─────────────────────────────────────────────────────────┐" >&2
        echo "│  OpenClaw Gateway Required                             │" >&2
        echo "│                                                         │" >&2
        echo "│  TraderBot agents run as OpenClaw agents. The gateway  │" >&2
        echo "│  manages scheduling (cron), heartbeats, and sessions.  │" >&2
        echo "│                                                         │" >&2
        echo "│  Install: https://github.com/openclaw/openclaw         │" >&2
        echo "│                                                         │" >&2
        echo "│  After installing OpenClaw:                             │" >&2
        echo "│    1. Run: openclaw init                                │" >&2
        echo "│    2. Configure your agent workspace                    │" >&2
        echo "│    3. Re-run this installer                             │" >&2
        echo "└─────────────────────────────────────────────────────────┘" >&2
        exit 1
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

    echo "Running interactive configuration..."
    interactive_config_flow

    echo "Merging OpenClaw agent config..."
    deploy_workspace_files || true

    echo
    echo "Installation complete!"
}

main "$@"
