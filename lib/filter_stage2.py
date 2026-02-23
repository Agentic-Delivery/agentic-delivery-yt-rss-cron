#!/usr/bin/env python3
"""Stage 2: Deterministic scoring using yt-dlp metadata.

Reads Stage 1 candidates from stdin (JSON array), fetches yt-dlp metadata
for each, applies deterministic scoring heuristic, outputs qualifying videos.

No LLM calls. Costs only yt-dlp network requests (2-5s each).

Usage:
    cat candidates.json | python3 lib/filter_stage2.py [--config config.yaml]
"""

import json
import math
import os
import subprocess
import sys

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Tunable scoring constants — calibrated via lib/calibrate.py grid search
SCORING_PARAMS = {
    "kw_max": 4.5,           # Keyword relevance ceiling
    "kw_scale": 2.2,         # sqrt scaling factor
    "depth_max": 2.5,        # Content depth ceiling
    "ch_factor_none": 0.65,  # Chapter factor when 0-2 chapters
    "ch_factor_mid": 0.5,    # Chapter factor when 3-4 chapters
    "social_max": 0.75,      # Social proof ceiling
    "short_cap_under2": 3.5, # Score cap for <2min videos
    "short_cap_2to3": 5.0,   # Score cap for 2-3min videos
}


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


def score_metadata(candidate, metadata, keyword_groups, params=None):
    """Deterministic scoring on yt-dlp metadata. Returns 0-10 score.

    4-component formula:
      1. Keyword Relevance (0-kw_max): ALL matches counted, location-weighted,
         sqrt diminishing returns.
      2. Content Depth (0-depth_max): duration_factor * chapter_factor (multiplicative).
      3. Channel Authority (0-1): primary channel boost.
      4. Social Proof (0-social_max): graduated view tiers + engagement bonus.
    Negative keywords apply -2.0 penalty post-assembly.
    """
    if params is None:
        params = SCORING_PARAMS
    reasons = []

    title = (metadata.get("title") or "").lower()
    tags = [t.lower() for t in (metadata.get("tags") or [])]
    description = (metadata.get("description") or "").lower()
    tags_text = " ".join(tags)

    # ── 1. Keyword Relevance (max 6.0) ──────────────────────────────
    raw_kw_score = 0.0
    neg_penalty = 0.0
    # Track matched keywords per location to skip substring overlaps
    # e.g. "ai code" is a substring of "ai coding" — don't double-count
    matched_in_title = []
    matched_in_tags = []
    matched_in_desc = []

    def _is_substring_of_matched(kw, matched_list):
        """Return True if kw is a substring of any already-matched keyword."""
        return any(kw in m for m in matched_list if kw != m)

    for group_name, group in keyword_groups.items():
        weight = group["weight"]
        if weight < 0:
            for kw in group["keywords"]:
                if kw.lower() in f"{title} {tags_text} {description}":
                    neg_penalty += 2.0
                    reasons.append(f"neg:{kw}")
                    break
        else:
            for kw in group["keywords"]:
                kw_lower = kw.lower()
                matched = False
                if kw_lower in title and not _is_substring_of_matched(kw_lower, matched_in_title):
                    raw_kw_score += weight * 1.0
                    reasons.append(f"kw_title:{group_name}:{kw}")
                    matched_in_title.append(kw_lower)
                    matched = True
                if kw_lower in tags_text and not _is_substring_of_matched(kw_lower, matched_in_tags):
                    raw_kw_score += weight * 0.5
                    if not matched:
                        reasons.append(f"kw_tag:{group_name}:{kw}")
                    matched_in_tags.append(kw_lower)
                    matched = True
                if kw_lower in description and not _is_substring_of_matched(kw_lower, matched_in_desc):
                    raw_kw_score += weight * 0.3
                    if not matched:
                        reasons.append(f"kw_desc:{group_name}:{kw}")
                    matched_in_desc.append(kw_lower)

    keyword_score = min(params["kw_max"], params["kw_scale"] * math.sqrt(raw_kw_score))
    if keyword_score > 0:
        reasons.append(f"kw_raw={raw_kw_score:.1f}->scaled={keyword_score:.2f}")

    # ── 2. Content Depth (max 2.0) ──────────────────────────────────
    duration = metadata.get("duration", 0) or 0
    if duration >= 1800:
        duration_factor = 1.0
    elif duration >= 600:
        duration_factor = 0.4 + 0.6 * ((duration - 600) / 1200)
    elif duration >= 120:
        duration_factor = 0.2 + 0.2 * ((duration - 120) / 480)
    else:
        duration_factor = 0.0

    chapters = metadata.get("chapters")
    chapter_count = len(chapters) if chapters else 0
    if chapter_count >= 5:
        chapter_factor = 1.0
    elif chapter_count >= 3:
        chapter_factor = params["ch_factor_mid"]
    else:
        chapter_factor = params["ch_factor_none"]

    depth_score = params["depth_max"] * duration_factor * chapter_factor
    reasons.append(f"depth={depth_score:.2f}(dur={duration}s,ch={chapter_count})")

    # ── 3. Channel Authority (max 1.0) ──────────────────────────────
    authority_score = 0.0
    if candidate.get("channel_category") == "primary":
        authority_score = 1.0
        reasons.append("primary_channel")

    # ── 4. Social Proof (max 1.0) ───────────────────────────────────
    view_count = metadata.get("view_count") or 0
    like_count = metadata.get("like_count") or 0

    if view_count >= 100000:
        view_pts = 0.6
    elif view_count >= 25000:
        view_pts = 0.4
    elif view_count >= 5000:
        view_pts = 0.2
    elif view_count >= 500:
        view_pts = 0.1
    else:
        view_pts = 0.0

    engagement_pts = 0.0
    if view_count > 0 and like_count / view_count > 0.04:
        engagement_pts = 0.4
    elif view_count > 0 and like_count / view_count > 0.02:
        engagement_pts = 0.2

    social_score = min(params["social_max"], view_pts + engagement_pts)
    if social_score > 0:
        reasons.append(f"social={social_score:.1f}(v={view_count},l={like_count})")

    # ── Short-form penalty ────────────────────────────────────────
    # Short videos can't contain deep content regardless of keywords.
    # <2min: hard cap at 4.5 (below threshold).
    # 2-3min: cap at 5.0 (borderline — only exceptionally relevant pass).
    short_cap = None
    if duration < 120:
        short_cap = params["short_cap_under2"]
        reasons.append(f"short_cap={short_cap}(dur={duration}s)")
    elif duration < 180:
        short_cap = params["short_cap_2to3"]
        reasons.append(f"short_cap={short_cap}(dur={duration}s)")

    # ── Assemble ────────────────────────────────────────────────────
    subtotal = keyword_score + depth_score + authority_score + social_score
    if short_cap is not None:
        subtotal = min(subtotal, short_cap)
    total = subtotal - neg_penalty
    normalized = max(0.0, min(10.0, total))

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
