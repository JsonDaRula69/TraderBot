#!/bin/bash
# TraderBot Installer — Linux (systemd) and macOS (launchd)
set -euo pipefail

TRADERBOT_REPO="${TRADERBOT_REPO:-JsonDaRula69/TraderBot}"
TRADERBOT_ORG="${TRADERBOT_ORG:-JsonDaRula69}"
INSTALL_DIR="${HOME}/traderbot"
SUPPORTED_DISTROS="ubuntu|debian|raspbian"
_CLEANUP_TEMP_DIR=""

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

_write_heartbeat_to_config() {
    local agent_id="$1"
    local interval="$2"
    local config_path="$3"

    if command -v jq &>/dev/null; then
        local tmp_file
        tmp_file="$(mktemp)"
        jq --arg agent "$agent_id" --arg every "$interval" '
            (.agents.list // []) as $list |
            if any($list[]; .id == $agent) then
                .agents.list = [.agents.list[] | if .id == $agent then .heartbeat = {"every": $every, "lightContext": true, "isolatedSession": true} else . end]
            else
                .agents.list = ($list + [{"id": $agent, "heartbeat": {"every": $every, "lightContext": true, "isolatedSession": true}}])
            end
        ' "$config_path" > "$tmp_file" && mv "$tmp_file" "$config_path"
        echo "  ✓ heartbeat config written to $config_path"
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
    agent_list.append({'id': agent_id, 'heartbeat': {'every': interval, 'lightContext': True, 'isolatedSession': True}})
with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)
print('  ✓ heartbeat config written')
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

build_sandbox_image() {
    # Build the OpenClaw sandbox Docker image if Docker is available and image missing
    if ! command -v docker &>/dev/null; then
        echo "  Docker not available — skipping sandbox image build."
        return 0
    fi

    if docker image inspect openclaw-sandbox:bookworm-slim &>/dev/null; then
        echo "  Sandbox image openclaw-sandbox:bookworm-slim already exists."
        return 0
    fi

    echo "Building OpenClaw sandbox Docker image..."
    local tmpdir
    tmpdir="$(mktemp -d openclaw-sandbox.XXXXXX)"

    cat > "${tmpdir}/Dockerfile" << 'DOCKERFILE'
FROM debian:bookworm-slim@sha256:f9c6a2fd2ddbc23e336b6257a5245e31f996953ef06cd13a59fa0a1df2d5c252

ENV DEBIAN_FRONTEND=noninteractive

RUN --mount=type=cache,id=openclaw-sandbox-bookworm-apt-cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,id=openclaw-sandbox-bookworm-apt-lists,target=/var/lib/apt,sharing=locked \
  apt-get update \
  && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    git \
    jq \
    python3 \
    ripgrep

RUN useradd --create-home --shell /bin/bash sandbox
USER sandbox
WORKDIR /home/sandbox

CMD ["sleep", "infinity"]
DOCKERFILE

    if docker build -t openclaw-sandbox:bookworm-slim "${tmpdir}" 2>&1; then
        echo "  Sandbox image built successfully."
    else
        echo "  Warning: Failed to build sandbox image. Agent sandboxing may not work." >&2
        echo "  You can build it manually with: docker build -t openclaw-sandbox:bookworm-slim <dir>" >&2
    fi
    rm -rf "${tmpdir}"
}

check_openclaw() {
    if [[ -d "${HOME}/.openclaw" ]] && command -v openclaw &>/dev/null; then
        return 0
    fi
    return 1
}

check_docker() {
    if command -v docker &>/dev/null; then
        # Verify Docker daemon is running
        if docker info &>/dev/null; then
            return 0
        else
            echo "Warning: Docker is installed but the daemon is not running." >&2
            echo "  Start Docker Desktop or the Docker service to enable sandboxing." >&2
            return 1
        fi
    fi
    return 1
}

install_dependencies_debian() {
    local pkgs=(build-essential g++ python3-dev python3-venv python3.12 python3.12-venv python3.12-dev unzip curl git file python3-pip jq)

    # Install Docker if not present (required for OpenClaw agent sandboxing)
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

    # Install Docker Desktop if not present (required for OpenClaw agent sandboxing)
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
                _CLEANUP_TEMP_DIR="$temp_dir"

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
    echo "Kalshi API secret (paste the full PEM key including BEGIN/END markers):"
    # Capture PEM key with stty -echo so terminal doesn't leak lines.
    # Discard any content before -----BEGIN and after -----END.
    local pem_started=false
    kalshi_secret=""
    local old_tty_settings
    old_tty_settings=$(stty -g 2>/dev/null) || true
    stty -echo 2>/dev/null || true
    while IFS= read -r line; do
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
    stty "$old_tty_settings" 2>/dev/null || true
    echo
    kalshi_secret="${kalshi_secret%$'\n'}"
    if [[ -n "$kalshi_secret" ]] && [[ "$kalshi_secret" != *"BEGIN"* ]]; then
        echo "  Warning: PEM key should contain BEGIN/END markers. The key may be invalid." >&2
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
    echo "Select Kalshi API tier:"
    echo "  1) Basic     (20 req/sec)  — free, 200 read tokens/sec"
    echo "  2) Advanced  (30 req/sec)  — 300 read + 300 write tokens/sec"
    echo "  3) Premier   (100 req/sec) — 1000 read + 1000 write tokens/sec"
    echo "  4) Paragon   (200 req/sec) — 2000 read + 2000 write tokens/sec"
    echo "  5) Prime     (400 req/sec) — 4000 read + 4000 write tokens/sec"
    kalshi_tier=$(_read_tier "Tier [1]: " 1 5 1)
    case "$kalshi_tier" in
        2) _env_set "$env_file" "KALSHI_RATE_LIMIT_RPS" "30" ;;
        3) _env_set "$env_file" "KALSHI_RATE_LIMIT_RPS" "100" ;;
        4) _env_set "$env_file" "KALSHI_RATE_LIMIT_RPS" "200" ;;
        5) _env_set "$env_file" "KALSHI_RATE_LIMIT_RPS" "400" ;;
        *) _env_set "$env_file" "KALSHI_RATE_LIMIT_RPS" "20" ;;
    esac

    # --- NewsAPI (optional) ---
    echo
    echo "--- NewsAPI (optional) ---"
    local newsapi_key=""
    read -r -p "NewsAPI key (press Enter to skip): " newsapi_key
    if [[ -n "$newsapi_key" ]]; then
        _validate_key "$newsapi_key" "NewsAPI key" 20 || newsapi_key=""
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
    fi
    if [[ -z "$newsapi_key" ]]; then
        echo "Skipped. Set later with: traderbot auth set-key newsapi api_key"
    fi

    # --- Voyage (optional) ---
    echo
    echo "--- Voyage (optional) ---"
    local voyage_key=""
    read -r -p "Voyage API key (press Enter to skip): " voyage_key
    if [[ -n "$voyage_key" ]]; then
        _validate_prefix "$voyage_key" "pa-" "Voyage API key" || voyage_key=""
        if [[ -n "$voyage_key" ]]; then
            _validate_key "$voyage_key" "Voyage API key" 20 || voyage_key=""
        fi
        if [[ -n "$voyage_key" ]]; then
            _env_set "$env_file" "VOYAGE_API_KEY" "$voyage_key"
            echo "Voyage key stored."
        fi
    fi
    if [[ -z "$voyage_key" ]]; then
        echo "Skipped. Set later with: traderbot auth set-key voyage api_key"
    fi

    # --- Twitter/X (optional) ---
    echo
    echo "--- Twitter/X (optional) ---"
    local twitter_key=""
    read -r -p "Twitter API key (press Enter to skip): " twitter_key
    if [[ -n "$twitter_key" ]]; then
        _validate_key "$twitter_key" "Twitter API key" 20 || twitter_key=""
        if [[ -n "$twitter_key" ]]; then
            _env_set "$env_file" "TWITTER_API_KEY" "$twitter_key"
            echo "Twitter key stored."
        fi
    fi
    if [[ -z "$twitter_key" ]]; then
        echo "Skipped. Set later with: traderbot auth set-key twitter api_key"
    fi

    # --- Reddit (optional) ---
    echo
    echo "--- Reddit (optional) ---"
    local reddit_id=""
    local reddit_secret=""
    read -r -p "Reddit client ID (press Enter to skip): " reddit_id
    if [[ -n "$reddit_id" ]]; then
        _validate_key "$reddit_id" "Reddit client ID" 10 || reddit_id=""
        if [[ -n "$reddit_id" ]]; then
            read -r -p "Reddit client secret: " -s reddit_secret
            echo
            _env_set "$env_file" "REDDIT_CLIENT_ID" "$reddit_id"
            if [[ -n "$reddit_secret" ]]; then
                _env_set "$env_file" "REDDIT_CLIENT_SECRET" "$reddit_secret"
            fi
            echo "Reddit credentials stored."
        fi
    fi
    if [[ -z "$reddit_id" ]]; then
        echo "Skipped. Set later with: traderbot auth set-key reddit client_id"
    fi

    # --- OpenWeatherMap (optional) ---
    echo
    echo "--- OpenWeatherMap (optional) ---"
    echo "Free tier: 1,000 calls/day. Register at https://openweathermap.org/api"
    local owm_key=""
    read -r -p "OpenWeatherMap API key (press Enter to skip): " owm_key
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
    read -r -p "CoinGecko API key (press Enter to skip): " cg_key
    if [[ -n "$cg_key" ]]; then
        _env_set "$env_file" "COINGECKO_API_KEY" "$cg_key"
        echo "CoinGecko key stored."
    else
        echo "Skipped. Set later with: traderbot auth set-key coingecko api_key"
    fi

    # --- FRED (optional) ---
    echo
    echo "--- FRED (optional) ---"
    echo "Free tier: 120 req/min. Register at https://fred.stlouisfed.org/docs/api/api_key.html"
    local fred_key=""
    read -r -p "FRED API key (press Enter to skip): " fred_key
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
    local merge_mode="--yes"
    echo
    echo "Workspace file mode:"
    echo "  1) Merge — backup existing files, then merge TraderBot templates (recommended)"
    echo "  2) Overwrite — replace workspace files with TraderBot templates"
    read -r -p "Select [1]: " ws_choice
    case "$ws_choice" in
        2) merge_mode="--yes --overwrite" ;;
        *) merge_mode="--yes" ;;
    esac
    if [[ -x "$tb_cmd" ]]; then
        echo "Assigning agent $agent_name to profile $profile_name..."
        set +e
        TOKEN_OUTPUT=$("$tb_cmd" profile assign "$profile_name" "$agent_name" $merge_mode 2>&1)
        local assign_exit=$?
        set -e
        if [[ $assign_exit -ne 0 ]]; then
            echo "Error: assign failed (exit code $assign_exit) with output:" >&2
            echo "$TOKEN_OUTPUT" >&2
            echo "Try manually: $tb_cmd profile assign $profile_name $agent_name" >&2
            TOKEN_OUTPUT=""
        fi
        if [[ -n "$TOKEN_OUTPUT" ]]; then
            echo "$TOKEN_OUTPUT"
            echo
            token_value=$(echo "$TOKEN_OUTPUT" | sed -n 's/^RAW_TOKEN://p' || echo "")
        fi
    else
        echo "Assignment skipped. TraderBot not found."
    fi

    if [[ -n "$token_value" ]]; then
        echo "Installing service for agent $agent_name..."
        install_service_for_agent "$agent_name" "$token_value" "$OS_TYPE"
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

            if openclaw cron add \
                --name decision_loop \
                --cron "*/5 * * * *" \
                --session isolated \
                --message "$DECISION_MSG" \
                --agent "$agent_name" \
                --announce 2>&1; then
                echo "  ✓ decision_loop registered"
            else
                echo "  ✗ decision_loop failed" >&2
                cron_ok=false
            fi

            if openclaw cron add \
                --name heartbeat_loop \
                --every "30m" \
                --session isolated \
                --message "$HEARTBEAT_MSG" \
                --agent "$agent_name" \
                --announce 2>&1; then
                echo "  ✓ heartbeat_loop registered"
            else
                echo "  ✗ heartbeat_loop failed" >&2
                cron_ok=false
            fi

            if openclaw cron add \
                --name news_loop \
                --event impact \
                --session main \
                --message "$NEWS_MSG" \
                --agent "$agent_name" \
                --announce 2>&1; then
                echo "  ✓ news_loop registered"
            else
                echo "  ✗ news_loop failed" >&2
                cron_ok=false
            fi

            local oc_config="${HOME}/.openclaw/openclaw.json"
            if [[ -f "$oc_config" ]]; then
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

merge_openclaw_agent_config() {
    local config_path="${HOME}/.openclaw/openclaw.json"
    local agent_config="${INSTALL_DIR}/install/openclaw-agent-config.json"

    if [[ ! -f "$agent_config" ]]; then
        echo "Warning: Agent config snippet not found at $agent_config" >&2
        return 1
    fi

    mkdir -p "${HOME}/.openclaw"

    if [[ ! -f "$config_path" ]]; then
        cp "$agent_config" "$config_path"
        echo "Created $config_path from agent config template."
    else
        # Use python3 for correct deep merge (deduplicates agents.list by ID)
        if command -v python3 &>/dev/null; then
            python3 -c "
import json, sys
config_path, agent_config_path = sys.argv[1], sys.argv[2]
with open(config_path) as f: existing = json.load(f)
with open(agent_config_path) as f: new = json.load(f)

for key, value in new.items():
    if key == 'agents' and key in existing:
        existing_ids = {a.get('id') for a in existing.get('agents', {}).get('list', [])}
        agent_list = existing.setdefault('agents', {}).setdefault('list', [])
        for entry in value.get('list', []):
            if entry.get('id') not in existing_ids:
                agent_list.append(entry)
        # Merge secrets if present
        if 'secrets' in value:
            existing_secret_ids = {s.get('id') for s in existing.get('secrets', [])}
            secrets = existing.setdefault('secrets', [])
            for s in value.get('secrets', []):
                if s.get('id') not in existing_secret_ids:
                    secrets.append(s)
    else:
        existing[key] = value

# Preserve any sub-keys of agents that weren't in the template (e.g., hooks, sandbox)
if 'agents' in existing and isinstance(existing['agents'], dict) and 'list' in existing['agents']:
    for entry in existing['agents']['list']:
        # __PROFILE_NAME__ placeholder was already expanded by profile assign
        pass

with open(config_path, 'w') as f:
    json.dump(existing, f, indent=2)
" "$config_path" "$agent_config"
            echo "Merged agent config into $config_path (using python3)."
        elif command -v jq &>/dev/null; then
            # jq fallback — note: array merge is by index, not by element ID.
            # Prefer python3 for correct dedup behavior.
            local tmp_file
            tmp_file="$(mktemp)"
            jq -s '
                .[0] as $existing |
                .[1] as $new |
                $existing * $new |
                if $new.agents and ($existing.agents.list | length > 0) then
                    .agents.list = (
                        ($existing.agents.list | map({key: .id, value: .}) | from_entries) *
                        ($new.agents.list | map({key: .id, value: .}) | from_entries)
                    ) | [.[] | {key: ., value: .}] | map(.value)
                else . end
            ' "$config_path" "$agent_config" > "$tmp_file" && mv "$tmp_file" "$config_path"
            echo "Merged agent config into $config_path (using jq)."
        else
            echo "Warning: Neither jq nor python3 available. Cannot merge agent config automatically." >&2
            echo "Manually merge $agent_config into $config_path" >&2
            return 1
        fi
    fi

    # Expand placeholders in config
    if [[ -f "$config_path" ]]; then
        _sed_inplace "s|__HOME_PLACEHOLDER__|$HOME|g" "$config_path"
        _sed_inplace "s|__PROJECT_ROOT_PLACEHOLDER__|$INSTALL_DIR|g" "$config_path"
        _sed_inplace "s|__PROFILE_NAME__|${profile_name:-economics}|g" "$config_path"
    fi

    # Workspace files deployed by traderbot profile assign — not duplicated here.
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

    if ! check_docker; then
        echo "" >&2
        echo "  Note: Docker is not running. OpenClaw agent sandboxing will be disabled." >&2
        echo "  Install and start Docker to enable agent sandboxing." >&2
        echo "" >&2
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

    echo "Building OpenClaw sandbox image..."
    build_sandbox_image

    echo "Installing TraderBot..."
    install_traderbot

    echo "Running interactive configuration..."
    interactive_config_flow

    echo "Merging OpenClaw agent config..."
    merge_openclaw_agent_config || true

    echo
    echo "Installation complete!"
}

main "$@"
