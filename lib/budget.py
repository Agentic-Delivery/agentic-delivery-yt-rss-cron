"""Daily spend tracking and circuit breaker."""

import json
import os
import tempfile
from datetime import datetime, timezone

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")
BUDGET_FILE = os.path.join(STATE_DIR, "budget.json")


def _ensure_state_dir():
    os.makedirs(STATE_DIR, exist_ok=True)


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_budget():
    """Load budget.json, returning empty structure if missing."""
    _ensure_state_dir()
    if not os.path.exists(BUDGET_FILE):
        return {"date": _today(), "spent_usd": 0.0, "invocations": 0}
    with open(BUDGET_FILE, "r") as f:
        data = json.load(f)
    # Reset if it's a new day
    if data.get("date") != _today():
        return {"date": _today(), "spent_usd": 0.0, "invocations": 0}
    return data


def save_budget(budget):
    """Atomic write budget state."""
    _ensure_state_dir()
    fd, tmp_path = tempfile.mkstemp(dir=STATE_DIR, suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(budget, f, indent=2)
        os.replace(tmp_path, BUDGET_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def can_spend(daily_limit_usd, per_video_usd):
    """Check if budget allows another invocation."""
    budget = load_budget()
    remaining = daily_limit_usd - budget["spent_usd"]
    return remaining >= per_video_usd


def record_spend(amount_usd):
    """Record a spend event."""
    budget = load_budget()
    budget["spent_usd"] = round(budget["spent_usd"] + amount_usd, 4)
    budget["invocations"] += 1
    save_budget(budget)


def get_remaining(daily_limit_usd):
    """Get remaining budget for today."""
    budget = load_budget()
    return round(daily_limit_usd - budget["spent_usd"], 4)


def get_summary():
    """Get budget summary for logging."""
    budget = load_budget()
    return f"Date: {budget['date']}, Spent: ${budget['spent_usd']:.2f}, Invocations: {budget['invocations']}"
