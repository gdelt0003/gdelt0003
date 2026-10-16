import tempfile
import unittest
from unittest import mock
from pathlib import Path

from scripts.monitor_official_whitehouse_videos import (
    CHANNEL_URL,
    empty_state,
    format_run_summary,
    format_warning_annotations,
    load_state,
    research_official_video_page,
    research_related_source_metadata,
    run_monitor,
    validate_state,
    write_json,
)


RUN_URL = "https://github.com/example/repo/actions/runs/123"
VIDEO_ID = "aBcDeFgHiJ1"
OTHER_VIDEO_ID = "zYxWvUtSrQ0"
STARTED_AT = "2026-10-16T12:00:00+00:00"


def page_research(video_id, researched_at_utc):
    return {
        "status": "completed",
        "requested_url": f"https://www.youtube.com/watch?v={video_id}",
        "final_url": f"https://www.youtube.com/watch?v={video_id}",
        "http_status": 200,
        "researched_at_utc": researched_at_utc,
        "research_scope": "official watch-page HTML metadata only",
        "page_title": "Official recording",
        "page_description": "A public event recording.",
        "canonical_url": f"https://www.youtube.com/watch?v={video_id}",
    }


def source_research(title, researched_at_utc):
    return {
        "status": "completed_with_candidates",
        "api_url": "https://api.gdeltproject.org/api/v2/doc/doc",
        "query": f'"{title}"',
        "researched_at_utc": researched_at_utc,
        "research_scope": "GDELT article metadata search only; candidates are unverified leads",
        "candidate_count": 1,
        "candidates": [
            {
                "title": "Candidate coverage",
                "publisher": "example.com",
                "url": "https://example.com/story",
                "seen_date_utc_metadata": "20261016T120000Z",
                "event_id": None,
                "event_date": None,
                "evidence_status": "article_metadata_only",
            }
        ],
    }


class OfficialVideoMonitorTests(unittest.TestCase):
    def test_stable_video_ids_are_deduplicated_across_persisted_runs(self):
        first_state, first_run = run_monitor(
            state=empty_state(),
            run_id="123",
            run_url=RUN_URL,
            trigger="schedule",
            poller=lambda: {
                "entries": [
                    {"id": VIDEO_ID, "title": "New video"},
                    {"id": VIDEO_ID, "title": "Duplicate in this poll"},
                ]
            },
            page_researcher=page_research,
            source_researcher=source_research,
            started_at_utc=STARTED_AT,
        )
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            write_json(state_path, first_state)
            reloaded = load_state(state_path)
            second_state, second_run = run_monitor(
                state=reloaded,
                run_id="124",
                run_url=RUN_URL,
                trigger="schedule",
                poller=lambda: {"entries": [{"id": VIDEO_ID, "title": "Changed title"}]},
                page_researcher=lambda *_: self.fail("seen video must not be researched again"),
                source_researcher=lambda *_: self.fail("seen video must not be searched again"),
                started_at_utc="2026-10-16T12:05:00+00:00",
            )

        self.assertEqual(first_run["new_video_ids"], [VIDEO_ID])
        self.assertEqual(first_run["already_seen_video_ids"], [VIDEO_ID])
        self.assertEqual(second_run["new_video_ids"], [])
        self.assertEqual(second_run["already_seen_video_ids"], [VIDEO_ID])
        self.assertEqual(second_state["videos"][VIDEO_ID]["title"], "New video")

    def test_each_new_video_has_individual_run_and_source_page_provenance(self):
        searched_titles = []

        def search_sources(title, researched_at_utc):
            searched_titles.append(title)
            return source_research(title, researched_at_utc)

        state, run = run_monitor(
            state=empty_state(),
            run_id="123",
            run_url=RUN_URL,
            trigger="workflow_dispatch",
            poller=lambda: {
                "entries": [
                    {"id": VIDEO_ID, "title": "First"},
                    {"id": OTHER_VIDEO_ID, "title": "Second"},
                ]
            },
            page_researcher=page_research,
            source_researcher=search_sources,
            started_at_utc=STARTED_AT,
        )

        self.assertEqual(
            run["metadata_discovery_status"], "metadata_discovery_completed"
        )
        self.assertEqual(run["scheduled_cadence_minutes"], 5)
        self.assertEqual(set(run["new_video_ids"]), {VIDEO_ID, OTHER_VIDEO_ID})
        for video_id in run["new_video_ids"]:
            record = state["videos"][video_id]
            self.assertEqual(
                record["metadata_discovery"]["started_status"],
                "metadata_discovery_started",
            )
            self.assertEqual(
                record["metadata_discovery"]["status"],
                "metadata_discovery_completed",
            )
            self.assertEqual(
                record["metadata_discovery"]["started_at_utc"], STARTED_AT
            )
            self.assertTrue(record["metadata_discovery"]["completed_at_utc"])
            self.assertEqual(record["metadata_discovery"]["run_id"], "123")
            self.assertEqual(record["metadata_discovery"]["run_url"], RUN_URL)
            self.assertEqual(record["metadata_discovery"]["source_url"], CHANNEL_URL)
            self.assertEqual(record["official_source_page_research"]["status"], "completed")
            self.assertEqual(record["official_source_page_research"]["http_status"], 200)
            self.assertEqual(
                record["event_source_research"]["status"],
                "completed_with_unverified_leads",
            )
            self.assertEqual(record["event_source_research"]["run_url"], RUN_URL)
            self.assertEqual(
                record["event_source_research"]["additional_source_search"]["candidate_count"],
                1,
            )
            self.assertEqual(
                record["event_source_research"]["additional_source_search"]["candidates"][0]["evidence_status"],
                "article_metadata_only",
            )
            self.assertEqual(
                record["event_source_research"]["event_identity_status"],
                "unassigned_event_lead",
            )
            self.assertEqual(
                record["event_source_research"]["reuse_rights_research_status"],
                "not_attempted_no_configured_evidence_source",
            )
            self.assertEqual(
                record["media_review_gate"]["status"],
                "not_started_blocked_waiting_for_authorization_and_rights",
            )
            self.assertNotIn("started_at_utc", record["media_review_gate"])
            self.assertTrue(record["media_review_gate"]["blocked_at_utc"])
        self.assertCountEqual(searched_titles, ["First", "Second"])

    def test_metadata_source_research_starts_while_media_review_remains_blocked(self):
        state, run = run_monitor(
            state=empty_state(),
            run_id="123",
            run_url=RUN_URL,
            trigger="schedule",
            poller=lambda: {"entries": [{"id": VIDEO_ID, "title": "New video"}]},
            page_researcher=page_research,
            source_researcher=source_research,
            started_at_utc=STARTED_AT,
        )
        record = state["videos"][VIDEO_ID]
        event_research = record["event_source_research"]
        media_gate = record["media_review_gate"]

        self.assertEqual(event_research["status"], "completed_with_unverified_leads")
        self.assertTrue(event_research["started_at_utc"])
        self.assertTrue(event_research["completed_at_utc"])
        self.assertEqual(
            event_research["additional_source_search"]["status"],
            "completed_with_candidates",
        )
        self.assertEqual(event_research["event_identity_status"], "unassigned_event_lead")
        self.assertEqual(
            event_research["reuse_rights_research_status"],
            "not_attempted_no_configured_evidence_source",
        )
        self.assertIn(
            "no configured source provides source-specific reuse-rights evidence; rights have not been established or reviewed",
            event_research["missing_items"],
        )
        self.assertEqual(media_gate["authorization_status"], "not_provided_for_this_video")
        self.assertEqual(media_gate["reuse_rights_status"], "unknown_not_inferred")
        self.assertEqual(media_gate["media_inspection_status"], "blocked_not_attempted")
        self.assertEqual(media_gate["publication_status"], "not_published")
        self.assertIn(
            f"explicit processing authorization naming video ID {VIDEO_ID}",
            media_gate["missing_items"],
        )
        self.assertIn(
            "source-specific reuse-rights evidence and confirmation; the polling request does not grant reuse rights",
            media_gate["missing_items"],
        )
        summary = format_run_summary(run)
        self.assertIn(
            "Event/source metadata research: **completed_with_unverified_leads**.",
            summary,
        )
        self.assertIn("full event/source research is not complete", summary)
        self.assertIn(
            "Media review: **not started; blocked pending exact-video authorization and reuse-rights evidence**.",
            summary,
        )
        self.assertIn(f"Research notice: {VIDEO_ID}", summary)
        self.assertIn("GitHub Actions may queue or delay scheduled runs", summary)
        self.assertIn(
            "no external push notification is configured",
            summary,
        )
        self.assertNotIn("fully researched", summary.lower())
        annotations = format_warning_annotations(run)
        self.assertTrue(any(VIDEO_ID in line for line in annotations))
        self.assertTrue(any("authorization naming video ID" in line for line in annotations))
        self.assertTrue(any("GDELT" in line for line in annotations))

    def test_source_page_failure_stays_explicitly_incomplete(self):
        state, run = run_monitor(
            state=empty_state(),
            run_id="123",
            run_url=RUN_URL,
            trigger="schedule",
            poller=lambda: {"entries": [{"id": VIDEO_ID, "title": "New video"}]},
            page_researcher=lambda *_: (_ for _ in ()).throw(
                OSError("source page unavailable")
            ),
            source_researcher=source_research,
            started_at_utc=STARTED_AT,
        )

        record = state["videos"][VIDEO_ID]
        self.assertEqual(record["official_source_page_research"]["status"], "failed")
        self.assertIn(
            "successful official video watch-page metadata retrieval",
            record["event_source_research"]["missing_items"],
        )
        self.assertIn("source page unavailable", record["official_source_page_research"]["error"])
        self.assertIn("**failed**", format_run_summary(run))

    def test_failed_metadata_collection_is_recorded_and_not_success_shaped(self):
        state, run = run_monitor(
            state=empty_state(),
            run_id="123",
            run_url=RUN_URL,
            trigger="schedule",
            poller=lambda: (_ for _ in ()).throw(RuntimeError("endpoint unavailable")),
            page_researcher=page_research,
            source_researcher=source_research,
            started_at_utc=STARTED_AT,
        )

        self.assertEqual(run["status"], "failure")
        self.assertEqual(
            run["metadata_discovery_status"], "metadata_discovery_failed"
        )
        self.assertIn("endpoint unavailable", run["error"])
        self.assertEqual(state["videos"], {})
        self.assertTrue(
            any(
                line.startswith("::error title=Official video metadata discovery failed::")
                for line in format_warning_annotations(run)
            )
        )

    def test_empty_channel_result_is_a_collection_failure(self):
        _, run = run_monitor(
            state=empty_state(),
            run_id="123",
            run_url=RUN_URL,
            trigger="schedule",
            poller=lambda: {"entries": []},
            page_researcher=page_research,
            source_researcher=source_research,
            started_at_utc=STARTED_AT,
        )

        self.assertEqual(run["status"], "failure")
        self.assertEqual(
            run["metadata_discovery_status"], "metadata_discovery_failed"
        )
        self.assertIn("no video entries", run["error"])

    @mock.patch("scripts.monitor_official_whitehouse_videos.fetch_articles")
    def test_related_source_search_records_gdelt_metadata_candidates(self, fetch):
        fetch.return_value = {
            "articles": [
                {
                    "title": "Candidate coverage",
                    "domain": "example.com",
                    "url": "https://example.com/story",
                    "seendate": "20261016T120000Z",
                }
            ]
        }

        result = research_related_source_metadata("Official event title", STARTED_AT)

        self.assertEqual(result["status"], "completed_with_candidates")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(
            result["candidates"][0]["evidence_status"], "article_metadata_only"
        )
        self.assertIsNone(result["candidates"][0]["event_date"])
        self.assertEqual(result["query"], '"Official event title"')
        fetch.assert_called_once_with('"Official event title"', 10, "1w")

    @mock.patch("scripts.monitor_official_whitehouse_videos.fetch_articles")
    def test_gdelt_search_failure_is_recorded_as_incomplete(self, fetch):
        fetch.side_effect = RuntimeError("GDELT HTTP 429")

        result = research_related_source_metadata("Official event title", STARTED_AT)

        self.assertEqual(result["status"], "failed")
        self.assertIn("HTTP 429", result["error"])
        self.assertEqual(result["candidates"], [])

    @mock.patch("scripts.monitor_official_whitehouse_videos.fetch_articles")
    def test_no_gdelt_results_are_recorded_without_claiming_candidate_leads(self, fetch):
        fetch.return_value = {"articles": []}
        state, _ = run_monitor(
            state=empty_state(),
            run_id="123",
            run_url=RUN_URL,
            trigger="schedule",
            poller=lambda: {"entries": [{"id": VIDEO_ID, "title": "New video"}]},
            page_researcher=page_research,
            source_researcher=research_related_source_metadata,
            started_at_utc=STARTED_AT,
        )

        event_research = state["videos"][VIDEO_ID]["event_source_research"]
        self.assertEqual(
            event_research["status"], "completed_metadata_search_no_candidates"
        )
        self.assertEqual(
            event_research["additional_source_search"]["candidate_count"], 0
        )

    def test_per_video_source_search_failure_is_not_reported_as_complete(self):
        failed_search = {
            "status": "failed",
            "api_url": "https://api.gdeltproject.org/api/v2/doc/doc",
            "query": '"New video"',
            "researched_at_utc": STARTED_AT,
            "research_scope": "GDELT article metadata search only",
            "candidate_count": 0,
            "candidates": [],
            "error": "GDELT HTTP 429",
        }
        state, run = run_monitor(
            state=empty_state(),
            run_id="123",
            run_url=RUN_URL,
            trigger="schedule",
            poller=lambda: {"entries": [{"id": VIDEO_ID, "title": "New video"}]},
            page_researcher=page_research,
            source_researcher=lambda *_: failed_search,
            started_at_utc=STARTED_AT,
        )

        event_research = state["videos"][VIDEO_ID]["event_source_research"]
        self.assertEqual(event_research["status"], "completed_with_search_failure")
        self.assertTrue(event_research["completed_at_utc"])
        self.assertIn(
            "successful GDELT additional-source metadata search",
            event_research["missing_items"],
        )
        self.assertIn("GDELT HTTP 429", format_run_summary(run))

    def test_missing_title_records_source_search_blocker(self):
        result = research_related_source_metadata("", STARTED_AT)

        self.assertEqual(result["status"], "blocked_missing_official_title")
        self.assertIsNone(result["query"])

    def test_official_page_research_extracts_metadata_without_media_download(self):
        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, limit):
                self.assert_limit = limit
                return (
                    b'<meta property="og:title" content="Official title">'
                    b'<meta property="og:description" content="Official description">'
                    b'<link rel="canonical" href="https://www.youtube.com/watch?v='
                    + VIDEO_ID.encode()
                    + b'">'
                )

            def geturl(self):
                return f"https://www.youtube.com/watch?v={VIDEO_ID}"

        response = FakeResponse()

        def fake_urlopen(request, timeout):
            self.assertEqual(request.full_url, f"https://www.youtube.com/watch?v={VIDEO_ID}")
            self.assertEqual(timeout, 20)
            return response

        with mock.patch(
            "scripts.monitor_official_whitehouse_videos.urlopen", fake_urlopen
        ):
            result = research_official_video_page(VIDEO_ID, STARTED_AT)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["page_title"], "Official title")
        self.assertEqual(result["page_description"], "Official description")
        self.assertIn("HTML metadata only", result["research_scope"])
        self.assertEqual(response.assert_limit, 2 * 1024 * 1024)
        self.assertFalse(hasattr(response, "video_downloaded"))

    def test_state_validation_rejects_corruption_instead_of_resetting_dedupe(self):
        with self.assertRaisesRegex(ValueError, "version 1 object"):
            validate_state({"schema_version": 2, "videos": {}})
        with self.assertRaisesRegex(ValueError, "invalid video record"):
            validate_state({"schema_version": 1, "videos": {"bad": {}}})


if __name__ == "__main__":
    unittest.main()
