from io import BytesIO
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from scripts.discover_gdelt_articles import fetch_articles, normalize_articles


class GdeltDiscoveryTests(unittest.TestCase):
    def test_article_metadata_stays_unassigned_and_https_only(self):
        result = normalize_articles(
            {
                "articles": [
                    {
                        "url": "https://news.example/story",
                        "title": "Trump appears at an event",
                        "domain": "news.example",
                        "seendate": "20261013T120000Z",
                        "language": "English",
                        "sourcecountry": "United States",
                    },
                    {"url": "http://news.example/insecure"},
                    {"url": "https://news.example/story"},
                    None,
                ]
            },
            "2026-10-13T12:30:00+00:00",
        )
        self.assertEqual(len(result["leads"]), 1)
        lead = result["leads"][0]
        self.assertIsNone(lead["event_id"])
        self.assertIsNone(lead["event_date"])
        self.assertEqual(lead["assignment_status"], "unassigned_event_lead")
        self.assertEqual(lead["evidence_status"], "article_metadata_only")
        self.assertIn("not event time", result["identity_rule"])

    def test_rejects_empty_results_without_success_shaped_fallback(self):
        with self.assertRaisesRegex(ValueError, "no article entries"):
            normalize_articles({"articles": []}, "2026-10-13T12:30:00+00:00")

    @patch("scripts.discover_gdelt_articles.urlopen")
    def test_fetch_requests_json_article_metadata(self, mocked_urlopen):
        mocked_urlopen.return_value = BytesIO(b'{"articles": []}')
        result = fetch_articles("trump", 250, "1w")

        self.assertEqual(result, {"articles": []})
        request = mocked_urlopen.call_args.args[0]
        self.assertIn("mode=ArtList", request.full_url)
        self.assertIn("maxrecords=250", request.full_url)
        self.assertIn("query=trump", request.full_url)

    @patch("scripts.discover_gdelt_articles.urlopen")
    def test_rate_limit_error_is_reported_with_retry_after(self, mocked_urlopen):
        error = HTTPError(
            "https://api.gdeltproject.org",
            429,
            "Too Many Requests",
            {"Retry-After": "60"},
            BytesIO(b""),
        )
        mocked_urlopen.side_effect = error
        with self.assertRaisesRegex(
            RuntimeError, "HTTP 429 Too Many Requests; Retry-After: 60"
        ):
            fetch_articles("trump", 250, "1w")
        error.close()


if __name__ == "__main__":
    unittest.main()
