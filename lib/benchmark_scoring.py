#!/usr/bin/env python3
"""Benchmark harness: compare old vs new Stage 2 scoring against Claude ground truth.

Uses cached yt-dlp metadata by default (instant, deterministic).
Pass --live to fetch fresh metadata via yt-dlp.

Usage:
    python3 lib/benchmark_scoring.py          # cached (default)
    python3 lib/benchmark_scoring.py --live   # live yt-dlp fetch
"""

import argparse
import json
import math
import os
import sys

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from lib.filter_stage2 import fetch_metadata, load_keywords, load_yaml

CACHE_PATH = os.path.join(REPO_ROOT, "tests", "fixtures", "benchmark_metadata.json")

# ── Reference videos with Claude ground-truth scores ─────────────────────
REFERENCE_VIDEOS = [
    {"video_id": "bDcgHzCBgmQ", "claude_score": 9, "expected": "PASS"},
    {"video_id": "41UDGsBEjoI", "claude_score": 8, "expected": "PASS"},
    {"video_id": "uvs1Igr4u6g", "claude_score": 8, "expected": "PASS"},
    {"video_id": "efctPj6bjCY", "claude_score": 8, "expected": "PASS"},
    {"video_id": "Y3PIZtR9gik", "claude_score": 7, "expected": "PASS"},
    {"video_id": "60G93MXT4DI", "claude_score": 7, "expected": "PASS"},
    {"video_id": "xaNZIoQETWw", "claude_score": 7, "expected": "PASS"},
    {"video_id": "FDYhPXYDS_o", "claude_score": 5, "expected": "FAIL"},
    {"video_id": "_ykT_l4e8F8", "claude_score": 4, "expected": "FAIL"},
    {"video_id": "-P79jTyYtWA", "claude_score": 3, "expected": "FAIL"},
]

THRESHOLD = 6


# ── Old scoring function (preserved for comparison) ──────────────────────
def score_metadata_old(candidate, metadata, keyword_groups):
    """Original scoring function (before redesign)."""
    score = 0.0
    reasons = []

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

    tags = [t.lower() for t in (metadata.get("tags") or [])]
    description = (metadata.get("description") or "").lower()
    title = (metadata.get("title") or "").lower()
    full_text = f"{title} {description} {' '.join(tags)}"

    for group_name, group in keyword_groups.items():
        weight = group["weight"]
        if weight < 0:
            for kw in group["keywords"]:
                if kw.lower() in full_text:
                    score -= 2.0
                    reasons.append(f"neg:{kw}")
                    break
        else:
            for kw in group["keywords"]:
                if kw.lower() in full_text:
                    score += weight * 0.5
                    reasons.append(f"{group_name}:{kw}")
                    break

    if candidate.get("channel_category") == "primary":
        score += 1.5
        reasons.append("primary_channel")

    view_count = metadata.get("view_count") or 0
    like_count = metadata.get("like_count") or 0
    if view_count > 50000:
        score += 0.5
        reasons.append("high_views")
    if view_count > 0 and like_count / max(view_count, 1) > 0.04:
        score += 0.5
        reasons.append("high_engagement")

    chapters = metadata.get("chapters")
    if chapters and len(chapters) > 2:
        score += 0.5
        reasons.append("has_chapters")

    normalized = max(0.0, min(10.0, score))
    return round(normalized, 1), reasons


def spearman_rank_correlation(x, y):
    """Compute Spearman rank correlation between two lists."""
    n = len(x)
    if n < 2:
        return 0.0

    def rank(vals):
        sorted_indices = sorted(range(n), key=lambda i: vals[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j < n - 1 and vals[sorted_indices[j]] == vals[sorted_indices[j + 1]]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                ranks[sorted_indices[k]] = avg_rank
            i = j + 1
        return ranks

    rx = rank(x)
    ry = rank(y)
    d_sq = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    return 1.0 - (6.0 * d_sq) / (n * (n * n - 1))


def load_cached_metadata():
    """Load cached metadata from tests/fixtures/benchmark_metadata.json."""
    if not os.path.exists(CACHE_PATH):
        print(f"ERROR: Cache not found at {CACHE_PATH}", file=sys.stderr)
        print("Run: python3 lib/cache_metadata.py", file=sys.stderr)
        sys.exit(1)
    with open(CACHE_PATH) as f:
        return json.load(f)


def main():
    from lib.filter_stage2 import score_metadata as score_metadata_new

    parser = argparse.ArgumentParser(description="Benchmark Stage 2 scoring")
    parser.add_argument("--live", action="store_true",
                        help="Fetch fresh metadata via yt-dlp instead of using cache")
    args = parser.parse_args()

    keyword_groups = load_keywords(os.path.join(REPO_ROOT, "keywords.yaml"))

    # Load channel list to determine primary/secondary
    channels_data = load_yaml(os.path.join(REPO_ROOT, "channels.yaml"))
    channel_categories = {}
    for ch in channels_data["channels"]:
        channel_categories[ch["channel_id"]] = ch["category"]
        channel_categories[ch["name"].lower()] = ch["category"]

    # Load metadata (cached or live)
    cache = None
    if not args.live:
        cache = load_cached_metadata()
        print("Using cached metadata.\n")
    else:
        print("Fetching metadata for reference videos (live)...\n")

    results = []
    for ref in REFERENCE_VIDEOS:
        vid = ref["video_id"]

        if cache is not None:
            if vid not in cache:
                print(f"  SKIP: {vid} not in cache")
                continue
            metadata = cache[vid]
            category = metadata.get("channel_category", "secondary")
            print(f"  Cached: {vid} — {metadata.get('title', '')[:50]}")
        else:
            print(f"  Fetching: {vid}...", end=" ", flush=True)
            metadata = fetch_metadata(vid)
            if metadata is None:
                print("FAILED")
                continue
            print("OK")
            uploader = (metadata.get("uploader") or "").lower()
            channel_id = metadata.get("channel_id") or ""
            category = channel_categories.get(channel_id,
                       channel_categories.get(uploader, "secondary"))

        candidate = {
            "video_id": vid,
            "title": metadata.get("title", ""),
            "channel_category": category,
        }

        old_score, old_reasons = score_metadata_old(candidate, metadata, keyword_groups)
        new_score, new_reasons = score_metadata_new(candidate, metadata, keyword_groups)

        new_pass = "PASS" if new_score >= THRESHOLD else "FAIL"
        correct = new_pass == ref["expected"]

        results.append({
            "video_id": vid,
            "title": metadata.get("title", "")[:55],
            "claude": ref["claude_score"],
            "expected": ref["expected"],
            "old_score": old_score,
            "new_score": new_score,
            "new_pass": new_pass,
            "correct": correct,
            "old_reasons": old_reasons,
            "new_reasons": new_reasons,
        })

    if not results:
        print("\nERROR: No metadata fetched. Check network/yt-dlp.", file=sys.stderr)
        sys.exit(1)

    # ── Report ───────────────────────────────────────────────────────
    print("\n" + "=" * 100)
    print("BENCHMARK RESULTS")
    print("=" * 100)

    header = f"{'Title':<55} {'Claude':>6} {'Old':>5} {'New':>5} {'Pass?':>5} {'OK?':>4}"
    print(header)
    print("-" * 100)

    for r in results:
        ok_mark = " Y " if r["correct"] else "** N **"
        print(f"{r['title']:<55} {r['claude']:>6} {r['old_score']:>5} {r['new_score']:>5} {r['new_pass']:>5} {ok_mark:>7}")

    # ── Statistics ───────────────────────────────────────────────────
    claude_scores = [r["claude"] for r in results]
    old_scores = [r["old_score"] for r in results]
    new_scores = [r["new_score"] for r in results]

    old_corr = spearman_rank_correlation(claude_scores, old_scores)
    new_corr = spearman_rank_correlation(claude_scores, new_scores)

    old_mae = sum(abs(c - o) for c, o in zip(claude_scores, old_scores)) / len(results)
    new_mae = sum(abs(c - n) for c, n in zip(claude_scores, new_scores)) / len(results)

    correct_count = sum(1 for r in results if r["correct"])
    total = len(results)

    print(f"\n{'Metric':<35} {'Old':>10} {'New':>10}")
    print("-" * 55)
    print(f"{'Spearman rank correlation':<35} {old_corr:>10.3f} {new_corr:>10.3f}")
    print(f"{'Mean Absolute Error vs Claude':<35} {old_mae:>10.2f} {new_mae:>10.2f}")
    print(f"{'Pass/Fail accuracy (threshold=5)':<35} {'n/a':>10} {correct_count}/{total:>8}")

    # ── Detailed reasons for new scoring ─────────────────────────────
    print(f"\n{'=' * 100}")
    print("DETAILED NEW SCORING REASONS")
    print("=" * 100)
    for r in results:
        print(f"\n{r['title']} (Claude={r['claude']}, New={r['new_score']})")
        for reason in r["new_reasons"]:
            print(f"  - {reason}")

    if correct_count < total:
        print(f"\nWARNING: {total - correct_count} video(s) misclassified at threshold {THRESHOLD}.")
        sys.exit(1)
    else:
        print(f"\nAll {total} videos correctly classified at threshold {THRESHOLD}.")


if __name__ == "__main__":
    main()
