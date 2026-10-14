import json
import tempfile
import unittest
from pathlib import Path

from scripts.publish_smartsub_preview import SOURCE_SHA256, SOURCE_SIZE, publish


class SmartSubPreviewPublicationTests(unittest.TestCase):
    def test_publishes_preview_urls_without_claiming_review_passed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            comparison_path = root / "comparison.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "input_size_bytes": SOURCE_SIZE,
                        "input_sha256": SOURCE_SHA256,
                        "source_match_status": "operator_attested_exact_event",
                        "render": {
                            "application": "SmartSub",
                            "version": "3.9.0",
                            "compose": "hardcode",
                            "encoder": "CPU",
                            "subtitle_authoring": "pysubs2==1.8.0",
                        },
                        "measurements": {"resolution": "1920x1080"},
                    }
                ),
                encoding="utf-8",
            )
            comparison_path.write_text(
                json.dumps(
                    {
                        "event": {},
                        "variants": [{"id": "open-source-baseline"}],
                    }
                ),
                encoding="utf-8",
            )

            publish(
                manifest_path,
                comparison_path,
                "https://github.com/gdelt0003/gdelt0003/releases/download/draft",
            )

            comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
            preview = comparison["smartsub_preview"]
            self.assertEqual(preview["status"], "public_unverified_preview")
            self.assertEqual(
                preview["review_status"]["translation_accuracy"],
                "not_verified",
            )
            self.assertEqual(
                preview["review_status"]["release_gate"],
                "blocked",
            )
            self.assertTrue(preview["video_url"].endswith("pvXbHQrIvTw-smartsub-draft.mp4"))
            self.assertEqual(
                comparison["variants"][0]["status"],
                "preview_unverified",
            )
            self.assertIn(
                "SmartSub 3.9.0",
                comparison["variants"][0]["render"],
            )

    def test_rejects_a_manifest_for_a_different_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            comparison_path = root / "comparison.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "input_size_bytes": SOURCE_SIZE,
                        "input_sha256": "0" * 64,
                        "source_match_status": "operator_attested_exact_event",
                    }
                ),
                encoding="utf-8",
            )
            comparison_path.write_text(
                json.dumps({"event": {}, "variants": []}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "does not match"):
                publish(manifest_path, comparison_path, "https://example.com/release")


if __name__ == "__main__":
    unittest.main()
