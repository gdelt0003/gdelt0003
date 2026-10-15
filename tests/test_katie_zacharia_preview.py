import json
import tempfile
import unittest
from pathlib import Path

from scripts.publish_full_video_preview import (
    EVENT_ID,
    EVENT_EVIDENCE_URL,
    RIGHTS_EVIDENCE_URL,
    SOURCE_ASSET_ID,
    SOURCE_ASSET_NAME,
    SOURCE_SHA256,
    SOURCE_SIZE_BYTES,
    SOURCE_URL,
    REVIEW_STATUS,
    publish_catalog_entry,
    record_provenance,
    validate_source_verification,
)
from scripts.verify_operation_audit import validate_operation_audit


class KatieZachariaPreviewTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def write_json(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def source_verification(self, **overrides):
        record = {
            "release_tag": "g7we6gecwnc-source-intake-20261015",
            "release_is_draft": True,
            "asset_id": SOURCE_ASSET_ID,
            "asset_name": SOURCE_ASSET_NAME,
            "size_bytes": SOURCE_SIZE_BYTES,
            "sha256": SOURCE_SHA256,
            "verified_download_started_at": "2026-10-15T00:00:00.000Z",
            "verified_at": "2026-10-15T00:01:00.000Z",
            "duration_seconds": 866,
            "width": 1920,
            "height": 1080,
            "source_url": SOURCE_URL,
            "event_identity_evidence_url": EVENT_EVIDENCE_URL,
            "source_match_evidence_url": EVENT_EVIDENCE_URL,
            "rights_evidence_url": RIGHTS_EVIDENCE_URL,
            "same_event_source_match_confirmed": True,
            "reuse_rights_confirmed": True,
            "reuse_rights_status": "user requested public test preview",
        }
        record.update(overrides)
        return record

    def test_source_validation_rejects_under_1080p(self):
        with self.assertRaisesRegex(ValueError, "below 1920x1080"):
            validate_source_verification(self.source_verification(height=720))

    def test_source_validation_rejects_wrong_asset_hash(self):
        with self.assertRaisesRegex(ValueError, "sha256 mismatch"):
            validate_source_verification(self.source_verification(sha256="0" * 64))

    def test_records_exact_source_provenance_and_unverified_status(self):
        manifest = self.write_json(
            "manifest.json",
            {
                "source_video": SOURCE_ASSET_NAME,
                "duration_seconds": 866,
                "resolution": "1920x1080",
                "asr_model": "large-v3-turbo",
                "translation_model": "facebook/m2m100_1.2B",
                "reused_existing_subtitles": False,
                "processing_operations": [],
            },
        )
        audit = self.write_json(
            "operation-audit.json",
            {"task_id": "100.1", "pipeline_version": "abc123", "operations": []},
        )
        source = self.write_json(
            "source-verification.json", self.source_verification()
        )

        record_provenance(manifest, audit, source, "100")

        result = json.loads(manifest.read_text(encoding="utf-8"))
        audit_result = json.loads(audit.read_text(encoding="utf-8"))
        self.assertEqual(result["event"]["event_id"], EVENT_ID)
        self.assertEqual(result["input_sha256"], SOURCE_SHA256)
        self.assertEqual(result["review_status"], REVIEW_STATUS)
        self.assertEqual(result["processing_operations"], audit_result["operations"])
        self.assertEqual(
            audit_result["operations"][0]["operation"],
            "source_asset_download_and_integrity_verification",
        )
        self.assertTrue(
            audit_result["operations"][0]["details"]["verified_before_media_processing"]
        )
        self.assertEqual(validate_operation_audit(audit, manifest), 1)

    def test_catalog_adds_idempotent_preview_links_without_rewriting_existing_items(self):
        manifest = self.write_json(
            "manifest.json",
            {
                "workflow_run_id": "100",
                "input_sha256": SOURCE_SHA256,
                "review_status": REVIEW_STATUS,
                "resolution": "1920x1080",
                "duration_seconds": 866,
            },
        )
        existing = {"id": "existing-video", "video_url": "https://example.com/video.mp4"}
        catalog = self.write_json(
            "main-videos.json",
            {"schema_version": 1, "videos": [existing]},
        )
        release_url = (
            "https://github.com/gdelt0003/gdelt0003/releases/download/"
            "katie-zacharia-g7we6gecwnc-bilingual-preview-100"
        )

        publish_catalog_entry(manifest, catalog, release_url, "100")
        publish_catalog_entry(manifest, catalog, release_url, "100")

        result = json.loads(catalog.read_text(encoding="utf-8"))
        self.assertEqual(result["videos"][0], existing)
        preview = result["videos"][1]
        self.assertEqual(preview["id"], f"{EVENT_ID}-preview-100")
        self.assertIn("bilingual.mp4", preview["video_url"])
        self.assertIn(SOURCE_SHA256, preview["note"])
        self.assertIn("未经人工核验", preview["review_status"])
        self.assertEqual(len(preview["subtitles"]), 4)
        self.assertIn("manifest.json", preview["manifest_url"])

    def test_catalog_rejects_wrong_source_and_unverified_status(self):
        manifest = self.write_json(
            "manifest.json",
            {
                "workflow_run_id": "100",
                "input_sha256": "0" * 64,
                "review_status": REVIEW_STATUS,
            },
        )
        catalog = self.write_json("main-videos.json", {"videos": []})
        release_url = (
            "https://github.com/gdelt0003/gdelt0003/releases/download/"
            "katie-zacharia-g7we6gecwnc-bilingual-preview-100"
        )

        with self.assertRaisesRegex(ValueError, "pinned source SHA-256"):
            publish_catalog_entry(manifest, catalog, release_url, "100")

    def test_workflow_is_opt_in_pinned_and_uses_a_github_hosted_runner(self):
        workflow_path = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "publish-katie-zacharia-preview.yml"
        )
        workflow = workflow_path.read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("default: false", workflow)
        self.assertIn("runs-on: ubuntu-latest", workflow)
        self.assertIn("642103215", workflow)
        self.assertIn(SOURCE_SHA256, workflow)
        self.assertIn("same_event_source_confirmed", workflow)
        self.assertIn("reuse_rights_confirmed", workflow)
        self.assertIn("width < 1920 or height < 1080", workflow)
        self.assertIn("scripts/process_full_video.py", workflow)
        self.assertIn("--prerelease", workflow)
        self.assertIn("actions/deploy-pages@v4", workflow)
        self.assertNotIn("OPENROUTER_API_KEY", workflow)


if __name__ == "__main__":
    unittest.main()
