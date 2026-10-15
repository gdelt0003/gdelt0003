import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from scripts.generate_default_video_batch import (
    Clip,
    Cue,
    SpeakerTurn,
    ass_color,
    assign_speakers,
    build_clips,
    merge_bilingual_cues,
    parse_timestamp,
    read_autosubs_speakers,
    read_vtt,
    require_cloud_diarization,
    srt_timestamp,
    write_ass,
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

    def test_read_autosubs_segments_preserves_labeled_turns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transcript.json"
            path.write_text(
                '{"segments": ['
                '{"start": 0.5, "end": 1.5, "speaker_id": "1"},'
                '{"start": 1.5, "end": 2.0, "speaker_id": null},'
                '{"start": 2.0, "end": 3.0, "speaker_id": "?"}'
                ']}',
                encoding="utf-8",
            )
            self.assertEqual(
                read_autosubs_speakers(path),
                [SpeakerTurn(0.5, 1.5, "1")],
            )

    def test_read_autosubs_rejects_non_object_payload_and_invalid_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transcript.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "must be an object"):
                read_autosubs_speakers(path)

            path.write_text(
                '{"segments": [{"start": "NaN", "end": 2, "speaker_id": "1"}]}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "Invalid interval"):
                read_autosubs_speakers(path)

    def test_diarization_is_restricted_to_github_actions(self):
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "false"}):
            with self.assertRaisesRegex(RuntimeError, "GitHub-hosted"):
                require_cloud_diarization(True)
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}):
            require_cloud_diarization(True)
        require_cloud_diarization(False)

    def test_assign_speakers_uses_greatest_overlap_and_leaves_ties_unlabeled(self):
        rows = [
            (0.0, 2.0, "First turn"),
            (2.0, 4.0, "Overlapping turn"),
            (4.0, 5.0, "No speaker coverage"),
        ]
        turns = [
            SpeakerTurn(0.0, 1.5, "1"),
            SpeakerTurn(1.5, 2.0, "2"),
            SpeakerTurn(2.0, 3.0, "1"),
            SpeakerTurn(3.0, 4.0, "2"),
        ]
        self.assertEqual(
            assign_speakers(rows, turns),
            [
                (0.0, 2.0, "First turn", "1"),
                (2.0, 4.0, "Overlapping turn", None),
                (4.0, 5.0, "No speaker coverage", None),
            ],
        )

    def test_ass_color_converts_rgb_to_ass_bgr(self):
        self.assertEqual(ass_color("#40C4FF"), "&H00FFC440&")

    def test_write_ass_colors_speaker_rows_and_keeps_unknown_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captions.ass"
            write_ass(
                path,
                Clip(0, 10, "Highlight"),
                [
                    (0.0, 2.0, "Speaker one", "1"),
                    (2.0, 4.0, "Unlabeled"),
                ],
                1080,
                1920,
            )
            output = path.read_text(encoding="utf-8")
            self.assertIn(r"{\c&H00FFC440&}Speaker one", output)
            self.assertIn(",,Unlabeled", output)


if __name__ == "__main__":
    unittest.main()
