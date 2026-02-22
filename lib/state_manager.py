"""JSON state file operations with atomic writes."""

import json
import os
import tempfile

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")
STATE_FILE = os.path.join(STATE_DIR, "processed.json")


def _ensure_state_dir():
    os.makedirs(STATE_DIR, exist_ok=True)


def load_state():
    """Load processed.json, returning empty dict if missing."""
    _ensure_state_dir()
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r") as f:
        return json.load(f)


def save_state(state):
    """Atomic write: write to temp file, then rename."""
    _ensure_state_dir()
    fd, tmp_path = tempfile.mkstemp(dir=STATE_DIR, suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2, sort_keys=True)
        os.replace(tmp_path, STATE_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def is_processed(video_id):
    """Check if a video has already been processed."""
    state = load_state()
    return video_id in state


def mark_processed(video_id, data):
    """Mark a video as processed with metadata."""
    state = load_state()
    state[video_id] = data
    save_state(state)


def get_entry(video_id):
    """Get state entry for a video, or None."""
    state = load_state()
    return state.get(video_id)
