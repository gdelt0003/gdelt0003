import tempfile
import unittest
from pathlib import Path

from scripts.generate_default_video_batch import (
    Clip,
    Cue,
    build_clips,
    merge_bilingual_cues,
    parse_timestamp,
    read_vtt,
    srt_timestamp,
)


class SubtitleProcessingTests(unittest.TestCase):
    def test_parse_timestamp_accepts_webvtt_hours(self):
        self.assertEqual(parse_timestamp("00:43:51.100"), 2631.1)

    def test_read_vtt_strips_tags_and_decodes_entities(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captions.vtt"
            path.write_text(
                "WEBVTT\n\n00:00:01.000 --> 00:00:02.500\n"
                "<c>Xi &amp; China</c>\n",
                encoding="utf-8",
            )
            self.assertEqual(
                read_vtt(path),
                [Cue(1.0, 2.5, "Xi & China")],
            )

    def test_highlight_selection_requires_china_or_xi_and_caps_duration(self):
        english = [
            Cue(90, 95, "Welcome to the meeting."),
            Cue(100, 104, "President Xi Jinping will speak with China."),
            Cue(300, 304, "A separate topic unrelated to the requested keywords."),
        ]
        chinese = [
            Cue(90, 95, "欢迎参加会议。"),
            Cue(100, 104, "习近平主席将与中国进行会谈。"),
        ]

        clips = build_clips(english, chinese)

        self.assertEqual(len(clips), 1)
        self.assertEqual(clips[0], Clip(88, 143, "中美与习近平现场对话"))
        self.assertLessEqual(clips[0].end - clips[0].start, 55)

    def test_bilingual_captions_are_merged_and_shifted_to_clip_time(self):
        clip = Clip(88, 143, "特朗普谈中国")
        rows = merge_bilingual_cues(
            clip,
            [Cue(100, 102, "President Trump mentioned China.")],
            [Cue(100.1, 102.1, "特朗普提到了中国。")],
        )
        self.assertEqual(rows, [(12, 14, "President Trump mentioned China.\\N特朗普提到了中国。")])

    def test_srt_timestamps_use_milliseconds(self):
        self.assertEqual(srt_timestamp(65.125), "00:01:05,125")


if __name__ == "__main__":
    unittest.main()
