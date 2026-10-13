import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from scripts.create_shorts import (
    AVAILABLE_STYLES,
    Cue,
    VIDEO_FILTER,
    load_highlights,
    parse_styles,
    parse_vtt,
    remove_rolling_overlap,
    filter_for,
    improve_translation,
    load_translation_cache,
    srt_time,
    subtitle_text,
    validate_highlights,
    validate_source_formats,
    write_srt,
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

    def test_requires_real_1080p_source_format(self):
        with self.assertRaisesRegex(RuntimeError, "refusing to upscale"):
            validate_source_formats(
                {"formats": [{"width": 1280, "height": 720}]}
            )
        self.assertEqual(
            validate_source_formats(
                {
                    "formats": [
                        {"width": 1280, "height": 720},
                        {"width": 1920, "height": 1080},
                        {"width": 3840, "height": 2160},
                    ]
                }
            ),
            (3840, 2160),
        )

    def test_highlights_need_distinct_intervals_and_reasons(self):
        highlights = [
            {
                "id": "topic-one",
                "start": 1,
                "end": 15,
                "title": "Topic one",
                "reason": "A clear claim and response.",
            },
            {
                "id": "topic-two",
                "start": 30,
                "end": 45,
                "title": "Topic two",
                "reason": "A distinct policy point.",
            },
        ]
        self.assertEqual(len(validate_highlights(highlights, 60)), 2)
        with self.assertRaisesRegex(ValueError, "At least two"):
            validate_highlights(highlights[:1], 60)
        with self.assertRaisesRegex(ValueError, "must be distinct"):
            validate_highlights(
                [highlights[0], {**highlights[1], "start": 1, "end": 15}],
                60,
            )
        with self.assertRaisesRegex(ValueError, "invalid time range"):
            validate_highlights(
                [{**highlights[0], "end": 61}, highlights[1]], 60
            )
        with self.assertRaisesRegex(ValueError, "invalid time range"):
            validate_highlights(
                [{**highlights[0], "start": float("nan")}, highlights[1]],
                60,
            )
        with self.assertRaisesRegex(ValueError, "editorial reason"):
            validate_highlights(
                [{**highlights[0], "reason": ""}, highlights[1]], 60
            )

    def test_loads_highlights_from_reviewed_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "highlights.json"
            path.write_text(
                '[{"id":"one","start":0,"end":5,"title":"One","reason":"A"},'
                '{"id":"two","start":10,"end":15,"title":"Two","reason":"B"}]',
                encoding="utf-8",
            )
            self.assertEqual(len(load_highlights(path, 20)), 2)

    def test_styles_are_explicit_and_validated(self):
        self.assertEqual(parse_styles("editorial,punchy"), ["editorial", "punchy"])
        self.assertEqual(len(AVAILABLE_STYLES), 10)
        self.assertEqual(
            parse_styles(",".join(AVAILABLE_STYLES)),
            list(AVAILABLE_STYLES),
        )
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            parse_styles("editorial,viral")
        with self.assertRaisesRegex(ValueError, "unique"):
            parse_styles("punchy,punchy")

    def test_writes_full_english_and_bilingual_transcripts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "full.en-zh.srt"
            write_srt(
                path,
                [
                    {
                        "start": 0,
                        "end": 3,
                        "english": "Good afternoon.",
                        "chinese": "下午好。",
                    }
                ],
                bilingual=True,
            )
            self.assertIn("Good afternoon.\n下午好。", path.read_text(encoding="utf-8-sig"))

    def test_translation_cache_parses_wrapped_srt_lines_by_language(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache_path = root / "translations.json"
            output_dir = root / "output"
            output_dir.mkdir()
            cache_path.write_text(
                json.dumps(
                    {
                        "Good afternoon, everybody.": "下午好，大家好。",
                        "of the systems": "的系统的",
                        "We're delivering systems that will hunt threats":
                            "before the crews can even see them.",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (output_dir / "sample.en-zh.srt").write_text(
                "1\n00:00:00,000 --> 00:00:05,000\n"
                "The quality of the systems that we produce\n"
                "and the strength of the industrial base.\n"
                "我们生产的系统的质量以及构建和维持\n"
                "这些系统的工业基础的强度。\n",
                encoding="utf-8",
            )

            cache = load_translation_cache(cache_path, output_dir)

        self.assertEqual(
            cache["The quality of the systems that we produce and "
                  "the strength of the industrial base."],
            "我们生产的系统的质量以及构建和维持这些系统的工业基础的强度。",
        )
        self.assertEqual(cache["Good afternoon, everybody."], "下午好，大家好。")
        self.assertNotIn("of the systems", cache)
        self.assertNotIn(
            "We're delivering systems that will hunt threats",
            cache,
        )

    def test_portrait_layout_preserves_full_source_frame(self):
        for style in ("editorial", "punchy"):
            video_filter = filter_for(style, Path("captions.ass"))
            foreground_filter = video_filter.rsplit("[fg]", 1)[1].split(
                "[foreground]", 1
            )[0]
            self.assertIn("scale=1080:-2", foreground_filter)
            self.assertNotIn("crop=", foreground_filter)
            self.assertNotIn("overlay=0:", video_filter)

    def test_styles_render_different_source_treatments(self):
        rendered_filters = {
            filter_for(style, Path("captions.ass"))
            for style in AVAILABLE_STYLES
        }
        self.assertEqual(len(rendered_filters), 10)
        self.assertIn("hue=s=0", filter_for("monochrome", Path("captions.ass")))
        self.assertIn("[fg]scale=1080:-2", filter_for("vivid", Path("captions.ass")))
        self.assertNotIn("C\\:/Windows/Fonts", filter_for("editorial", Path("captions.ass")))

    def test_high_resolution_selector_does_not_accept_narrow_1080p_formats(self):
        self.assertIn("width>=1920", VIDEO_FILTER)
        self.assertIn("height>=1080", VIDEO_FILTER)


if __name__ == "__main__":
    unittest.main()
