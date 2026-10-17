import json
from email.message import Message
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import research_rose_garden_source_attempts as attempts


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "research-rose-garden-source-attempts.yml"


class FakeResponse:
    def __init__(self, body, content_type="text/html", url="https://example.test/"):
        self.body = body
        self.status = 200
        self.url = url
        self.headers = Message()
        self.headers["Content-Type"] = f"{content_type}; charset=utf-8"
        self.read_called = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit):
        self.read_called = True
        return self.body[:limit]

    def geturl(self):
        return self.url


class RoseGardenSourceAttemptTests(unittest.TestCase):
    def test_inventory_has_thirteen_individual_urls_and_expected_sources(self):
        inventory = json.loads(
            (ROOT / "config" / "event-discovery-sources.json").read_text(encoding="utf-8")
        )
        sources = inventory["sources"]
        self.assertEqual(len(sources), 13)
        self.assertEqual(len({source["url"] for source in sources}), 13)
        self.assertEqual(len({source["source_id"] for source in sources}), 13)
        self.assertIn("https://www.forth.news/lists/trumpts", {source["url"] for source in sources})

    def test_research_attempts_each_registered_url_and_records_fetch_failure(self):
        inventory = json.loads(
            (ROOT / "config" / "event-discovery-sources.json").read_text(encoding="utf-8")
        )
        called_urls = []

        def fake_urlopen(request, timeout):
            called_urls.append(request.full_url)
            if "rollcall.com" in request.full_url:
                raise OSError("connection refused")
            if "bing.com" in request.full_url:
                body = (
                    "<rss><channel><item><title>Rose Garden Lunch video</title>"
                    "<link>https://news.example/rose-garden-lunch-video</link>"
                    "<description>Trump Rose Garden Lunch October 15, 2026</description>"
                    "</item></channel></rss>"
                ).encode()
                return FakeResponse(body, "application/rss+xml", request.full_url)
            page = (
                "<html><head><title>Source page</title>"
                '<meta name="description" content="Rose Garden Lunch"></head>'
                '<body><a href="https://example.test/rose-garden-lunch-video">'
                "Rose Garden Lunch video</a></body></html>"
            ).encode()
            return FakeResponse(page, url=request.full_url)

        with tempfile.TemporaryDirectory() as temp, patch.object(
            attempts.urllib.request, "urlopen", side_effect=fake_urlopen
        ):
            report = attempts.research(Path(temp))
            saved = json.loads(
                (Path(temp) / "rose-garden-source-attempts.json").read_text(encoding="utf-8")
            )
            summary = (Path(temp) / "rose-garden-source-attempts.md").read_text(encoding="utf-8")

        self.assertEqual(report["source_attempt_count"], 13)
        self.assertEqual(report["source_not_attempted_count"], 0)
        self.assertEqual(report["search_query_attempt_count"], sum(len(a["queries"]) for a in attempts.SEARCH_AVENUES))
        self.assertTrue(all(row["attempted"] for row in saved["source_attempts"]))
        self.assertTrue(all(row["attempted_at_utc"] for row in saved["source_attempts"]))
        expected_request_urls = {
            source["url"].split("#", 1)[0] for source in inventory["sources"]
        }
        observed_source_urls = {url for url in called_urls if "bing.com" not in url}
        self.assertEqual(observed_source_urls, expected_request_urls)
        failed = [row for row in saved["source_attempts"] if row["access_status"] == "fetch_error"]
        self.assertEqual(len(failed), 3)
        self.assertIn("connection refused", failed[0]["error"])
        self.assertTrue(all(lead["lead_status"].startswith("unverified") for lead in saved["candidate_leads"]))
        self.assertTrue(all(lead["discovered_from_url"] for lead in saved["candidate_leads"]))
        self.assertIn("- Exact inventory rows attempted: 13 / 13", summary)
        self.assertIn("absence of other sources", summary)
        self.assertFalse(saved["media_downloaded"])
        self.assertFalse(saved["media_frames_audio_inspected"])
        self.assertFalse(saved["event_facts_verified"])

    def test_fragment_is_logged_but_not_sent_to_server(self):
        source = {
            "source_id": "gdelt",
            "name": "GDELT Explorer",
            "category": "news_search",
            "url": "https://gdelt.github.io/#api=doc&query=trump",
        }
        observed = {}

        def fake_urlopen(request, timeout):
            observed["url"] = request.full_url
            return FakeResponse(b"<html><title>GDELT Explorer</title></html>", url=request.full_url)

        with patch.object(attempts.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = attempts._source_attempt(source)

        self.assertEqual(result["url"], source["url"])
        self.assertEqual(observed["url"], "https://gdelt.github.io/")
        self.assertTrue(result["url_fragment_excluded_from_http_request"])
        self.assertTrue(result["attempted"])

    def test_non_html_source_response_is_logged_without_reading_body(self):
        source = {
            "source_id": "media",
            "name": "Media endpoint",
            "category": "official_video",
            "url": "https://example.test/video",
        }
        response = FakeResponse(b"media bytes", "video/mp4", source["url"])
        with patch.object(attempts.urllib.request, "urlopen", return_value=response):
            result = attempts._source_attempt(source)

        self.assertEqual(result["http_status"], 200)
        self.assertEqual(result["access_status"], "non_html_response")
        self.assertIn("video/mp4", result["error"])
        self.assertFalse(response.read_called)

    def test_workflow_is_hosted_scheduled_and_uploads_report_without_media_tools(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("schedule:", workflow)
        self.assertIn("push:", workflow)
        self.assertIn("runs-on: ubuntu-latest", workflow)
        self.assertIn("research_rose_garden_source_attempts.py", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertNotIn("yt-dlp", workflow.lower())
        self.assertNotIn("deploy-pages", workflow.lower())


if __name__ == "__main__":
    unittest.main()
