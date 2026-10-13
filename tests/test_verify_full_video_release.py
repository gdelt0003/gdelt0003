import unittest

from scripts.verify_full_video_release import release_blockers


class FullVideoReleaseGateTests(unittest.TestCase):
    def test_blocks_unverified_translation_audio_and_visual_review(self):
        self.assertIn(
            "quality_checks is missing",
            release_blockers({}),
        )

    def test_reports_each_missing_release_evidence(self):
        manifest = {
            "quality_checks": {
                "structural_checks": "passed",
                "bilingual_cue_sync": {
                    "status": "passed",
                    "audio_level_alignment": "not_verified",
                },
                "cue_timing": "passed",
                "source_resolution": "passed",
                "subtitle_readability": {
                    "status": "style_contract_passed",
                    "english_to_chinese_size_ratio": 1.22,
                    "visual_frame_review": "required",
                    "english_reading_speed_over_20_cps_cues": [],
                    "chinese_reading_speed_over_10_cps_cues": [],
                },
                "translation_accuracy": {
                    "status": "not_verified",
                    "translation_models_compared": 1,
                    "llm_judges": 0,
                    "source_cross_check_passes": 0,
                    "audio_level_alignment": "not_verified",
                    "source_audio_review": "required",
                    "independent_translation_review": "required",
                },
            }
        }
        blockers = release_blockers(manifest)
        self.assertIn("audio-level alignment has not passed", blockers)
        self.assertIn("visual frame review has not passed", blockers)
        self.assertIn("translation accuracy has not been verified", blockers)
        self.assertIn("fewer than 10 translation models completed", blockers)
        self.assertIn("fewer than 3 independent LLM judges completed", blockers)
        self.assertIn("fewer than 3 source cross-checks completed", blockers)

    def test_accepts_complete_verified_release_evidence(self):
        manifest = {
            "quality_checks": {
                "structural_checks": "passed",
                "bilingual_cue_sync": {
                    "status": "passed",
                    "audio_level_alignment": "passed",
                },
                "cue_timing": "passed",
                "source_resolution": "passed",
                "subtitle_readability": {
                    "status": "style_contract_passed",
                    "english_to_chinese_size_ratio": 1.22,
                    "visual_frame_review": "passed",
                    "english_reading_speed_over_20_cps_cues": [],
                    "chinese_reading_speed_over_10_cps_cues": [],
                },
                "translation_accuracy": {
                    "status": "verified",
                    "translation_models_compared": 10,
                    "llm_judges": 3,
                    "source_cross_check_passes": 3,
                    "audio_level_alignment": "passed",
                    "source_audio_review": "passed",
                    "independent_translation_review": "passed",
                },
            }
        }
        self.assertEqual(release_blockers(manifest), [])


if __name__ == "__main__":
    unittest.main()
