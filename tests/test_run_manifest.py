import copy
import unittest

from scripts.run_manifest import create_run_manifest, validate_run_manifest


class RunManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = create_run_manifest(
            run_id="synthetic-run-17",
            inputs=[
                {
                    "id": "synthetic-input-1",
                    "sha256": "a" * 64,
                }
            ],
            tool_versions={"transcriber": "test-version-1"},
            started_at="2026-10-15T08:00:00.000Z",
        )

    def test_helper_initializes_distinct_non_success_states(self):
        validate_run_manifest(self.manifest)
        self.assertEqual(self.manifest["processing_status"], "running")
        self.assertEqual(self.manifest["publication_status"], "not_published")
        self.assertEqual(self.manifest["content_review_status"], "not_verified")
        self.assertIsNone(self.manifest["ended_at"])
        self.assertIsNone(self.manifest["failed_at"])
        self.assertIsNone(self.manifest["failure_reason"])

    def test_accepts_completed_run_with_explicit_success_states(self):
        manifest = copy.deepcopy(self.manifest)
        manifest.update(
            {
                "processing_status": "succeeded",
                "publication_status": "published",
                "content_review_status": "passed",
                "ended_at": "2026-10-15T08:02:00Z",
            }
        )
        validate_run_manifest(manifest)

    def test_rejects_unknown_statuses_without_defaulting_to_success(self):
        for field in (
            "processing_status",
            "publication_status",
            "content_review_status",
        ):
            with self.subTest(field=field):
                manifest = copy.deepcopy(self.manifest)
                manifest[field] = "unknown"
                with self.assertRaisesRegex(ValueError, "unknown status"):
                    validate_run_manifest(manifest)

    def test_rejects_missing_input_identity_or_tool_version(self):
        for field, value in (
            ("inputs", []),
            ("tool_versions", {}),
        ):
            with self.subTest(field=field):
                manifest = copy.deepcopy(self.manifest)
                manifest[field] = value
                with self.assertRaises(ValueError):
                    validate_run_manifest(manifest)

    def test_rejects_invalid_or_duplicate_input_hash_records(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["inputs"][0]["sha256"] = "not-a-digest"
        with self.assertRaisesRegex(ValueError, "lowercase SHA-256"):
            validate_run_manifest(manifest)

        manifest = copy.deepcopy(self.manifest)
        manifest["inputs"].append(copy.deepcopy(manifest["inputs"][0]))
        with self.assertRaisesRegex(ValueError, "repeats id"):
            validate_run_manifest(manifest)

    def test_requires_utc_timestamps_in_correct_order(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["started_at"] = "2026-10-15T08:00:00+00:00"
        with self.assertRaisesRegex(ValueError, "ending in 'Z'"):
            validate_run_manifest(manifest)

        manifest = copy.deepcopy(self.manifest)
        manifest.update(
            {
                "processing_status": "succeeded",
                "ended_at": "2026-10-15T07:59:59Z",
            }
        )
        with self.assertRaisesRegex(ValueError, "earlier than started_at"):
            validate_run_manifest(manifest)

    def test_failed_status_requires_timestamp_and_reason(self):
        manifest = copy.deepcopy(self.manifest)
        manifest.update(
            {
                "processing_status": "failed",
                "ended_at": "2026-10-15T08:01:00Z",
                "failed_at": "2026-10-15T08:00:30Z",
            }
        )
        with self.assertRaisesRegex(ValueError, "failure_reason"):
            validate_run_manifest(manifest)

        manifest["failure_reason"] = "synthetic processing error"
        validate_run_manifest(manifest)

    def test_rejects_unexpected_fields_and_non_utc_failure_time(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["legacy_status"] = "passed"
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            validate_run_manifest(manifest)

        manifest = copy.deepcopy(self.manifest)
        manifest.update(
            {
                "processing_status": "failed",
                "ended_at": "2026-10-15T08:01:00Z",
                "failed_at": "2026-10-15T08:00:30+00:00",
                "failure_reason": "synthetic processing error",
            }
        )
        with self.assertRaisesRegex(ValueError, "ending in 'Z'"):
            validate_run_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
