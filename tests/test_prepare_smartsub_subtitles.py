import tempfile
import unittest
from pathlib import Path

from scripts.prepare_smartsub_subtitles import prepare


class SmartSubSubtitlePreparationTests(unittest.TestCase):
    def test_creates_styled_ass_and_measured_report_from_matching_srt_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            english = root / "english.srt"
            chinese = root / "chinese.srt"
            output = root / "captions.ass"
            report_path = root / "report.json"
            english.write_text(
                "1\n00:00:01,000 --> 00:00:03,000\nHello, everybody.\n",
                encoding="utf-8",
            )
            chinese.write_text(
                "1\n00:00:01,000 --> 00:00:03,000\n大家好。\n",
                encoding="utf-8",
            )

            report = prepare(
                english,
                chinese,
                output,
                report_path,
                width=1920,
                height=1080,
                duration=4,
            )

            ass_text = output.read_text(encoding="utf-8")
            self.assertIn(r"{\rChinese\fs56\1c&H004DD8FF&}大家好。", ass_text)
            self.assertIn(
                r"{\rEnglish\fs45\1c&H00FFFFFF&}Hello, everybody.",
                ass_text,
            )
            self.assertEqual(report["input_srt_timings_match"], True)
            self.assertEqual(
                report["style"]["english_to_chinese_font_ratio"],
                0.804,
            )
            self.assertEqual(
                report["translation_accuracy"],
                "not_verified",
            )

    def test_rejects_mismatched_language_cue_timings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            english = root / "english.srt"
            chinese = root / "chinese.srt"
            english.write_text(
                "1\n00:00:01,000 --> 00:00:03,000\nHello.\n",
                encoding="utf-8",
            )
            chinese.write_text(
                "1\n00:00:01,100 --> 00:00:03,000\n你好。\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "mismatched language timings"):
                prepare(
                    english,
                    chinese,
                    root / "captions.ass",
                    root / "report.json",
                    width=1920,
                    height=1080,
                    duration=4,
                )


if __name__ == "__main__":
    unittest.main()
