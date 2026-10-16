import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pysubs2

from scripts.process_full_video import (
    Cue,
    KATIE_SUBTITLE_LAYOUT,
    ROSE_GARDEN_SUBTITLE_LAYOUT,
    _estimated_text_width,
    _rose_caption_geometry,
    _rose_garden_font_sizes_for_region,
    _rose_garden_wrap_limits,
    _wrap_chinese,
    _wrap_chinese_to_width,
    _wrap_english,
    _wrap_english_to_width,
    _katie_wrap_limits,
    _wrap_katie_chinese,
    _wrap_katie_english,
    ass_escape,
    ass_time,
    bilingual_srt_text,
    copy_review_evidence,
    merge_sentence_fragments,
    reflow_rose_garden_cues,
    reflow_cues,
    read_srt,
    srt_text,
    timestamp,
    validate_asset_prefix,
    parse_source_graphics_regions,
    require_trusted_mask_review,
    rose_caption_region,
    validate_rose_caption_placement,
    validate_release_asset_size,
    vtt_from_bilingual_srt,
    verify_cues,
    write_ass,
)
from scripts.verify_rose_garden_review import user_still_source_graphics_regions
from scripts.spoken_word_highlighting import TimedWord


class FullVideoSubtitleTests(unittest.TestCase):
    ROSE_SOURCE_GRAPHICS = [
        {
            "label": "synthetic-source-lower-third-test-fixture",
            "human_verified": True,
            "x": 0.10,
            "y": 0.68,
            "width": 0.80,
            "height": 0.30,
        }
    ]

    def test_unverified_still_draft_bypasses_signature_but_not_fixed_source_checks(self):
        with patch(
            "scripts.verify_rose_garden_review.file_sha256_and_size",
            return_value=(
                "e0b04fb669fd0d09f1492de6a3160bb3b6dae2e3e396be77372f4b5635da5f73",
                1_030_142_647,
            ),
        ):
            result = require_trusted_mask_review(
                "mask-lower-third",
                source_path=Path("pinned-test-source.mp4"),
                source_width=1920,
                source_height=1080,
                source_duration=2193.261,
                source_frame_review_record_json="{}",
                source_frame_review_signature="",
                source_graphics_regions_json="[]",
                dispatch_actor="publisher",
                frame_review_mode="unverified-review-draft",
            )
        self.assertEqual(
            result,
            {
                "source_frame_review": "pending",
                "production_bbox_input": "false",
                "measurement_status": "unverified_still_estimate",
            },
        )
        with self.assertRaisesRegex(RuntimeError, "fixed user-still estimate"):
            require_trusted_mask_review(
                "mask-lower-third",
                source_path=Path("pinned-test-source.mp4"),
                source_width=1920,
                source_height=1080,
                source_duration=2193.261,
                source_frame_review_record_json="{}",
                source_frame_review_signature="",
                source_graphics_regions_json=json.dumps(self.ROSE_SOURCE_GRAPHICS),
                dispatch_actor="publisher",
                frame_review_mode="unverified-review-draft",
            )

    def test_direct_script_import_can_load_rose_review_validator(self):
        repo_root = Path(__file__).resolve().parents[1]
        script = """
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "scripts"))
import process_full_video
import verify_rose_garden_review
assert process_full_video._rose_garden_review_module() is verify_rose_garden_review
regions = verify_rose_garden_review.user_still_source_graphics_regions(1920, 1080)
report = process_full_video.verify_cues(
    [process_full_video.Cue(0, 3, "A sentence.", "一句话。")],
    duration=10,
    width=1920,
    height=1080,
    layout_profile=process_full_video.ROSE_GARDEN_SUBTITLE_LAYOUT,
    caption_position="mask-lower-third",
    source_graphics_regions=regions,
    occlusion_exception_authorized=True,
    mask_padding_px_per_edge=2,
    allow_unverified_estimate=True,
)
assert (
    report["subtitle_readability"]["source_graphics_review"]["measurement_status"]
    == "unverified_still_estimate"
)
verify_rose_garden_review.SOURCE_SHA256 = "expected"
verify_rose_garden_review.SOURCE_SIZE_BYTES = 1
verify_rose_garden_review.file_sha256_and_size = lambda _: ("expected", 1)
verify_rose_garden_review.user_still_source_graphics_regions = lambda *_: []
measurement = (
    process_full_video._rose_garden_review_module()
    .user_provided_still_measurement()
)
assert measurement["measurement_status"] == "unverified_still_estimate"
result = process_full_video.require_trusted_mask_review(
    "mask-lower-third",
    source_path=Path("fixture.mp4"),
    source_width=1920,
    source_height=1080,
    source_duration=1.0,
    source_frame_review_record_json="{}",
    source_frame_review_signature="",
    source_graphics_regions_json="[]",
    dispatch_actor="test",
    frame_review_mode="unverified-review-draft",
)
assert result["source_frame_review"] == "pending"
assert result["production_bbox_input"] == "false"
source = Path(sys.argv[1], "scripts", "process_full_video.py")
assert "from scripts." not in source.read_text(encoding="utf-8")
"""
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(
                [sys.executable, "-c", script, str(repo_root)],
                cwd=temp,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_release_asset_size_guard_accepts_limit_and_rejects_oversize(self):
        validate_release_asset_size(1_950_000_000)
        with self.assertRaisesRegex(RuntimeError, "too large for a GitHub Release asset"):
            validate_release_asset_size(1_950_000_001)

    def test_validates_safe_asset_prefix_for_reusable_renderer(self):
        self.assertEqual(
            validate_asset_prefix("pvXbHQrIvTw"),
            "pvXbHQrIvTw",
        )
        for unsafe in ("../outside", "folder/name", ""):
            with self.subTest(unsafe=unsafe):
                with self.assertRaisesRegex(ValueError, "filename-safe"):
                    validate_asset_prefix(unsafe)

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
            rendered = pysubs2.load(str(path), encoding="utf-8")
        self.assertIn(
            r"{\rChinese\fs56\1c&H004DD8FF&}中文"
            r"\N{\rEnglish\fs84\1c&H00FFFFFF&}Text \{one\}",
            content,
        )
        self.assertIn("0:00:00.00,0:00:02.50", content)
        self.assertIn("Style: Chinese,Noto Sans CJK SC,56,&H004DD8FF", content)
        self.assertIn("Style: English,Noto Sans CJK SC,84,&H00FFFFFF", content)
        self.assertIn("&H70000000,-1,0,0,0,100,100,0,0,3,6,0,2", content)
        self.assertIn(",211,211,194,1", content)
        self.assertIn(",194,1\n", content)
        self.assertIn("WrapStyle: 0", content)
        self.assertEqual(rendered.styles["English"].fontsize, 84)
        self.assertEqual(rendered.styles["Chinese"].fontsize, 56)
        self.assertEqual(len(rendered.events), 1)
        self.assertIn(r"{\rEnglish\fs84\1c&H00FFFFFF&}", rendered.events[0].text)

    def test_default_wrapping_fails_closed_instead_of_merging_or_truncating(self):
        with self.assertRaisesRegex(ValueError, "more than 2 lines"):
            _wrap_english("one two three four five six", 8)
        with self.assertRaisesRegex(ValueError, "token exceeds"):
            _wrap_english("unbrokenverylongtoken", 8)
        with self.assertRaisesRegex(ValueError, "more than 2 lines"):
            _wrap_chinese("甲乙丙丁戊己庚辛壬癸子丑寅卯", 4)

    def test_rose_garden_tight_mask_records_exact_bbox_and_complete_text(self):
        cue = Cue(
            1,
            5,
            "The President welcomed every guest in the Rose Garden.",
            "总统欢迎玫瑰园的每一位来宾，并在午餐会上致辞。",
        )
        chinese_font, english_font, _max_chinese, _max_english = (
            _rose_garden_wrap_limits(1920, 1080)
        )
        mask = rose_caption_region(
            1920, 1080, "mask-lower-third", self.ROSE_SOURCE_GRAPHICS, 2
        )
        self.assertEqual(
            (mask["left"], mask["top"], mask["right"], mask["bottom"]),
            (190, 732, 1730, 1060),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rose-captions.ass"
            write_ass(
                path,
                [cue],
                1920,
                1080,
                layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
                caption_position="mask-lower-third",
                source_graphics_regions=self.ROSE_SOURCE_GRAPHICS,
                occlusion_exception_authorized=True,
                mask_padding_px_per_edge=2,
            )
            content = path.read_text(encoding="utf-8")
            rendered = pysubs2.load(str(path), encoding="utf-8")

        self.assertIn("WrapStyle: 2", content)
        self.assertEqual(len(rendered.events), 2)
        self.assertIn(r"\p1", rendered.events[0].text)
        self.assertIn(r"\1a&H00&", rendered.events[0].text)
        self.assertIn(f"\\pos({mask['left']},{mask['top']})", rendered.events[0].text)
        self.assertIn(
            f"l {mask['width']} {mask['height']}",
            rendered.events[0].text,
        )
        self.assertIn(r"\pos(960,", rendered.events[1].text)
        self.assertTrue(
            all(word in rendered.events[1].text for word in cue.english.split())
        )
        self.assertTrue(
            all(character in rendered.events[1].text for character in cue.chinese)
        )
        self.assertEqual((chinese_font, english_font), (35, 28))
        self.assertEqual(english_font / chinese_font, 0.8)
        self.assertEqual(rendered.styles["English"].fontsize, english_font)
        self.assertEqual(rendered.styles["Chinese"].fontsize, chinese_font)
        english_lines = _wrap_english_to_width(
            cue.english,
            min(round(1920 * 0.68), mask["width"] - 4),
            english_font,
        )
        chinese_lines = _wrap_chinese_to_width(
            cue.chinese,
            min(round(1920 * 0.68), mask["width"] - 4),
            chinese_font,
        )
        self.assertLessEqual(len(english_lines), 2)
        self.assertLessEqual(len(chinese_lines), 2)
        geometry = _rose_caption_geometry(
            english_lines,
            chinese_lines,
            width=1920,
            height=1080,
            english_font=english_font,
            chinese_font=chinese_font,
            position="mask-lower-third",
            source_graphics_regions=self.ROSE_SOURCE_GRAPHICS,
            mask_padding_px_per_edge=2,
        )
        self.assertLessEqual(
            max(_estimated_text_width(line, english_font) for line in english_lines),
            mask["width"] - 4,
        )
        self.assertLessEqual(
            max(_estimated_text_width(line, chinese_font) for line in chinese_lines),
            mask["width"] - 4,
        )
        self.assertLessEqual(
            geometry["estimated_text_height"],
            geometry["region_height"],
        )
        report = verify_cues(
            [cue],
            duration=10,
            width=1920,
            height=1080,
            layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
            caption_position="mask-lower-third",
            caption_safe_region_reviewed=True,
            source_graphics_regions=self.ROSE_SOURCE_GRAPHICS,
            occlusion_exception_authorized=True,
            mask_padding_px_per_edge=2,
        )
        readability = report["subtitle_readability"]
        self.assertEqual(readability["layout_configuration"], "passed")
        self.assertEqual(readability["caption_region_validation"], "not_verified")
        self.assertEqual(readability["caption_position_review"], "pending")
        self.assertEqual(readability["source_graphics_review"]["status"], "not_verified")
        self.assertEqual(readability["source_graphics_review"]["review_status"], "pending")
        self.assertFalse(readability["source_graphics_review"]["production_bbox_input"])
        self.assertEqual(readability["caption_region_height_percent"], 30.4)
        self.assertEqual(readability["horizontal_safe_width_percent"], 68)
        self.assertEqual(readability["max_lines_per_language"], 2)
        self.assertEqual(readability["english_font_px"], 28)
        self.assertEqual(readability["chinese_font_px"], 35)
        self.assertEqual(readability["english_to_chinese_size_ratio"], 0.8)
        self.assertEqual(readability["visual_frame_review"], "not_verified")
        self.assertEqual(readability["caption_band_occlusion"]["visual_review"], "pending")
        self.assertEqual(
            readability["caption_band_occlusion"]["source_banner_bbox_px"],
            {"left": 192, "top": 734, "right": 1728, "bottom": 1058, "width": 1536, "height": 324},
        )
        self.assertEqual(
            readability["caption_band_occlusion"]["padding_px_per_edge"], 2
        )
        self.assertEqual(
            readability["caption_band_occlusion"]["status_label"],
            "masked_not_clean",
        )
        self.assertEqual(readability["rose_source_evidence"]["event_match"], "pending")

    def test_rose_garden_ass_geometry_allows_centisecond_timestamp_rounding(self):
        cue = Cue(1.234, 3.456, "A complete English sentence.", "完整的一句话。")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rose-captions.ass"
            write_ass(
                path,
                [cue],
                1920,
                1080,
                layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
            )
            rendered = pysubs2.load(str(path), encoding="utf-8")

        self.assertEqual(rendered.events[0].start, 1230)
        self.assertEqual(rendered.events[0].end, 3460)

    def test_user_still_mask_adapts_font_to_fit_two_bilingual_lines(self):
        source_regions = user_still_source_graphics_regions(1920, 1080)
        region = rose_caption_region(
            1920,
            1080,
            "mask-lower-third",
            source_regions,
            2,
            allow_unverified_estimate=True,
        )
        chinese_font, english_font = _rose_garden_font_sizes_for_region(
            *_rose_garden_wrap_limits(1920, 1080)[:2],
            region["height"],
        )
        self.assertEqual(
            (
                region["left"],
                region["top"],
                region["right"],
                region["bottom"],
                region["width"],
                region["height"],
            ),
            (66, 883, 1852, 1022, 1786, 139),
        )
        self.assertEqual((chinese_font, english_font), (32, 26))
        self.assertLessEqual(
            round(chinese_font * 1.2) * 2
            + round(english_font * 1.2) * 2,
            region["height"],
        )
        self.assertAlmostEqual(english_font / chinese_font, 0.8, delta=0.02)

        cue = Cue(
            10,
            14,
            "The President welcomed guests from every state and territory "
            "to the Rose Garden for lunch today, and thanked every member "
            "of the team.",
            "总统欢迎来自各州和地区的来宾来到玫瑰园共进午餐，"
            "并感谢团队的每一位成员。",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rose-captions.ass"
            write_ass(
                path,
                [cue],
                1920,
                1080,
                layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
                caption_position="mask-lower-third",
                source_graphics_regions=source_regions,
                occlusion_exception_authorized=True,
                mask_padding_px_per_edge=2,
                allow_unverified_estimate=True,
            )
            rendered = pysubs2.load(str(path), encoding="utf-8")
        self.assertEqual(rendered.styles["Chinese"].fontsize, 32)
        self.assertEqual(rendered.styles["English"].fontsize, 26)
        self.assertEqual(len(rendered.events), 2)

        report = verify_cues(
            [cue],
            duration=20,
            width=1920,
            height=1080,
            layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
            caption_position="mask-lower-third",
            source_graphics_regions=source_regions,
            occlusion_exception_authorized=True,
            mask_padding_px_per_edge=2,
            allow_unverified_estimate=True,
        )
        readability = report["subtitle_readability"]
        self.assertEqual(readability["chinese_font_px"], 32)
        self.assertEqual(readability["english_font_px"], 26)
        self.assertAlmostEqual(
            readability["english_to_chinese_size_ratio"],
            0.812,
            delta=0.001,
        )

    def test_rose_garden_reflows_overflow_at_aligned_punctuation(self):
        short = Cue(2, 2.4, "Thanks, everyone.", "谢谢大家。")
        font_zh, font_en, *_ = _rose_garden_wrap_limits(1920, 1080)
        self.assertEqual(
            reflow_rose_garden_cues(
                [short],
                safe_width=1305,
                chinese_font=font_zh,
                english_font=font_en,
            ),
            [short],
        )
        original = Cue(
            100,
            112,
            "The President welcomed every guest who had gathered in the "
            "Rose Garden, and thanked the hardworking staff for making "
            "the special event possible, before joining the invited guests "
            "for a working lunch and conversation.",
            "总统欢迎所有聚集在玫瑰园的来宾，"
            "并感谢工作人员为特别活动付出的辛勤努力，"
            "随后与受邀来宾共进工作午餐并交流。",
        )
        with self.assertRaisesRegex(ValueError, "more than 2 lines"):
            _wrap_english_to_width(original.english, 1305, font_en)

        result = reflow_rose_garden_cues(
            [original],
            safe_width=1305,
            chinese_font=font_zh,
            english_font=font_en,
        )
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].start, original.start)
        self.assertEqual(result[-1].end, original.end)
        self.assertTrue(
            all(left.end == right.start for left, right in zip(result, result[1:]))
        )
        self.assertTrue(
            all(
                cue.end - cue.start >= 0.83
                for cue in result
            )
        )
        self.assertEqual(
            " ".join(cue.english for cue in result),
            original.english,
        )
        self.assertEqual(
            "".join(cue.chinese for cue in result),
            original.chinese,
        )
        for cue in result:
            self.assertLessEqual(
                len(_wrap_english_to_width(cue.english, 1305, font_en)),
                2,
            )
            self.assertLessEqual(
                len(_wrap_chinese_to_width(cue.chinese, 1305, font_zh)),
                2,
            )

    def test_rose_garden_reflow_records_unavoidable_overflow_without_dropping_cue(self):
        font_zh, font_en, *_ = _rose_garden_wrap_limits(1920, 1080)
        too_long = Cue(
            180.03,
            185,
            " ".join(["unbroken phrase"] * 24),
            "没有对应标点的中文长句" * 12,
        )
        overflow_records = []
        result = reflow_rose_garden_cues(
            [too_long],
            safe_width=1305,
            chinese_font=font_zh,
            english_font=font_en,
            overflow_records=overflow_records,
        )
        self.assertEqual(result, [too_long])
        self.assertEqual(len(overflow_records), 1)
        self.assertEqual(
            overflow_records[0]["reason"],
            "no_aligned_phrase_boundary",
        )
        self.assertEqual(overflow_records[0]["source_cue_index"], 1)
        self.assertGreater(overflow_records[0]["english_lines_required"], 2)
        self.assertGreater(overflow_records[0]["chinese_lines_required"], 2)

        too_short = Cue(
            180.03,
            181.2,
            "The first aligned clause, and the second aligned clause.",
            "第一个对应分句，第二个对应分句。",
        )
        short_records = []
        self.assertEqual(
            reflow_rose_garden_cues(
                [too_short],
                safe_width=350,
                chinese_font=font_zh,
                english_font=font_en,
                overflow_records=short_records,
            ),
            [too_short],
        )
        self.assertEqual(
            short_records[0]["reason"],
            "aligned_split_below_minimum_duration",
        )

    def test_recorded_rose_overflow_writes_ass_and_requires_manual_review(self):
        cue = Cue(
            180.03,
            185,
            " ".join(["unbroken phrase"] * 24),
            "没有对应标点的中文长句" * 12,
        )
        font_zh, font_en, *_ = _rose_garden_wrap_limits(1920, 1080)
        overflow_records = []
        cues = reflow_rose_garden_cues(
            [cue],
            safe_width=1305,
            chinese_font=font_zh,
            english_font=font_en,
            overflow_records=overflow_records,
        )

        render_modes = (
            {
                "caption_position": "top",
                "source_graphics_regions": [],
                "occlusion_exception_authorized": False,
                "mask_padding_px_per_edge": None,
            },
            {
                "caption_position": "mask-lower-third",
                "source_graphics_regions": self.ROSE_SOURCE_GRAPHICS,
                "occlusion_exception_authorized": True,
                "mask_padding_px_per_edge": 2,
            },
        )
        for mode in render_modes:
            with self.subTest(caption_position=mode["caption_position"]):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "rose-captions.ass"
                    write_ass(
                        path,
                        cues,
                        1920,
                        1080,
                        layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
                        caption_overflow_records=overflow_records,
                        **mode,
                    )
                    rendered = pysubs2.load(str(path), encoding="utf-8")

                expected_events = 2 if mode["caption_position"] == "mask-lower-third" else 1
                self.assertEqual(len(rendered.events), expected_events)
                caption = rendered.events[-1]
                self.assertEqual(caption.start, round(cue.start * 1000))
                self.assertIn("unbroken phrase", caption.text)
                self.assertIn("没有对应标点的中文长句", caption.text)
                report = verify_cues(
                    cues,
                    duration=200,
                    width=1920,
                    height=1080,
                    layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
                    caption_position=mode["caption_position"],
                    caption_safe_region_reviewed=(
                        mode["caption_position"] == "mask-lower-third"
                    ),
                    caption_overflow_records=overflow_records,
                    **{
                        key: value
                        for key, value in mode.items()
                        if key != "caption_position"
                    },
                )
                readability = report["subtitle_readability"]
                self.assertEqual(readability["status"], "manual_review_required")
                self.assertEqual(
                    readability["caption_overflow_exceptions"]["count"],
                    1,
                )
                self.assertEqual(
                    readability["caption_overflow_exceptions"]["cues"],
                    overflow_records,
                )

    def test_rose_garden_render_continues_with_overflow_at_cues_15_and_50(self):
        font_zh, font_en, *_ = _rose_garden_wrap_limits(1920, 1080)
        cues = []
        for cue_index in range(1, 51):
            if cue_index <= 14:
                start = 142 + (cue_index - 1) * 2
            elif cue_index == 15:
                start = 180.030
            elif cue_index < 50:
                start = 185 + (cue_index - 16) * 3
            else:
                start = 290.450
            if cue_index in {15, 50}:
                english = " ".join(["unbroken phrase"] * 24)
                chinese = "没有对应标点的中文长句" * 12
            else:
                english = f"Ordinary caption {cue_index}."
                chinese = f"普通字幕{cue_index}。"
            cues.append(Cue(start, start + 1.5, english, chinese))

        overflow_records = []
        reflowed = reflow_rose_garden_cues(
            cues,
            safe_width=round(1920 * 0.68),
            chinese_font=font_zh,
            english_font=font_en,
            overflow_records=overflow_records,
        )

        self.assertEqual(reflowed, cues)
        self.assertEqual(
            [
                (
                    record["source_cue_index"],
                    record["start_seconds"],
                    record["review_status"],
                )
                for record in overflow_records
            ],
            [
                (15, 180.03, "manual_review_required"),
                (50, 290.45, "manual_review_required"),
            ],
        )
        for index in (14, 49):
            self.assertEqual(reflowed[index], cues[index])

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rose-captions.ass"
            write_ass(
                path,
                reflowed,
                1920,
                1080,
                layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
                caption_overflow_records=overflow_records,
            )
            rendered = pysubs2.load(str(path), encoding="utf-8")

        self.assertEqual(len(rendered.events), len(cues))
        for cue_index in (15, 50):
            cue = cues[cue_index - 1]
            event = rendered.events[cue_index - 1]
            self.assertEqual(event.start, round(cue.start * 1000))
            self.assertEqual(event.end, round(cue.end * 1000))
            plain_text = re.sub(r"(?<!\\)\{[^}]*\}", "", event.text)
            plain_text = (
                plain_text.replace(r"\N", "\n")
                .replace(r"\{", "{")
                .replace(r"\}", "}")
                .replace(r"\\", "\\")
            )
            lines = plain_text.splitlines()
            record = overflow_records[0 if cue_index == 15 else 1]
            english_line_count = record["english_lines_required"]
            self.assertEqual(
                " ".join(lines[:english_line_count]),
                cue.english,
            )
            self.assertEqual(
                "".join(lines[english_line_count:]),
                cue.chinese,
            )

        report = verify_cues(
            reflowed,
            duration=300,
            width=1920,
            height=1080,
            layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
            caption_position="top",
            caption_overflow_records=overflow_records,
        )
        readability = report["subtitle_readability"]
        self.assertEqual(readability["status"], "manual_review_required")
        self.assertEqual(
            readability["caption_overflow_exceptions"]["cues"],
            overflow_records,
        )

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "cannot fit completely"):
                write_ass(
                    Path(directory) / "unrecorded-overflow.ass",
                    [
                        Cue(
                            1,
                            5,
                            " ".join(["unbroken phrase"] * 24),
                            "没有对应标点的中文长句" * 12,
                        )
                    ],
                    1920,
                    1080,
                    layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
                    caption_overflow_records=overflow_records,
                )

    def test_rose_garden_caption_mask_rejects_content_that_cannot_fit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rose-captions.ass"
            with self.assertRaisesRegex(ValueError, "cannot fit completely"):
                write_ass(
                    path,
                    [
                        Cue(
                            1,
                            5,
                            " ".join(["unbreakabletoken"] * 100),
                            "中文内容",
                        )
                    ],
                    1920,
                    1080,
                    layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
                    caption_position="mask-lower-third",
                    source_graphics_regions=self.ROSE_SOURCE_GRAPHICS,
                    occlusion_exception_authorized=True,
                    mask_padding_px_per_edge=2,
                )

    def test_rose_nonmask_layout_is_computable_without_bbox_but_stays_unreviewed(self):
        report = verify_cues(
            [Cue(1, 3, "Hello, everybody.", "大家好。")],
            duration=10,
            width=1920,
            height=1080,
            layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
            caption_position="top",
            caption_safe_region_reviewed=False,
            source_graphics_regions=[],
        )
        readability = report["subtitle_readability"]
        self.assertEqual(readability["caption_region_validation"], "not_verified")
        self.assertEqual(readability["caption_position_review"], "pending")
        self.assertEqual(readability["source_graphics_review"]["status"], "not_verified")
        self.assertEqual(readability["source_graphics_review"]["review_status"], "pending")
        self.assertFalse(readability["source_graphics_review"]["production_bbox_input"])
        self.assertEqual(readability["visual_frame_review"], "not_verified")
        self.assertEqual(
            readability["caption_band_occlusion"]["status"],
            "non_mask_layout_selected",
        )

    def test_rose_source_graphics_bbox_and_authorization_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "no defaults"):
            parse_source_graphics_regions("[]")
        with self.assertRaisesRegex(ValueError, "human-verified"):
            parse_source_graphics_regions(json.dumps([
                {
                    "label": "source-lower-third",
                    "x": 0.1,
                    "y": 0.8,
                    "width": 0.8,
                    "height": 0.1,
                }
            ]))
        regions = parse_source_graphics_regions(
            __import__("json").dumps(self.ROSE_SOURCE_GRAPHICS)
        )
        for padding in (1, 2, 5):
            region = rose_caption_region(
                1920, 1080, "mask-lower-third", regions, padding
            )
            self.assertEqual(
                (region["left"], region["top"], region["right"], region["bottom"]),
                (192 - padding, 734 - padding, 1728 + padding, 1058 + padding),
            )
        for padding in (0, 6):
            with self.subTest(padding=padding), self.assertRaisesRegex(
                ValueError, "1-5 px"
            ):
                rose_caption_region(
                    1920, 1080, "mask-lower-third", regions, padding
                )
        for position, reviewed, authorized, graphics, expected in (
            ("mask-lower-third", True, False, regions, "explicit Rose Garden"),
            ("mask-lower-third", False, True, [], "lower-third/ticker box"),
        ):
            with self.subTest(position=position, authorized=authorized), self.assertRaisesRegex(
                ValueError, expected
            ):
                validate_rose_caption_placement(
                    width=1920,
                    height=1080,
                    position=position,
                    safe_region_reviewed=reviewed,
                    source_graphics_regions=graphics,
                    occlusion_exception_authorized=authorized,
                    mask_padding_px_per_edge=2,
                )
        overlapping = [
            *regions,
            {
                "label": "logo",
                "human_verified": True,
                "x": 0.2,
                "y": 0.1,
                "width": 0.2,
                "height": 0.1,
            },
        ]
        self.assertEqual(
            validate_rose_caption_placement(
                width=1920,
                height=1080,
                position="top",
                safe_region_reviewed=False,
                source_graphics_regions=overlapping,
            ),
            rose_caption_region(1920, 1080, "top"),
        )

    def test_untrusted_claimed_bbox_cannot_enter_production_mask_render(self):
        claimed_region = json.dumps(self.ROSE_SOURCE_GRAPHICS)
        self.assertTrue(
            parse_source_graphics_regions(claimed_region)[0]["human_verified"]
        )
        frame_review = {
            "reviewer_identity": "claimed-reviewer",
            "reviewed_at": "2026-10-16T02:00:00Z",
            "source_timecode": "00:10:30.000",
            "source_resolution": {"width": 1920, "height": 1080},
            "source_banner_bbox_px": {
                "left": 192,
                "top": 734,
                "right": 1728,
                "bottom": 1058,
            },
            "evidence_ref": "https://example.org/review",
            "source_sha256": "e0b04fb669fd0d09f1492de6a3160bb3b6dae2e3e396be77372f4b5635da5f73",
        }
        with (
            patch(
                "scripts.verify_rose_garden_review.file_sha256_and_size",
                return_value=(
                    "e0b04fb669fd0d09f1492de6a3160bb3b6dae2e3e396be77372f4b5635da5f73",
                    1,
                ),
            ),
            self.assertRaisesRegex(RuntimeError, "base64 OpenSSH signature"),
        ):
            require_trusted_mask_review(
                "mask-lower-third",
                source_path=Path("pinned-test-source.mp4"),
                source_width=1920,
                source_height=1080,
                source_duration=2193.261,
                source_frame_review_record_json=json.dumps(frame_review),
                source_frame_review_signature="",
                source_graphics_regions_json=claimed_region,
                dispatch_actor="publisher",
            )
        out_of_frame = [
            {
                "label": "source-lower-third",
                "human_verified": True,
                "x": 0.1,
                "y": 0.001,
                "width": 0.8,
                "height": 0.1,
            }
        ]
        with self.assertRaisesRegex(ValueError, "exceed the source frame"):
            rose_caption_region(
                1920, 1080, "mask-lower-third", out_of_frame, 2
            )

    def test_default_layout_highlights_words_without_changing_phrase_timing(self):
        cue = Cue(1, 3, "Hello, world.", "你好，世界。")
        timings = (
            (
                TimedWord("Hello,", 1.1, 1.4),
                TimedWord("world.", 1.5, 2.5),
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captions.ass"
            highlighting_applied = write_ass(
                path,
                [cue],
                1920,
                1080,
                word_timings=timings,
            )
            content = path.read_text(encoding="utf-8")
            rendered = pysubs2.load(str(path), encoding="utf-8")

        self.assertTrue(highlighting_applied)
        self.assertIn(
            r"\t(10,11,\fscy108)\t(39,40,\fscy100)}Hello,",
            content,
        )
        self.assertEqual(rendered.events[0].start, 1000)
        self.assertEqual(rendered.events[0].end, 3000)

    def test_katie_layout_uses_fixed_chinese_first_lower_third_panel(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "katie-captions.ass"
            write_ass(
                path,
                [
                    Cue(0, 2.5, "A complete English sentence.", "完整的中文句子。"),
                    Cue(
                        2.5,
                        5,
                        "This thought stays together while the caption wraps "
                        "to line two.",
                        "完整意思仍然保留，同时英文分成两行显示。",
                    ),
                ],
                1920,
                1080,
                layout_profile=KATIE_SUBTITLE_LAYOUT,
            )
            rendered = pysubs2.load(str(path), encoding="utf-8")

        self.assertEqual(len(rendered.events), 6)
        self.assertEqual(
            [event.layer for event in rendered.events],
            [0, 1, 1, 0, 1, 1],
        )
        self.assertIn(r"\p1", rendered.events[0].text)
        self.assertIn(r"\1a&H00&", rendered.events[0].text)
        self.assertEqual(rendered.events[0].text, rendered.events[3].text)
        self.assertIn(r"\pos(0,859)", rendered.events[0].text)
        self.assertIn("l 1920 0 l 1920 221", rendered.events[0].text)
        self.assertIn(r"\an8\pos(960,", rendered.events[1].text)
        self.assertIn(r"\an2\pos(960,", rendered.events[2].text)
        self.assertIn("完整的中文句子。", rendered.events[1].text)
        self.assertIn("A complete English sentence.", rendered.events[2].text)
        self.assertIn(r"\pos(960,1067)", rendered.events[2].text)
        self.assertIn(r"\pos(960,1067)", rendered.events[5].text)
        self.assertNotIn(r"\N", rendered.events[2].text)
        self.assertIn(r"\N", rendered.events[5].text)
        self.assertGreaterEqual(
            rendered.styles["Chinese"].fontsize,
            round(rendered.styles["English"].fontsize * 1.20),
        )
        self.assertEqual(rendered.styles["Chinese"].fontsize, 28)
        self.assertEqual(rendered.styles["English"].fontsize, 22)

    def test_katie_fixed_layout_preserves_panel_while_highlighting_words(self):
        cue = Cue(0, 2.5, "A complete English sentence.", "完整的中文句子。")
        timings = (
            (
                TimedWord("A", 0.1, 0.3),
                TimedWord("complete", 0.35, 0.65),
                TimedWord("English", 0.7, 1.0),
                TimedWord("sentence.", 1.05, 1.45),
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "katie-word-captions.ass"
            highlighting_applied = write_ass(
                path,
                [cue],
                1920,
                1080,
                layout_profile=KATIE_SUBTITLE_LAYOUT,
                word_timings=timings,
            )
            rendered = pysubs2.load(str(path), encoding="utf-8")
            english_event = rendered.events[2]

        self.assertTrue(highlighting_applied)
        self.assertEqual(len(rendered.events), 3)
        self.assertIn(r"\pos(960,1067)", english_event.text)
        self.assertIn(r"\t(10,11,\fscy108)", english_event.text)
        self.assertTrue(
            all(
                word in english_event.text
                for word in ("A", "complete", "English", "sentence.")
            )
        )
        self.assertEqual(english_event.start, 0)
        self.assertEqual(english_event.end, 2500)

    def test_katie_fixed_layout_falls_back_if_any_word_timing_mismatches(self):
        cue = Cue(0, 2.5, "A complete English sentence.", "完整的中文句子。")
        timings = (
            (
                TimedWord("A", 0.1, 0.3),
                TimedWord("complete", 0.35, 0.65),
                TimedWord("English", 0.7, 1.0),
                TimedWord("wrong.", 1.05, 1.45),
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "katie-plain-captions.ass"
            highlighting_applied = write_ass(
                path,
                [cue],
                1920,
                1080,
                layout_profile=KATIE_SUBTITLE_LAYOUT,
                word_timings=timings,
            )
            rendered = pysubs2.load(str(path), encoding="utf-8")
            english_event = rendered.events[2]

        self.assertFalse(highlighting_applied)
        self.assertIn(r"\pos(960,1067)", english_event.text)
        self.assertNotIn(r"\fscy108", english_event.text)
        self.assertIn("A complete English sentence.", english_event.text)
    def test_katie_wrapping_preserves_text_and_rejects_overflow(self):
        _chinese_font, _english_font, max_chinese, max_english = (
            _katie_wrap_limits(1920, 1080)
        )
        english = (
            "Please preserve every word in this sentence without dropping "
            "any phrase."
        )
        chinese = "这是一段完整的中文说明，字幕应当保留全部文字，并且维持原本的意思。"

        english_lines = _wrap_katie_english(english, max_english)
        chinese_lines = _wrap_katie_chinese(chinese, max_chinese)

        self.assertLessEqual(len(english_lines), 2)
        self.assertLessEqual(len(chinese_lines), 2)
        self.assertTrue(all(len(line) <= max_english for line in english_lines))
        self.assertTrue(all(len(line) <= max_chinese for line in chinese_lines))
        self.assertEqual(" ".join(english_lines).split(), english.split())
        self.assertEqual("".join(chinese_lines), chinese)
        with self.assertRaisesRegex(ValueError, "more than two English lines"):
            _wrap_katie_english(" ".join(["longword"] * 100), max_english)
        with self.assertRaisesRegex(ValueError, "without a safe punctuation"):
            _wrap_katie_chinese("超长而且没有任何安全的中文分句标点符号" * 5, max_chinese)

    def test_katie_reflows_punctuation_aligned_translation_clauses(self):
        original = Cue(
            13.605,
            35.11,
            "The committee released a detailed report yesterday. "
            "Members will answer questions at the briefing. "
            "Additional records will be available next week.",
            "委员会昨天发布了一份详细报告，成员将在简报会上回答问题，"
            "更多记录将于下周公布。",
        )
        original_srt = srt_text([original], "en")

        self.assertEqual(reflow_cues([original]), [original])
        reflowed = reflow_cues(
            [original],
            align_sentence_to_clause_punctuation=True,
        )
        _chinese_font, _english_font, _max_chinese, max_english = (
            _katie_wrap_limits(1920, 1080)
        )

        self.assertEqual(len(reflowed), 3)
        self.assertEqual(reflowed[0].start, original.start)
        self.assertEqual(reflowed[-1].end, original.end)
        self.assertTrue(
            all(
                left.end == right.start
                for left, right in zip(reflowed, reflowed[1:])
            )
        )
        self.assertEqual(
            " ".join(cue.english for cue in reflowed),
            original.english,
        )
        self.assertEqual(
            "".join(cue.chinese for cue in reflowed),
            original.chinese,
        )
        self.assertTrue(
            all(
                len(_wrap_katie_english(cue.english, max_english)) <= 2
                for cue in reflowed
            )
        )
        self.assertEqual(srt_text([original], "en"), original_srt)

    def test_katie_preserves_pinned_intro_boundary_and_reflows_full_sentences(self):
        original = [
            Cue(
                7.54,
                13.605,
                "Good morning. I am so honored to work for President Trump",
                "我很荣幸能为特朗普总统",
            ),
            Cue(
                13.605,
                35.11,
                "and the American people as the new White House press secretary. "
                "I want to thank President Trump for his trust that he has "
                "placed in me. I have wanted to work for him for a a very "
                "long time.",
                "和美国人民担任新的白宫新闻秘书,"
                "我要感谢特朗普总统对我的信任,"
                "我很想为他工作很长一段时间。",
            ),
        ]

        merged = merge_sentence_fragments(
            original,
            preserve_katie_intro_boundary=True,
        )
        reflowed = reflow_cues(
            merged,
            align_sentence_to_clause_punctuation=True,
        )
        _chinese_font, _english_font, max_chinese, max_english = (
            _katie_wrap_limits(1920, 1080)
        )

        self.assertEqual(len(merged), 2)
        self.assertEqual(merged, original)
        self.assertEqual(
            [(cue.start, cue.end) for cue in reflowed],
            [
                (7.54, 13.605),
                (13.605, 19.67051282051282),
                (19.67051282051282, 27.941666666666666),
                (27.941666666666666, 35.11),
            ],
        )
        self.assertEqual(
            [cue.english for cue in reflowed],
            [
                "Good morning. I am so honored to work for President Trump",
                "and the American people as the new White House press secretary.",
                "I want to thank President Trump for his trust that he has placed in me.",
                "I have wanted to work for him for a a very long time.",
            ],
        )
        self.assertEqual(
            [cue.chinese for cue in reflowed],
            [
                "我很荣幸能为特朗普总统",
                "和美国人民担任新的白宫新闻秘书,",
                "我要感谢特朗普总统对我的信任,",
                "我很想为他工作很长一段时间。",
            ],
        )
        self.assertEqual(
            " ".join(cue.english for cue in reflowed),
            " ".join(cue.english for cue in original),
        )
        self.assertEqual(
            "".join(cue.chinese for cue in reflowed),
            "".join(cue.chinese for cue in original),
        )
        for cue in reflowed:
            self.assertLessEqual(
                len(_wrap_katie_english(cue.english, max_english)),
                2,
            )
            self.assertLessEqual(
                len(_wrap_katie_chinese(cue.chinese, max_chinese)),
                2,
            )

    def test_katie_reflows_midterm_blitz_at_matched_bilingual_phrases(self):
        original = [
            Cue(
                35.11,
                45.721,
                "I'm looking forward to working with each of you as well, "
                "especially as we are in the middle of the midterm blitz "
                "with energy",
                "我期待着与你们每个人一起工作,"
                "特别是因为我们正处在中期闪电中,"
                "在中期历史上从未见过的能量",
            ),
            Cue(
                45.721,
                51.91,
                "and excitement never seen before in the history of midterms "
                "thanks to President Trump.",
                "和兴奋,感谢特朗普总统。",
            ),
        ]
        original_english = " ".join(cue.english for cue in original)
        original_chinese = "".join(cue.chinese for cue in original)

        merged = merge_sentence_fragments(original)
        reflowed = reflow_cues(
            merged,
            align_sentence_to_clause_punctuation=True,
        )
        _chinese_font, _english_font, max_chinese, max_english = (
            _katie_wrap_limits(1920, 1080)
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(len(reflowed), 4)
        self.assertEqual(
            [cue.english for cue in reflowed],
            [
                "I'm looking forward to working with each of you as well,",
                "especially as we are in the middle of the midterm blitz",
                "with energy and excitement never seen before in the history "
                "of midterms",
                "thanks to President Trump.",
            ],
        )
        self.assertEqual(
            [cue.chinese for cue in reflowed],
            [
                "我期待着与你们每个人一起工作,",
                "特别是因为我们正处在中期闪电中,",
                "在中期历史上从未见过的能量和兴奋,",
                "感谢特朗普总统。",
            ],
        )
        self.assertEqual(
            " ".join(cue.english for cue in reflowed),
            original_english,
        )
        self.assertEqual(
            "".join(cue.chinese for cue in reflowed),
            original_chinese,
        )
        self.assertEqual(reflowed[0].start, original[0].start)
        self.assertEqual(reflowed[-1].end, original[-1].end)
        self.assertTrue(
            all(left.end == right.start for left, right in zip(reflowed, reflowed[1:]))
        )
        for cue in reflowed:
            self.assertLessEqual(
                len(_wrap_katie_english(cue.english, max_english)),
                2,
            )
            self.assertLessEqual(
                len(_wrap_katie_chinese(cue.chinese, max_chinese)),
                2,
            )

    def test_katie_reflows_youngstown_appositive_and_relative_clause(self):
        original = Cue(
            51.91,
            62.33,
            "Just look no further than last night in Youngstown, Ohio, "
            "where President Trump delivered another blockbuster rally "
            "out on the trail.",
            "只需看看昨晚在俄亥俄州Youngstown,"
            "特朗普总统在那里举行了另一场大规模集会。",
        )
        reflowed = reflow_cues(
            [original],
            align_sentence_to_clause_punctuation=True,
        )
        _chinese_font, _english_font, max_chinese, max_english = (
            _katie_wrap_limits(1920, 1080)
        )

        self.assertEqual(
            [(cue.english, cue.chinese) for cue in reflowed],
            [
                (
                    "Just look no further than last night in Youngstown, Ohio,",
                    "只需看看昨晚在俄亥俄州Youngstown,",
                ),
                (
                    "where President Trump delivered another blockbuster rally "
                    "out on the trail.",
                    "特朗普总统在那里举行了另一场大规模集会。",
                ),
            ],
        )
        self.assertEqual(reflowed[0].start, original.start)
        self.assertEqual(reflowed[-1].end, original.end)
        self.assertEqual(" ".join(cue.english for cue in reflowed), original.english)
        self.assertEqual("".join(cue.chinese for cue in reflowed), original.chinese)
        for cue in reflowed:
            self.assertLessEqual(
                len(_wrap_katie_english(cue.english, max_english)),
                2,
            )
            self.assertLessEqual(
                len(_wrap_katie_chinese(cue.chinese, max_chinese)),
                2,
            )

    def test_katie_reflows_arena_attendees_and_named_guests(self):
        original = Cue(
            62.33,
            75.15,
            "The arena was overflowing with enthusiasm as thousands came out "
            "to support President Trump as well as special guest Jake Paul "
            "and football legend John Gruden.",
            "竞技场充满了热情,因为成千上万的人来支持特朗普总统"
            "以及特别嘉宾杰克保罗和足球传奇约翰格鲁登。",
        )
        reflowed = reflow_cues(
            [original],
            align_sentence_to_clause_punctuation=True,
        )
        _chinese_font, _english_font, max_chinese, max_english = (
            _katie_wrap_limits(1920, 1080)
        )

        self.assertEqual(
            [(cue.english, cue.chinese) for cue in reflowed],
            [
                (
                    "The arena was overflowing with enthusiasm",
                    "竞技场充满了热情,",
                ),
                (
                    "as thousands came out to support President Trump as well "
                    "as special guest Jake Paul",
                    "因为成千上万的人来支持特朗普总统以及特别嘉宾杰克保罗",
                ),
                (
                    "and football legend John Gruden.",
                    "和足球传奇约翰格鲁登。",
                ),
            ],
        )
        self.assertEqual(
            " ".join(cue.english for cue in reflowed),
            original.english,
        )
        self.assertEqual(
            "".join(cue.chinese for cue in reflowed),
            original.chinese,
        )
        self.assertEqual(reflowed[0].start, original.start)
        self.assertEqual(reflowed[-1].end, original.end)
        for cue in reflowed:
            self.assertLessEqual(
                len(_wrap_katie_english(cue.english, max_english)),
                2,
            )
            self.assertLessEqual(
                len(_wrap_katie_chinese(cue.chinese, max_chinese)),
                2,
            )

    def test_katie_reflows_navy_repair_center_announcement(self):
        original = Cue(
            75.15,
            87.51,
            "The President also announced the Department of War has officially "
            "selected Cleveland Ohio as the new home for the U.S. Navy's "
            "submarine component repair center.",
            "总统还宣布,美国军方已正式选择克利夫兰俄亥俄州"
            "作为美国海军潜艇零部件维修中心的新家。",
        )
        reflowed = reflow_cues(
            [original],
            align_sentence_to_clause_punctuation=True,
        )
        _chinese_font, _english_font, max_chinese, max_english = (
            _katie_wrap_limits(1920, 1080)
        )

        self.assertEqual(
            [(cue.english, cue.chinese) for cue in reflowed],
            [
                (
                    "The President also announced",
                    "总统还宣布,",
                ),
                (
                    "the Department of War has officially selected Cleveland "
                    "Ohio",
                    "美国军方已正式选择克利夫兰俄亥俄州",
                ),
                (
                    "as the new home for the U.S. Navy's submarine component "
                    "repair center.",
                    "作为美国海军潜艇零部件维修中心的新家。",
                ),
            ],
        )
        self.assertEqual(
            " ".join(cue.english for cue in reflowed),
            original.english,
        )
        self.assertEqual(
            "".join(cue.chinese for cue in reflowed),
            original.chinese,
        )
        self.assertEqual(reflowed[0].start, original.start)
        self.assertEqual(reflowed[-1].end, original.end)
        for cue in reflowed:
            self.assertLessEqual(
                len(_wrap_katie_english(cue.english, max_english)),
                2,
            )
            self.assertLessEqual(
                len(_wrap_katie_chinese(cue.chinese, max_chinese)),
                2,
            )

    def test_katie_reflows_america_first_policy_list(self):
        original = Cue(
            103.55,
            121.0,
            "Everyday Americans are showing up in droves to attend these "
            "rallies because of President Trump's America First agenda of "
            "lower taxes, higher wages, and one of my favorite secure borders.",
            "每日的美国人都在参加这些集会,"
            "因为特朗普总统的“美国第一”议程是降低税收,"
            "提高工资,以及我最喜欢的安全边界之一。",
        )
        reflowed = reflow_cues(
            [original],
            align_sentence_to_clause_punctuation=True,
        )
        _chinese_font, _english_font, max_chinese, max_english = (
            _katie_wrap_limits(1920, 1080)
        )

        self.assertEqual(
            [(cue.english, cue.chinese) for cue in reflowed],
            [
                (
                    "Everyday Americans are showing up in droves to attend "
                    "these rallies",
                    "每日的美国人都在参加这些集会,",
                ),
                (
                    "because of President Trump's America First agenda of "
                    "lower taxes,",
                    "因为特朗普总统的“美国第一”议程是降低税收,",
                ),
                ("higher wages,", "提高工资,"),
                (
                    "and one of my favorite secure borders.",
                    "以及我最喜欢的安全边界之一。",
                ),
            ],
        )
        self.assertEqual(
            " ".join(cue.english for cue in reflowed),
            original.english,
        )
        self.assertEqual(
            "".join(cue.chinese for cue in reflowed),
            original.chinese,
        )
        self.assertEqual(reflowed[0].start, original.start)
        self.assertEqual(reflowed[-1].end, original.end)
        for cue in reflowed:
            self.assertLessEqual(
                len(_wrap_katie_english(cue.english, max_english)),
                2,
            )
            self.assertLessEqual(
                len(_wrap_katie_chinese(cue.chinese, max_chinese)),
                2,
            )

    def test_katie_layout_failure_identifies_cue_without_logging_caption_text(self):
        overflow_text = " ".join(["longword"] * 100)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "katie-captions.ass"
            with self.assertRaisesRegex(
                ValueError,
                r"Katie subtitle cue 2 .*English characters=\d+, "
                r"maximum characters per line=42",
            ) as raised:
                write_ass(
                    path,
                    [
                        Cue(0, 2, "A short sentence.", "简短的一句话。"),
                        Cue(2, 10, overflow_text, "需要人工重新对齐。"),
                    ],
                    1920,
                    1080,
                    layout_profile=KATIE_SUBTITLE_LAYOUT,
                )

        self.assertNotIn(overflow_text, str(raised.exception))

    def test_reflow_splits_only_at_bilingually_aligned_clauses(self):
        original = Cue(
            0,
            42.39,
            "The quality of the systems that we produce and the strength "
            "of the industrial base that constructs and sustains those systems.",
            "我们生产的系统的质量以及构建和维持这些系统的工业基础的强度。",
        )
        reflowed = reflow_cues([original])

        self.assertEqual(
            [
                (
                    cue.english,
                    cue.chinese,
                )
                for cue in reflowed
            ],
            [
                (
                    "The quality of the systems that we produce",
                    "我们生产的系统的质量",
                ),
                (
                    "and the strength of the industrial base that constructs "
                    "and sustains those systems.",
                    "以及构建和维持这些系统的工业基础的强度。",
                ),
            ],
        )
        self.assertEqual(reflowed[0].start, original.start)
        self.assertEqual(reflowed[-1].end, original.end)
        self.assertTrue(
            all(left.end == right.start for left, right in zip(reflowed, reflowed[1:]))
        )
        first_clause_words = len(reflowed[0].english.split())
        total_words = len(original.english.split())
        self.assertAlmostEqual(
            reflowed[0].end - reflowed[0].start,
            42.39 * first_clause_words / total_words,
        )
        self.assertEqual(
            " ".join(cue.english for cue in reflowed),
            original.english,
        )
        self.assertEqual(
            "".join(cue.chinese for cue in reflowed),
            original.chinese,
        )

    def test_reflow_does_not_split_an_unmatched_translation_order(self):
        original = Cue(
            1336.28,
            1362.42,
            "Ladies and gentlemen, the Secretary of War, the Honorable Exeter.",
            "女士们，先生们，战争部长，尊敬的埃克塞特。",
        )
        reflowed = reflow_cues([original])

        self.assertEqual(reflowed, [original])

    def test_reflow_keeps_a_long_intro_sentence_bilingually_together(self):
        original = Cue(
            0,
            6.2,
            "Please welcome the Co-Founder and Chief Executive Officer "
            "of Anduril Industries, Brian Schimpf.",
            "欢迎Anduril Industries联合创始人兼首席执行官Brian Schimpf。",
        )
        reflowed = reflow_cues([original])

        self.assertEqual(reflowed, [original])

    def test_reflow_splits_matching_complete_sentences(self):
        original = Cue(
            0,
            12,
            "The shipyard opened today. Workers will build submarines.",
            "造船厂今天开业。工人将建造潜艇。",
        )
        reflowed = reflow_cues([original])

        self.assertEqual(
            [(cue.english, cue.chinese) for cue in reflowed],
            [
                ("The shipyard opened today.", "造船厂今天开业。"),
                ("Workers will build submarines.", "工人将建造潜艇。"),
            ],
        )
        self.assertEqual(reflowed[0].start, original.start)
        self.assertEqual(reflowed[-1].end, original.end)
        self.assertEqual(reflowed[0].end, reflowed[1].start)

    def test_reflow_keeps_short_english_chunks_synchronized(self):
        reflowed = reflow_cues([Cue(0, 3, "Hello world.", "你好，世界。")])
        self.assertEqual(len(reflowed), 1)
        self.assertEqual(reflowed[0].chinese, "你好，世界。")
        self.assertEqual(reflowed[0].english, "Hello world.")

    def test_merges_asr_fragments_before_rendering_bilingual_captions(self):
        fragments = [
            Cue(484.740, 490.737, "Good", "下午好,"),
            Cue(490.737, 496.733, "afternoon,", "大家"),
            Cue(496.733, 502.730, "everybody.", "。"),
            Cue(502.830, 504.870, "Distinguished guests,", "尊敬的嘉宾,"),
        ]

        merged = merge_sentence_fragments(fragments)

        self.assertEqual(
            merged,
            [
                Cue(
                    484.740,
                    502.730,
                    "Good afternoon, everybody.",
                    "下午好,大家。",
                ),
                Cue(
                    502.830,
                    504.870,
                    "Distinguished guests,",
                    "尊敬的嘉宾,",
                ),
            ],
        )
        reflowed = reflow_cues(merged)
        self.assertEqual(
            [(cue.english, cue.chinese) for cue in reflowed],
            [
                ("Good afternoon,", "下午好,"),
                ("everybody.", "大家。"),
                ("Distinguished guests,", "尊敬的嘉宾,"),
            ],
        )
        self.assertAlmostEqual(reflowed[0].end, fragments[2].start, delta=0.001)
        self.assertAlmostEqual(reflowed[1].end, fragments[2].end, delta=0.001)

    def test_fragment_merging_preserves_ascii_spaces_inside_names(self):
        merged = merge_sentence_fragments([
            Cue(0, 1, "Welcome to New", "欢迎来到New"),
            Cue(1, 2, "York.", "York。"),
        ])
        self.assertEqual(merged[0].english, "Welcome to New York.")
        self.assertEqual(merged[0].chinese, "欢迎来到New York。")

    def test_caption_verification_records_unverified_translation_and_style(self):
        report = verify_cues(
            [Cue(0, 2, "Hello, everybody.", "大家好。")],
            duration=10,
            width=1920,
            height=1080,
        )
        self.assertEqual(report["structural_checks"], "passed")
        self.assertEqual(report["bilingual_cue_sync"]["status"], "passed")
        self.assertEqual(
            report["bilingual_cue_sync"]["audio_level_alignment"],
            "not_verified",
        )
        self.assertEqual(
            report["translation_accuracy"]["status"],
            "not_verified",
        )
        self.assertAlmostEqual(
            report["subtitle_readability"]["english_to_chinese_size_ratio"],
            1.5,
        )
        self.assertEqual(
            report["subtitle_readability"]["lower_margin_percent"],
            18,
        )

    def test_katie_layout_verification_keeps_visual_review_unverified(self):
        report = verify_cues(
            [Cue(0, 3, "A complete sentence.", "完整的一句话。")],
            duration=10,
            width=1920,
            height=1080,
            layout_profile=KATIE_SUBTITLE_LAYOUT,
        )
        readability = report["subtitle_readability"]

        self.assertEqual(readability["layout_configuration"], "passed")
        self.assertEqual(readability["status"], "manual_review_required")
        self.assertEqual(readability["visual_frame_review"], "not_verified")
        self.assertEqual(readability["line_order"], ["zh-Hans", "en"])
        self.assertGreaterEqual(
            readability["chinese_to_english_size_ratio"],
            1.20,
        )
        self.assertAlmostEqual(
            readability["chinese_to_english_size_ratio"],
            1.27,
            places=2,
        )
        self.assertEqual(readability["lower_margin_percent"], 0)

    def test_copies_review_evidence_for_output_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "output"
            evidence = source / "review" / "audio-pass.json"
            evidence.parent.mkdir(parents=True)
            evidence.write_text("reviewed audio", encoding="utf-8")
            review = {
                "source_audio_passes": [
                    {"evidence_file": "review/audio-pass.json"}
                ]
            }
            copy_review_evidence(source, output, review, {})
            self.assertEqual(
                (output / "review" / "audio-pass.json").read_text(
                    encoding="utf-8"
                ),
                "reviewed audio",
            )

    def test_rejects_review_evidence_outside_manifest_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            with self.assertRaisesRegex(RuntimeError, "must stay within"):
                copy_review_evidence(
                    source,
                    output,
                    {"models": [{"evidence_file": "../outside.json"}]},
                    {},
                )

    def test_caption_verification_rejects_overlapping_cues(self):
        with self.assertRaisesRegex(RuntimeError, "overlaps"):
            verify_cues(
                [
                    Cue(0, 2, "First.", "第一句。"),
                    Cue(1.9, 3, "Second.", "第二句。"),
                ],
                duration=10,
                width=1920,
                height=1080,
            )

    def test_caption_verification_preserves_completed_accuracy_review(self):
        report = verify_cues(
            [Cue(0, 2, "Hello, everybody.", "大家好。")],
            duration=10,
            width=1920,
            height=1080,
            translation_review={
                "status": "verified",
                "audio_level_alignment": True,
                "source_audio_review": True,
                "independent_translation_review": True,
                "translation_models_compared": 10,
                "llm_judges": 3,
                "source_cross_check_passes": 3,
            },
        )
        self.assertEqual(
            report["translation_accuracy"],
            {
                "status": "verified",
                "audio_level_alignment": "passed",
                "source_audio_review": "passed",
                "independent_translation_review": "passed",
                "translation_models_compared": 10,
                "llm_judges": 3,
                "source_cross_check_passes": 3,
            },
        )

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
