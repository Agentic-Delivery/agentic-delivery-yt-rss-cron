"""Utility functions: slugify, timestamps, URL builders."""

import re
from datetime import datetime, timezone


def slugify(text, max_length=50):
    """Convert text to URL-safe slug."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text).strip('-')
    return text[:max_length]


def rss_url(channel_id):
    """Build YouTube RSS feed URL from channel ID."""
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def video_url(video_id):
    """Build YouTube watch URL from video ID."""
    return f"https://www.youtube.com/watch?v={video_id}"


def now_iso():
    """Current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def today_str():
    """Today's date as YYYY-MM-DD."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def parse_rss_date(date_str):
    """Parse RSS published date (ISO 8601) to datetime."""
    # YouTube RSS uses format: 2025-01-15T12:00:00+00:00
    try:
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


def days_old(date_str):
    """Return how many days old a date string is."""
    dt = parse_rss_date(date_str)
    if dt is None:
        return 9999
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).days
