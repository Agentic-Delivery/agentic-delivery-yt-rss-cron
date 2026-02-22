#!/usr/bin/env bash
# trigger.sh — Invoke claude -p with the vendored yt-intel skill for a single video.
#
# Usage: bash lib/trigger.sh <youtube-url> <video-id> <log-file>
#
# Reads skill/SKILL.md, constructs prompt, invokes claude -p with budget/model/MCP flags.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

URL="${1:?Usage: trigger.sh <youtube-url> <video-id> <log-file>}"
VIDEO_ID="${2:?Usage: trigger.sh <youtube-url> <video-id> <log-file>}"
LOG_FILE="${3:?Usage: trigger.sh <youtube-url> <video-id> <log-file>}"

# Load config
CONFIG_FILE="${REPO_ROOT}/config.yaml"
MODEL=$(python3 -c "import yaml; c=yaml.safe_load(open('${CONFIG_FILE}')); print(c['budget']['model'])")
PER_VIDEO_USD=$(python3 -c "import yaml; c=yaml.safe_load(open('${CONFIG_FILE}')); print(c['budget']['per_video_usd'])")
TIMEOUT=$(python3 -c "import yaml; c=yaml.safe_load(open('${CONFIG_FILE}')); print(c['trigger']['timeout_seconds'])")
MCP_CONFIG="${REPO_ROOT}/$(python3 -c "import yaml; c=yaml.safe_load(open('${CONFIG_FILE}')); print(c['trigger']['mcp_config'])")"
SKILL_FILE="${REPO_ROOT}/$(python3 -c "import yaml; c=yaml.safe_load(open('${CONFIG_FILE}')); print(c['trigger']['skill_file'])")"

# Read skill content
if [[ ! -f "$SKILL_FILE" ]]; then
    echo "ERROR: Skill file not found: $SKILL_FILE" | tee -a "$LOG_FILE"
    exit 1
fi
SKILL_CONTENT=$(cat "$SKILL_FILE")

# Ensure working directory exists
mkdir -p /tmp/yt-intel

# Record budget before invocation
python3 -c "
import sys
sys.path.insert(0, '${REPO_ROOT}/lib')
from budget import record_spend
record_spend(${PER_VIDEO_USD})
"

# Construct prompt
PROMPT="You are running the yt-intel pipeline in UNATTENDED mode. Process this video and complete all steps.

VIDEO URL: ${URL}

--- SKILL INSTRUCTIONS ---
${SKILL_CONTENT}
--- END SKILL INSTRUCTIONS ---

IMPORTANT: This is an automated run. For the relevance gate (Step 3):
- Score >= 6: PROCEED with Steps 4-6 (DOCX, Drive, Discord)
- Score 3-5: PROCEED with Steps 4-6 but add '[MARGINAL]' prefix to the Discord message title
- Score < 3: SKIP Steps 4-6. Output the summary and score, then stop.

Do NOT ask for user input. Complete all applicable steps autonomously."

# Invoke claude
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] TRIGGER: ${VIDEO_ID} — ${URL}" | tee -a "$LOG_FILE"

if timeout "${TIMEOUT}" claude -p "$PROMPT" \
    --model "$MODEL" \
    --max-budget-usd "$PER_VIDEO_USD" \
    --mcp-config "$MCP_CONFIG" \
    --dangerously-skip-permissions \
    >> "$LOG_FILE" 2>&1; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] SUCCESS: ${VIDEO_ID}" | tee -a "$LOG_FILE"
    exit 0
else
    EXIT_CODE=$?
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] FAILED: ${VIDEO_ID} (exit code: ${EXIT_CODE})" | tee -a "$LOG_FILE"
    exit "$EXIT_CODE"
fi
