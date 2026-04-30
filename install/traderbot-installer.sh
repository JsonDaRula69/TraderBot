#!/bin/bash
# TraderBot Installer
# Installs TraderBot with OS detection, dependency management, persistence setup, and config flow

set -euo pipefail

TRADERBOT_REPO="${TRADERBOT_REPO:-TraderBot/TraderBot}"
TRADERBOT_ORG="${TRADERBOT_ORG:-TraderBot}"
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
    --update        Pull latest from GitHub and restart services
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

check_openclaw() {
    if [[ -d "${HOME}/.openclaw" ]] && command -v openclaw &>/dev/null; then
        return 0
    fi
    return 1
}

install_dependencies_debian() {
    local pkgs=(build-essential python3-dev python3-venv gnome-keyring)
    if command -v apt &>/dev/null; then
        echo "Installing dependencies with apt..."
        sudo apt update
        sudo apt install -y "${pkgs[@]}"
    fi
}

install_dependencies_macos() {
    if ! command -v xcode-select &>/dev/null || [[ ! -d "$(xcode-select -p)" ]]; then
        echo "Installing Xcode CLI tools..."
        xcode-select --install 2>/dev/null || true
        local timeout=30
        while [[ ! -d "$(xcode-select -p 2>/dev/null)" ]] && [[ $timeout -gt 0 ]]; do
            sleep 1
            ((timeout--))
        done
        if [[ ! -d "$(xcode-select -p 2>/dev/null)" ]]; then
            echo "Error: Xcode CLI tools installation timed out after 30 seconds." >&2
            exit 1
        fi
    fi
    if ! command -v python3 &>/dev/null; then
        echo "Python3 not found. Please install Python 3.12+ from python.org"
        exit 1
    fi
    if ! python3 -c 'import sys; assert sys.version_info >= (3,12)' 2>/dev/null; then
        echo "Error: Python 3.12+ required. Found: $(python3 --version)" >&2
        exit 1
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
                read -p "Update to latest? (y/n): " -n 1 -r
                echo
                if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                    echo "Skipping installation."
                    return 0
                fi
                cd "$INSTALL_DIR"
                if ! git pull origin main 2>/dev/null && ! git pull origin master 2>/dev/null; then
                    echo "Error: git pull failed for both 'main' and 'master' branches." >&2
                    exit 1
                fi
            else
                echo "TraderBot directory exists but not in PATH. Updating..."
                cd "$INSTALL_DIR"
                if ! git pull origin main 2>/dev/null && ! git pull origin master 2>/dev/null; then
                    echo "Error: git pull failed for both 'main' and 'master' branches." >&2
                    exit 1
                fi
            fi
        else
            echo "Downloading TraderBot..."
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
        fi
    fi

    cd "$INSTALL_DIR"
    if command -v uv &>/dev/null; then
        uv pip install -e . 2>/dev/null || uv pip install --user -e .
    else
        pip install -e . 2>/dev/null || pip install --user -e .
    fi

    if ! command -v traderbot &>/dev/null || ! traderbot --version &>/dev/null; then
        echo "Error: traderbot installation verification failed." >&2
        echo "The package installed but 'traderbot --version' returned an error." >&2
        exit 1
    fi
    echo "TraderBot installed successfully: $(traderbot --version 2>/dev/null)"
}

stop_services() {
    local os_type="$1"
    if [[ "$os_type" == "macos" ]]; then
        launchctl list 2>/dev/null | grep 'com.traderbot.agent' | awk '{print $3}' | while read -r label; do
            launchctl stop "$label" 2>/dev/null || true
        done
    else
        systemctl --user list-units --type=service --state=running 2>/dev/null | grep 'traderbot-agent@' | awk '{print $1}' | while read -r unit; do
            systemctl --user stop "$unit" 2>/dev/null || true
        done
    fi
}

uninstall_services() {
    local os_type="$1"
    if [[ "$os_type" == "macos" ]]; then
        local plist_dir="${HOME}/Library/LaunchAgents"
        if [[ -d "$plist_dir" ]]; then
            find "$plist_dir" -maxdepth 1 -name 'com.traderbot.agent.*.plist' 2>/dev/null | while read -r plist; do
                local label
                label="$(basename "$plist" .plist)"
                launchctl unload "$plist" 2>/dev/null || true
                rm -f "$plist"
                echo "Removed: $plist"
            done
        fi
    else
        local service_dir="${HOME}/.config/systemd/user"
        if [[ -d "$service_dir" ]]; then
            find "$service_dir" -maxdepth 1 -name 'traderbot-agent@*.service' 2>/dev/null | while read -r service; do
                local unit
                unit="$(basename "$service")"
                systemctl --user stop "$unit" 2>/dev/null || true
                systemctl --user disable "$unit" 2>/dev/null || true
                rm -f "$service"
                echo "Removed: $service"
            done
            systemctl --user daemon-reload 2>/dev/null || true
        fi
    fi
    echo "Services uninstalled. Data preserved at $INSTALL_DIR"
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
        local plist_dir="${HOME}/Library/LaunchAgents"
        if [[ -d "$plist_dir" ]]; then
            find "$plist_dir" -maxdepth 1 -name 'com.traderbot.agent.*.plist' 2>/dev/null | while read -r plist; do
                launchctl load "$plist" 2>/dev/null || true
            done
        fi
    else
        systemctl --user list-units --type=service 2>/dev/null | grep 'traderbot-agent@' | awk '{print $1}' | while read -r unit; do
            systemctl --user start "$unit" 2>/dev/null || true
        done
    fi
}

install_service_for_agent() {
    local agent_name="$1"
    local profile_token="$2"
    local os_type="$3"
    local script_dir
    script_dir="$(cd "$(dirname "$0")" && pwd)"
    if [[ "$os_type" == "macos" ]]; then
        bash "${script_dir}/services/install-launchd.sh" "$agent_name" "$profile_token"
    else
        bash "${script_dir}/services/install-service.sh" "$agent_name" "$profile_token"
    fi
}

interactive_config_flow() {
    if [[ ! -t 0 ]]; then
        echo "Error: interactive config requires a TTY. Run this script in a terminal." >&2
        exit 1
    fi
    echo "=== TraderBot Configuration ==="
    echo
    read -p "Create a trading profile? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Skipping profile creation."
        return 0
    fi

    read -r -p "Profile name: " profile_name
    read -r -p "Mode (paper/live): " profile_mode
    read -r -p "Categories (comma-separated, e.g., politics,sports): " profile_categories

    if command -v traderbot &>/dev/null; then
        traderbot profile create "$profile_name" --mode "$profile_mode" \
            --categories "$profile_categories" 2>/dev/null || \
            echo "Profile created manually. Please run: traderbot profile create $profile_name"
    else
        echo "TraderBot not in PATH. Profile creation skipped."
    fi

    echo
    echo "=== API Key Setup ==="
    read -r -p "Kalshi API Key ID: " kalshi_key_id
    if [[ -n "$kalshi_key_id" ]] && command -v traderbot &>/dev/null; then
        traderbot profile set-auth "$profile_name" kalshi "$kalshi_key_id" 2>/dev/null || true
    fi

    echo
    echo "=== Agent Assignment ==="
    if command -v traderbot &>/dev/null; then
        echo "Available agents:"
        traderbot profile discover-agents 2>/dev/null || echo "  (no agents found, or TraderBot not in PATH)"
    fi

    read -r -p "Agent name to assign: " agent_name
    if [[ -n "$agent_name" ]] && command -v traderbot &>/dev/null; then
        echo "Assigning agent $agent_name to profile $profile_name..."
        traderbot profile assign "$agent_name" "$profile_name" 2>/dev/null || \
            echo "Assignment skipped. Token will need to be set manually."
    fi

    echo
    echo "=== Verification ==="
    if command -v traderbot &>/dev/null; then
        local token
        token="${TRADERBOT_PROFILE_TOKEN:-}"
        if [[ -n "$token" ]]; then
            if traderbot heartbeat --json 2>/dev/null; then
                echo "Heartbeat verification: PASSED"
            else
                echo "Heartbeat verification: FAILED (check credentials)"
            fi
        else
            echo "No profile token set. Verification skipped."
        fi
    else
        echo "TraderBot not in PATH. Verification skipped."
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

    echo "Checking for OpenClaw..."
    if ! check_openclaw; then
        echo "Error: OpenClaw not found." >&2
        echo "Please install OpenClaw first: https://github.com/openclaw/openclaw" >&2
        echo "Required: ~/.openclaw/ directory and openclaw binary in PATH" >&2
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
        *)
            echo "Error: Unsupported OS: $OS_TYPE" >&2
            exit 1
            ;;
    esac

    echo "Installing TraderBot..."
    install_traderbot

    echo "Running interactive configuration..."
    interactive_config_flow

    echo
    echo "Installation complete!"
    echo "To assign agents and start services, run:"
    echo "  $(basename "$0") --update"
}

main "$@"