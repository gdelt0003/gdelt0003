import tempfile
import unittest
from pathlib import Path

import pysubs2

from scripts.process_full_video import (
    Cue,
    KATIE_SUBTITLE_LAYOUT,
    _katie_wrap_limits,
    _wrap_katie_chinese,
    _wrap_katie_english,
    ass_escape,
    ass_time,
    bilingual_srt_text,
    copy_review_evidence,
    merge_sentence_fragments,
    reflow_cues,
    read_srt,
    srt_text,
    timestamp,
    validate_asset_prefix,
    validate_release_asset_size,
    vtt_from_bilingual_srt,
    verify_cues,
    write_ass,
)


class FullVideoSubtitleTests(unittest.TestCase):
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
        self.assertEqual(rendered.events[0].text, rendered.events[3].text)
        self.assertIn(r"\pos(106,827)", rendered.events[0].text)
        self.assertIn("l 1709 0 l 1709 221", rendered.events[0].text)
        self.assertIn(r"\an8\pos(960,", rendered.events[1].text)
        self.assertIn(r"\an2\pos(960,", rendered.events[2].text)
        self.assertIn("完整的中文句子。", rendered.events[1].text)
        self.assertIn("A complete English sentence.", rendered.events[2].text)
        self.assertIn(r"\pos(960,1035)", rendered.events[2].text)
        self.assertIn(r"\pos(960,1035)", rendered.events[5].text)
        self.assertNotIn(r"\N", rendered.events[2].text)
        self.assertIn(r"\N", rendered.events[5].text)
        self.assertGreater(
            rendered.styles["Chinese"].fontsize,
            rendered.styles["English"].fontsize,
        )
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
        self.assertAlmostEqual(
            readability["chinese_to_english_size_ratio"],
            38 / 30,
            places=2,
        )

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
