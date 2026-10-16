import json
from email.message import Message
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.research_rose_garden_sources import (
    EVENT_ID,
    SEARCH_PROVIDERS,
    SEARCH_QUERIES,
    inspect_landing_page,
    research,
)


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "research-rose-garden-sources.yml"


class FakeResponse:
    def __init__(self, body, content_type="text/html", url="https://example.test/page"):
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


class RoseGardenMetadataResearchTests(unittest.TestCase):
    def test_search_records_landing_metadata_only_as_unverified(self):
        search_html = (
            '<a class="result__a" href="https://example.test/rose">'
            "Rose Garden report</a>"
        ).encode()
        landing_html = (
            "<html><head><title>Rose Garden report</title>"
            '<meta name="description" content="Page summary">'
            '<meta property="og:site_name" content="Example News">'
            '<link rel="canonical" href="/canonical"></head></html>'
        ).encode()
        bing_rss = (
            "<rss><channel><item><title>Rose Garden report</title>"
            "<link>https://example.test/rose</link>"
            "<description>Search snippet</description></item></channel></rss>"
        ).encode()

        def fake_urlopen(request, timeout):
            self.assertGreater(timeout, 0)
            if "duckduckgo.com" in request.full_url:
                return FakeResponse(search_html, url=request.full_url)
            if "bing.com" in request.full_url:
                return FakeResponse(
                    bing_rss,
                    content_type="application/rss+xml",
                    url=request.full_url,
                )
            return FakeResponse(landing_html, url=request.full_url)

        with tempfile.TemporaryDirectory() as temp, patch(
            "scripts.research_rose_garden_sources.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            json_path, summary_path, report = research(Path(temp))
            saved = json.loads(json_path.read_text(encoding="utf-8"))
            summary = summary_path.read_text(encoding="utf-8")

        self.assertEqual(report["event_id"], EVENT_ID)
        self.assertEqual(report["search_providers"], list(SEARCH_PROVIDERS))
        self.assertEqual(report["search_query_count"], len(SEARCH_QUERIES) * 2)
        self.assertEqual(saved["candidate_count"], 1)
        lead = saved["candidates"][0]
        self.assertEqual(lead["candidate_status"], "lead_unverified")
        self.assertEqual(lead["event_match"], "unverified")
        self.assertEqual(lead["video_source_credibility"], "not_assessed")
        self.assertEqual(lead["video_content_credibility"], "not_assessed")
        self.assertEqual(lead["human_video_content_review"], "not_performed")
        self.assertFalse(lead["media_frames_audio_inspected"])
        self.assertEqual(lead["page_title"], "Rose Garden report")
        self.assertEqual(lead["search_provider"], "duckduckgo_html")
        self.assertEqual(len(lead["search_observations"]), 6)
        self.assertEqual(lead["page_description"], "Page summary")
        self.assertEqual(lead["site_name"], "Example News")
        self.assertEqual(lead["canonical_url"], "https://example.test/canonical")
        self.assertIn("all leads are unverified", summary)
        self.assertIn("Human video-content review: not performed", summary)
        self.assertIn("not an exhaustive web census", report["search_coverage"])

    def test_refuses_non_html_media_responses_before_reading_body(self):
        response = FakeResponse(b"not media bytes", content_type="video/mp4")
        with patch(
            "scripts.research_rose_garden_sources.urllib.request.urlopen",
            return_value=response,
        ):
            result = inspect_landing_page(
                {
                    "query": SEARCH_QUERIES[0],
                    "search_url": "https://search.example",
                    "search_http_status": "200",
                    "search_checked_at": "now",
                    "url": "https://example.test/video.mp4",
                    "title": "video result",
                },
                "now",
            )
        self.assertIn("Refused non-HTML", result["landing_page_metadata_error"])
        self.assertFalse(response.read_called)

    def test_workflow_is_manual_main_only_and_never_publishes(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertIn("runs-on: ubuntu-latest", workflow)
        self.assertIn('GITHUB_REF" != "refs/heads/main"', workflow)
        self.assertIn("research_rose_garden_sources.py", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertNotIn("actions/deploy-pages@", workflow)
        self.assertNotIn("gh release", workflow.lower())
        self.assertNotIn("yt-dlp", workflow.lower())


if __name__ == "__main__":
    unittest.main()
