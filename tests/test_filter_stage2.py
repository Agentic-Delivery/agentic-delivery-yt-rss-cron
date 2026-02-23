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

    def test_depth_score_format(self):
        """Duration contributes to depth score reported as depth=X.XX(dur=Ns,ch=N)."""
        candidate = self._make_candidate()
        metadata = {"duration": 600, "tags": [], "description": "", "title": ""}
        score, reasons = score_metadata(candidate, metadata, KEYWORD_GROUPS)
        self.assertTrue(any(r.startswith("depth=") for r in reasons))

    def test_short_video_capped(self):
        """Videos under 2 minutes get a short_cap applied."""
        candidate = self._make_candidate()
        metadata = {"duration": 30, "tags": [], "description": "", "title": ""}
        score, reasons = score_metadata(candidate, metadata, KEYWORD_GROUPS)
        self.assertTrue(any("short_cap=" in r for r in reasons))

    def test_long_video_depth(self):
        """Very long videos still get scored via depth component."""
        candidate = self._make_candidate()
        metadata = {"duration": 20000, "tags": [], "description": "", "title": ""}
        score, reasons = score_metadata(candidate, metadata, KEYWORD_GROUPS)
        self.assertTrue(any(r.startswith("depth=") and "dur=20000s" in r for r in reasons))

    def test_primary_channel_boost(self):
        candidate_primary = self._make_candidate("primary")
        candidate_secondary = self._make_candidate("secondary")
        metadata = {"duration": 600, "tags": [], "description": "", "title": ""}
        score_p, _ = score_metadata(candidate_primary, metadata, KEYWORD_GROUPS)
        score_s, _ = score_metadata(candidate_secondary, metadata, KEYWORD_GROUPS)
        self.assertGreater(score_p, score_s)

    def test_social_score_format(self):
        """High views + engagement produce a social=X.X reason."""
        candidate = self._make_candidate()
        metadata = {"duration": 600, "tags": [], "description": "", "title": "", "view_count": 100000, "like_count": 5000}
        score, reasons = score_metadata(candidate, metadata, KEYWORD_GROUPS)
        self.assertTrue(any(r.startswith("social=") for r in reasons))

    def test_chapters_improve_depth(self):
        """Videos with chapters get a higher depth score than without."""
        candidate = self._make_candidate()
        base_meta = {"duration": 1800, "tags": [], "description": "", "title": ""}
        meta_with_ch = {**base_meta, "chapters": [{"title": f"Ch{i}"} for i in range(5)]}
        score_no_ch, _ = score_metadata(candidate, base_meta, KEYWORD_GROUPS)
        score_ch, _ = score_metadata(candidate, meta_with_ch, KEYWORD_GROUPS)
        self.assertGreater(score_ch, score_no_ch)

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
