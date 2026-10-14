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
            main_videos_path = root / "main-videos.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "input_size_bytes": SOURCE_SIZE,
                        "input_sha256": SOURCE_SHA256,
                        "source_match_status": "operator_attested_exact_event",
                        "workflow_run_id": 12345,
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
                        "event": {
                            "source_url": "https://www.youtube.com/watch?v=pvXbHQrIvTw",
                        },
                        "variants": [{"id": "open-source-baseline"}],
                    }
                ),
                encoding="utf-8",
            )
            main_videos_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "videos": [
                            {
                                "id": "whitehouse-oW-PQlgw1wo",
                                "video_url": "https://example.test/oW.mp4",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            publish(
                manifest_path,
                comparison_path,
                main_videos_path,
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
            catalog = json.loads(main_videos_path.read_text(encoding="utf-8"))
            self.assertEqual(
                [video["id"] for video in catalog["videos"]],
                ["whitehouse-oW-PQlgw1wo", "pvXbHQrIvTw-smartsub-draft-12345"],
            )
            preview_video = catalog["videos"][1]
            self.assertIn("未经人工核验", preview_video["title"])
            self.assertEqual(
                preview_video["video_url"],
                preview["video_url"],
            )
            self.assertEqual(
                [subtitle["url"] for subtitle in preview_video["subtitles"]],
                list(preview["subtitles"].values()),
            )
            self.assertIn("未验证", preview_video["review_status"])

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
                publish(
                    manifest_path,
                    comparison_path,
                    root / "main-videos.json",
                    "https://example.com/release",
                )


if __name__ == "__main__":
    unittest.main()
