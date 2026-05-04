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
    local pkgs=(build-essential g++ python3-dev python3-venv python3.12 python3.12-venv python3.12-dev gnome-keyring unzip curl git file python3-pip)
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
    local py_bin
    py_bin="$(find_compatible_python 2>/dev/null)" || true
    if [[ -z "$py_bin" ]]; then
        echo "Error: Python 3.12 is required (chromadb dependency has no wheels for 3.13+)." >&2
        echo "Install Python 3.12 from python.org or: brew install python@3.12" >&2
        exit 1
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

    local REPLY=""

    # --- Kalshi (required) ---
    echo "--- Kalshi (required) ---"
    local kalshi_key=""
    local kalshi_secret=""
    read -r -p "Kalshi API key: " kalshi_key
    if [[ -z "$kalshi_key" ]]; then
        echo "Warning: Kalshi API key is required. Set it later with: traderbot auth set-key kalshi api_key" >&2
    else
        read -r -p "Kalshi API secret: " -s kalshi_secret
        echo
        _env_set "$env_file" "KALSHI_API_KEY" "$kalshi_key"
        if [[ -n "$kalshi_secret" ]]; then
            _env_set "$env_file" "KALSHI_API_SECRET" "$kalshi_secret"
        fi
        echo "Kalshi credentials stored."
    fi

    # --- NewsAPI (optional) ---
    echo
    echo "--- NewsAPI (optional) ---"
    local newsapi_key=""
    read -r -p "NewsAPI key (press Enter to skip): " newsapi_key
    if [[ -n "$newsapi_key" ]]; then
        _env_set "$env_file" "NEWSAPI_KEY" "$newsapi_key"
        echo "NewsAPI key stored."
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

    local profile_name=""
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

    echo "Select market categories (enter numbers, space-separated):"
    echo "  1) Politics"
    echo "  2) Economics"
    echo "  3) Sports"
    echo "  4) Crypto"
    echo "  5) Science/Tech"
    echo "  6) Weather"
    echo "  7) Culture"
    echo "  8) All categories"
    read -r -p "Choice [8]: " cat_choice
    case "$cat_choice" in
        1) profile_categories="politics" ;;
        2) profile_categories="economics" ;;
        3) profile_categories="sports" ;;
        4) profile_categories="crypto" ;;
        5) profile_categories="science" ;;
        6) profile_categories="weather" ;;
        7) profile_categories="culture" ;;
        *) profile_categories="politics,economics,sports,crypto,science,weather,culture" ;;
    esac

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
        echo "  traderbot profile assign $agent_name $profile_name"
        return 0
    fi

    local tb_cmd="${INSTALL_DIR}/.venv/bin/traderbot"
    local token_value=""
    if [[ -x "$tb_cmd" ]]; then
        echo "Assigning agent $agent_name to profile $profile_name..."
        set +e
        TOKEN_OUTPUT=$("$tb_cmd" profile assign "$profile_name" "$agent_name" 2>&1)
        local assign_exit=$?
        set -e
        if [[ $assign_exit -ne 0 ]]; then
            echo "Error: assign failed (exit code $assign_exit) with output:" >&2
            echo "$TOKEN_OUTPUT" >&2
            echo "Try manually: $tb_cmd profile assign $agent_name $profile_name" >&2
            TOKEN_OUTPUT=""
        fi
        if [[ -n "$TOKEN_OUTPUT" ]]; then
            echo "$TOKEN_OUTPUT"
            echo
            token_value=$(echo "$TOKEN_OUTPUT" | grep -oP 'Token: \K\S+' || echo "")
        fi
    else
        echo "Assignment skipped. TraderBot not found."
    fi

    if [[ -n "$token_value" ]]; then
        echo "Installing service for agent $agent_name..."
        install_service_for_agent "$agent_name" "$token_value" "$OS_TYPE"
    fi

    echo
    echo "=== Verification ==="
    if [[ -n "${TRADERBOT_PROFILE_TOKEN:-}" ]] && command -v traderbot &>/dev/null; then
        if traderbot heartbeat --json 2>/dev/null; then
            echo "Heartbeat verification: PASSED"
        else
            echo "Heartbeat verification: FAILED (check credentials)"
        fi
    else
        echo "No profile token set. Verification skipped."
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
        echo "Error: OpenClaw not found." >&2
        echo "Please install OpenClaw first: https://github.com/openclaw/openclaw" >&2
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

    echo
    echo "Installation complete!"
}

main "$@"
