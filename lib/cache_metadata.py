#!/usr/bin/env python3
"""Cache yt-dlp metadata for benchmark reference videos.

Fetches metadata once and saves to tests/fixtures/benchmark_metadata.json
so that benchmark and calibration scripts can run offline and deterministically.

Usage:
    python3 lib/cache_metadata.py
"""

import json
import os
import sys

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from lib.filter_stage2 import fetch_metadata

CACHE_PATH = os.path.join(REPO_ROOT, "tests", "fixtures", "benchmark_metadata.json")

# Same reference videos as benchmark_scoring.py
REFERENCE_VIDEO_IDS = [
    "bDcgHzCBgmQ",
    "41UDGsBEjoI",
    "uvs1Igr4u6g",
    "efctPj6bjCY",
    "Y3PIZtR9gik",
    "60G93MXT4DI",
    "xaNZIoQETWw",
    "FDYhPXYDS_o",
    "_ykT_l4e8F8",
    "-P79jTyYtWA",
]

# Fields to cache (skip huge fields like formats, thumbnails, etc.)
KEEP_FIELDS = [
    "id", "title", "description", "duration", "view_count", "like_count",
    "tags", "chapters", "channel_id", "uploader", "upload_date",
]


def load_channels():
    """Load channel categories from channels.yaml."""
    with open(os.path.join(REPO_ROOT, "channels.yaml")) as f:
        data = yaml.safe_load(f)
    categories = {}
    for ch in data["channels"]:
        categories[ch["channel_id"]] = ch["category"]
        categories[ch["name"].lower()] = ch["category"]
    return categories


def main():
    # Load existing cache if present
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH) as f:
            cache = json.load(f)
    else:
        cache = {}

    channel_categories = load_channels()

    fetched = 0
    skipped = 0
    for vid in REFERENCE_VIDEO_IDS:
        if vid in cache:
            print(f"  CACHED: {vid} ({cache[vid].get('title', '')[:50]})")
            skipped += 1
            continue

        print(f"  Fetching: {vid}...", end=" ", flush=True)
        metadata = fetch_metadata(vid)
        if metadata is None:
            print("FAILED")
            continue

        # Keep only relevant fields
        slim = {k: metadata.get(k) for k in KEEP_FIELDS}

        # Add channel_category lookup
        channel_id = metadata.get("channel_id") or ""
        uploader = (metadata.get("uploader") or "").lower()
        slim["channel_category"] = channel_categories.get(
            channel_id, channel_categories.get(uploader, "secondary")
        )

        cache[vid] = slim
        fetched += 1
        print(f"OK — {slim['title'][:50]}")

    # Write cache
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)

    print(f"\nCached {fetched} new, {skipped} already cached → {CACHE_PATH}")


if __name__ == "__main__":
    main()
