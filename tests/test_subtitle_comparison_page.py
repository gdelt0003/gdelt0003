import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "outputs" / "president-trump-gaggle-oct-13-2026" / "comparison.json"


class SubtitleComparisonPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.variants = {item["id"]: item for item in cls.manifest["variants"]}

    def test_event_identity_does_not_promote_filename_date_or_assign_an_event_id(self):
        event = self.manifest["event"]
        self.assertIsNone(event["event_id"])
        self.assertEqual(event["identity_status"], "incomplete_unverified")
        self.assertIn("未独立核实", event["date_display"])
        self.assertEqual(event["source_match_status"], "not_verified")
        self.assertEqual(event["reuse_rights_status"], "not_confirmed")

    def test_requested_microsoft_label_is_not_presented_as_a_configured_model(self):
        variant = self.variants["microsoft-copilot-gpt6-request"]
        self.assertEqual(variant["status"], "not_configured")
        self.assertIsNone(variant["model_id"])
        self.assertFalse(variant["provider_endpoint_configured"])
        self.assertFalse(variant["credentials_configured"])
        self.assertTrue(all(value is None for value in variant["quality"].values()))

    def test_open_source_baseline_names_existing_models_without_fake_outputs(self):
        variant = self.variants["open-whisper-m2m100"]
        self.assertEqual(variant["status"], "not_run")
        self.assertEqual(variant["asr_model"], "large-v3-turbo")
        self.assertEqual(variant["translation_model"], "facebook/m2m100_1.2B")
        self.assertTrue(all(value is None for value in variant["assets"].values()))
        self.assertTrue(all(value is None for value in variant["quality"].values()))

    def test_comparable_metrics_are_explicitly_unverified_for_both_variants(self):
        self.assertEqual(
            len(self.manifest["metrics"]),
            4,
        )
        for metric in self.manifest["metrics"]:
            with self.subTest(metric=metric["id"]):
                self.assertIn("copilot", metric["variants"])
                self.assertIn("open_source", metric["variants"])
                self.assertIsNone(metric["variants"]["copilot"]["value"])
                self.assertIsNone(metric["variants"]["open_source"]["value"])

    def test_page_is_linked_from_home_and_labels_the_requested_constraint(self):
        home = (ROOT / "index.html").read_text(encoding="utf-8")
        page = (ROOT / "subtitle-comparison.html").read_text(encoding="utf-8")
        renderer = (ROOT / "assets" / "comparison.js").read_text(encoding="utf-8")
        self.assertIn('href="subtitle-comparison.html"', home)
        self.assertIn("GPT-6", page)
        self.assertIn("GitHub-hosted runner", page)
        self.assertIn("textContent", renderer)
        self.assertIn("url.protocol === 'https:'", renderer)


if __name__ == "__main__":
    unittest.main()
