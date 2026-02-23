#!/usr/bin/env python3
"""Grid search calibration for Stage 2 scoring parameters.

Loads cached yt-dlp metadata, sweeps all parameter combinations,
finds the set that minimizes MAE vs Claude ground-truth scores
while maintaining 10/10 pass/fail accuracy at threshold 5.

Usage:
    python3 lib/calibrate.py
"""

import itertools
import json
import math
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from lib.filter_stage2 import load_keywords, score_metadata, SCORING_PARAMS

CACHE_PATH = os.path.join(REPO_ROOT, "tests", "fixtures", "benchmark_metadata.json")
THRESHOLD = 6

# Reference videos with Claude ground-truth scores
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

# Parameter search space
SEARCH_SPACE = {
    "kw_max":          [4.5, 5.0, 5.5, 6.0],
    "kw_scale":        [1.4, 1.6, 1.8, 2.0, 2.2],
    "depth_max":       [2.0, 2.5, 3.0, 3.5],
    "ch_factor_none":  [0.2, 0.35, 0.5, 0.65],
    "ch_factor_mid":   [0.5, 0.6, 0.7],
    "social_max":      [0.5, 0.75, 1.0],
    "short_cap_under2": [3.5, 4.0, 4.5],
    "short_cap_2to3":  [4.5, 4.9, 5.0],
}


def spearman_rank_correlation(x, y):
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


def evaluate_params(params, videos, keyword_groups):
    """Score all videos with given params. Returns (mae, spearman, pass_fail_correct, scores)."""
    scores = []
    claude_scores = []
    correct = 0

    for ref, (metadata, candidate) in videos:
        score, _ = score_metadata(candidate, metadata, keyword_groups, params=params)
        scores.append(score)
        claude_scores.append(ref["claude_score"])

        predicted_pass = "PASS" if score >= THRESHOLD else "FAIL"
        if predicted_pass == ref["expected"]:
            correct += 1

    mae = sum(abs(c - s) for c, s in zip(claude_scores, scores)) / len(scores)
    spearman = spearman_rank_correlation(claude_scores, scores)
    return mae, spearman, correct, scores


def main():
    # Load cached metadata
    if not os.path.exists(CACHE_PATH):
        print(f"ERROR: Cache not found at {CACHE_PATH}", file=sys.stderr)
        print("Run: python3 lib/cache_metadata.py", file=sys.stderr)
        sys.exit(1)

    with open(CACHE_PATH) as f:
        cache = json.load(f)

    keyword_groups = load_keywords(os.path.join(REPO_ROOT, "keywords.yaml"))

    # Build video list: (ref, (metadata, candidate))
    videos = []
    for ref in REFERENCE_VIDEOS:
        vid = ref["video_id"]
        if vid not in cache:
            print(f"WARNING: {vid} not in cache, skipping", file=sys.stderr)
            continue
        metadata = cache[vid]
        candidate = {
            "video_id": vid,
            "title": metadata.get("title", ""),
            "channel_category": metadata.get("channel_category", "secondary"),
        }
        videos.append((ref, (metadata, candidate)))

    if len(videos) != len(REFERENCE_VIDEOS):
        print(f"WARNING: Only {len(videos)}/{len(REFERENCE_VIDEOS)} videos cached", file=sys.stderr)

    # ── Current baseline ─────────────────────────────────────────────
    cur_mae, cur_spearman, cur_correct, cur_scores = evaluate_params(
        SCORING_PARAMS, videos, keyword_groups
    )
    print(f"Current params: MAE={cur_mae:.3f}, Spearman={cur_spearman:.3f}, "
          f"Pass/Fail={cur_correct}/{len(videos)}")

    # ── Grid search ──────────────────────────────────────────────────
    param_names = list(SEARCH_SPACE.keys())
    param_values = [SEARCH_SPACE[k] for k in param_names]
    total_combos = 1
    for v in param_values:
        total_combos *= len(v)
    print(f"\nSearching {total_combos:,} parameter combinations...")

    best_mae = float("inf")
    best_spearman = -1.0
    best_params = None
    best_scores = None
    passing_combos = 0

    for combo in itertools.product(*param_values):
        params = dict(zip(param_names, combo))
        mae, spearman, correct, scores = evaluate_params(params, videos, keyword_groups)

        # Hard constraint: 10/10 pass/fail
        if correct < len(videos):
            continue
        passing_combos += 1

        # Minimize MAE, tiebreak on Spearman
        if mae < best_mae or (mae == best_mae and spearman > best_spearman):
            best_mae = mae
            best_spearman = spearman
            best_params = params
            best_scores = scores

    print(f"Combos with 10/10 pass/fail: {passing_combos:,}/{total_combos:,}")

    if best_params is None:
        print("\nERROR: No parameter combination achieves 10/10 pass/fail!", file=sys.stderr)
        sys.exit(1)

    # ── Report ───────────────────────────────────────────────────────
    print(f"\n{'=' * 90}")
    print("OPTIMAL PARAMETERS")
    print("=" * 90)
    print("SCORING_PARAMS = {")
    for k, v in best_params.items():
        # Align with current param formatting
        print(f'    "{k}": {v},')
    print("}")

    print(f"\n{'=' * 90}")
    print("PER-VIDEO COMPARISON")
    print("=" * 90)
    header = f"{'Title':<50} {'Claude':>6} {'Current':>8} {'Optimal':>8} {'Delta':>6}"
    print(header)
    print("-" * 90)

    for i, (ref, (metadata, _)) in enumerate(videos):
        title = metadata.get("title", "")[:48]
        claude = ref["claude_score"]
        cur = cur_scores[i]
        opt = best_scores[i]
        delta = opt - claude
        delta_str = f"{delta:+.1f}"
        print(f"{title:<50} {claude:>6} {cur:>8.1f} {opt:>8.1f} {delta_str:>6}")

    print(f"\n{'Metric':<35} {'Current':>10} {'Optimal':>10}")
    print("-" * 55)
    print(f"{'MAE vs Claude':<35} {cur_mae:>10.3f} {best_mae:>10.3f}")
    print(f"{'Spearman correlation':<35} {cur_spearman:>10.3f} {best_spearman:>10.3f}")
    print(f"{'Pass/Fail accuracy':<35} {cur_correct}/{len(videos):>8} {len(videos)}/{len(videos):>8}")

    # ── Paste-ready dict ─────────────────────────────────────────────
    print(f"\n{'=' * 90}")
    print("PASTE INTO lib/filter_stage2.py:")
    print("=" * 90)
    print("SCORING_PARAMS = {")
    for k, v in best_params.items():
        comment = {
            "kw_max": "Keyword relevance ceiling",
            "kw_scale": "sqrt scaling factor",
            "depth_max": "Content depth ceiling",
            "ch_factor_none": "Chapter factor when 0-2 chapters",
            "ch_factor_mid": "Chapter factor when 3-4 chapters",
            "social_max": "Social proof ceiling",
            "short_cap_under2": "Score cap for <2min videos",
            "short_cap_2to3": "Score cap for 2-3min videos",
        }.get(k, "")
        padding = " " * (20 - len(f'"{k}": {v},'))
        print(f'    "{k}": {v},{padding}# {comment}')
    print("}")


if __name__ == "__main__":
    main()
