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
                started_at_utc="2026-10-16T12:05:00+00:00",
            )

        self.assertEqual(first_run["new_video_ids"], [VIDEO_ID])
        self.assertEqual(first_run["already_seen_video_ids"], [VIDEO_ID])
        self.assertEqual(second_run["new_video_ids"], [])
        self.assertEqual(second_run["already_seen_video_ids"], [VIDEO_ID])
        self.assertEqual(second_state["videos"][VIDEO_ID]["title"], "New video")

    def test_each_new_video_has_individual_run_and_source_page_provenance(self):
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
            self.assertEqual(record["full_research"]["run_url"], RUN_URL)
            self.assertEqual(
                record["full_research"]["status"],
                "not_started_blocked_waiting_for_authorization_and_rights",
            )
            self.assertNotIn("started_at_utc", record["full_research"])
            self.assertTrue(record["full_research"]["blocked_at_utc"])

    def test_full_research_is_truthfully_blocked_without_exact_video_authorization(self):
        state, run = run_monitor(
            state=empty_state(),
            run_id="123",
            run_url=RUN_URL,
            trigger="schedule",
            poller=lambda: {"entries": [{"id": VIDEO_ID, "title": "New video"}]},
            page_researcher=page_research,
            started_at_utc=STARTED_AT,
        )
        record = state["videos"][VIDEO_ID]
        full_research = record["full_research"]

        self.assertEqual(full_research["authorization_status"], "not_provided_for_this_video")
        self.assertEqual(full_research["reuse_rights_status"], "unknown_not_inferred")
        self.assertEqual(full_research["media_inspection_status"], "blocked_not_attempted")
        self.assertEqual(full_research["publication_status"], "not_published")
        self.assertIn(
            f"explicit processing authorization naming video ID {VIDEO_ID}",
            full_research["missing_items"],
        )
        self.assertIn(
            "source-specific reuse-rights evidence and confirmation; the polling request does not grant reuse rights",
            full_research["missing_items"],
        )
        summary = format_run_summary(run)
        self.assertIn(
            "Full event/media research: **not started; blocked pending authorization and rights**.",
            summary,
        )
        self.assertIn(f"Research notice: {VIDEO_ID}", summary)
        self.assertIn("GitHub Actions may queue or delay scheduled runs", summary)
        self.assertNotIn("fully researched", summary.lower())
        annotations = format_warning_annotations(run)
        self.assertTrue(any(VIDEO_ID in line for line in annotations))
        self.assertTrue(any("authorization naming video ID" in line for line in annotations))

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
            started_at_utc=STARTED_AT,
        )

        record = state["videos"][VIDEO_ID]
        self.assertEqual(record["official_source_page_research"]["status"], "failed")
        self.assertIn(
            "successful official video watch-page metadata retrieval",
            record["full_research"]["missing_items"],
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
            started_at_utc=STARTED_AT,
        )

        self.assertEqual(run["status"], "failure")
        self.assertEqual(
            run["metadata_discovery_status"], "metadata_discovery_failed"
        )
        self.assertIn("no video entries", run["error"])

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
