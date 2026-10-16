import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "public_source_discovery.py"
SPEC = importlib.util.spec_from_file_location("public_source_discovery", SCRIPT)
discovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(discovery)


class PublicSourceDiscoveryTests(unittest.TestCase):
    def test_bluesky_results_are_direct_unverified_post_leads(self):
        payload = {
            "posts": [
                {
                    "uri": "at://did:plc:abc/app.bsky.feed.post/post-key",
                    "indexedAt": "2026-10-14T15:00:00Z",
                    "record": {
                        "text": "Reaction",
                        "createdAt": "2026-10-14T14:59:00Z",
                    },
                    "author": {"handle": "example.bsky.social"},
                }
            ]
        }
        items = discovery.parse("bluesky", json.dumps(payload))
        self.assertEqual(
            items[0]["url"],
            "https://bsky.app/profile/example.bsky.social/post/post-key",
        )
        self.assertEqual(
            items[0]["raw_date_metadata"]["createdAt"],
            "2026-10-14T14:59:00Z",
        )

    def test_run_lane_keeps_records_unverified_and_attempts_failures(self):
        def fake_attempt(service, query, url):
            if service == "gdelt":
                return (
                    {
                        "service": service,
                        "query": query,
                        "request_url": url,
                        "attempted_at_utc": "2026-10-16T00:00:00+00:00",
                        "status": "reached",
                        "http_status": 200,
                    },
                    json.dumps(
                        {
                            "articles": [
                                {
                                    "title": "Briefing article",
                                    "url": "https://news.example/article",
                                    "domain": "news.example",
                                    "seendate": "20261016T000000Z",
                                }
                            ]
                        }
                    ),
                )
            return (
                {
                    "service": service,
                    "query": query,
                    "request_url": url,
                    "attempted_at_utc": "2026-10-16T00:00:01+00:00",
                    "status": "rate_limited",
                    "http_status": 429,
                    "error": "HTTP 429 Too Many Requests",
                },
                None,
            )

        with patch.object(discovery, "attempt", side_effect=fake_attempt):
            report = discovery.run_lane(
                "news",
                "Katie Zacharia White House briefing 2026-10-13",
                "https://github.com/example/repo/actions/runs/123",
            )
        self.assertEqual(report["status"], "results_unverified")
        self.assertEqual(report["attempts"][1]["status"], "rate_limited")
        self.assertEqual(report["leads"][0]["record_status"], "unassigned/unverified lead")
        self.assertEqual(report["leads"][0]["event_match_status"], "unverified")
        self.assertEqual(report["leads"][0]["raw_date_metadata"]["seendate"], "20261016T000000Z")
        self.assertIn("runs/123", report["leads"][0]["attempt_url"])

    def test_endpoints_cover_requested_lanes_without_credentials(self):
        endpoint_map = discovery.endpoints("Katie Zacharia briefing")
        self.assertEqual(
            set(endpoint_map),
            {
                "news",
                "newspapers",
                "social",
                "forums",
                "internet-archive",
                "library-catalog",
                "google-search",
                "scholarly-metadata",
            },
        )
        services = {service for lane in endpoint_map.values() for service, _ in lane}
        self.assertTrue({"gdelt", "google-news-rss", "google-news-newspaper-search"} <= services)
        self.assertTrue({"loc", "openlibrary"} <= services)
        self.assertTrue({"openalex", "crossref"} <= services)
        self.assertTrue({"google-web", "google-scholar"} <= services)
        self.assertTrue({"bluesky", "reddit", "hacker-news"} <= services)

    def test_google_search_is_not_fetched_when_robots_disallows_it(self):
        with (
            patch.object(discovery, "robots_allows", return_value=(False, None)),
            patch.object(discovery, "attempt") as request,
            patch.object(discovery.time, "sleep"),
        ):
            report = discovery.run_lane(
                "google-search",
                "Katie Zacharia White House briefing 2026-10-13",
                "https://github.com/example/repo/actions/runs/123",
            )
        request.assert_not_called()
        self.assertEqual(report["status"], "unavailable_or_blocked")
        self.assertTrue(
            all(item["status"] == "robots_disallowed" for item in report["attempts"])
        )


if __name__ == "__main__":
    unittest.main()
