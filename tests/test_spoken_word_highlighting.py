import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from scripts.spoken_word_highlighting import (
    TimedWord,
    ass_highlighted_english_line,
    disabled_word_highlighting_status,
    load_reviewed_word_timings,
    validate_reviewed_word_timings,
)


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    english: str


class SpokenWordTimingTests(unittest.TestCase):
    def setUp(self):
        self.cues = [
            Cue(1.0, 2.0, "Hello, world."),
            Cue(3.0, 4.0, "Good morning."),
        ]
        self.data = {
            "schema_version": 1,
            "timing_source": "forced_alignment",
            "review": {
                "status": "verified",
                "checked_against_soundtrack": True,
                "evidence": "review/audio-check.json",
            },
            "cues": [
                {
                    "cue_index": 1,
                    "start": 1.0,
                    "end": 2.0,
                    "english": "Hello, world.",
                    "words": [
                        {"text": "Hello,", "start": 1.1, "end": 1.4},
                        {"text": "world.", "start": 1.5, "end": 1.9},
                    ],
                },
                {
                    "cue_index": 2,
                    "start": 3.0,
                    "end": 4.0,
                    "english": "Good morning.",
                    "words": [
                        {"text": "Good", "start": 3.1, "end": 3.4},
                        {"text": "morning.", "start": 3.5, "end": 3.9},
                    ],
                },
            ],
        }

    def test_accepts_complete_reviewed_audio_word_timings(self):
        timings, status = validate_reviewed_word_timings(self.data, self.cues)

        self.assertEqual(status["status"], "enabled")
        self.assertEqual(status["timing_source"], "forced_alignment")
        self.assertEqual(status["cue_count"], 2)
        self.assertEqual(
            timings,
            (
                (
                    TimedWord("Hello,", 1.1, 1.4),
                    TimedWord("world.", 1.5, 1.9),
                ),
                (
                    TimedWord("Good", 3.1, 3.4),
                    TimedWord("morning.", 3.5, 3.9),
                ),
            ),
        )

    def test_renders_each_aligned_word_with_a_timed_modest_scale_pulse(self):
        words, _status = validate_reviewed_word_timings(self.data, self.cues)

        rendered = ass_highlighted_english_line(
            "Hello, world.",
            words[0],
            self.cues[0].start,
            84,
            lambda text: text,
        )

        self.assertIn(
            r"{\rEnglish\fs84\1c&H00FFFFFF&\fscy100"
            r"\t(10,11,\fscy108)\t(39,40,\fscy100)}Hello,",
            rendered,
        )
        self.assertIn(
            r"\t(50,51,\fscy108)\t(89,90,\fscy100)}world.",
            rendered,
        )
        self.assertEqual(rendered.count(r"\fscy108"), 2)

    def test_renderer_fails_closed_when_wrapped_text_no_longer_aligns(self):
        result = ass_highlighted_english_line(
            "Hello, there.",
            (TimedWord("Hello,", 1.1, 1.4), TimedWord("world.", 1.5, 1.9)),
            1.0,
            84,
            lambda text: text,
        )
        self.assertIsNone(result)

    def test_missing_input_is_not_verified(self):
        timings, status = load_reviewed_word_timings(None, self.cues)
        self.assertIsNone(timings)
        self.assertEqual(status, {
            "status": "not_verified",
            "reason": "word_timing_input_not_provided",
        })

    def test_explicit_opt_out_is_disabled(self):
        self.assertEqual(
            disabled_word_highlighting_status(),
            {"status": "disabled", "reason": "disabled_by_operator"},
        )

    def test_malformed_json_is_not_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "word-timings.json"
            path.write_text("{invalid", encoding="utf-8")
            timings, status = load_reviewed_word_timings(path, self.cues)
        self.assertIsNone(timings)
        self.assertEqual(
            status["reason"],
            "word_timing_input_malformed_json",
        )

    def test_missing_soundtrack_review_evidence_fails_closed(self):
        data = self._copy_data()
        data["review"] = {
            "status": "verified",
            "checked_against_soundtrack": True,
        }
        self._assert_not_verified(data, "soundtrack_review_evidence_not_verified")

    def test_non_audio_timing_source_fails_closed(self):
        data = self._copy_data()
        data["timing_source"] = "estimated_from_text"
        self._assert_not_verified(data, "word_timing_source_not_audio_derived")

    def test_malformed_timing_source_fails_closed_without_raising(self):
        data = self._copy_data()
        data["timing_source"] = []
        self._assert_not_verified(data, "word_timing_source_not_audio_derived")

    def test_boolean_schema_version_is_not_accepted_as_version_one(self):
        data = self._copy_data()
        data["schema_version"] = True
        self._assert_not_verified(data, "word_timing_schema_invalid")

    def test_incomplete_cue_coverage_fails_closed(self):
        data = self._copy_data()
        data["cues"].pop()
        self._assert_not_verified(data, "word_timings_incomplete_cue_coverage")

    def test_incomplete_word_coverage_fails_closed(self):
        data = self._copy_data()
        data["cues"][0]["words"].pop()
        self._assert_not_verified(data, "word_timings_incomplete_word_coverage")

    def test_out_of_order_word_timing_fails_closed(self):
        data = self._copy_data()
        data["cues"][0]["words"][1]["start"] = 1.3
        self._assert_not_verified(
            data,
            "word_timings_out_of_order_or_overlapping",
        )

    def test_word_text_mismatch_fails_closed(self):
        data = self._copy_data()
        data["cues"][0]["words"][0]["text"] = "Hi,"
        self._assert_not_verified(data, "word_timing_text_alignment_mismatch")

    def test_cue_text_mismatch_fails_closed(self):
        data = self._copy_data()
        data["cues"][0]["english"] = "Hi, world."
        self._assert_not_verified(
            data,
            "word_timing_cue_text_or_alignment_mismatch",
        )

    def test_cue_order_mismatch_fails_closed(self):
        data = self._copy_data()
        data["cues"][0]["cue_index"] = 2
        self._assert_not_verified(data, "word_timing_cue_order_invalid")

    def test_invalid_numeric_timing_fails_closed(self):
        data = self._copy_data()
        data["cues"][0]["words"][0]["start"] = float("nan")
        self._assert_not_verified(data, "word_timing_outside_cue_or_invalid")

    def test_extreme_integer_timing_fails_closed(self):
        data = self._copy_data()
        data["cues"][0]["words"][0]["start"] = 10 ** 1000
        self._assert_not_verified(data, "word_timing_outside_cue_or_invalid")

    def test_timing_below_ass_precision_fails_closed(self):
        data = self._copy_data()
        data["cues"][0]["words"][0]["end"] = 1.101
        self._assert_not_verified(data, "word_timing_below_ass_precision")

    def test_word_too_short_for_ass_scale_pulse_fails_closed(self):
        data = self._copy_data()
        data["cues"][0]["words"][0]["end"] = 1.12
        self._assert_not_verified(data, "word_timing_below_ass_precision")

    def test_missing_file_is_not_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.json"
            timings, status = load_reviewed_word_timings(path, self.cues)
        self.assertIsNone(timings)
        self.assertEqual(status["reason"], "word_timing_input_missing")

    def _copy_data(self):
        return json.loads(json.dumps(self.data))

    def _assert_not_verified(self, data, reason):
        timings, status = validate_reviewed_word_timings(data, self.cues)
        self.assertIsNone(timings)
        self.assertEqual(status["status"], "not_verified")
        self.assertEqual(status["reason"], reason)


if __name__ == "__main__":
    unittest.main()
