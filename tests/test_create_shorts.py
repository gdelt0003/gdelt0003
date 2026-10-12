import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from scripts.create_shorts import (
    Cue,
    parse_vtt,
    remove_rolling_overlap,
    improve_translation,
    srt_time,
    subtitle_text,
)


class CaptionTests(unittest.TestCase):
    def test_parse_and_remove_rolling_caption_overlap(self):
        content = """WEBVTT

00:00:01.000 --> 00:00:03.000
The Navy will build more ships

00:00:02.500 --> 00:00:04.000
The Navy will build more ships for the fleet.
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captions.vtt"
            path.write_text(content, encoding="utf-8")
            cues = remove_rolling_overlap(parse_vtt(path))

        self.assertEqual(
            [(cue.start, cue.end, cue.text) for cue in cues],
            [
                (1.0, 3.0, "The Navy will build more ships"),
                (2.5, 4.0, "for the fleet."),
            ],
        )

    def test_corrects_and_deduplicates_rolling_asr_cues(self):
        cues = remove_rolling_overlap(
            [
                Cue(1.0, 2.0, "More hulls through our prime yards at better"),
                Cue(2.0, 3.0, "holes through our prime yards at better margin"),
            ]
        )
        self.assertEqual(
            [cue.text for cue in cues],
            ["More hulls through our prime yards at better", "margin"],
        )

    def test_subtitle_time_format(self):
        self.assertEqual(srt_time(65.432), "00:01:05,432")

    def test_preserves_project_terms_in_machine_translation(self):
        self.assertEqual(
            improve_translation("阿森纳2攻击生产问题，每年生产小时"),
            "Arsenal 2解决生产问题，每年生产工时",
        )

    def test_translates_complete_sentences_not_rolling_fragments(self):
        cues = [
            Cue(10.0, 12.0, "Arsenal 2 will help us attack production"),
            Cue(12.0, 15.0, "bottlenecks with the footprint to add up"),
            Cue(15.0, 18.0, "to 9 million production hours per year."),
        ]
        with patch(
            "scripts.create_shorts.translate",
            side_effect=lambda text, cache: f"译文：{text}",
        ):
            subtitles = subtitle_text(cues, 10.0, 18.0, {})

        self.assertEqual(len(subtitles), 1)
        self.assertEqual(
            subtitles[0]["english"],
            "Arsenal 2 will help us attack production\n"
            "bottlenecks with the footprint to add up to 9\n"
            "million production hours per year.",
        )
        self.assertEqual(subtitles[0]["start"], 0.0)
        self.assertEqual(subtitles[0]["end"], 8.0)


if __name__ == "__main__":
    unittest.main()
