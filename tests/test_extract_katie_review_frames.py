import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.extract_katie_review_frames import (
    extract_review_frames,
    select_review_times,
)


class KatieReviewFrameSamplingTests(unittest.TestCase):
    def test_selects_start_middle_end_and_densest_bilingual_caption(self):
        subtitle = (
            "1\n00:00:00,000 --> 00:00:04,000\n大家好。\nHello.\n\n"
            "2\n00:07:10,000 --> 00:07:11,000\n"
            "这是一条字幕文字密度很高的双语样例。\n"
            "This is a very dense bilingual sample.\n\n"
            "3\n00:14:22,000 --> 00:14:26,000\n再见。\nGoodbye.\n"
        )

        samples = select_review_times(subtitle, 866)

        self.assertEqual(
            [sample["label"] for sample in samples],
            ["start", "middle", "end", "densest_caption"],
        )
        self.assertEqual(
            [sample["time_seconds"] for sample in samples],
            [2.0, 433.0, 864.0, 430.5],
        )

    def test_rejects_missing_cues_and_invalid_duration(self):
        with self.assertRaisesRegex(ValueError, "No valid bilingual"):
            select_review_times("", 866)
        with self.assertRaisesRegex(ValueError, "greater than one"):
            select_review_times("1\n00:00:00,000 --> 00:00:02,000\n你好\nHello", 1)

    def test_writes_frame_sampling_report_without_claiming_manual_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "render.mp4"
            video.write_bytes(b"rendered")
            subtitle = root / "bilingual.srt"
            subtitle.write_text(
                "1\n00:00:00,000 --> 00:00:04,000\n大家好。\nHello.\n",
                encoding="utf-8",
            )
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"duration_seconds": 20}), encoding="utf-8")
            output_dir = root / "frames"

            def fake_ffmpeg(command, check):
                self.assertTrue(check)
                Path(command[-1]).write_bytes(b"sample-frame")

            with patch(
                "scripts.extract_katie_review_frames.subprocess.run",
                side_effect=fake_ffmpeg,
            ):
                samples = extract_review_frames(
                    video,
                    subtitle,
                    manifest,
                    output_dir,
                )

            report = json.loads(
                (output_dir / "sampling-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(samples), 3)
            self.assertEqual(samples[0]["also_labels"], ["densest_caption"])
            self.assertEqual(report["status"], "sampled_not_reviewed")
            self.assertEqual(report["manual_visual_review"], "not_verified")
            self.assertTrue(
                all((output_dir / item["file"]).is_file() for item in samples)
            )


if __name__ == "__main__":
    unittest.main()
