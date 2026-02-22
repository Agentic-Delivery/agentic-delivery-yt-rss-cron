#!/usr/bin/env python3
"""Stage 1: Fetch RSS feeds and apply keyword filtering.

Reads channels.yaml and keywords.yaml, fetches RSS for each channel,
filters for new videos matching keyword criteria, outputs JSON candidates.

Usage:
    python3 lib/fetch_rss.py [--config config.yaml] [--dry-run]
"""

import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# YouTube Atom feed namespace
NS = {"atom": "http://www.w3.org/2005/Atom", "media": "http://search.yahoo.com/mrss/"}


def load_yaml(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def fetch_feed(channel_id, timeout=15):
    """Fetch RSS feed XML for a channel. Returns parsed entries or empty list."""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "yt-rss-cron/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)
        return root.findall("atom:entry", NS)
    except Exception as e:
        print(f"  WARN: Failed to fetch feed for {channel_id}: {e}", file=sys.stderr)
        return []


def parse_entry(entry, channel_name, channel_category):
    """Parse an RSS entry into a candidate dict."""
    video_id_el = entry.find("atom:id", NS)
    title_el = entry.find("atom:title", NS)
    published_el = entry.find("atom:published", NS)
    # media:group > media:description
    media_group = entry.find("media:group", NS)
    description = ""
    if media_group is not None:
        desc_el = media_group.find("media:description", NS)
        if desc_el is not None and desc_el.text:
            description = desc_el.text

    video_id = ""
    if video_id_el is not None and video_id_el.text:
        # Format: yt:video:VIDEO_ID
        video_id = video_id_el.text.replace("yt:video:", "")

    title = title_el.text if title_el is not None and title_el.text else ""
    published = published_el.text if published_el is not None and published_el.text else ""

    return {
        "video_id": video_id,
        "title": title,
        "published": published,
        "description": description[:500],
        "channel_name": channel_name,
        "channel_category": channel_category,
        "url": f"https://www.youtube.com/watch?v={video_id}",
    }


def score_stage1(candidate, keyword_groups):
    """Apply weighted keyword matching to title + description. Returns score."""
    text = (candidate["title"] + " " + candidate["description"]).lower()
    score = 0
    matched_groups = []

    for group_name, group in keyword_groups.items():
        weight = group["weight"]
        for keyword in group["keywords"]:
            if keyword.lower() in text:
                score += weight
                matched_groups.append(f"{group_name}({keyword})")
                break  # One match per group is enough

    candidate["stage1_score"] = score
    candidate["stage1_matches"] = matched_groups
    return score


def days_old(published_str):
    """Return how many days old a published date is."""
    try:
        dt = datetime.fromisoformat(published_str)
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (now - dt).days
    except (ValueError, TypeError):
        return 9999


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Stage 1: RSS fetch + keyword filter")
    parser.add_argument("--config", default=os.path.join(REPO_ROOT, "config.yaml"))
    parser.add_argument("--channels", default=os.path.join(REPO_ROOT, "channels.yaml"))
    parser.add_argument("--keywords", default=os.path.join(REPO_ROOT, "keywords.yaml"))
    parser.add_argument("--state-file", default=os.path.join(REPO_ROOT, "state", "processed.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = load_yaml(args.config)
    channels_data = load_yaml(args.channels)
    keywords_data = load_yaml(args.keywords)

    min_score = config["thresholds"]["stage1_min_score"]
    max_age = config["thresholds"]["max_age_days"]
    max_videos = config["polling"]["max_videos_per_poll"]
    timeout = config["polling"]["feed_timeout_seconds"]

    # Load processed state
    processed = {}
    if os.path.exists(args.state_file):
        with open(args.state_file, "r") as f:
            processed = json.load(f)

    candidates = []

    for ch in channels_data["channels"]:
        name = ch["name"]
        channel_id = ch["channel_id"]
        category = ch["category"]

        print(f"Fetching: {name} ({channel_id})...", file=sys.stderr)
        entries = fetch_feed(channel_id, timeout=timeout)
        print(f"  Found {len(entries)} entries", file=sys.stderr)

        for entry in entries:
            candidate = parse_entry(entry, name, category)

            # Skip already processed
            if candidate["video_id"] in processed:
                continue

            # Skip old videos
            age = days_old(candidate["published"])
            if age > max_age:
                continue

            # Score Stage 1
            score = score_stage1(candidate, keywords_data["keyword_groups"])

            if score >= min_score:
                candidates.append(candidate)
                print(f"  PASS: [{score}] {candidate['title']}", file=sys.stderr)
            elif args.dry_run:
                print(f"  SKIP: [{score}] {candidate['title']}", file=sys.stderr)

    # Sort by score descending, limit
    candidates.sort(key=lambda c: c["stage1_score"], reverse=True)
    candidates = candidates[:max_videos]

    print(f"\nStage 1 result: {len(candidates)} candidates passed", file=sys.stderr)

    # Output JSON to stdout
    json.dump(candidates, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
