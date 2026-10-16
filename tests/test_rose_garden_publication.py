import hashlib
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from scripts.download_rose_garden_source_asset import (
    download_source_asset,
    find_draft_asset,
)
from scripts.verify_rose_garden_publication_review import (
    EVENT_ID,
    RENDERED_ASSET,
    SOURCE_ASSET,
    REVIEW_CATEGORIES,
    validate_publication_review,
)
from scripts.update_rose_garden_review_page import update_review_page
from scripts.prepare_rose_garden_review_preview import prepare_preview


ROOT = Path(__file__).resolve().parents[1]
PUBLISH_WORKFLOW = (
    ROOT / ".github" / "workflows" / "publish-reviewed-rose-garden.yml"
)
RENDER_WORKFLOW = ROOT / ".github" / "workflows" / "publish-rose-garden-review.yml"
PAGE = ROOT / "events" / EVENT_ID / "index.html"


class RoseGardenPublicationReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.artifact_dir = Path(self.temp.name)
        self.mp4_bytes = b"verified rendered media"
        (self.artifact_dir / RENDERED_ASSET).write_bytes(self.mp4_bytes)
        (self.artifact_dir / "operation-audit.json").write_text(
            '{"operations":[]}\n', encoding="utf-8"
        )
        (self.artifact_dir / "captions.srt").write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nHello / 你好\n",
            encoding="utf-8",
        )
        self.manifest = {
            "event_identity": {"event_id": EVENT_ID},
            "source_video": SOURCE_ASSET,
            "rendered_video": {
                "file": RENDERED_ASSET,
                "sha256": hashlib.sha256(self.mp4_bytes).hexdigest(),
                "size_bytes": len(self.mp4_bytes),
            },
            "subtitle_files": ["captions.srt"],
            "source_graphics_occlusion": {
                "status_label": "clean",
                "caption_band_masks_source_lower_third_in_derivative": False,
            },
        }
        (self.artifact_dir / "manifest.json").write_text(
            json.dumps(self.manifest), encoding="utf-8"
        )
        self.record = {
            "render_run_id": "123456789",
            "rendered_mp4_sha256": self.manifest["rendered_video"]["sha256"],
            "checks": {
                category: {
                    "reviewed": True,
                    "status": "passed",
                    "evidence_url": f"https://review.example/{category}",
                }
                for category in REVIEW_CATEGORIES
            },
        }

    def validate(self, record=None, run_id="123456789"):
        return validate_publication_review(
            artifact_dir=self.artifact_dir,
            review_record=record or self.record,
            render_run_id=run_id,
            reviewed_by="reviewer",
        )

    def test_accepts_five_distinct_https_reviews_bound_to_built_mp4(self):
        result = self.validate()
        self.assertEqual(
            result["rendered_mp4_sha256"],
            self.manifest["rendered_video"]["sha256"],
        )
        self.assertEqual(set(result["reviewed_checks"]), set(REVIEW_CATEGORIES))
        self.assertEqual(result["reviewed_by"], "reviewer")
        self.assertEqual(
            result["release_approval"],
            "approved_for_public_review_only",
        )

    def test_rejects_missing_or_unconfirmed_review_check(self):
        for checks in (
            {},
            {
                **self.record["checks"],
                "english_asr": {
                    **self.record["checks"]["english_asr"],
                    "reviewed": False,
                },
            },
            {
                **self.record["checks"],
                "clean_source_frames": {
                    **self.record["checks"]["clean_source_frames"],
                    "status": "failed",
                },
            },
        ):
            with self.subTest(checks=checks), self.assertRaises(RuntimeError):
                self.validate(self.record | {"checks": checks})

    def test_rejects_duplicate_or_non_https_evidence_urls(self):
        duplicate = dict(self.record["checks"])
        duplicate["chinese_translation"] = {
            **duplicate["chinese_translation"],
            "evidence_url": "https://REVIEW.example:443/source_event_match/#different-fragment",
        }
        duplicate["source_event_match"] = {
            **duplicate["source_event_match"],
            "evidence_url": "https://review.example/source_event_match",
        }
        non_https = dict(self.record["checks"])
        non_https["reuse_rights"] = {
            **non_https["reuse_rights"],
            "evidence_url": "http://review.example/rights",
        }
        for checks in (duplicate, non_https):
            with self.subTest(checks=checks), self.assertRaises(RuntimeError):
                self.validate(self.record | {"checks": checks})

    def test_rejects_run_or_mp4_sha_mismatch_and_modified_artifact(self):
        with self.assertRaisesRegex(RuntimeError, "selected render run"):
            self.validate(run_id="123456788")
        with self.assertRaisesRegex(RuntimeError, "not bound"):
            self.validate(self.record | {"rendered_mp4_sha256": "0" * 64})
        (self.artifact_dir / RENDERED_ASSET).write_bytes(b"tampered")
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            self.validate()

    def test_rejects_claim_of_clean_frames_for_masked_derivative(self):
        self.manifest["source_graphics_occlusion"] = {
            "status_label": "masked_not_clean",
            "caption_band_masks_source_lower_third_in_derivative": True,
        }
        (self.artifact_dir / "manifest.json").write_text(
            json.dumps(self.manifest), encoding="utf-8"
        )
        with self.assertRaisesRegex(RuntimeError, "cannot pass clean_source_frames"):
            self.validate()

    def test_page_update_points_to_approved_unique_release_and_marks_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            page = Path(temp) / "index.html"
            page.write_text(PAGE.read_text(encoding="utf-8"), encoding="utf-8")
            update_review_page(page, "rose-garden-lunch-review-123456789")
            updated = page.read_text(encoding="utf-8")
        self.assertEqual(
            updated.count(
                "releases/download/rose-garden-lunch-review-123456789/"
                "RoseGardenLunch-IySF_8OArvw-bilingual.mp4"
            ),
            2,
        )
        self.assertNotIn("releases/download/rose-garden-lunch-review/", updated)
        self.assertEqual(updated.count('<input type="checkbox" checked disabled>'), 5)
        self.assertEqual(updated.count("<span>已复核</span>"), 5)
        self.assertIn("REVIEW ATTESTATIONS RECORDED", updated)
        self.assertIn("不是独立认证", updated)
        self.assertIn(
            "releases/download/rose-garden-lunch-review-123456789/"
            "publication-review-verification.json",
            updated,
        )

    def test_pending_pages_preview_is_not_the_release_and_retains_pending_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            site_dir = Path(temp) / "site"
            event_dir = site_dir / "events" / EVENT_ID
            event_dir.mkdir(parents=True)
            page = event_dir / "index.html"
            page.write_text(PAGE.read_text(encoding="utf-8"), encoding="utf-8")
            preview_path = prepare_preview(
                artifact_dir=self.artifact_dir,
                site_dir=site_dir,
                render_run_id="123456789",
            )
            self.assertEqual(preview_path.read_bytes(), self.mp4_bytes)
            updated = page.read_text(encoding="utf-8")
        self.assertIn(
            "review-previews/run-123456789/RoseGardenLunch-IySF_8OArvw-bilingual.mp4",
            updated,
        )
        self.assertIn("公开 Pages 评审预览", updated)
        self.assertIn(
            "review-previews/run-123456789/manifest.json",
            updated,
        )
        self.assertIn(
            "review-previews/run-123456789/operation-audit.json",
            updated,
        )
        self.assertEqual(updated.count('<input type="checkbox" disabled>'), 5)
        self.assertIn("仍待审", updated)
        self.assertNotIn("rose-garden-lunch-review-123456789", updated)

    def test_render_and_publication_workflows_have_separate_hard_gates(self):
        render_workflow = RENDER_WORKFLOW.read_text(encoding="utf-8")
        publish_workflow = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("gh release create", render_workflow)
        self.assertIn("actions/deploy-pages@v4", render_workflow)
        self.assertIn("deploy-review-preview:", render_workflow)
        self.assertIn("needs: render", render_workflow)
        self.assertIn("prepare_rose_garden_review_preview.py", render_workflow)
        self.assertIn("contents: read", render_workflow)
        self.assertIn("rose-garden-publication", publish_workflow)
        self.assertIn("verify_rose_garden_publication_review.py", publish_workflow)
        self.assertIn("needs: validate-review", publish_workflow)
        self.assertIn("needs: publish-release", publish_workflow)
        self.assertIn('gh release create "$tag"', publish_workflow)
        self.assertNotIn("gh release edit", publish_workflow)
        self.assertNotIn("--clobber", publish_workflow)
        self.assertIn("actions/deploy-pages@v4", publish_workflow)
        self.assertIn("update_rose_garden_review_page.py", publish_workflow)


class RoseGardenDraftSourceAssetTests(unittest.TestCase):
    RELEASE = {
        "id": 123,
        "tag_name": "rose-garden-lunch-source-2026-10-15",
        "draft": True,
        "assets": [
            {
                "id": 456,
                "name": "RoseGardenLunch-IySF_8OArvw.mp4",
            }
        ],
    }

    def test_resolves_source_asset_from_draft_release_listing(self):
        self.assertEqual(
            find_draft_asset(
                [self.RELEASE],
                "rose-garden-lunch-source-2026-10-15",
                "RoseGardenLunch-IySF_8OArvw.mp4",
            ),
            (123, 456),
        )

    def test_rejects_missing_duplicate_non_draft_or_missing_asset(self):
        cases = (
            ([], "exactly one source release"),
            ([self.RELEASE, self.RELEASE], "exactly one source release"),
            ([self.RELEASE | {"draft": False}], "must remain a draft"),
            ([self.RELEASE | {"assets": []}], "Expected exactly one"),
        )
        for releases, message in cases:
            with self.subTest(releases=releases), self.assertRaisesRegex(
                RuntimeError, message
            ):
                find_draft_asset(
                    releases,
                    "rose-garden-lunch-source-2026-10-15",
                    "RoseGardenLunch-IySF_8OArvw.mp4",
                )

    def test_downloads_by_asset_id_and_checks_digest(self):
        payload = b"test-only source asset bytes"
        releases = [[self.RELEASE]]
        calls = 0

        def fake_gh(args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return subprocess.CompletedProcess(
                    args, 0, stdout=json.dumps(releases), stderr=""
                )
            kwargs["stdout"].write(payload)
            return subprocess.CompletedProcess(args, 0)

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "source.mp4"
            with patch(
                "scripts.download_rose_garden_source_asset.subprocess.run",
                side_effect=fake_gh,
            ):
                download_source_asset(
                    repo="gdelt0003/gdelt0003",
                    release_tag="rose-garden-lunch-source-2026-10-15",
                    asset_name="RoseGardenLunch-IySF_8OArvw.mp4",
                    expected_sha256=hashlib.sha256(payload).hexdigest(),
                    output=output,
                )
            self.assertEqual(output.read_bytes(), payload)
        self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
