#!/usr/bin/env bash
# poll.sh — Main entry point for yt-rss-cron.
#
# Usage:
#   bash poll.sh              # Single poll cycle
#   bash poll.sh --dry-run    # Poll + filter, but don't trigger claude
#   bash poll.sh --daemon     # Continuous polling at configured interval
#
# Pipeline: fetch_rss.py (Stage 1) -> filter_stage2.py (Stage 2) -> trigger.sh (Stage 3)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${REPO_ROOT}/config.yaml"
STATE_DIR="${REPO_ROOT}/state"
LOG_DIR="${REPO_ROOT}/logs"
PID_FILE="${STATE_DIR}/poll.pid"

DRY_RUN=false
DAEMON=false

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --daemon)  DAEMON=true ;;
        --help|-h)
            echo "Usage: bash poll.sh [--dry-run] [--daemon]"
            echo "  --dry-run   Poll and filter, but don't invoke claude"
            echo "  --daemon    Run continuously at configured interval"
            exit 0
            ;;
        *) echo "Unknown argument: $arg"; exit 1 ;;
    esac
done

# Ensure directories exist
mkdir -p "$STATE_DIR" "$LOG_DIR"

# PID lock (prevent concurrent runs)
if [[ -f "$PID_FILE" ]]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "ERROR: Another instance is running (PID: $OLD_PID)"
        exit 1
    else
        echo "WARN: Stale PID file found, removing"
        rm -f "$PID_FILE"
    fi
fi
echo $$ > "$PID_FILE"
trap 'rm -f "$PID_FILE"' EXIT

# Load config values
INTERVAL=$(python3 -c "import yaml; c=yaml.safe_load(open('${CONFIG}')); print(c['polling']['interval_minutes'])")
LOG_FILE="${LOG_DIR}/$(date -u +%Y-%m-%d).log"

log() {
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG_FILE"
}

run_cycle() {
    log "=== Poll cycle starting ==="
    log "Mode: $(${DRY_RUN} && echo 'DRY RUN' || echo 'LIVE')"

    # Stage 1: RSS fetch + keyword filter
    log "Stage 1: Fetching RSS feeds..."
    DRY_FLAG=""
    if $DRY_RUN; then DRY_FLAG="--dry-run"; fi

    STAGE1_OUTPUT=$(python3 "${REPO_ROOT}/lib/fetch_rss.py" \
        --config "$CONFIG" \
        --state-file "${STATE_DIR}/processed.json" \
        $DRY_FLAG 2>>"$LOG_FILE") || {
        log "ERROR: Stage 1 failed"
        return 1
    }

    CANDIDATE_COUNT=$(echo "$STAGE1_OUTPUT" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
    log "Stage 1 complete: ${CANDIDATE_COUNT} candidates"

    if [[ "$CANDIDATE_COUNT" == "0" ]]; then
        log "No new candidates — cycle done"
        return 0
    fi

    # Stage 2: yt-dlp metadata scoring
    log "Stage 2: Scoring with yt-dlp metadata..."
    STAGE2_OUTPUT=$(echo "$STAGE1_OUTPUT" | python3 "${REPO_ROOT}/lib/filter_stage2.py" \
        --config "$CONFIG" \
        $DRY_FLAG 2>>"$LOG_FILE") || {
        log "ERROR: Stage 2 failed"
        return 1
    }

    QUALIFY_COUNT=$(echo "$STAGE2_OUTPUT" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
    log "Stage 2 complete: ${QUALIFY_COUNT} videos qualify"

    if [[ "$QUALIFY_COUNT" == "0" ]]; then
        log "No qualifying videos — cycle done"
        return 0
    fi

    if $DRY_RUN; then
        log "DRY RUN — would trigger for these videos:"
        echo "$STAGE2_OUTPUT" | python3 -c "
import json, sys
for v in json.load(sys.stdin):
    print(f\"  [{v['stage2_score']}/10] {v['title'][:70]} ({v['url']})\")
" | tee -a "$LOG_FILE"
        return 0
    fi

    # Stage 3: Trigger claude -p for each qualifying video
    log "Stage 3: Triggering yt-intel pipeline..."
    echo "$STAGE2_OUTPUT" | python3 -c "
import json, sys
for v in json.load(sys.stdin):
    print(f\"{v['video_id']}\t{v['url']}\t{v['title']}\t{v['stage2_score']}\")
" | while IFS=$'\t' read -r VID_ID VID_URL VID_TITLE VID_SCORE; do
        log "TRIGGERING: [${VID_SCORE}/10] ${VID_TITLE}"
        if bash "${REPO_ROOT}/lib/trigger.sh" "$VID_URL" "$VID_ID" "$LOG_FILE" < /dev/null; then
            # Mark as processed
            python3 -c "
import sys, json
sys.path.insert(0, '${REPO_ROOT}/lib')
from state_manager import mark_processed
from utils import now_iso
mark_processed('${VID_ID}', {
    'title': $(python3 -c "import json; print(json.dumps('${VID_TITLE}'))"),
    'url': '${VID_URL}',
    'stage2_score': ${VID_SCORE},
    'status': 'completed',
    'triggered_at': now_iso()
})
"
            log "COMPLETED: ${VID_ID}"
        else
            # Mark as failed but processed (don't retry forever)
            python3 -c "
import sys
sys.path.insert(0, '${REPO_ROOT}/lib')
from state_manager import mark_processed
from utils import now_iso
mark_processed('${VID_ID}', {
    'title': $(python3 -c "import json; print(json.dumps('${VID_TITLE}'))"),
    'url': '${VID_URL}',
    'stage2_score': ${VID_SCORE},
    'status': 'failed',
    'triggered_at': now_iso()
})
"
            log "FAILED: ${VID_ID} — marked as processed to avoid retry loop"
        fi
    done

    log "=== Poll cycle complete ==="
}

# Main execution
if $DAEMON; then
    log "Starting daemon mode (interval: ${INTERVAL}m)"
    while true; do
        run_cycle || true
        log "Sleeping ${INTERVAL} minutes..."
        sleep $((INTERVAL * 60))
    done
else
    run_cycle
fi
