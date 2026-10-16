import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import verify_rose_garden_review as review


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "publish-rose-garden-review.yml"
)


class RoseGardenReviewWorkflowTests(unittest.TestCase):
    def test_workflow_pins_cloud_source_and_only_deploys_after_render(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        render = workflow.split("  render:", maxsplit=1)[1].split(
            "\n  deploy-pages:", maxsplit=1
        )[0]

        self.assertIn("runs-on: ubuntu-latest", render)
        self.assertIn("GITHUB_REF", render)
        self.assertIn("refs/heads/main", render)
        self.assertIn("inputs.authorize_public_review", render)
        self.assertIn("gh release download rose-garden-lunch-source-2026-10-15", render)
        self.assertIn("RoseGardenLunch-IySF_8OArvw.mp4", render)
        self.assertIn(review.SOURCE_SHA256, (
            WORKFLOW.parents[2] / "scripts" / "verify_rose_garden_review.py"
        ).read_text(encoding="utf-8"))
        self.assertIn("process_full_video.py", render)
        self.assertIn("--asset-prefix RoseGardenLunch-IySF_8OArvw", render)
        self.assertIn("verify_operation_audit.py", render)
        self.assertIn("needs: render", workflow)
        self.assertIn("actions/deploy-pages@v4", workflow)
        self.assertIn("--prerelease", render)
        audit_upload = render.split(
            "Preserve operation audit for this workflow run", maxsplit=1
        )[1]
        self.assertIn("operation-audit.json", audit_upload)
        self.assertNotIn("*-bilingual.mp4", audit_upload)

    def test_source_verification_checks_exact_asset_and_probe_requirements(self):
        self.assertEqual(review.SOURCE_SIZE_BYTES, 1_030_142_647)
        self.assertEqual(
            review.SOURCE_SHA256,
            "e0b04fb669fd0d09f1492de6a3160bb3b6dae2e3e396be77372f4b5635da5f73",
        )
        valid_probe = {
            "format": {"duration": "42.5"},
            "streams": [
                {"codec_type": "video", "width": 1920, "height": 1080},
                {"codec_type": "audio"},
            ],
        }
        self.assertEqual(review.validate_probe(valid_probe, label="Source"), (42.5, 1920, 1080))

        for invalid_probe, message in (
            (
                {
                    "format": {"duration": "42.5"},
                    "streams": [
                        {"codec_type": "video", "width": 1280, "height": 720},
                        {"codec_type": "audio"},
                    ],
                },
                "below the 1920x1080 minimum",
            ),
            (
                {
                    "format": {"duration": "42.5"},
                    "streams": [{"codec_type": "video", "width": 1920, "height": 1080}],
                },
                "no audio stream",
            ),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(
                RuntimeError, message
            ):
                review.validate_probe(invalid_probe, label="Source")

    def test_source_hash_is_checked_before_accepting_probe_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / review.SOURCE_ASSET
            source.write_bytes(b"pinned test source")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            probe = {
                "format": {"duration": "42.5"},
                "streams": [
                    {"codec_type": "video", "width": 1920, "height": 1080},
                    {"codec_type": "audio"},
                ],
            }
            with (
                patch.object(review, "SOURCE_SIZE_BYTES", source.stat().st_size),
                patch.object(review, "SOURCE_SHA256", digest),
                patch.object(review, "probe_media", return_value=probe),
            ):
                details = review.verify_source(source)
        self.assertEqual(details["sha256"], digest)
        self.assertEqual((details["width"], details["height"]), (1920, 1080))

    def test_final_manifest_records_source_hash_and_pending_review_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / review.SOURCE_ASSET
            source.write_bytes(b"unused test input")
            output_dir = root / "output"
            output_dir.mkdir()
            (output_dir / "operation-audit.json").write_text("{}", encoding="utf-8")
            (output_dir / f"{review.ASSET_PREFIX}-bilingual.mp4").write_bytes(b"video")
            subtitles = [
                f"{review.ASSET_PREFIX}.en.srt",
                f"{review.ASSET_PREFIX}.zh-Hans.srt",
                f"{review.ASSET_PREFIX}.en-zh.srt",
            ]
            for subtitle in subtitles:
                (output_dir / subtitle).write_text("subtitle", encoding="utf-8")
            manifest = {
                "source_video": review.SOURCE_ASSET,
                "video_file": f"{review.ASSET_PREFIX}-bilingual.mp4",
                "duration_seconds": 42.5,
                "resolution": "1920x1080",
                "languages": ["en", "zh-Hans"],
                "subtitle_files": subtitles,
            }
            (output_dir / "manifest.json").write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )
            source_details = {
                "duration_seconds": 42.5,
                "width": 1920,
                "height": 1080,
                "size_bytes": review.SOURCE_SIZE_BYTES,
                "sha256": review.SOURCE_SHA256,
            }
            with (
                patch.object(review, "verify_source", return_value=source_details),
                patch.object(
                    review,
                    "probe_media",
                    return_value={
                        "format": {"duration": "42.5"},
                        "streams": [
                            {"codec_type": "video", "width": 1920, "height": 1080},
                            {"codec_type": "audio"},
                        ],
                    },
                ),
            ):
                finalized = review.finalize_review_manifest(source, output_dir)

        self.assertEqual(
            finalized["source_provenance"]["sha256"],
            review.SOURCE_SHA256,
        )
        self.assertEqual(
            finalized["public_review"]["status"],
            "public_external_review_draft",
        )
        self.assertEqual(finalized["public_review"]["independent_rights_review"], "pending")
        self.assertEqual(finalized["public_review"]["source_frame_review"], "pending")
        self.assertEqual(finalized["public_review"]["source_audio_asr_review"], "pending")
        self.assertEqual(finalized["public_review"]["translation_review"], "pending")
        self.assertEqual(finalized["public_review"]["final_release_approval"], "not_granted")


if __name__ == "__main__":
    unittest.main()
