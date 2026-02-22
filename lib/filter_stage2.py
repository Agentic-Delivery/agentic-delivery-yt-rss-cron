#!/usr/bin/env python3
"""Stage 2: Deterministic scoring using yt-dlp metadata.

Reads Stage 1 candidates from stdin (JSON array), fetches yt-dlp metadata
for each, applies deterministic scoring heuristic, outputs qualifying videos.

No LLM calls. Costs only yt-dlp network requests (2-5s each).

Usage:
    cat candidates.json | python3 lib/filter_stage2.py [--config config.yaml]
"""

import json
import os
import subprocess
import sys

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_yaml(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_keywords(path):
    """Load all keywords from keywords.yaml into a flat dict of group->keywords."""
    data = load_yaml(path)
    return data["keyword_groups"]


def fetch_metadata(video_id):
    """Run yt-dlp --dump-json to get video metadata. Returns dict or None."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--skip-download", "--no-warnings", url],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"  WARN: yt-dlp failed for {video_id}: {result.stderr[:200]}", file=sys.stderr)
            return None
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        print(f"  WARN: yt-dlp timeout for {video_id}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  WARN: yt-dlp error for {video_id}: {e}", file=sys.stderr)
        return None


def score_metadata(candidate, metadata, keyword_groups):
    """Deterministic scoring on yt-dlp metadata. Returns 0-10 score."""
    score = 0.0
    reasons = []

    # --- Duration sweet spot (2min - 3hr) ---
    duration = metadata.get("duration", 0)
    if 120 <= duration <= 10800:
        score += 1.0
        reasons.append("duration_ok")
    elif duration < 60:
        score -= 1.0
        reasons.append("too_short")
    elif duration > 10800:
        score -= 0.5
        reasons.append("very_long")

    # --- Tag matching ---
    tags = [t.lower() for t in (metadata.get("tags") or [])]
    description = (metadata.get("description") or "").lower()
    title = (metadata.get("title") or "").lower()
    full_text = f"{title} {description} {' '.join(tags)}"

    tag_hits = 0
    for group_name, group in keyword_groups.items():
        weight = group["weight"]
        if weight < 0:
            # Check negative keywords
            for kw in group["keywords"]:
                if kw.lower() in full_text:
                    score -= 2.0
                    reasons.append(f"neg:{kw}")
                    break
        else:
            for kw in group["keywords"]:
                if kw.lower() in full_text:
                    tag_hits += 1
                    score += weight * 0.5
                    reasons.append(f"{group_name}:{kw}")
                    break

    # --- Channel category boost ---
    if candidate.get("channel_category") == "primary":
        score += 1.5
        reasons.append("primary_channel")

    # --- View/engagement signal ---
    view_count = metadata.get("view_count") or 0
    like_count = metadata.get("like_count") or 0
    if view_count > 50000:
        score += 0.5
        reasons.append("high_views")
    if view_count > 0 and like_count / max(view_count, 1) > 0.04:
        score += 0.5
        reasons.append("high_engagement")

    # --- Chapters presence (signals structured content) ---
    chapters = metadata.get("chapters")
    if chapters and len(chapters) > 2:
        score += 0.5
        reasons.append("has_chapters")

    # Normalize to 0-10
    normalized = max(0.0, min(10.0, score))

    return round(normalized, 1), reasons


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Stage 2: yt-dlp metadata scoring")
    parser.add_argument("--config", default=os.path.join(REPO_ROOT, "config.yaml"))
    parser.add_argument("--keywords", default=os.path.join(REPO_ROOT, "keywords.yaml"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = load_yaml(args.config)
    keyword_groups = load_keywords(args.keywords)

    threshold = config["thresholds"]["stage2_min_score"]

    # Read Stage 1 candidates from stdin
    candidates = json.load(sys.stdin)
    print(f"Stage 2: Scoring {len(candidates)} candidates...", file=sys.stderr)

    qualifying = []

    for candidate in candidates:
        video_id = candidate["video_id"]
        print(f"  Fetching metadata: {video_id} ({candidate['title'][:60]})...", file=sys.stderr)

        metadata = fetch_metadata(video_id)
        if metadata is None:
            print(f"  SKIP (no metadata): {video_id}", file=sys.stderr)
            continue

        score, reasons = score_metadata(candidate, metadata, keyword_groups)
        candidate["stage2_score"] = score
        candidate["stage2_reasons"] = reasons

        if score >= threshold:
            qualifying.append(candidate)
            print(f"  PASS: [{score}/10] {candidate['title'][:60]}", file=sys.stderr)
            print(f"         Reasons: {', '.join(reasons)}", file=sys.stderr)
        else:
            print(f"  FAIL: [{score}/10] {candidate['title'][:60]}", file=sys.stderr)
            if args.dry_run:
                print(f"         Reasons: {', '.join(reasons)}", file=sys.stderr)

    # Sort by Stage 2 score descending
    qualifying.sort(key=lambda c: c["stage2_score"], reverse=True)

    print(f"\nStage 2 result: {len(qualifying)} videos qualify (threshold: {threshold})", file=sys.stderr)

    # Output JSON to stdout
    json.dump(qualifying, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
