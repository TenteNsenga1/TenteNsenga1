import unittest

from jobagent.scoring import score_job

PROFILE = {
    "target_categories": [
        {
            "name": "Prompt Engineering & AI Workflow Automation",
            "weight": 1.2,
            "keywords": ["prompt engineer", "llm", "generative ai"],
        },
        {
            "name": "AI-Assisted QA & Software Testing",
            "weight": 1.0,
            "keywords": ["qa engineer", "software tester"],
        },
    ],
    "ai_signal_keywords": ["ai", "llm", "chatgpt", "generative ai"],
    "exclusion_keywords": ["cold calling", "call center", "sales representative"],
    "exclusion_threshold": 1,
}


class ScoreJobTests(unittest.TestCase):
    def test_matches_best_category(self):
        result = score_job(
            "Remote Prompt Engineer",
            "Design prompts for our generative AI / LLM products.",
            "ai,remote",
            PROFILE,
        )
        self.assertEqual(result.category, "Prompt Engineering & AI Workflow Automation")
        self.assertFalse(result.excluded)
        self.assertGreater(result.fit_score, 0)

    def test_excludes_customer_facing_roles(self):
        result = score_job(
            "Inside Sales Rep",
            "Cold calling leads all day, call center environment, quota driven.",
            "sales",
            PROFILE,
        )
        self.assertTrue(result.excluded)
        self.assertLess(result.fit_score, 0)
        self.assertIn("cold calling", result.exclusion_hits)

    def test_no_category_match_is_not_excluded(self):
        result = score_job("Warehouse Associate", "Lift boxes.", "", PROFILE)
        self.assertIsNone(result.category)
        self.assertFalse(result.excluded)
        self.assertEqual(result.fit_score, 0)

    def test_ai_signal_adds_score_even_without_category_match(self):
        result = score_job(
            "Data Coordinator",
            "You'll use AI and ChatGPT tools daily.",
            "",
            PROFILE,
        )
        self.assertGreater(result.ai_score, 0)
        self.assertGreater(result.fit_score, 0)


if __name__ == "__main__":
    unittest.main()
