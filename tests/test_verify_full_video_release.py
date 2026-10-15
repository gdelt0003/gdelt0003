import hashlib
import tempfile
import unittest
from pathlib import Path

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

    def test_katie_profile_checks_english_larger_than_chinese(self):
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
                    "status": "manual_review_required",
                    "layout_profile": "katie-fixed-lower-third-zh-first",
                    "english_to_chinese_size_ratio": 1.1,
                    "chinese_to_english_size_ratio": 0.91,
                    "visual_frame_review": "not_verified",
                    "english_reading_speed_over_20_cps_cues": [],
                    "chinese_reading_speed_over_10_cps_cues": [],
                },
                "translation_accuracy": {"status": "not_verified"},
            }
        }

        blockers = release_blockers(manifest)
        self.assertIn(
            "English subtitle font is less than 1.20x Chinese font for the Katie layout",
            blockers,
        )
        manifest["quality_checks"]["subtitle_readability"][
            "english_to_chinese_size_ratio"
        ] = 1.25
        blockers = release_blockers(manifest)
        self.assertNotIn(
            "English subtitle font is less than 1.20x Chinese font for the Katie layout",
            blockers,
        )
        self.assertIn("visual frame review has not passed", blockers)

    def test_asserted_statuses_without_records_or_artifacts_are_blocked(self):
        manifest = complete_manifest()
        blockers = release_blockers(manifest)
        self.assertIn(
            "model output is missing a local evidence file and SHA-256",
            blockers,
        )
        self.assertIn(
            "judge report is missing a local evidence file and SHA-256",
            blockers,
        )
        self.assertIn("source-audio pass is missing a local evidence file and SHA-256", blockers)
        self.assertIn("visual frame is missing a local evidence file and SHA-256", blockers)

    def test_accepts_complete_verified_release_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = complete_manifest()
            add_evidence_files(manifest, Path(directory))
            self.assertEqual(release_blockers(manifest, Path(directory)), [])

    def test_rejects_evidence_path_escape_and_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = complete_manifest()
            add_evidence_files(manifest, root)
            manifest["translation_review"]["models"][0]["evidence_file"] = "../outside.txt"
            manifest["translation_review"]["models"][1]["sha256"] = "0" * 64
            blockers = release_blockers(manifest, root)
            self.assertIn(
                "model output evidence path escapes the manifest directory",
                blockers,
            )
            self.assertIn("model output evidence SHA-256 does not match", blockers)


def complete_manifest():
    return {
        "duration_seconds": 100,
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
        },
        "translation_review": {
            "models": [
                {
                    "model_id": f"provider/model-{index}",
                    "translated_cues": 100,
                    "evidence_file": f"models/model-{index}.json",
                }
                for index in range(10)
            ],
            "judges": [
                {
                    "judge_id": f"judge-{index}",
                    "sampled_cues": 120,
                    "evidence_file": f"judges/judge-{index}.json",
                }
                for index in range(3)
            ],
            "source_cross_checks": [
                {
                    "url": f"https://source-{index}.example.org/transcript",
                    "publisher": f"Publisher {index}",
                    "checked_at": "2026-10-13T10:00:00Z",
                    "finding": "Compared transcript wording with the source recording.",
                    "evidence_file": f"sources/source-{index}.json",
                }
                for index in range(3)
            ],
            "source_audio_passes": [
                {
                    "pass_number": index,
                    "reviewer": f"reviewer-{index}",
                    "start_seconds": 0,
                    "end_seconds": 100,
                    "notes": f"Full-span source-audio review pass {index}.",
                    "evidence_file": f"audio/pass-{index}.json",
                }
                for index in range(1, 4)
            ],
        },
        "visual_review": {
            "frames": [
                {
                    "timestamp_seconds": timestamp,
                    "notes": f"Reviewed frame at {timestamp}s.",
                    "evidence_file": f"frames/frame-{timestamp}.png",
                }
                for timestamp in (5, 50, 95)
            ],
        },
    }


def add_evidence_files(manifest, root):
    review = manifest["translation_review"]
    records = (
        review["models"]
        + review["judges"]
        + review["source_cross_checks"]
        + review["source_audio_passes"]
        + manifest["visual_review"]["frames"]
    )
    for record in records:
        path = root / record["evidence_file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        content = f"Evidence for {record['evidence_file']}".encode()
        path.write_bytes(content)
        record["sha256"] = hashlib.sha256(content).hexdigest()


if __name__ == "__main__":
    unittest.main()
