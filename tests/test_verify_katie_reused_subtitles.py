import json
import tempfile
import unittest
from pathlib import Path

from scripts.publish_full_video_preview import (
    EVENT_EVIDENCE_URL,
    EVENT_ID,
    SOURCE_SHA256,
    SOURCE_URL,
)
from scripts.verify_katie_reused_subtitles import verify_reusable_subtitles


class KatieReusableSubtitleTests(unittest.TestCase):
    def test_accepts_matching_source_and_bilingual_cues(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifact"
            artifact.mkdir()
            (artifact / "manifest.json").write_text(
                json.dumps({
                    "input_sha256": SOURCE_SHA256,
                    "source_url": SOURCE_URL,
                    "event": {
                        "event_id": EVENT_ID,
                        "official_video_url": SOURCE_URL,
                    },
                }),
                encoding="utf-8",
            )
            prefix = "katie-zacharia-g7we6gecwnc"
            srt = "1\n00:00:01,000 --> 00:00:03,000\n"
            (artifact / f"{prefix}.en.srt").write_text(
                srt + "Hello.\n",
                encoding="utf-8",
            )
            (artifact / f"{prefix}.zh-Hans.srt").write_text(
                srt + "你好。\n",
                encoding="utf-8",
            )
            source_verification = root / "source-verification.json"
            source_verification.write_text(
                json.dumps({
                    "sha256": SOURCE_SHA256,
                    "source_url": SOURCE_URL,
                    "event_identity_evidence_url": EVENT_EVIDENCE_URL,
                    "source_match_evidence_url": EVENT_EVIDENCE_URL,
                    "same_event_source_match_confirmed": True,
                    "reuse_rights_confirmed": True,
                }),
                encoding="utf-8",
            )

            result = verify_reusable_subtitles(artifact, source_verification)

        self.assertEqual(result["status"], "verified_for_reuse")
        self.assertEqual(result["cue_count"], 1)
        self.assertEqual(result["translation_accuracy"], "not_verified")

    def test_rejects_prior_manifest_from_different_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifact"
            artifact.mkdir()
            (artifact / "manifest.json").write_text(
                json.dumps({"input_sha256": "0" * 64}),
                encoding="utf-8",
            )
            source_verification = root / "source-verification.json"
            source_verification.write_text(
                json.dumps({
                    "sha256": SOURCE_SHA256,
                    "source_url": SOURCE_URL,
                    "event_identity_evidence_url": EVENT_EVIDENCE_URL,
                    "source_match_evidence_url": EVENT_EVIDENCE_URL,
                    "same_event_source_match_confirmed": True,
                    "reuse_rights_confirmed": True,
                }),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "not tied to the pinned"):
                verify_reusable_subtitles(artifact, source_verification)


if __name__ == "__main__":
    unittest.main()
