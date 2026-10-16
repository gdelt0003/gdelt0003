import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import verify_rose_garden_review as review
from scripts.process_full_video import (
    Cue,
    ROSE_GARDEN_SUBTITLE_LAYOUT,
    verify_cues,
    write_ass,
)


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "publish-rose-garden-review.yml"
)


class RoseGardenReviewWorkflowTests(unittest.TestCase):
    @staticmethod
    def synthetic_caption_frame(width, height):
        pixels = bytearray([255, 0, 0] * width * height)
        band_height = round(height * review.CAPTION_BAND_HEIGHT_PERCENT / 100)
        band_top = height - band_height
        for y in range(band_top, height):
            for x in range(width):
                offset = (y * width + x) * 3
                pixels[offset:offset + 3] = bytes((24, 24, 24))
        top_padding = round(
            height * review.CAPTION_BAND_TOP_PADDING_PERCENT / 100
        )
        text_top = band_top + top_padding + 2
        for y in range(text_top, text_top + 2):
            for x in range(width // 2 - 2, width // 2 + 2):
                offset = (y * width + x) * 3
                pixels[offset:offset + 3] = bytes((255, 216, 77))
        return bytes(pixels)

    def test_workflow_pins_cloud_source_and_only_deploys_after_render(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        render = workflow.split("  render:", maxsplit=1)[1].split(
            "\n  deploy-pages:", maxsplit=1
        )[0]

        self.assertIn("runs-on: ubuntu-latest", render)
        self.assertIn("GITHUB_REF", render)
        self.assertIn("refs/heads/main", render)
        for field in (
            "inputs.event_id",
            "inputs.event_title",
            "inputs.event_date",
            "inputs.source_url",
            "inputs.source_release_tag",
            "inputs.source_asset",
            "inputs.source_sha256",
            "inputs.requester_authorized_processing",
            "inputs.requester_authorized_publication",
            "inputs.rights_evidence_url",
        ):
            with self.subTest(field=field):
                self.assertIn(field, render)
        self.assertIn("gh release download rose-garden-lunch-source-2026-10-15", render)
        self.assertIn("RoseGardenLunch-IySF_8OArvw.mp4", render)
        self.assertIn(review.SOURCE_SHA256, (
            WORKFLOW.parents[2] / "scripts" / "verify_rose_garden_review.py"
        ).read_text(encoding="utf-8"))
        self.assertIn("process_full_video.py", render)
        self.assertIn("--asset-prefix RoseGardenLunch-IySF_8OArvw", render)
        self.assertIn(
            "--subtitle-layout rose-garden-fixed-caption-band",
            render,
        )
        self.assertIn("verify_operation_audit.py", render)
        self.assertIn("needs: render", workflow)
        self.assertIn("actions/deploy-pages@v4", workflow)
        self.assertIn("--prerelease", render)
        self.assertIn("test -s \"$RUNNER_TEMP/rose-garden-output/RoseGardenLunch-IySF_8OArvw-bilingual.mp4\"", render)
        self.assertIn("test -s \"$RUNNER_TEMP/rose-garden-output/manifest.json\"", render)
        self.assertIn("test -s \"$RUNNER_TEMP/rose-garden-output/operation-audit.json\"", render)
        self.assertIn(
            "test -s \"$RUNNER_TEMP/rose-garden-output/RoseGardenLunch-IySF_8OArvw.en-zh.ass\"",
            render,
        )
        self.assertIn("validate_caption_ass(manifest, output_dir)", (
            WORKFLOW.parents[2] / "scripts" / "verify_rose_garden_review.py"
        ).read_text(encoding="utf-8"))
        self.assertIn("name: rose-garden-review-run-${{ github.run_id }}", render)
        self.assertIn("Require every render and artifact stage to succeed before publication", render)
        self.assertIn("GITHUB_STEP_SUMMARY", render)
        self.assertIn("Collect render diagnostics", render)
        self.assertIn("Upload per-run diagnostics", render)
        for outcome in (
            "steps.checkout.outcome",
            "steps.setup_python.outcome",
            "steps.install_ffmpeg.outcome",
            "steps.input_validation.outcome",
            "steps.source_download.outcome",
            "steps.install_dependencies.outcome",
            "steps.render_video.outcome",
            "steps.validate_audit.outcome",
            "steps.finalize_manifest.outcome",
            "steps.validate_bundle.outcome",
            "steps.upload_bundle.outcome",
            "steps.publish_release.outcome",
            "steps.verify_public_asset.outcome",
            "steps.upload_diagnostics.outcome",
        ):
            with self.subTest(outcome=outcome):
                self.assertIn(outcome, render)
        self.assertIn("rose-garden-review-run-${{ github.run_id }}", render)
        self.assertIn("Failure/blocker:", render)
        deploy = workflow.split("  deploy-pages:", maxsplit=1)[1]
        self.assertIn("if: always()", deploy)
        self.assertIn("needs.render.result == 'success'", deploy)
        self.assertIn("Upload Pages artifact", deploy)
        self.assertIn("Deploy to GitHub Pages", deploy)
        self.assertIn("steps.deployment.outputs.page_url", deploy)
        self.assertIn("Write Pages deployment outcome summary", deploy)
        self.assertIn("Failure/blocker:", deploy)

    def test_dispatch_inputs_are_exact_and_rights_evidence_does_not_claim_review(self):
        defaults = {
            "event_id": review.EVENT_ID,
            "event_title": review.EVENT_TITLE,
            "event_date": review.EVENT_DATE,
            "source_url": review.SOURCE_URL,
            "source_release_tag": review.SOURCE_RELEASE_TAG,
            "source_asset": review.SOURCE_ASSET,
            "source_sha256": review.SOURCE_SHA256,
            "rights_evidence_url": "https://www.whitehouse.gov/copyright/",
        }
        review.validate_dispatch_inputs(**defaults)
        defaults["source_sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "source_sha256"):
            review.validate_dispatch_inputs(**defaults)
        defaults["source_sha256"] = review.SOURCE_SHA256
        defaults["rights_evidence_url"] = "http://example.com/rights"
        with self.assertRaisesRegex(RuntimeError, "HTTPS"):
            review.validate_dispatch_inputs(**defaults)

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
            cue = Cue(1, 3, "Hello, everybody.", "大家好。")
            ass_name = f"{review.ASSET_PREFIX}.en-zh.ass"
            write_ass(
                output_dir / ass_name,
                [cue],
                1920,
                1080,
                layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
            )
            subtitles = [
                f"{review.ASSET_PREFIX}.en.srt",
                f"{review.ASSET_PREFIX}.zh-Hans.srt",
                f"{review.ASSET_PREFIX}.en-zh.srt",
                ass_name,
            ]
            (output_dir / subtitles[0]).write_text(
                "1\n00:00:01,000 --> 00:00:03,000\nHello, everybody.\n",
                encoding="utf-8",
            )
            (output_dir / subtitles[1]).write_text(
                "1\n00:00:01,000 --> 00:00:03,000\n大家好。\n",
                encoding="utf-8",
            )
            (output_dir / subtitles[2]).write_text("subtitle", encoding="utf-8")
            readability = verify_cues(
                [cue],
                duration=42.5,
                width=1920,
                height=1080,
                layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
            )["subtitle_readability"]
            manifest = {
                "source_video": review.SOURCE_ASSET,
                "video_file": f"{review.ASSET_PREFIX}-bilingual.mp4",
                "duration_seconds": 42.5,
                "resolution": "1920x1080",
                "languages": ["en", "zh-Hans"],
                "subtitle_files": subtitles,
                "subtitle_ass_file": ass_name,
                "subtitle_ass_sha256": hashlib.sha256(
                    (output_dir / ass_name).read_bytes()
                ).hexdigest(),
                "quality_checks": {
                    "subtitle_readability": readability,
                },
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
                    "render_caption_geometry_frame",
                    side_effect=lambda _path, width, height, _start: (
                        self.synthetic_caption_frame(width, height)
                    ),
                ),
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
        self.assertEqual(
            finalized["event_identity"]["review_status"],
            "pending",
        )
        self.assertEqual(
            finalized["rendered_video"]["sha256"],
            hashlib.sha256(b"video").hexdigest(),
        )
        self.assertEqual(finalized["rendered_video"]["size_bytes"], 5)
        self.assertEqual(
            finalized["rights_review"]["requester_authorization"],
            "confirmed_for_this_run",
        )
        self.assertEqual(finalized["public_review"]["independent_rights_review"], "pending")
        self.assertEqual(finalized["public_review"]["source_frame_review"], "pending")
        self.assertEqual(finalized["public_review"]["source_audio_asr_review"], "pending")
        self.assertEqual(finalized["public_review"]["translation_review"], "pending")
        self.assertEqual(finalized["public_review"]["final_release_approval"], "not_granted")
        self.assertEqual(
            finalized["quality_checks"]["subtitle_readability"][
                "caption_ass_validation"
            ]["status"],
            "passed",
        )
        self.assertEqual(
            finalized["source_graphics_occlusion"][
                "caption_band_masks_source_lower_third_in_derivative"
            ],
            True,
        )
        self.assertEqual(
            finalized["source_graphics_occlusion"]["visual_review"],
            "pending",
        )
        self.assertEqual(
            finalized["quality_checks"]["subtitle_readability"][
                "caption_ass_validation"
            ]["synthetic_libass_geometry_render"],
            "passed",
        )

    def test_caption_layout_gate_accepts_the_bounded_rose_profile(self):
        readability = verify_cues(
            [Cue(1, 3, "Hello, everybody.", "大家好。")],
            duration=10,
            width=1920,
            height=1080,
            layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
        )["subtitle_readability"]
        review.validate_caption_layout(
            {"quality_checks": {"subtitle_readability": readability}}
        )

    def test_caption_layout_gate_rejects_missing_or_unsafe_contracts(self):
        valid = verify_cues(
            [Cue(1, 3, "Hello, everybody.", "大家好。")],
            duration=10,
            width=1920,
            height=1080,
            layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
        )["subtitle_readability"]
        mutations = (
            ("default profile", "layout_profile", "default", "required Rose Garden"),
            ("null band", "caption_region_height_percent", None, "height"),
            ("small English font", "english_font_px", 40, "20% larger"),
            ("missing occlusion record", "caption_band_occlusion", None, "occlusion"),
        )
        for label, field, value, message in mutations:
            with self.subTest(label=label):
                readability = dict(valid)
                readability[field] = value
                with self.assertRaisesRegex(RuntimeError, message):
                    review.validate_caption_layout(
                        {"quality_checks": {"subtitle_readability": readability}}
                    )

    def test_caption_ass_gate_rejects_a_manifest_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cue = Cue(1, 3, "Hello, everybody.", "大家好。")
            ass_name = f"{review.ASSET_PREFIX}.en-zh.ass"
            write_ass(
                root / ass_name,
                [cue],
                1920,
                1080,
                layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
            )
            manifest = {
                "subtitle_ass_file": ass_name,
                "subtitle_ass_sha256": "0" * 64,
                "resolution": "1920x1080",
            }
            with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                review.validate_caption_ass(manifest, root)

    def test_rendered_caption_bounds_reject_out_of_band_text(self):
        frame = self.synthetic_caption_frame(20, 20)
        bounds = review.inspect_caption_geometry_frame(frame, 20, 20)
        self.assertEqual(bounds["band_top"], 14)
        self.assertGreaterEqual(bounds["top"], bounds["band_top"])
        self.assertEqual(bounds["bottom"], 17)

        pixels = bytearray(frame)
        offset = (10 * 20 + 1) * 3
        pixels[offset:offset + 3] = bytes((255, 255, 255))
        with self.assertRaisesRegex(RuntimeError, "safe band"):
            review.inspect_caption_geometry_frame(bytes(pixels), 20, 20)


if __name__ == "__main__":
    unittest.main()
