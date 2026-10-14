import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.create_comparison_frame_review import create_review


class ComparisonFrameReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.manifest_path = self.root / "manifest.json"
        self.video_path = self.root / "rendered.mp4"
        self.vtt_path = self.root / "captions.vtt"
        self.output_dir = self.root / "review"
        self.video_path.write_bytes(b"test placeholder")
        self.manifest_path.write_text(
            json.dumps(
                {
                    "source_video": "pvXbHQrIvTw-source.mp4",
                    "input_size_bytes": 262338614,
                    "input_sha256": (
                        "33bf25655531190a2d73510649b780b21343481b308f993c107d87053e067171"
                    ),
                    "source_match_status": "operator_attested_exact_event",
                    "duration_seconds": 12.0,
                    "subtitle_cues": 3,
                    "quality_checks": {
                        "structural_checks": "passed",
                        "bilingual_cue_sync": {"status": "passed"},
                        "subtitle_readability": {
                            "english_reading_speed_over_20_cps_cues": [2],
                            "chinese_reading_speed_over_10_cps_cues": [2],
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        self.vtt_path.write_text(
            "WEBVTT\n\n"
            "1\n00:00:01.000 --> 00:00:02.000\n第一句\nFirst phrase.\n\n"
            "2\n00:00:04.000 --> 00:00:06.000\n第二句\nSecond phrase.\n\n"
            "3\n00:00:09.000 --> 00:00:10.000\n第三句\nThird phrase.\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def probe_video(self, *args, **kwargs):
        return json.dumps(
            {
                "format": {"duration": "12.0", "size": "12345"},
                "streams": [
                    {"codec_type": "video", "width": 1920, "height": 1080},
                    {"codec_type": "audio"},
                ],
            }
        )

    @staticmethod
    def extract_frame(command, check):
        Path(command[-1]).write_bytes(b"frame")

    def test_review_includes_representative_and_every_flagged_cue_and_stays_blocked(self):
        with (
            patch(
                "scripts.create_comparison_frame_review.subprocess.check_output",
                side_effect=self.probe_video,
            ),
            patch(
                "scripts.create_comparison_frame_review.subprocess.run",
                side_effect=self.extract_frame,
            ) as extract,
        ):
            report = create_review(
                self.manifest_path,
                self.video_path,
                self.vtt_path,
                self.output_dir,
                "38523026469",
            )

        self.assertEqual(report["release_status"], "blocked")
        self.assertEqual(report["frame_count"], 6)
        flagged = [frame for frame in report["frames"] if frame["flags"]]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(
            set(flagged[0]["flags"]),
            {"english_over_20_cps", "chinese_over_10_cps"},
        )
        self.assertEqual(extract.call_count, 6)
        self.assertEqual(
            report["checks"]["translation_accuracy"]["status"],
            "not_verified",
        )
        self.assertTrue(
            report["checks"]["source_audio_and_asr_accuracy"]["blocking"]
        )
        self.assertTrue((self.output_dir / "release-report.json").is_file())
        review_html = (self.output_dir / "frame-review.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("Release blocked", review_html)
        self.assertIn("cue-002", review_html)

    def test_rejects_artifact_with_wrong_source_fingerprint_before_probing(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["input_sha256"] = "0" * 64
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        with patch(
            "scripts.create_comparison_frame_review.subprocess.check_output"
        ) as probe:
            with self.assertRaisesRegex(ValueError, "input_sha256 mismatch"):
                create_review(
                    self.manifest_path,
                    self.video_path,
                    self.vtt_path,
                    self.output_dir,
                    "38523026469",
                )
        probe.assert_not_called()

    def test_rejects_speed_flag_referencing_nonexistent_cue(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["quality_checks"]["subtitle_readability"][
            "english_reading_speed_over_20_cps_cues"
        ] = [4]
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        with (
            patch(
                "scripts.create_comparison_frame_review.subprocess.check_output",
                side_effect=self.probe_video,
            ),
            patch(
                "scripts.create_comparison_frame_review.subprocess.run"
            ) as extract,
        ):
            with self.assertRaisesRegex(ValueError, "refers to a missing cue"):
                create_review(
                    self.manifest_path,
                    self.video_path,
                    self.vtt_path,
                    self.output_dir,
                    "38523026469",
                )
        extract.assert_not_called()


if __name__ == "__main__":
    unittest.main()
