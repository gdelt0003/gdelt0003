import hashlib
import base64
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import verify_rose_garden_review as review
from scripts.process_full_video import (
    Cue,
    ROSE_GARDEN_SUBTITLE_LAYOUT,
    reflow_rose_garden_cues,
    require_trusted_mask_review,
    srt_text,
    verify_cues,
    write_ass,
)
from scripts.verify_rose_garden_review import user_still_source_graphics_regions


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "publish-rose-garden-review.yml"
)
PRIVATE_RENDER_WORKFLOW = WORKFLOW.with_name("render-rose-garden-private.yml")


class RoseGardenReviewWorkflowTests(unittest.TestCase):
    SOURCE_GRAPHICS = [
        {
            "label": "synthetic-source-lower-third-test-fixture",
            "human_verified": True,
            "x": 0.1,
            "y": 0.68,
            "width": 0.8,
            "height": 0.3,
        }
    ]

    @staticmethod
    def synthetic_caption_frame(width, height, mask=None):
        pixels = bytearray([255, 0, 0] * width * height)
        mask = mask or {
            "left": 190,
            "top": 732,
            "right": 1730,
            "bottom": 1060,
        }
        for y in range(mask["top"], mask["bottom"]):
            for x in range(mask["left"], mask["right"]):
                offset = (y * width + x) * 3
                pixels[offset:offset + 3] = bytes((24, 24, 24))
        text_top = mask["top"] + 20
        for y in range(text_top, text_top + 2):
            for x in range(width // 2 - 2, width // 2 + 2):
                offset = (y * width + x) * 3
                pixels[offset:offset + 3] = bytes((255, 255, 255))
        return bytes(pixels)

    def test_validator_imports_as_script_and_package(self):
        repo_root = Path(__file__).resolve().parents[1]
        script_path = repo_root / "scripts" / "verify_rose_garden_review.py"
        for argument in ("--help", "--validate-private-dispatch-inputs"):
            with self.subTest(argument=argument):
                script_result = subprocess.run(
                    [sys.executable, "-S", str(script_path), argument],
                    cwd=repo_root,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(script_result.returncode, 0, script_result.stderr)

        package_result = subprocess.run(
            [
                sys.executable,
                "-S",
                "-c",
                (
                    "import sys; "
                    "import scripts.verify_rose_garden_review; "
                    "assert 'scripts.process_full_video' not in sys.modules"
                ),
            ],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(package_result.returncode, 0, package_result.stderr)

    def build_caption_ass_manifest(self, root, cues, overflow_records):
        regions = user_still_source_graphics_regions(1920, 1080)
        readability = verify_cues(
            cues,
            duration=400,
            width=1920,
            height=1080,
            layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
            caption_position="mask-lower-third",
            source_graphics_regions=regions,
            occlusion_exception_authorized=True,
            mask_padding_px_per_edge=2,
            allow_unverified_estimate=True,
            caption_overflow_records=overflow_records,
        )["subtitle_readability"]
        ass_name = f"{review.ASSET_PREFIX}.en-zh.ass"
        write_ass(
            root / ass_name,
            cues,
            1920,
            1080,
            layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
            caption_position="mask-lower-third",
            source_graphics_regions=regions,
            occlusion_exception_authorized=True,
            mask_padding_px_per_edge=2,
            allow_unverified_estimate=True,
            caption_overflow_records=overflow_records,
        )
        (root / f"{review.ASSET_PREFIX}.en.srt").write_text(
            srt_text(cues, "en"),
            encoding="utf-8",
        )
        (root / f"{review.ASSET_PREFIX}.zh-Hans.srt").write_text(
            srt_text(cues, "zh"),
            encoding="utf-8",
        )
        return {
            "subtitle_ass_file": ass_name,
            "subtitle_ass_sha256": hashlib.sha256(
                (root / ass_name).read_bytes()
            ).hexdigest(),
            "resolution": "1920x1080",
            "frame_review_mode": "unverified-review-draft",
            "subtitle_overflow_exceptions": overflow_records,
            "quality_checks": {
                "subtitle_readability": readability,
            },
        }

    @staticmethod
    def sign_frame_review(frame_record, directory):
        root = Path(directory)
        private_key = root / "reviewer"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)],
            check=True,
            capture_output=True,
        )
        public_key = private_key.with_suffix(".pub").read_text(encoding="utf-8").split()
        allowed_signers = root / "allowed_signers"
        allowed_signers.write_text(
            f'{frame_record["reviewer_identity"]} '
            f'namespaces="{review.FRAME_REVIEW_SIGNATURE_NAMESPACE}" '
            f"{public_key[0]} {public_key[1]}\n",
            encoding="utf-8",
        )
        payload = root / "frame-review.json"
        payload.write_bytes(review.canonical_frame_review_payload(frame_record))
        subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "sign",
                "-f",
                str(private_key),
                "-n",
                review.FRAME_REVIEW_SIGNATURE_NAMESPACE,
                str(payload),
            ],
            check=True,
            capture_output=True,
        )
        signature = base64.b64encode(Path(f"{payload}.sig").read_bytes()).decode("ascii")
        return allowed_signers, signature

    @staticmethod
    def sign_frame_review(frame_record, directory):
        root = Path(directory)
        private_key = root / "reviewer"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)],
            check=True,
            capture_output=True,
        )
        public_key = private_key.with_suffix(".pub").read_text(encoding="utf-8").split()
        allowed_signers = root / "allowed_signers"
        allowed_signers.write_text(
            f'{frame_record["reviewer_identity"]} '
            f'namespaces="{review.FRAME_REVIEW_SIGNATURE_NAMESPACE}" '
            f"{public_key[0]} {public_key[1]}\n",
            encoding="utf-8",
        )
        payload = root / "review.json"
        payload.write_bytes(review.canonical_frame_review_payload(frame_record))
        subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "sign",
                "-f",
                str(private_key),
                "-n",
                review.FRAME_REVIEW_SIGNATURE_NAMESPACE,
                str(payload),
            ],
            check=True,
            capture_output=True,
        )
        return (
            allowed_signers,
            base64.b64encode(Path(f"{payload}.sig").read_bytes()).decode("ascii"),
        )

    def test_render_workflow_only_builds_private_artifacts(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        render = workflow.split("  render:", maxsplit=1)[1]

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
            "inputs.reuse_rights_confirmed",
            "inputs.event_identity_evidence_url",
            "inputs.exact_event_match_confirmed",
            "inputs.event_match_evidence_url",
            "inputs.event_time_timezone_evidence_url",
            "inputs.source_lineage_evidence_url",
            "inputs.source_frame_review_record_json",
            "inputs.source_frame_review_signature",
            "inputs.frame_review_mode",
            "inputs.caption_position",
            "inputs.caption_safe_region_reviewed",
            "inputs.source_graphics_regions_json",
            "inputs.rose_mask_authorized",
            "inputs.mask_padding_px_per_edge",
        ):
            with self.subTest(field=field):
                self.assertIn(field, render)
        self.assertIn("download_rose_garden_source_asset.py", render)
        self.assertIn("RoseGardenLunch-IySF_8OArvw.mp4", render)
        self.assertIn(review.SOURCE_SHA256, (
            WORKFLOW.parents[2] / "scripts" / "verify_rose_garden_review.py"
        ).read_text(encoding="utf-8"))
        self.assertIn("process_full_video.py", render)
        self.assertIn("--asset-prefix RoseGardenLunch-IySF_8OArvw", render)
        self.assertIn(
            "--subtitle-layout rose-garden-source-aware-bilingual",
            render,
        )
        for arg in (
            "--caption-position",
            "--source-graphics-regions-json",
            "--mask-padding-px-per-edge",
            "--occlusion-exception-authorized",
            "--validate-layout-inputs",
            "--validate-review-gates",
            "--caption-position",
            "--source-frame-review-record-json",
            "--source-frame-review-signature",
            "--frame-review-mode",
        ):
            self.assertIn(arg, render)
        self.assertIn("verify_operation_audit.py", render)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("gh release upload", workflow)
        self.assertIn("actions/deploy-pages@v4", workflow)
        self.assertIn("upload-pages-artifact", workflow)
        self.assertIn("deploy-review-preview:", workflow)
        preview = workflow.split("  deploy-review-preview:", maxsplit=1)[1]
        self.assertIn("needs: render", preview)
        self.assertIn("needs.render.result == 'success'", preview)
        self.assertIn("prepare_rose_garden_review_preview.py", preview)
        self.assertIn("Five distinct post-build HTTPS evidence URLs", preview)
        self.assertIn("contents: write", workflow)
        self.assertIn("--event-identity-evidence-url", render)
        self.assertIn("--event-match-evidence-url", render)
        self.assertIn("--event-time-timezone-evidence-url", render)
        self.assertIn("--source-lineage-evidence-url", render)
        self.assertIn("--exact-event-match-confirmed", render)
        self.assertIn("--reuse-rights-confirmed", render)
        self.assertLess(
            render.index("--validate-dispatch-inputs"),
            render.index("download_rose_garden_source_asset.py"),
        )
        self.assertLess(
            render.index("--validate-dispatch-inputs"),
            render.index("id: source_download"),
        )
        self.assertLess(
            render.index("--validate-dispatch-inputs"),
            render.index("id: render_video"),
        )
        self.assertLess(
            render.index("--validate-review-gates"),
            render.index("download_rose_garden_source_asset.py"),
        )
        rights_input = workflow.split("      rights_evidence_url:", maxsplit=1)[1].split(
            "\n      independent_rights_review_passed:", maxsplit=1
        )[0]
        self.assertIn("required: true", rights_input)
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
            "steps.upload_diagnostics.outcome",
        ):
            with self.subTest(outcome=outcome):
                self.assertIn(outcome, render)
        self.assertIn("rose-garden-review-run-${{ github.run_id }}", render)
        self.assertIn("Failure/blocker:", render)
        self.assertIn("private Actions artifact plus a separate public Pages review preview", render)

    def test_private_render_dispatch_only_uploads_artifact_and_never_publishes(self):
        workflow = PRIVATE_RENDER_WORKFLOW.read_text(encoding="utf-8")
        lower = workflow.lower()

        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("GITHUB_REF", workflow)
        self.assertIn("--validate-private-dispatch-inputs", workflow)
        self.assertIn("--caption-box \"$CAPTION_BOX\"", workflow)
        self.assertIn("requester_authorized_processing", workflow)
        self.assertNotIn("requester_authorized_publication", workflow)
        for field in (
            "inputs.event_id",
            "inputs.event_title",
            "inputs.event_date",
            "inputs.source_url",
            "inputs.source_release_tag",
            "inputs.source_asset",
            "inputs.source_sha256",
            "inputs.rights_evidence_url",
            "inputs.event_identity_evidence_url",
            "inputs.event_match_evidence_url",
            "inputs.caption_box",
            "inputs.source_frame_review_record_json",
            "inputs.source_frame_review_signature",
            "inputs.frame_review_mode",
        ):
            with self.subTest(field=field):
                self.assertIn(field, workflow)
        self.assertIn("permissions:\n  contents: write", workflow)
        self.assertIn("GH_TOKEN: ${{ github.token }}", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("retention-days: 30", workflow)
        self.assertNotIn("inputs.reuse_rights_confirmed", workflow)
        self.assertNotIn("inputs.exact_event_match_confirmed", workflow)
        self.assertNotIn("--exact-event-match-confirmed", workflow)
        self.assertNotIn("--reuse-rights-confirmed", workflow)
        self.assertNotIn("actions/deploy-pages", lower)
        self.assertNotIn("upload-pages-artifact", lower)
        self.assertNotIn("pages: write", lower)
        self.assertNotIn("gh release", lower)
        self.assertNotIn("create release", lower)
        self.assertNotIn("deploy-pages", lower)
        rights_input = workflow.split("      rights_evidence_url:", maxsplit=1)[1].split(
            "\n      event_identity_evidence_url:", maxsplit=1
        )[0]
        self.assertIn('default: ""', rights_input)
        self.assertIn("required: false", rights_input)

    def test_optional_evidence_inputs_can_be_omitted_from_workflow_dispatch(self):
        inputs = WORKFLOW.read_text(encoding="utf-8").split("\njobs:", maxsplit=1)[0]
        for field in (
            "event_time_timezone_evidence_url",
            "source_lineage_evidence_url",
            "source_frame_review_signature",
        ):
            match = re.search(
                rf"(?ms)^      {field}:\n(?P<body>.*?)(?=^      [a-z_][a-z0-9_]*:|\Z)",
                inputs,
            )
            self.assertIsNotNone(match)
            block = match.group("body")
            with self.subTest(field=field):
                self.assertIn('default: ""', block)
                self.assertIn("required: false", block)

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
        private_render = defaults | {
            "rights_evidence_url": "",
            "event_identity_evidence_url": "not-a-verified-reference",
            "event_match_evidence_url": "file://local/match",
        }
        review.validate_dispatch_inputs(**private_render)
        self.assertEqual(private_render["rights_evidence_url"], "")
        self.assertEqual(
            review.validate_review_gates(
                caption_position="top",
                independent_rights_review_passed=False,
                event_match_review_passed=False,
                event_time_timezone_review_passed=False,
                source_lineage_review_passed=False,
                source_frame_review_record_json="{}",
                source_graphics_regions_json="[]",
                dispatch_actor="publisher",
                rights_evidence_url="http://example.org/rights",
                event_match_evidence_url="file://local/match",
                event_time_timezone_evidence_url="",
                source_lineage_evidence_url="",
                frame_review_mode="unverified-review-draft",
                private_render=True,
            )["source_frame_review"],
            "pending",
        )
        processing = defaults | {
            "rights_evidence_url": "https://example.org/reuse-rights",
            "event_identity_evidence_url": "https://example.org/event-identity",
            "event_match_evidence_url": "https://example.org/exact-match",
            "exact_event_match_confirmed": True,
            "reuse_rights_confirmed": True,
            "require_processing_evidence": True,
        }
        review.validate_dispatch_inputs(**processing)
        for field, replacement, message in (
            ("event_identity_evidence_url", "", "event identity"),
            ("event_match_evidence_url", "http://example.org/match", "HTTPS"),
            ("exact_event_match_confirmed", False, "exact-event match confirmation"),
            ("reuse_rights_confirmed", False, "reuse-rights confirmation"),
            ("rights_evidence_url", "", "source-specific reuse rights"),
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(RuntimeError, message):
                    review.validate_dispatch_inputs(
                        **(processing | {field: replacement})
                    )
        defaults["source_sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "source_sha256"):
            review.validate_dispatch_inputs(**defaults)
        processing["rights_evidence_url"] = "http://example.com/rights"
        with self.assertRaisesRegex(RuntimeError, "HTTPS"):
            review.validate_dispatch_inputs(**processing)

    def test_layout_dispatch_is_fail_closed_for_missing_bbox_review_or_mask_auth(self):
        bbox = json.dumps(self.SOURCE_GRAPHICS)
        valid = {
            "caption_position": "mask-lower-third",
            "caption_safe_region_reviewed": True,
            "source_graphics_regions_json": bbox,
            "rose_mask_authorized": True,
            "mask_padding_px_per_edge": 2,
        }
        self.assertEqual(review.validate_layout_inputs(**valid), self.SOURCE_GRAPHICS)
        failures = (
            ({"source_graphics_regions_json": "[]"}, "real production source-banner BBox"),
            ({"caption_safe_region_reviewed": False}, "human review"),
            ({"rose_mask_authorized": False}, "explicit Rose exception"),
            ({"mask_padding_px_per_edge": 0}, "integer from 1 to 5"),
            ({"mask_padding_px_per_edge": 6}, "integer from 1 to 5"),
            (
                {
                    "source_graphics_regions_json": bbox.replace(
                        '"human_verified": true', '"human_verified": false'
                    )
                },
                "not human-verified",
            ),
            (
                {
                    "source_graphics_regions_json": bbox.replace(
                        '"x": 0.1', '"x": 0.9'
                    )
                },
                "outside frame bounds",
            ),
        )
        for mutation, message in failures:
            with self.subTest(mutation=mutation), self.assertRaisesRegex(
                RuntimeError, message
            ):
                review.validate_layout_inputs(**(valid | mutation))

    def test_unverified_still_estimate_renders_pending_draft_without_signature(self):
        layout = {
            "caption_position": "mask-lower-third",
            "caption_safe_region_reviewed": False,
            "source_graphics_regions_json": "[]",
            "rose_mask_authorized": True,
            "mask_padding_px_per_edge": 2,
            "frame_review_mode": "unverified-review-draft",
        }
        self.assertEqual(review.validate_layout_inputs(**layout), [])
        with self.assertRaisesRegex(RuntimeError, "exactly 2 px"):
            review.validate_layout_inputs(
                **(layout | {"mask_padding_px_per_edge": 3})
            )

        review_inputs = {
            "caption_position": "mask-lower-third",
            "independent_rights_review_passed": False,
            "event_match_review_passed": False,
            "event_time_timezone_review_passed": False,
            "source_lineage_review_passed": False,
            "source_frame_review_record_json": "{}",
            "source_frame_review_signature": "",
            "source_graphics_regions_json": "[]",
            "dispatch_actor": "publisher",
            "rights_evidence_url": "",
            "event_match_evidence_url": "",
            "event_time_timezone_evidence_url": "",
            "source_lineage_evidence_url": "",
            "frame_review_mode": "unverified-review-draft",
        }
        pending_review = {
            "source_frame_review": "pending",
            "production_bbox_input": "false",
        }
        self.assertEqual(
            review.validate_review_gates(**review_inputs),
            pending_review,
        )
        with self.assertRaisesRegex(RuntimeError, "must not include"):
            review.validate_review_gates(
                **(review_inputs | {"source_frame_review_signature": "signature"})
            )

        with patch.object(
            review,
            "file_sha256_and_size",
            return_value=(review.SOURCE_SHA256, review.SOURCE_SIZE_BYTES),
        ):
            self.assertEqual(
                require_trusted_mask_review(
                    "mask-lower-third",
                    source_path=Path("pinned-source.mp4"),
                    source_width=1920,
                    source_height=1080,
                    source_duration=2193.261,
                    source_frame_review_record_json="{}",
                    source_frame_review_signature="",
                    source_graphics_regions_json="[]",
                    dispatch_actor="publisher",
                    frame_review_mode="unverified-review-draft",
                ),
                {
                    "source_frame_review": "pending",
                    "production_bbox_input": "false",
                    "measurement_status": "unverified_still_estimate",
                },
            )

        regions = review.user_still_source_graphics_regions(1920, 1080)
        cue = Cue(1, 3, "Hello, everybody.", "大家好。")
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            ass_name = f"{review.ASSET_PREFIX}.en-zh.ass"
            ass_path = output_dir / ass_name
            write_ass(
                ass_path,
                [cue],
                1920,
                1080,
                layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
                caption_position="mask-lower-third",
                source_graphics_regions=regions,
                occlusion_exception_authorized=True,
                mask_padding_px_per_edge=2,
                allow_unverified_estimate=True,
            )
            readability = verify_cues(
                [cue],
                duration=10,
                width=1920,
                height=1080,
                layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
                caption_position="mask-lower-third",
                caption_safe_region_reviewed=False,
                source_graphics_regions=regions,
                occlusion_exception_authorized=True,
                mask_padding_px_per_edge=2,
                allow_unverified_estimate=True,
            )["subtitle_readability"]
            still_measurement = review.user_provided_still_measurement()
            manifest = {
                "frame_review_mode": "unverified-review-draft",
                "source_frame_measurement": still_measurement
                | {"review_status": "pending"},
                "user_estimated_banner_bbox": still_measurement[
                    "user_estimated_banner_bbox"
                ],
                "resolution": "1920x1080",
                "subtitle_ass_file": ass_name,
                "subtitle_ass_sha256": hashlib.sha256(
                    ass_path.read_bytes()
                ).hexdigest(),
                "quality_checks": {"subtitle_readability": readability},
            }
            review.validate_caption_layout(
                manifest,
                expected_source_sha256=review.SOURCE_SHA256,
            )
            (output_dir / f"{review.ASSET_PREFIX}.en.srt").write_text(
                "1\n00:00:01,000 --> 00:00:03,000\nHello, everybody.\n",
                encoding="utf-8",
            )
            (output_dir / f"{review.ASSET_PREFIX}.zh-Hans.srt").write_text(
                "1\n00:00:01,000 --> 00:00:03,000\n大家好。\n",
                encoding="utf-8",
            )
            mask = readability["caption_band_occlusion"]["mask_bbox_px"]
            with patch.object(
                review,
                "render_caption_geometry_frame",
                side_effect=lambda _path, width, height, _start: (
                    self.synthetic_caption_frame(width, height, mask)
                ),
            ), patch.object(
                review,
                "_process_full_video_module",
                wraps=review._process_full_video_module,
            ) as load_renderer:
                ass_validation = review.validate_caption_ass(
                    manifest,
                    output_dir,
                )
            load_renderer.assert_called_once_with()

        self.assertEqual(ass_validation["visual_frame_review"], "pending")
        source_review = readability["source_graphics_review"]
        self.assertEqual(source_review["measurement_source"], "user_provided_still")
        self.assertEqual(
            source_review["measurement_status"],
            "unverified_still_estimate",
        )
        self.assertIs(source_review["production_bbox_input"], False)
        self.assertEqual(source_review["source_timecode"], "not_verified")
        self.assertEqual(source_review["source_provenance"], "not_verified")
        self.assertEqual(source_review["review_status"], "pending")
        self.assertEqual(
            readability["caption_band_occlusion"]["mask_bbox_px"],
            {
                "left": 66,
                "top": 883,
                "right": 1852,
                "bottom": 1022,
                "width": 1786,
                "height": 139,
                "mask_padding_px_per_edge": 2,
            },
        )

    def test_review_gates_allow_nonmask_layout_with_frame_review_pending(self):
        frame_record = {
            "reviewer_identity": "reviewer@example.org",
            "reviewed_at": "2026-10-16T02:00:00Z",
            "source_timecode": "00:10:30.000",
            "source_resolution": {"width": 1920, "height": 1080},
            "source_banner_bbox_px": {
                "left": 192,
                "top": 734,
                "right": 1728,
                "bottom": 1058,
            },
            "evidence_ref": "https://example.org/review/123",
            "source_sha256": review.SOURCE_SHA256,
        }
        values = {
            "caption_position": "top",
            "independent_rights_review_passed": True,
            "event_match_review_passed": True,
            "event_time_timezone_review_passed": True,
            "source_lineage_review_passed": True,
            "source_frame_review_record_json": json.dumps(frame_record),
            "source_graphics_regions_json": json.dumps(self.SOURCE_GRAPHICS),
            "dispatch_actor": "publisher",
            "rights_evidence_url": "https://example.org/rights",
            "event_match_evidence_url": "https://example.org/event-match",
            "event_time_timezone_evidence_url": "https://example.org/event-time",
            "source_lineage_evidence_url": "https://example.org/lineage",
        }
        layout = {
            "caption_position": "top",
            "caption_safe_region_reviewed": False,
            "source_graphics_regions_json": "[]",
            "rose_mask_authorized": False,
            "mask_padding_px_per_edge": 2,
        }
        self.assertEqual(review.validate_layout_inputs(**layout), [])
        self.assertEqual(
            review.validate_review_gates(
                **(values | {"source_frame_review_record_json": "{}"})
            ),
            {
                "source_frame_review": "pending",
                "production_bbox_input": "false",
            },
        )

        pending = values | {
            "independent_rights_review_passed": False,
            "event_match_review_passed": False,
            "event_time_timezone_review_passed": False,
            "source_lineage_review_passed": False,
            "rights_evidence_url": "",
            "event_match_evidence_url": "",
            "event_time_timezone_evidence_url": "",
            "source_lineage_evidence_url": "",
        }
        self.assertEqual(
            review.validate_review_gates(
                **(pending | {"source_frame_review_record_json": "{}"})
            ),
            {
                "source_frame_review": "pending",
                "production_bbox_input": "false",
            },
        )

    def test_mask_review_gate_requires_bbox_and_keeps_untrusted_review_pending(self):
        frame_record = {
            "reviewer_identity": "reviewer@example.org",
            "reviewed_at": "2026-10-16T02:00:00Z",
            "source_timecode": "00:10:30.000",
            "source_resolution": {"width": 1920, "height": 1080},
            "source_banner_bbox_px": {
                "left": 192,
                "top": 734,
                "right": 1728,
                "bottom": 1058,
            },
            "evidence_ref": "https://example.org/review/123",
            "source_sha256": review.SOURCE_SHA256,
        }
        values = {
            "caption_position": "mask-lower-third",
            "independent_rights_review_passed": True,
            "event_match_review_passed": True,
            "event_time_timezone_review_passed": True,
            "source_lineage_review_passed": True,
            "source_frame_review_record_json": "{}",
            "source_graphics_regions_json": json.dumps(self.SOURCE_GRAPHICS),
            "dispatch_actor": "publisher",
            "rights_evidence_url": "https://example.org/rights",
            "event_match_evidence_url": "https://example.org/event-match",
            "event_time_timezone_evidence_url": "https://example.org/event-time",
            "source_lineage_evidence_url": "https://example.org/lineage",
        }
        with self.assertRaisesRegex(RuntimeError, "reviewer, timestamp"):
            review.validate_review_gates(**values)

        values["source_frame_review_record_json"] = json.dumps(frame_record)
        with self.assertRaisesRegex(RuntimeError, "base64 OpenSSH signature"):
            review.validate_review_gates(**values)

        out_of_bounds = dict(frame_record)
        out_of_bounds["source_banner_bbox_px"] = {
            **frame_record["source_banner_bbox_px"],
            "right": 2000,
        }
        with self.assertRaisesRegex(RuntimeError, "out of bounds"):
            review.validate_review_gates(
                **(
                    values
                    | {"source_frame_review_record_json": json.dumps(out_of_bounds)}
                )
            )

        same_reviewer = dict(frame_record)
        with self.assertRaisesRegex(RuntimeError, "other than the dispatcher"):
            review.validate_review_gates(
                **(
                    values
                    | {
                        "source_frame_review_record_json": json.dumps(same_reviewer),
                        "dispatch_actor": "reviewer@example.org",
                    }
                )
            )

    def test_trusted_signed_review_passes_gate_and_mask_renderer(self):
        frame_record = {
            "reviewer_identity": "reviewer-login",
            "reviewed_at": "2026-10-16T02:00:00Z",
            "source_timecode": "00:10:30.000",
            "source_resolution": {"width": 1920, "height": 1080},
            "source_banner_bbox_px": {
                "left": 192,
                "top": 734,
                "right": 1728,
                "bottom": 1058,
            },
            "evidence_ref": "https://example.org/review/123",
            "source_sha256": review.SOURCE_SHA256,
        }
        with tempfile.TemporaryDirectory() as temporary:
            allowed_signers, signature = self.sign_frame_review(
                frame_record, temporary
            )
            values = {
                "caption_position": "mask-lower-third",
                "independent_rights_review_passed": False,
                "event_match_review_passed": False,
                "event_time_timezone_review_passed": False,
                "source_lineage_review_passed": False,
                "source_frame_review_record_json": json.dumps(frame_record),
                "source_frame_review_signature": signature,
                "source_graphics_regions_json": json.dumps(self.SOURCE_GRAPHICS),
                "dispatch_actor": "publisher",
                "rights_evidence_url": "",
                "event_match_evidence_url": "",
                "event_time_timezone_evidence_url": "",
                "source_lineage_evidence_url": "",
            }
            expected = {
                "source_frame_review": "verified_by_trusted_signature",
                "production_bbox_input": "true",
            }
            with patch.object(review, "FRAME_REVIEW_ALLOWED_SIGNERS", allowed_signers):
                self.assertEqual(review.validate_review_gates(**values), expected)
                readability = verify_cues(
                    [Cue(1, 3, "Hello, everybody.", "\u5927\u5bb6\u597d\u3002")],
                    duration=10,
                    width=1920,
                    height=1080,
                    layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
                    caption_position="mask-lower-third",
                    caption_safe_region_reviewed=True,
                    source_graphics_regions=self.SOURCE_GRAPHICS,
                    occlusion_exception_authorized=True,
                    mask_padding_px_per_edge=2,
                    trusted_frame_review={
                        "record": frame_record,
                        "signature_base64": signature,
                    },
                )["subtitle_readability"]
                self.assertTrue(
                    readability["source_graphics_review"]["production_bbox_input"]
                )
                self.assertEqual(
                    readability["source_graphics_review"]["review_status"],
                    "verified",
                )
                review.validate_caption_layout(
                    {
                        "resolution": "1920x1080",
                        "quality_checks": {"subtitle_readability": readability},
                    },
                    expected_source_sha256=review.SOURCE_SHA256,
                )
                with patch.object(
                    review,
                    "file_sha256_and_size",
                    return_value=(review.SOURCE_SHA256, 123),
                ):
                    self.assertEqual(
                        require_trusted_mask_review(
                            "mask-lower-third",
                            source_path=Path(temporary) / review.SOURCE_ASSET,
                            source_width=1920,
                            source_height=1080,
                            source_duration=2193.261,
                            source_frame_review_record_json=json.dumps(frame_record),
                            source_frame_review_signature=signature,
                            source_graphics_regions_json=json.dumps(self.SOURCE_GRAPHICS),
                            dispatch_actor="publisher",
                        ),
                        expected,
                    )

    def test_trusted_signature_rejects_tampering_bbox_mismatch_and_missing_key(self):
        frame_record = {
            "reviewer_identity": "reviewer-login",
            "reviewed_at": "2026-10-16T02:00:00Z",
            "source_timecode": "00:10:30.000",
            "source_resolution": {"width": 1920, "height": 1080},
            "source_banner_bbox_px": {
                "left": 192,
                "top": 734,
                "right": 1728,
                "bottom": 1058,
            },
            "evidence_ref": "https://example.org/review/123",
            "source_sha256": review.SOURCE_SHA256,
        }
        with tempfile.TemporaryDirectory() as temporary:
            allowed_signers, signature = self.sign_frame_review(
                frame_record, temporary
            )
            base = {
                "caption_position": "mask-lower-third",
                "independent_rights_review_passed": False,
                "event_match_review_passed": False,
                "event_time_timezone_review_passed": False,
                "source_lineage_review_passed": False,
                "source_frame_review_record_json": json.dumps(frame_record),
                "source_frame_review_signature": signature,
                "source_graphics_regions_json": json.dumps(self.SOURCE_GRAPHICS),
                "dispatch_actor": "publisher",
                "rights_evidence_url": "",
                "event_match_evidence_url": "",
                "event_time_timezone_evidence_url": "",
                "source_lineage_evidence_url": "",
            }
            with patch.object(review, "FRAME_REVIEW_ALLOWED_SIGNERS", allowed_signers):
                tampered_record = frame_record | {
                    "source_timecode": "00:10:31.000"
                }
                with self.assertRaisesRegex(RuntimeError, "signature is invalid"):
                    review.validate_review_gates(
                        **(
                            base
                            | {
                                "source_frame_review_record_json": json.dumps(
                                    tampered_record
                                )
                            }
                        )
                    )
                changed_regions = [
                    self.SOURCE_GRAPHICS[0] | {"x": 0.11}
                ]
                with self.assertRaisesRegex(RuntimeError, "does not match"):
                    review.validate_review_gates(
                        **(
                            base
                            | {
                                "source_graphics_regions_json": json.dumps(
                                    changed_regions
                                )
                            }
                        )
                    )
            with patch.object(
                review,
                "FRAME_REVIEW_ALLOWED_SIGNERS",
                Path(temporary) / "not-configured",
            ):
                with self.assertRaisesRegex(RuntimeError, "has not been configured"):
                    review.validate_review_gates(**base)

    def test_allowlisted_signed_review_passes_mask_gate_and_renderer(self):
        frame_record = {
                    "reviewer_identity": "reviewer@example.org",
                    "reviewed_at": "2026-10-16T02:00:00Z",
                    "source_timecode": "00:10:30.000",
                    "source_resolution": {"width": 1920, "height": 1080},
                    "source_banner_bbox_px": {
                        "left": 192,
                        "top": 734,
                        "right": 1728,
                        "bottom": 1058,
                    },
                    "evidence_ref": "https://example.org/review/123",
                    "source_sha256": review.SOURCE_SHA256,
        }
        with tempfile.TemporaryDirectory() as temporary:
                    allowed_signers, signature = self.sign_frame_review(
                        frame_record, temporary
                    )
                    values = {
                        "caption_position": "mask-lower-third",
                        "independent_rights_review_passed": False,
                        "event_match_review_passed": False,
                        "event_time_timezone_review_passed": False,
                        "source_lineage_review_passed": False,
                        "source_frame_review_record_json": json.dumps(frame_record),
                        "source_frame_review_signature": signature,
                        "source_graphics_regions_json": json.dumps(self.SOURCE_GRAPHICS),
                        "dispatch_actor": "publisher",
                        "rights_evidence_url": "",
                        "event_match_evidence_url": "",
                        "event_time_timezone_evidence_url": "",
                        "source_lineage_evidence_url": "",
                    }
                    expected = {
                        "source_frame_review": "verified_by_trusted_signature",
                        "production_bbox_input": "true",
                    }
                    with patch.object(review, "FRAME_REVIEW_ALLOWED_SIGNERS", allowed_signers):
                        self.assertEqual(review.validate_review_gates(**values), expected)
                        with patch.object(
                            review,
                            "file_sha256_and_size",
                            return_value=(review.SOURCE_SHA256, 1),
                        ):
                            self.assertEqual(
                                require_trusted_mask_review(
                                    "mask-lower-third",
                                    source_path=Path(temporary) / review.SOURCE_ASSET,
                                    source_width=1920,
                                    source_height=1080,
                                    source_duration=2193.261,
                                    source_frame_review_record_json=json.dumps(frame_record),
                                    source_frame_review_signature=signature,
                                    source_graphics_regions_json=json.dumps(self.SOURCE_GRAPHICS),
                                    dispatch_actor="publisher",
                                ),
                                expected,
                            )

    def test_signed_review_rejects_tampered_payload_bbox_mismatch_and_missing_key(self):
        frame_record = {
                    "reviewer_identity": "reviewer@example.org",
                    "reviewed_at": "2026-10-16T02:00:00Z",
                    "source_timecode": "00:10:30.000",
                    "source_resolution": {"width": 1920, "height": 1080},
                    "source_banner_bbox_px": {
                        "left": 192,
                        "top": 734,
                        "right": 1728,
                        "bottom": 1058,
                    },
                    "evidence_ref": "https://example.org/review/123",
                    "source_sha256": review.SOURCE_SHA256,
        }
        with tempfile.TemporaryDirectory() as temporary:
                    allowed_signers, signature = self.sign_frame_review(
                        frame_record, temporary
                    )
                    base = {
                        "caption_position": "mask-lower-third",
                        "independent_rights_review_passed": False,
                        "event_match_review_passed": False,
                        "event_time_timezone_review_passed": False,
                        "source_lineage_review_passed": False,
                        "source_frame_review_record_json": json.dumps(frame_record),
                        "source_frame_review_signature": signature,
                        "source_graphics_regions_json": json.dumps(self.SOURCE_GRAPHICS),
                        "dispatch_actor": "publisher",
                        "rights_evidence_url": "",
                        "event_match_evidence_url": "",
                        "event_time_timezone_evidence_url": "",
                        "source_lineage_evidence_url": "",
                    }
                    with patch.object(review, "FRAME_REVIEW_ALLOWED_SIGNERS", allowed_signers):
                        tampered = frame_record | {"source_timecode": "00:10:31.000"}
                        with self.assertRaisesRegex(RuntimeError, "signature is invalid"):
                            review.validate_review_gates(
                                **(
                                    base
                                    | {"source_frame_review_record_json": json.dumps(tampered)}
                                )
                            )
                        changed_regions = [
                            self.SOURCE_GRAPHICS[0] | {"x": 0.11}
                        ]
                        with self.assertRaisesRegex(RuntimeError, "does not match"):
                            review.validate_review_gates(
                                **(
                                    base
                                    | {
                                        "source_graphics_regions_json": json.dumps(
                                            changed_regions
                                        )
                                    }
                                )
                            )
                    with patch.object(
                        review,
                        "FRAME_REVIEW_ALLOWED_SIGNERS",
                        Path(temporary) / "missing-allowlist",
                    ):
                        with self.assertRaisesRegex(RuntimeError, "has not been configured"):
                            review.validate_review_gates(**base)

    def test_user_still_bbox_is_recorded_as_unverified_and_not_production_input(self):
        measurement = review.user_provided_still_measurement()
        self.assertEqual(measurement["measurement_source"], "user_provided_still")
        self.assertEqual(measurement["evidence_type"], "user_provided_still_measurement")
        self.assertEqual(measurement["measurement_status"], "unverified_still_estimate")
        self.assertEqual(measurement["source_resolution_px"], {
            "width": 1920,
            "height": 1080,
        })
        self.assertEqual(
            measurement["source_banner_bbox_px_half_open"],
            {"left": 68, "top": 885, "right": 1850, "bottom": 1020},
        )
        self.assertEqual(
            measurement["proposed_mask_bbox_px_half_open"],
            {"left": 66, "top": 883, "right": 1852, "bottom": 1022},
        )
        self.assertEqual(
            measurement["proposed_mask_dimensions_px"],
            {"width": 1786, "height": 139},
        )
        self.assertEqual(measurement["padding_px_per_edge"], 2)
        self.assertEqual(measurement["source_timecode"], "not_verified")
        self.assertEqual(measurement["source_provenance"], "not_verified")
        self.assertEqual(measurement["timecode_status"], "not_verified")
        self.assertEqual(measurement["provenance_status"], "not_verified")
        self.assertEqual(measurement["video_wide_position_stability"], "not_verified")
        self.assertEqual(measurement["controlled_cloud_frame_review"], "not_verified")
        self.assertFalse(measurement["production_bbox_input"])
        with self.assertRaisesRegex(RuntimeError, "no defaults"):
            review.validate_layout_inputs(
                caption_position="mask-lower-third",
                caption_safe_region_reviewed=True,
                source_graphics_regions_json="[]",
                rose_mask_authorized=True,
                mask_padding_px_per_edge=2,
            )
        self.assertEqual(
            review.validate_layout_inputs(
                caption_position="mask-lower-third",
                caption_safe_region_reviewed=False,
                source_graphics_regions_json="[]",
                rose_mask_authorized=True,
                mask_padding_px_per_edge=2,
                frame_review_mode="unverified-review-draft",
            ),
            [],
        )
        with self.assertRaisesRegex(RuntimeError, "only the fixed user-still estimate"):
            review.validate_layout_inputs(
                caption_position="mask-lower-third",
                caption_safe_region_reviewed=False,
                source_graphics_regions_json=json.dumps(self.SOURCE_GRAPHICS),
                rose_mask_authorized=True,
                mask_padding_px_per_edge=2,
                frame_review_mode="unverified-review-draft",
            )
        with self.assertRaisesRegex(RuntimeError, "reviewer, timestamp"):
            review.validate_review_gates(
                caption_position="mask-lower-third",
                independent_rights_review_passed=True,
                event_match_review_passed=True,
                event_time_timezone_review_passed=True,
                source_lineage_review_passed=True,
                source_frame_review_record_json=json.dumps(measurement),
                source_graphics_regions_json="[]",
                dispatch_actor="publisher",
                rights_evidence_url="https://example.org/rights",
                event_match_evidence_url="https://example.org/event",
                event_time_timezone_evidence_url="https://example.org/time",
                source_lineage_evidence_url="https://example.org/lineage",
            )

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
                caption_position="mask-lower-third",
                source_graphics_regions=self.SOURCE_GRAPHICS,
                occlusion_exception_authorized=True,
                mask_padding_px_per_edge=2,
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
                caption_position="mask-lower-third",
                caption_safe_region_reviewed=True,
                source_graphics_regions=self.SOURCE_GRAPHICS,
                occlusion_exception_authorized=True,
                mask_padding_px_per_edge=2,
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
                finalized = review.finalize_review_manifest(
                    source,
                    output_dir,
                    rights_evidence_url="",
                    event_identity_evidence_url="https://example.org/event-identity",
                    event_match_evidence_url="https://example.org/exact-match",
                    event_time_timezone_evidence_url="https://example.org/event-time",
                    source_lineage_evidence_url="https://example.org/source-lineage",
                    private_render=True,
                )

        self.assertEqual(
            finalized["source_provenance"]["sha256"],
            review.SOURCE_SHA256,
        )
        self.assertEqual(
            finalized["private_review"]["status"],
            "private_artifact_only",
        )
        self.assertEqual(
            finalized["processing_prerequisites"]["independent_evidence_review"],
            "pending",
        )
        self.assertEqual(
            finalized["processing_prerequisites"][
                "source_specific_reuse_rights_evidence_url"
            ],
            None,
        )
        self.assertEqual(
            finalized["processing_prerequisites"][
                "source_url_to_release_asset_lineage_evidence_url"
            ],
            "https://example.org/source-lineage",
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
        self.assertEqual(finalized["rights_review"]["reuse_rights_assessment"], "unassessed")
        self.assertIsNone(finalized["rights_review"]["rights_evidence_url"])
        self.assertEqual(finalized["private_review"]["independent_rights_review"], "pending")
        self.assertEqual(finalized["private_review"]["source_frame_review"], "pending")
        self.assertEqual(finalized["private_review"]["source_audio_asr_review"], "pending")
        self.assertEqual(finalized["private_review"]["translation_review"], "pending")
        self.assertEqual(finalized["private_review"]["public_release"], "not_authorized")
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
            finalized["source_graphics_occlusion"]["status_label"],
            "masked_not_clean",
        )
        self.assertEqual(
            finalized["source_graphics_occlusion"]["mask_bbox_px"],
            {
                "left": 190,
                "top": 732,
                "right": 1730,
                "bottom": 1060,
                "width": 1540,
                "height": 328,
                "mask_padding_px_per_edge": 2,
            },
        )
        self.assertEqual(
            finalized["source_event_evidence"]["source_url_to_release_lineage"],
            "pending",
        )
        self.assertEqual(
            finalized["source_provenance"]["url_to_release_lineage_review"],
            "pending",
        )
        self.assertEqual(
            finalized["quality_checks"]["subtitle_readability"][
                "caption_ass_validation"
            ]["synthetic_libass_geometry_render"],
            "passed",
        )

    def test_caption_layout_gate_accepts_the_tight_authorized_rose_mask(self):
        readability = verify_cues(
            [Cue(1, 3, "Hello, everybody.", "大家好。")],
            duration=10,
            width=1920,
            height=1080,
            layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
            caption_position="mask-lower-third",
            caption_safe_region_reviewed=True,
            source_graphics_regions=self.SOURCE_GRAPHICS,
            occlusion_exception_authorized=True,
            mask_padding_px_per_edge=2,
        )["subtitle_readability"]
        review.validate_caption_layout(
            {"quality_checks": {"subtitle_readability": readability}}
        )

    def test_user_still_estimate_draft_manifest_stays_pending_and_nonproduction(self):
        regions = review.user_still_source_graphics_regions(1920, 1080)
        measurement = review.user_provided_still_measurement()
        readability = verify_cues(
            [Cue(1, 3, "Hello, everybody.", "\u5927\u5bb6\u597d\u3002")],
            duration=10,
            width=1920,
            height=1080,
            layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
            caption_position="mask-lower-third",
            caption_safe_region_reviewed=False,
            source_graphics_regions=regions,
            occlusion_exception_authorized=True,
            mask_padding_px_per_edge=2,
            allow_unverified_estimate=True,
        )["subtitle_readability"]
        source_review = readability["source_graphics_review"]
        self.assertEqual(source_review["status"], "user_provided_still_estimate")
        self.assertEqual(source_review["review_status"], "pending")
        self.assertFalse(source_review["production_bbox_input"])
        expected_bbox = {
            "source_values_xyxy_px": [68, 885, 1850, 1020],
            "padding_px_per_edge": 2,
            "derived_mask_values_xyxy_px": [66, 883, 1852, 1022],
            "measurement_status": "unverified_still_estimate",
            "source_frame_review_record": False,
            "production_bbox_input": False,
        }
        self.assertEqual(measurement["user_estimated_banner_bbox"], expected_bbox)
        self.assertEqual(source_review["user_estimated_banner_bbox"], expected_bbox)
        manifest = {
            "resolution": "1920x1080",
            "frame_review_mode": "unverified-review-draft",
            "source_frame_measurement": {**measurement, "review_status": "pending"},
            "user_estimated_banner_bbox": expected_bbox,
            "quality_checks": {"subtitle_readability": readability},
        }
        review.validate_caption_layout(
            manifest,
            expected_source_sha256=review.SOURCE_SHA256,
        )

        source_review["production_bbox_input"] = True
        with self.assertRaisesRegex(RuntimeError, "pending"):
            review.validate_caption_layout(manifest)

    def test_caption_layout_gate_rejects_missing_or_unsafe_contracts(self):
        valid = verify_cues(
            [Cue(1, 3, "Hello, everybody.", "大家好。")],
            duration=10,
            width=1920,
            height=1080,
            layout_profile=ROSE_GARDEN_SUBTITLE_LAYOUT,
            caption_position="mask-lower-third",
            caption_safe_region_reviewed=True,
            source_graphics_regions=self.SOURCE_GRAPHICS,
            occlusion_exception_authorized=True,
            mask_padding_px_per_edge=2,
        )["subtitle_readability"]
        mutations = (
            ("default profile", "layout_profile", "default", "required Rose Garden"),
            ("wrong width", "horizontal_safe_width_percent", 78, "68%"),
            ("wrong English font ratio", "english_font_px", 40, "0.8x"),
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
                caption_position="mask-lower-third",
                source_graphics_regions=self.SOURCE_GRAPHICS,
                occlusion_exception_authorized=True,
                mask_padding_px_per_edge=2,
            )
            manifest = {
                "subtitle_ass_file": ass_name,
                "subtitle_ass_sha256": "0" * 64,
                "resolution": "1920x1080",
            }
            with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                review.validate_caption_ass(manifest, root)

    def test_caption_ass_keeps_recorded_cue_50_overflow_manual_and_checks_other_cues(self):
        ordinary = Cue(1, 3, "A complete English sentence.", "完整的中文句子。")
        overflow = Cue(
            290.45,
            296.45,
            " ".join(["unbroken phrase"] * 24),
            "没有对应标点的中文长句" * 12,
        )
        record = {
            "source_cue_index": 50,
            "start_seconds": 290.45,
            "end_seconds": 296.45,
            "reason": "bilingual_caption_exceeds_safe_region_height",
            "fallback": "preserved_complete_bilingual_cue; render_with_overflow",
            "safe_width_px": 1306,
            "english_lines_required": 3,
            "chinese_lines_required": 3,
            "estimated_text_height_px": 207,
            "safe_height_px": 139,
        }
        cues = [ordinary, overflow]

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self.build_caption_ass_manifest(root, cues, [record])
            region = manifest["quality_checks"]["subtitle_readability"][
                "caption_region_box_px"
            ]
            frame = self.synthetic_caption_frame(1920, 1080, region)
            with patch(
                "scripts.verify_rose_garden_review.render_caption_geometry_frame",
                return_value=frame,
            ) as render_frame:
                result = review.validate_caption_ass(manifest, root)

            self.assertEqual(result["status"], "manual_review_required")
            self.assertEqual(
                result["synthetic_libass_geometry_render"],
                "passed_with_recorded_overflow",
            )
            self.assertEqual(result["caption_overflow_exception_count"], 1)
            self.assertEqual(
                manifest["quality_checks"]["subtitle_readability"][
                    "caption_overflow_exceptions"
                ]["cues"],
                [record],
            )
            render_frame.assert_called_once()
            self.assertEqual(render_frame.call_args.args[-1], ordinary.start)

            spilled_frame = bytearray(frame)
            offset = (region["bottom"] * 1920 + 960) * 3
            spilled_frame[offset:offset + 3] = bytes((255, 255, 255))
            with patch(
                "scripts.verify_rose_garden_review.render_caption_geometry_frame",
                return_value=bytes(spilled_frame),
            ):
                with self.assertRaisesRegex(RuntimeError, "caption region"):
                    review.validate_caption_ass(manifest, root)

    def test_caption_ass_with_only_recorded_overflow_stays_manual_without_sampling(self):
        cue = Cue(
            290.45,
            296.45,
            " ".join(["unbroken phrase"] * 24),
            "没有对应标点的中文长句" * 12,
        )
        record = {
            "source_cue_index": 50,
            "start_seconds": 290.45,
            "end_seconds": 296.45,
            "reason": "bilingual_caption_exceeds_safe_region_height",
            "fallback": "preserved_complete_bilingual_cue; render_with_overflow",
            "safe_width_px": 1306,
            "english_lines_required": 3,
            "chinese_lines_required": 3,
            "estimated_text_height_px": 207,
            "safe_height_px": 139,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self.build_caption_ass_manifest(root, [cue], [record])
            with patch(
                "scripts.verify_rose_garden_review.render_caption_geometry_frame"
            ) as render_frame:
                result = review.validate_caption_ass(manifest, root)

        self.assertEqual(result["status"], "manual_review_required")
        self.assertEqual(
            result["synthetic_libass_geometry_render"],
            "not_sampled_all_cues_recorded_overflow",
        )
        self.assertIsNone(result["rendered_text_bounds_px"])
        render_frame.assert_not_called()

    def test_rendered_caption_bounds_validate_exact_mask_and_reject_spill(self):
        width = height = 20
        mask = {"left": 4, "top": 4, "right": 16, "bottom": 16}
        frame = bytearray([255, 0, 0] * width * height)
        for y in range(mask["top"], mask["bottom"]):
            for x in range(mask["left"], mask["right"]):
                offset = (y * width + x) * 3
                frame[offset:offset + 3] = bytes((24, 24, 24))
        for y in (8, 9):
            for x in (9, 10):
                offset = (y * width + x) * 3
                frame[offset:offset + 3] = bytes((255, 255, 255))
        bounds = review.inspect_caption_geometry_frame(
            bytes(frame), width, height, mask, mask
        )
        self.assertEqual(
            (bounds["mask_left"], bounds["mask_top"],
             bounds["mask_right"], bounds["mask_bottom"]),
            (4, 4, 16, 16),
        )

        spill = bytearray(frame)
        offset = (2 * width + 2) * 3
        spill[offset:offset + 3] = bytes((255, 255, 255))
        with self.assertRaisesRegex(RuntimeError, "caption region"):
            review.inspect_caption_geometry_frame(
                bytes(spill), width, height, mask, mask
            )


if __name__ == "__main__":
    unittest.main()
