import tempfile
import unittest
from pathlib import Path

from scripts.process_full_video import (
    Cue,
    ass_escape,
    ass_time,
    bilingual_srt_text,
    reflow_cues,
    read_srt,
    srt_text,
    timestamp,
    vtt_from_bilingual_srt,
    write_ass,
)


class FullVideoSubtitleTests(unittest.TestCase):
    def test_timestamp_formats_hours_and_milliseconds(self):
        self.assertEqual(timestamp(3661.234, decimal=","), "01:01:01,234")
        self.assertEqual(timestamp(3661.234, decimal="."), "01:01:01.234")

    def test_writes_separate_and_bilingual_srt(self):
        cues = [Cue(1.25, 3.5, "Hello, world.", "你好，世界。")]
        self.assertIn(
            "00:00:01,250 --> 00:00:03,500\nHello, world.",
            srt_text(cues, "en"),
        )
        self.assertIn(
            "00:00:01,250 --> 00:00:03,500\n"
            "你好，世界。\nHello, world.",
            bilingual_srt_text(cues),
        )

    def test_converts_bilingual_srt_to_vtt(self):
        content = bilingual_srt_text(
            [Cue(0, 2, "Welcome, everyone.", "欢迎，大家。")]
        )
        self.assertTrue(vtt_from_bilingual_srt(content).startswith("WEBVTT\n\n"))
        self.assertIn("00:00:00.000 --> 00:00:02.000", vtt_from_bilingual_srt(content))
        self.assertIn("欢迎，大家。\nWelcome, everyone.", vtt_from_bilingual_srt(content))

    def test_writes_escaped_bilingual_ass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captions.ass"
            write_ass(
                path,
                [Cue(0, 2.5, r"Text {one}", "中文")],
                1920,
                1080,
            )
            content = path.read_text(encoding="utf-8")
        self.assertIn(r"{\rChinese}中文\N{\rEnglish}Text \{one\}", content)
        self.assertIn("0:00:00.00,0:00:02.50", content)
        self.assertIn("Style: Chinese,Noto Sans CJK SC,56,&H004DD8FF", content)
        self.assertIn("Style: English,Noto Sans CJK SC,50,&H00FFFFFF", content)
        self.assertIn(",216,1\n", content)
        self.assertIn("WrapStyle: 0", content)

    def test_reflows_long_bilingual_cues_without_changing_total_timing(self):
        original = Cue(
            0,
            42.39,
            "The quality of the systems that we produce and the strength "
            "of the industrial base that constructs and sustains those systems.",
            "我们生产的系统的质量以及构建和维持这些系统的工业基础的强度。",
        )
        reflowed = reflow_cues([original], 1920, 1080)

        self.assertGreater(len(reflowed), 1)
        self.assertEqual(reflowed[0].start, original.start)
        self.assertEqual(reflowed[-1].end, original.end)
        self.assertTrue(
            all(
                cue.end - cue.start <= 7.01
                for cue in reflowed
            )
        )
        self.assertTrue(
            all(left.end == right.start for left, right in zip(reflowed, reflowed[1:]))
        )
        self.assertEqual(
            " ".join(cue.english for cue in reflowed),
            original.english,
        )
        self.assertEqual(
            "".join(cue.chinese for cue in reflowed),
            original.chinese,
        )

    def test_reflow_balances_timing_instead_of_overholding_short_chunks(self):
        original = Cue(
            1336.28,
            1362.42,
            "Ladies and gentlemen, the Secretary of War, the Honorable Exeter.",
            "女士们，先生们，战争部长，尊敬的埃克塞特。",
        )
        reflowed = reflow_cues([original], 1920, 1080)

        self.assertGreater(len(reflowed), 1)
        self.assertTrue(
            all(cue.end - cue.start <= 7.01 for cue in reflowed)
        )
        self.assertTrue(
            all(left.end == right.start for left, right in zip(reflowed, reflowed[1:]))
        )
        self.assertEqual(
            " ".join(cue.english for cue in reflowed),
            original.english,
        )
        self.assertIn(
            "the Secretary of War,",
            [cue.english for cue in reflowed],
        )

    def test_reflow_splits_long_lines_before_wrapping(self):
        original = Cue(
            0,
            6.2,
            "Please welcome the Co-Founder and Chief Executive Officer "
            "of Anduril Industries, Brian Schimpf.",
            "欢迎Anduril Industries联合创始人兼首席执行官Brian Schimpf。",
        )
        reflowed = reflow_cues([original], 1920, 1080)

        self.assertGreater(len(reflowed), 1)
        self.assertTrue(
            all(len(cue.english) <= 48 for cue in reflowed)
        )
        self.assertTrue(all(cue.chinese for cue in reflowed))
        self.assertEqual(
            " ".join(cue.english for cue in reflowed),
            original.english,
        )
        self.assertTrue(
            any("Industries" in cue.chinese for cue in reflowed)
        )
        self.assertTrue(any("Schimpf" in cue.chinese for cue in reflowed))

    def test_reflow_keeps_short_english_chunks_synchronized(self):
        reflowed = reflow_cues(
            [Cue(0, 3, "Hello world.", "你好，世界。")],
            1920,
            1080,
        )
        self.assertEqual(len(reflowed), 1)
        self.assertEqual(reflowed[0].chinese, "你好，世界。")
        self.assertEqual(reflowed[0].english, "Hello world.")

    def test_reads_srt_cue_times_and_multiline_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captions.srt"
            path.write_text(
                "1\n00:00:01,250 --> 00:00:03,500\n"
                "A caption\non two lines\n",
                encoding="utf-8",
            )
            self.assertEqual(
                read_srt(path),
                [(1.25, 3.5, "A caption\non two lines")],
            )

    def test_ass_escapes_override_characters(self):
        self.assertEqual(ass_escape(r"a\b {c}"), r"a\\b \{c\}")
        self.assertEqual(ass_time(65.432), "0:01:05.43")


if __name__ == "__main__":
    unittest.main()
