import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "outputs" / "pvXbHQrIvTw" / "comparison.json"
PAGE = ROOT / "events" / "pvXbHQrIvTw" / "index.html"
SCRIPT = ROOT / "assets" / "comparison.js"
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-pages.yml"


class SubtitleComparisonPageTests(unittest.TestCase):
    def test_manifest_has_two_explicit_variants_and_unknown_metrics(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        variants = {variant["id"]: variant for variant in manifest["variants"]}

        self.assertEqual(set(variants), {"open-source-baseline", "microsoft-copilot-gpt6"})
        self.assertEqual(variants["open-source-baseline"]["status"], "not_run")
        self.assertEqual(
            variants["open-source-baseline"]["models"]["asr"],
            "faster-whisper large-v3-turbo (repository pipeline)",
        )
        self.assertEqual(
            variants["open-source-baseline"]["models"]["translation"],
            "facebook/m2m100_1.2B (repository pipeline)",
        )
        self.assertEqual(
            variants["microsoft-copilot-gpt6"]["status"],
            "blocked_model_unavailable",
        )
        self.assertIsNone(variants["microsoft-copilot-gpt6"]["models"]["asr"])
        self.assertIsNone(variants["microsoft-copilot-gpt6"]["metrics"]["wer"])
        self.assertFalse(manifest["comparison_metrics"]["measured"])
        self.assertEqual(manifest["event"]["video_id"], "pvXbHQrIvTw")
        self.assertEqual(manifest["event"]["local_file_size_bytes"], 262338614)
        self.assertFalse(manifest["comparison_metrics"]["same_input_verified"])

    def test_page_does_not_advertise_missing_video_or_subtitles_as_available(self):
        page = PAGE.read_text(encoding="utf-8")
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("尚未生成", script)
        self.assertIn("尚无生成文本", script)
        self.assertIn("blocked_model_unavailable", script)
        self.assertIn("未测 / 未提供", script)
        self.assertNotIn("<source src=", page)
        self.assertIn("pvXbHQrIvTw", page)

    def test_event_page_changes_trigger_pages_deploy(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        push = workflow.split("  workflow_dispatch:", maxsplit=1)[0]

        self.assertIn("      - 'events/**'", push)
        self.assertIn("      - 'outputs/**'", push)


if __name__ == "__main__":
    unittest.main()
