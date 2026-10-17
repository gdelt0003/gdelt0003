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
from scripts.update_rose_garden_main_video_catalog import update_main_video_catalog
from scripts.prepare_rose_garden_review_preview import prepare_preview


ROOT = Path(__file__).resolve().parents[1]
PUBLISH_WORKFLOW = (
    ROOT / ".github" / "workflows" / "publish-reviewed-rose-garden.yml"
)
RENDER_WORKFLOW = ROOT / ".github" / "workflows" / "publish-rose-garden-review.yml"
PAGE = ROOT / "events" / EVENT_ID / "index.html"
SOURCES_PAGE = ROOT / "events" / EVENT_ID / "sources.html"


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
            result["publication_status"],
            "pending_external_review_draft",
        )
        self.assertFalse(result["review_statuses_are_publication_gates"])

    def test_accepts_pending_review_statuses_without_blocking_draft(self):
        pending_checks = {
            category: {
                "reviewed": False,
                "status": "pending",
                "evidence_url": None,
            }
            for category in REVIEW_CATEGORIES
        }
        result = self.validate(self.record | {"checks": pending_checks})
        self.assertTrue(
            all(
                check["status"] == "pending"
                for check in result["reviewed_checks"].values()
            )
        )
        self.assertEqual(
            result["publication_status"],
            "pending_external_review_draft",
        )

    def test_failed_review_status_is_recorded_without_blocking_draft(self):
        checks = {
            category: {"reviewed": False, "status": "unverified"}
            for category in REVIEW_CATEGORIES
        }
        checks["reuse_rights"] = {
            "reviewed": True,
            "status": "failed",
            "evidence_url": "https://review.example/rights",
        }
        result = self.validate(self.record | {"checks": checks})
        self.assertEqual(result["reviewed_checks"]["reuse_rights"]["status"], "failed")
        self.assertEqual(
            result["publication_status"],
            "pending_external_review_draft",
        )

    def test_rejects_missing_or_malformed_review_check_record(self):
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
                "clean_source_frames": {"reviewed": False, "status": "unknown"},
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

    def test_page_update_records_statuses_without_claiming_approval(self):
        with tempfile.TemporaryDirectory() as temp:
            page = Path(temp) / "index.html"
            page.write_text(PAGE.read_text(encoding="utf-8"), encoding="utf-8")
            verification = self.validate()
            update_review_page(
                page,
                "rose-garden-lunch-review-123456789",
                verification,
            )
            updated = page.read_text(encoding="utf-8")
        self.assertEqual(
            updated.count(
                "releases/download/rose-garden-lunch-review-123456789/"
                "RoseGardenLunch-IySF_8OArvw-bilingual.mp4"
            ),
            2,
        )
        self.assertNotIn("releases/download/rose-garden-lunch-review/", updated)
        self.assertEqual(updated.count('<input type="checkbox" checked="checked" disabled>'), 5)
        self.assertEqual(updated.count("<span data-review-status>操作员记录通过</span>"), 5)
        self.assertIn("PENDING", updated)
        self.assertIn("不会被表述为通过", updated)
        self.assertIn("不代表独立认证", updated)
        self.assertIn(
            "releases/download/rose-garden-lunch-review-123456789/"
            "publication-review-verification.json",
            updated,
        )

    def test_page_update_publishes_pending_labels_without_checked_boxes(self):
        with tempfile.TemporaryDirectory() as temp:
            page = Path(temp) / "index.html"
            page.write_text(PAGE.read_text(encoding="utf-8"), encoding="utf-8")
            pending = self.record | {
                "checks": {
                    category: {
                        "reviewed": False,
                        "status": "pending",
                        "evidence_url": None,
                    }
                    for category in REVIEW_CATEGORIES
                }
            }
            verification = self.validate(pending)
            update_review_page(
                page,
                "rose-garden-lunch-review-123456789",
                verification,
            )
            updated = page.read_text(encoding="utf-8")
        self.assertEqual(updated.count('<input type="checkbox" disabled>'), 5)
        self.assertEqual(updated.count("<span data-review-status>待审</span>"), 5)
        self.assertNotIn("操作员记录通过", updated)
        self.assertIn("PENDING", updated)

    def test_catalog_registers_per_render_release_with_attestation_limited_status(self):
        catalog_path = Path(self.temp.name) / "main-videos.json"
        original_video = {"id": "existing", "event_date": "2026-10-16"}
        catalog_path.write_text(
            json.dumps({"schema_version": 1, "videos": [original_video]}),
            encoding="utf-8",
        )

        update_main_video_catalog(
            catalog_path,
            "rose-garden-lunch-review-123456789",
            "123456789",
        )
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        self.assertEqual(catalog["videos"][0], original_video)
        rose = catalog["videos"][1]
        release_url = (
            "https://github.com/gdelt0003/gdelt0003/releases/download/"
            "rose-garden-lunch-review-123456789"
        )
        self.assertEqual(rose["event_date"], "2026-10-15")
        self.assertEqual(
            rose["source_details_url"],
            "events/rose-garden-lunch-2026-10-15/sources.html",
        )
        self.assertEqual(
            rose["video_url"],
            f"{release_url}/RoseGardenLunch-IySF_8OArvw-bilingual.mp4",
        )
        self.assertEqual(rose["id"], "rose-garden-lunch-2026-10-15-review")
        self.assertIn("工作流校验", rose["homepage_status"])
        self.assertIn("未独立验证复核结论", rose["review_status"])
        self.assertIn("不代表最终发布批准", rose["review_status"])
        self.assertEqual(len(rose["subtitles"]), 5)
        self.assertTrue(
            all(subtitle["url"].startswith(release_url) for subtitle in rose["subtitles"])
        )

        legacy = {
            "id": "rose-garden-lunch-review-123456788",
            "event_date": "2026-10-15",
            "video_url": "https://example.test/old-run.mp4",
        }
        repeated = json.loads(catalog_path.read_text(encoding="utf-8"))
        repeated["videos"].append(legacy)
        catalog_path.write_text(json.dumps(repeated), encoding="utf-8")
        update_main_video_catalog(
            catalog_path,
            "rose-garden-lunch-review-123456790",
            "123456790",
        )
        repeated = json.loads(catalog_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [video["id"] for video in repeated["videos"]].count(
                "rose-garden-lunch-2026-10-15-review"
            ),
            1,
        )
        self.assertFalse(
            any(
                str(video.get("id", "")).startswith("rose-garden-lunch-review-")
                for video in repeated["videos"]
            )
        )
        self.assertTrue(
            next(
                video
                for video in repeated["videos"]
                if video["id"] == "rose-garden-lunch-2026-10-15-review"
            )["video_url"].startswith(
                "https://github.com/gdelt0003/gdelt0003/releases/download/"
                "rose-garden-lunch-review-123456790/"
            )
        )

    def test_catalog_rejects_release_tag_not_bound_to_render_run(self):
        catalog_path = Path(self.temp.name) / "main-videos.json"
        catalog_path.write_text('{"videos": []}\n', encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "match the reviewed render run"):
            update_main_video_catalog(
                catalog_path,
                "rose-garden-lunch-review-123456789",
                "123456788",
            )

    def test_source_details_page_is_explicitly_pending_without_candidates(self):
        page = SOURCES_PAGE.read_text(encoding="utf-8")
        self.assertIn("事件来源核验 · 待补充", page)
        self.assertIn("视频源可信度", page)
        self.assertIn("视频本身可信度", page)
        self.assertIn("当前没有已记录并核验的候选来源", page)
        self.assertIn("不表示已完成检索", page)
        self.assertIn("user_estimated_banner_bbox", page)
        self.assertIn("[68, 885, 1850, 1020]", page)
        self.assertIn("[66, 883, 1852, 1022]", page)
        self.assertIn("不声称 run <code>38895767927</code> 使用了该 bbox", page)
        self.assertIn(
            'data-video-id="rose-garden-lunch-2026-10-15-review"',
            page,
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
        render_job = render_workflow.split("  render:", maxsplit=1)[1].split(
            "\n  deploy-review-preview:", maxsplit=1
        )[0]
        self.assertIn("permissions:\n      contents: write", render_job)
        self.assertNotIn("gh release create", render_job)
        self.assertNotIn("gh release edit", render_job)
        self.assertIn("rose-garden-publication", publish_workflow)
        self.assertIn("verify_rose_garden_publication_review.py", publish_workflow)
        self.assertIn("needs: validate-review", publish_workflow)
        self.assertIn("needs: publish-release", publish_workflow)
        self.assertIn('gh release create "$tag"', publish_workflow)
        self.assertNotIn("gh release edit", publish_workflow)
        self.assertNotIn("--clobber", publish_workflow)
        self.assertIn("actions/deploy-pages@v4", publish_workflow)
        self.assertIn("update_rose_garden_review_page.py", publish_workflow)
        self.assertIn("do not block this draft publication", publish_workflow)
        self.assertIn("update_rose_garden_main_video_catalog.py", publish_workflow)
        self.assertLess(
            publish_workflow.index("update_rose_garden_main_video_catalog.py"),
            publish_workflow.index("actions/upload-pages-artifact@v3"),
        )


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
