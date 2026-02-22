#!/usr/bin/env python3
"""Tests for Stage 2 metadata scoring."""

import json
import os
import sys
import unittest

# Add lib to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

from filter_stage2 import score_metadata

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

KEYWORD_GROUPS = {
    "dark_factory": {
        "weight": 3,
        "keywords": ["dark factory", "autonomous agent", "multi-agent", "software factory"],
    },
    "ai_coding": {
        "weight": 2,
        "keywords": ["claude code", "cursor", "copilot", "agentic coding", "vibe coding", "mcp server"],
    },
    "devops": {
        "weight": 2,
        "keywords": ["ci/cd", "kubernetes", "docker", "gitops", "devops", "terraform"],
    },
    "enterprise": {
        "weight": 1,
        "keywords": ["engineering management", "developer productivity", "dora metrics"],
    },
    "business": {
        "weight": 1,
        "keywords": ["saas pricing", "product-led growth", "startup"],
    },
    "negative": {
        "weight": -3,
        "keywords": ["gaming", "minecraft", "cooking", "workout", "mukbang"],
    },
}


class TestStage2Scoring(unittest.TestCase):
    def _make_candidate(self, category="secondary"):
        return {"channel_category": category}

    def test_relevant_video_with_fixture(self):
        with open(os.path.join(FIXTURES_DIR, "sample_metadata.json")) as f:
            metadata = json.load(f)
        candidate = self._make_candidate("primary")
        score, reasons = score_metadata(candidate, metadata, KEYWORD_GROUPS)
        self.assertGreaterEqual(score, 4.0)
        self.assertIn("primary_channel", reasons)

    def test_duration_sweet_spot(self):
        candidate = self._make_candidate()
        metadata = {"duration": 600, "tags": [], "description": "", "title": ""}
        score, reasons = score_metadata(candidate, metadata, KEYWORD_GROUPS)
        self.assertIn("duration_ok", reasons)

    def test_too_short(self):
        candidate = self._make_candidate()
        metadata = {"duration": 30, "tags": [], "description": "", "title": ""}
        score, reasons = score_metadata(candidate, metadata, KEYWORD_GROUPS)
        self.assertIn("too_short", reasons)

    def test_very_long(self):
        candidate = self._make_candidate()
        metadata = {"duration": 20000, "tags": [], "description": "", "title": ""}
        score, reasons = score_metadata(candidate, metadata, KEYWORD_GROUPS)
        self.assertIn("very_long", reasons)

    def test_primary_channel_boost(self):
        candidate_primary = self._make_candidate("primary")
        candidate_secondary = self._make_candidate("secondary")
        metadata = {"duration": 600, "tags": [], "description": "", "title": ""}
        score_p, _ = score_metadata(candidate_primary, metadata, KEYWORD_GROUPS)
        score_s, _ = score_metadata(candidate_secondary, metadata, KEYWORD_GROUPS)
        self.assertGreater(score_p, score_s)

    def test_high_views_bonus(self):
        candidate = self._make_candidate()
        metadata = {"duration": 600, "tags": [], "description": "", "title": "", "view_count": 100000, "like_count": 5000}
        score, reasons = score_metadata(candidate, metadata, KEYWORD_GROUPS)
        self.assertIn("high_views", reasons)
        self.assertIn("high_engagement", reasons)

    def test_chapters_bonus(self):
        candidate = self._make_candidate()
        metadata = {
            "duration": 600, "tags": [], "description": "", "title": "",
            "chapters": [{"title": "Intro"}, {"title": "Main"}, {"title": "Outro"}]
        }
        score, reasons = score_metadata(candidate, metadata, KEYWORD_GROUPS)
        self.assertIn("has_chapters", reasons)

    def test_keyword_in_tags(self):
        candidate = self._make_candidate()
        metadata = {"duration": 600, "tags": ["claude code", "agentic AI"], "description": "", "title": ""}
        score, reasons = score_metadata(candidate, metadata, KEYWORD_GROUPS)
        self.assertTrue(any("ai_coding" in r for r in reasons))

    def test_negative_keywords_penalize(self):
        candidate = self._make_candidate()
        metadata = {"duration": 600, "tags": ["gaming", "minecraft"], "description": "gaming stream", "title": "Minecraft Build"}
        score, reasons = score_metadata(candidate, metadata, KEYWORD_GROUPS)
        self.assertTrue(any("neg:" in r for r in reasons))

    def test_score_clamped(self):
        candidate = self._make_candidate()
        # All negative signals
        metadata = {"duration": 10, "tags": ["gaming"], "description": "gaming cooking mukbang", "title": ""}
        score, _ = score_metadata(candidate, metadata, KEYWORD_GROUPS)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 10.0)


if __name__ == "__main__":
    unittest.main()
