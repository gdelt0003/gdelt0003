import unittest

from scripts.prepare_event_production import prepare_metadata
from scripts.register_event_release import publication_record


class PrepareEventProductionTests(unittest.TestCase):
    def setUp(self):
        self.identity = {
            "event_date": "2026-10-09",
            "event_time_local": None,
            "time_precision": "day",
            "timezone": None,
            "location": "White House East Room",
            "event_type": "Columbus Day celebration",
            "title": "President Hosts a Columbus Day Celebration",
            "participants": ["President Trump"],
            "official_video_url": "https://www.youtube.com/watch?v=official",
            "verified_source_urls": [
                "https://www.youtube.com/watch?v=reviewed-alternative"
            ],
        }
        self.evidence = {
            "identity_evidence_url": "https://example.com/event",
            "source_match_evidence_url": "https://example.com/matched-frames",
            "same_event_match_confirmed": True,
            "rights_evidence_url": "https://example.com/rights",
        }

    def prepare(self, source_url):
        return prepare_metadata(
            self.identity,
            source_url=source_url,
            **self.evidence,
            prepared_at="2026-10-13T00:00:00+00:00",
        )

    def test_accepts_official_anchor_and_records_selected_source(self):
        metadata = self.prepare(self.identity["official_video_url"])

        self.assertEqual(metadata["source_url"], self.identity["official_video_url"])
        self.assertEqual(metadata["official_video_url"], self.identity["official_video_url"])
        self.assertEqual(
            metadata["source_match_evidence_url"],
            self.evidence["source_match_evidence_url"],
        )

    def test_accepts_only_explicitly_verified_same_event_alternative(self):
        metadata = self.prepare(self.identity["verified_source_urls"][0])

        self.assertEqual(metadata["source_url"], self.identity["verified_source_urls"][0])

    def test_rejects_unlisted_alternative(self):
        with self.assertRaisesRegex(ValueError, "verified_source_urls"):
            self.prepare("https://www.youtube.com/watch?v=unreviewed")

    def test_rejects_unconfirmed_same_event_match(self):
        with self.assertRaisesRegex(ValueError, "exact event"):
            prepare_metadata(
                self.identity,
                source_url=self.identity["official_video_url"],
                **{**self.evidence, "same_event_match_confirmed": False},
            )

    def test_rejects_http_evidence(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            prepare_metadata(
                self.identity,
                source_url=self.identity["official_video_url"],
                **{**self.evidence, "source_match_evidence_url": "http://example.com"},
            )


class RegisterEventReleaseTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {
            "event_id": "evt-20261009-example",
            "identity": {"title": "Columbus Day celebration"},
            "source_url": "https://www.youtube.com/watch?v=reviewed-alternative",
            "official_video_url": "https://www.youtube.com/watch?v=official",
            "identity_evidence_url": "https://example.com/event",
            "source_match_evidence_url": "https://example.com/matched-frames",
            "same_event_match_confirmed": True,
            "rights_evidence_url": "https://example.com/rights",
        }
        self.manifest = {
            "event_id": self.metadata["event_id"],
            "highlights": [
                {
                    "id": "highlight-1",
                    "title": "A reviewed highlight",
                    "reason": "A concise, self-contained statement.",
                    "source_start": 120,
                    "source_end": 150,
                    "subtitles": "highlight-1.srt",
                    "variants": [
                        {
                            "file": "highlight-1-editorial.mp4",
                            "style": "editorial",
                            "duration_seconds": 30,
                            "resolution": "1080x1920",
                        }
                    ],
                }
            ],
        }
        self.review = {
            "reuse_rights_confirmed": True,
            "same_event_match_confirmed": True,
            "source_frames_clean": True,
            "captions_reviewed": True,
            "translation_reviewed": True,
            "evidence_urls": [
                "https://example.com/rights-review",
                "https://example.com/source-match-review",
                "https://example.com/frame-review",
                "https://example.com/asr-review",
                "https://example.com/translation-review",
            ],
        }
        self.arguments = {
            "tag": "evt-20261009-example-123",
            "release_url": "https://github.com/example/repo/releases",
            "repository": "example/repo",
            "reviewed_at": "2026-10-13T00:00:00+00:00",
        }

    def test_registry_record_retains_selected_source_and_links(self):
        record = publication_record(
            self.metadata, self.manifest, self.review, **self.arguments
        )

        self.assertEqual(record["source_url"], self.metadata["source_url"])
        self.assertEqual(record["official_video_url"], self.metadata["official_video_url"])
        self.assertEqual(len(record["clips"]), 1)
        self.assertTrue(record["clips"][0]["video_url"].endswith("highlight-1-editorial.mp4"))
        self.assertTrue(record["clips"][0]["subtitle_url"].endswith("highlight-1.srt"))

    def test_rejects_missing_reuse_rights_attestation(self):
        review = {**self.review, "reuse_rights_confirmed": False}

        with self.assertRaisesRegex(ValueError, "reuse-rights"):
            publication_record(self.metadata, self.manifest, review, **self.arguments)

    def test_rejects_missing_same_event_attestation(self):
        review = {**self.review, "same_event_match_confirmed": False}

        with self.assertRaisesRegex(ValueError, "event-match"):
            publication_record(self.metadata, self.manifest, review, **self.arguments)

    def test_requires_five_distinct_https_review_evidence_urls(self):
        review = {
            **self.review,
            "evidence_urls": [
                "https://example.com/rights-review",
                "https://example.com/rights-review",
                "https://example.com/frame-review",
                "https://example.com/asr-review",
                "https://example.com/translation-review",
            ],
        }

        with self.assertRaisesRegex(ValueError, "five distinct HTTPS"):
            publication_record(self.metadata, self.manifest, review, **self.arguments)

    def test_rejects_mismatched_event_identity(self):
        manifest = {**self.manifest, "event_id": "another-event"}

        with self.assertRaisesRegex(ValueError, "does not match"):
            publication_record(self.metadata, manifest, self.review, **self.arguments)


if __name__ == "__main__":
    unittest.main()
