import unittest

from scripts.download_authorized_source import (
    HTTPSOnlyRedirectHandler,
    validate_https_url,
    validate_manifest,
)


def reviewed_manifest():
    return {
        "event": {
            "event_id": "evt-20261013-example",
            "identity_status": "verified",
            "source_match_status": "verified",
            "same_event_match_confirmed": True,
            "source_reuse_rights_confirmed": True,
            "official_anchor_url": "https://www.whitehouse.gov/videos/example/",
            "selected_source_url": "https://example.org/authorized.mp4",
            "identity_evidence_url": "https://example.org/event",
            "source_match_evidence_url": "https://example.org/match",
            "rights_evidence_url": "https://example.org/rights",
        }
    }


class AuthorizedSourceDownloadTests(unittest.TestCase):
    def test_accepts_only_complete_reviewed_manifest(self):
        self.assertEqual(
            validate_manifest(reviewed_manifest()),
            "https://example.org/authorized.mp4",
        )

    def test_rejects_missing_event_identity_or_rights_review(self):
        manifest = reviewed_manifest()
        manifest["event"]["identity_status"] = "incomplete_unverified"
        with self.assertRaisesRegex(ValueError, "identity"):
            validate_manifest(manifest)

        manifest = reviewed_manifest()
        manifest["event"]["source_reuse_rights_confirmed"] = False
        with self.assertRaisesRegex(ValueError, "reuse rights"):
            validate_manifest(manifest)

    def test_rejects_missing_or_reused_evidence_urls(self):
        manifest = reviewed_manifest()
        manifest["event"]["rights_evidence_url"] = "https://example.org/match"
        with self.assertRaisesRegex(ValueError, "distinct"):
            validate_manifest(manifest)

    def test_rejects_non_https_and_youtube_selected_source(self):
        for url in (
            "http://example.org/video.mp4",
            "https://youtube.com/watch?v=example",
            "https://youtu.be/example",
            "https://www.youtube-nocookie.com/embed/example",
            "https://googlevideo.com/video",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_https_url(
                    url,
                    "source",
                    disallow_youtube=True,
                )

    def test_blocks_redirects_to_http_or_youtube(self):
        handler = HTTPSOnlyRedirectHandler()
        for target in ("http://example.org/file.mp4", "https://youtu.be/example"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                handler.redirect_request(None, None, 302, "Found", {}, target)


if __name__ == "__main__":
    unittest.main()
