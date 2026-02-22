#!/usr/bin/env python3
"""Tests for Stage 1 keyword filtering."""

import os
import sys
import unittest

# Add lib to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

from fetch_rss import score_stage1

# Test keyword groups matching keywords.yaml structure
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


class TestStage1Scoring(unittest.TestCase):
    def _make_candidate(self, title, description=""):
        return {"title": title, "description": description}

    def test_highly_relevant_dark_factory(self):
        c = self._make_candidate("Building a Dark Factory with Autonomous Agents")
        score = score_stage1(c, KEYWORD_GROUPS)
        self.assertGreaterEqual(score, 3)
        self.assertIn("dark_factory", c["stage1_matches"][0])

    def test_ai_coding_match(self):
        c = self._make_candidate("Claude Code Tutorial: Agentic Coding with MCP Server")
        score = score_stage1(c, KEYWORD_GROUPS)
        self.assertGreaterEqual(score, 2)

    def test_devops_match(self):
        c = self._make_candidate("Kubernetes GitOps with ArgoCD")
        score = score_stage1(c, KEYWORD_GROUPS)
        self.assertGreaterEqual(score, 2)

    def test_multi_group_match(self):
        c = self._make_candidate(
            "Building a Software Factory with CI/CD and Claude Code",
            "autonomous agent deployment with kubernetes"
        )
        score = score_stage1(c, KEYWORD_GROUPS)
        # Should match dark_factory(3) + ai_coding(2) + devops(2) = 7
        self.assertGreaterEqual(score, 7)

    def test_irrelevant_content(self):
        c = self._make_candidate("Best Minecraft Builds 2025")
        score = score_stage1(c, KEYWORD_GROUPS)
        self.assertLess(score, 0)

    def test_negative_overrides_positive(self):
        c = self._make_candidate("Gaming with AI: Building Minecraft Mods with Copilot")
        score = score_stage1(c, KEYWORD_GROUPS)
        # ai_coding(2) + negative(-3) = -1
        self.assertLess(score, 2)

    def test_no_match(self):
        c = self._make_candidate("How to Make Sourdough Bread at Home")
        score = score_stage1(c, KEYWORD_GROUPS)
        self.assertEqual(score, 0)

    def test_description_matching(self):
        c = self._make_candidate(
            "New Video Today",
            "In this video we explore autonomous agent frameworks for software factory automation"
        )
        score = score_stage1(c, KEYWORD_GROUPS)
        self.assertGreaterEqual(score, 3)

    def test_case_insensitive(self):
        c = self._make_candidate("CLAUDE CODE is AMAZING for DEVOPS")
        score = score_stage1(c, KEYWORD_GROUPS)
        self.assertGreaterEqual(score, 2)

    def test_enterprise_low_weight(self):
        c = self._make_candidate("Engineering Management: Developer Productivity Tips")
        score = score_stage1(c, KEYWORD_GROUPS)
        self.assertEqual(score, 1)


if __name__ == "__main__":
    unittest.main()
