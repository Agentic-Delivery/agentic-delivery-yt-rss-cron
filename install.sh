#!/usr/bin/env bash
# install.sh — Setup script for yt-rss-cron.
#
# Usage:
#   bash install.sh --check     # Check dependencies only
#   bash install.sh --cron      # Install as cron job (every 30 min)
#   bash install.sh --systemd   # Install as systemd timer
#   bash install.sh --remove    # Remove cron/systemd installation

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
CRON_ID="yt-rss-cron"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}OK${NC}    $1"; }
warn() { echo -e "  ${YELLOW}WARN${NC}  $1"; }
fail() { echo -e "  ${RED}FAIL${NC}  $1"; }

check_deps() {
    echo "Checking dependencies..."
    ALL_OK=true

    # Python 3
    if command -v python3 &>/dev/null; then
        PY_VER=$(python3 --version 2>&1)
        ok "python3 ($PY_VER)"
    else
        fail "python3 not found"
        ALL_OK=false
    fi

    # PyYAML
    if python3 -c "import yaml" 2>/dev/null; then
        ok "PyYAML"
    else
        fail "PyYAML not installed (pip install pyyaml)"
        ALL_OK=false
    fi

    # yt-dlp
    if command -v yt-dlp &>/dev/null; then
        YT_VER=$(yt-dlp --version 2>&1)
        ok "yt-dlp ($YT_VER)"
    else
        fail "yt-dlp not found (pip install yt-dlp)"
        ALL_OK=false
    fi

    # claude CLI
    if command -v claude &>/dev/null; then
        ok "claude CLI"
    else
        fail "claude CLI not found"
        ALL_OK=false
    fi

    # MCP config
    if [[ -f "${REPO_ROOT}/mcp.json" ]]; then
        ok "mcp.json exists"
    else
        warn "mcp.json not found — copy from mcp.json.example and fill in secrets"
    fi

    # State/logs directories
    mkdir -p "${REPO_ROOT}/state" "${REPO_ROOT}/logs"
    ok "state/ and logs/ directories"

    if $ALL_OK; then
        echo -e "\n${GREEN}All dependencies satisfied.${NC}"
    else
        echo -e "\n${RED}Some dependencies are missing.${NC}"
        return 1
    fi
}

install_cron() {
    check_deps || { echo "Fix dependencies first."; exit 1; }

    INTERVAL=$(python3 -c "import yaml; c=yaml.safe_load(open('${REPO_ROOT}/config.yaml')); print(c['polling']['interval_minutes'])")
    CRON_LINE="*/${INTERVAL} * * * * cd ${REPO_ROOT} && bash poll.sh >> ${REPO_ROOT}/logs/cron.log 2>&1 # ${CRON_ID}"

    # Remove existing entry if present
    crontab -l 2>/dev/null | grep -v "# ${CRON_ID}" | crontab - 2>/dev/null || true

    # Add new entry
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
    echo -e "${GREEN}Cron job installed:${NC}"
    echo "  $CRON_LINE"
}

install_systemd() {
    check_deps || { echo "Fix dependencies first."; exit 1; }

    SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
    mkdir -p "$SYSTEMD_USER_DIR"

    # Copy service and timer files, replacing REPO_ROOT placeholder
    sed "s|REPO_ROOT_PLACEHOLDER|${REPO_ROOT}|g; s|USER_PLACEHOLDER|$(whoami)|g" \
        "${REPO_ROOT}/systemd/yt-rss-cron.service" > "${SYSTEMD_USER_DIR}/yt-rss-cron.service"
    cp "${REPO_ROOT}/systemd/yt-rss-cron.timer" "${SYSTEMD_USER_DIR}/yt-rss-cron.timer"

    systemctl --user daemon-reload
    systemctl --user enable yt-rss-cron.timer
    systemctl --user start yt-rss-cron.timer

    echo -e "${GREEN}Systemd timer installed and started.${NC}"
    echo "  Check status: systemctl --user status yt-rss-cron.timer"
    echo "  View logs:    journalctl --user -u yt-rss-cron.service"
}

remove() {
    # Remove cron
    crontab -l 2>/dev/null | grep -v "# ${CRON_ID}" | crontab - 2>/dev/null || true
    echo "Cron entry removed (if any)"

    # Remove systemd
    systemctl --user stop yt-rss-cron.timer 2>/dev/null || true
    systemctl --user disable yt-rss-cron.timer 2>/dev/null || true
    rm -f "${HOME}/.config/systemd/user/yt-rss-cron.service" \
          "${HOME}/.config/systemd/user/yt-rss-cron.timer"
    systemctl --user daemon-reload 2>/dev/null || true
    echo "Systemd timer removed (if any)"
}

case "${1:---check}" in
    --check)   check_deps ;;
    --cron)    install_cron ;;
    --systemd) install_systemd ;;
    --remove)  remove ;;
    *)
        echo "Usage: bash install.sh [--check|--cron|--systemd|--remove]"
        exit 1
        ;;
esac
