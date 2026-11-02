import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

from scripts.build_event_workbook import (
    build_workbook,
    load_catalog,
    load_source_registry,
)


class EventWorkbookTests(unittest.TestCase):
    def test_catalog_workbook_preserves_unknown_event_time_and_source_evidence(self):
        catalog_path = Path("outputs/event-catalog.json")
        catalog = load_catalog(catalog_path)
        source_registry = load_source_registry(
            Path("config/event-discovery-sources.json")
        )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "event-sources.xlsx"
            build_workbook(catalog, output, source_registry=source_registry)
            workbook = load_workbook(output, read_only=False, data_only=True)

        self.assertEqual(
            workbook.sheetnames,
            ["Events", "Sources", "Source Directory", "Read me", "User Instructions"],
        )
        events = list(workbook["Events"].values)
        headers = events[0]
        columbus = next(row for row in events[1:] if row[2] == "President Trump Hosts a Columbus Day Celebration")
        self.assertIsNone(columbus[headers.index("Event date")])
        self.assertIsNone(columbus[headers.index("Event local time")])
        self.assertEqual(columbus[headers.index("Identity status")], "incomplete")
        self.assertGreaterEqual(columbus[headers.index("Source count")], 10)
        self.assertEqual(
            columbus[headers.index("President attendance duration (minutes; verified)")],
            None,
        )
        self.assertEqual(
            columbus[headers.index("Speech word count (verified; language/method)")],
            None,
        )
        instruction_rows = list(workbook["User Instructions"].values)
        instructions = " ".join(str(row[1]) for row in instruction_rows[1:])
        self.assertIn("为御注", instructions)
        self.assertIn("你们乐意添加", instructions)

        source_rows = list(workbook["Sources"].values)
        source_headers = source_rows[0]
        fox_news = next(row for row in source_rows[1:] if row[source_headers.index("Publisher")] == "Fox News")
        self.assertEqual(fox_news[source_headers.index("Video resolution")], "unknown")
        self.assertEqual(fox_news[source_headers.index("Frame review")], "sampled_at_20:01,25:01,27:01")
        self.assertEqual(fox_news[source_headers.index("Clean-source status")], "unverified")
        ap = next(
            row for row in source_rows[1:]
            if row[source_headers.index("Publisher")] == "Associated Press"
        )
        self.assertEqual(ap[source_headers.index("Video resolution")], "1920x1080 (HD1080 player decode)")
        self.assertEqual(ap[source_headers.index("Clean-source status")], "failed")
        self.assertIn("not watermark-free", ap[source_headers.index("Evidence and limitations")])
        for row in source_rows[1:]:
            local_time = row[source_headers.index("Page-published local display (not event time)")]
            timestamp = row[source_headers.index("Published metadata (UTC; not event time)")]
            if local_time and timestamp:
                parsed_local = datetime.strptime(local_time, "%Y-%m-%d %H:%M PDT")
                expected_utc = parsed_local.replace(
                    tzinfo=ZoneInfo("America/Los_Angeles")
                ).astimezone(timezone.utc)
                self.assertEqual(
                    datetime.fromisoformat(timestamp),
                    expected_utc,
                    f"publication timestamp mismatch for {row[source_headers.index('Source URL')]}",
                )

    def test_source_directory_and_user_context_are_included(self):
        catalog = load_catalog(Path("outputs/event-catalog.json"))
        source_registry = load_source_registry(
            Path("config/event-discovery-sources.json")
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "event-sources.xlsx"
            build_workbook(catalog, output, source_registry=source_registry)
            workbook = load_workbook(output, read_only=False, data_only=True)

        directory_rows = list(workbook["Source Directory"].values)
        source_headers = directory_rows[0]
        white_house = next(
            row for row in directory_rows[1:]
            if row[source_headers.index("Source ID")] == "white-house-youtube"
        )
        self.assertEqual(
            white_house[source_headers.index("Collection mode")],
            "automated_metadata",
        )
        gdelt = next(
            row for row in directory_rows[1:]
            if row[source_headers.index("Source ID")] == "gdelt-trump-articles"
        )
        self.assertEqual(
            gdelt[source_headers.index("Collection mode")],
            "automated_metadata",
        )
        self.assertEqual(
            white_house[source_headers.index("User-provided URL (verbatim)")],
            "https://www.youtube.com/@WhiteHouse",
        )
        self.assertEqual(
            white_house[source_headers.index("User annotation on this source (verbatim)")],
            None,
        )
        self.assertEqual(len(directory_rows) - 1, 13)
        additional_source = next(
            row for row in directory_rows[1:]
            if row[source_headers.index("Source ID")] == "forth-trump-social-lists"
        )
        self.assertEqual(
            additional_source[source_headers.index("Collection mode")],
            "manual_review",
        )
        instructions = " ".join(
            str(row[1]) for row in workbook["User Instructions"].values
        )
        self.assertIn("https://www.forth.news/lists/trumpts", instructions)

    def test_gdelt_articles_are_exported_as_metadata_only_leads(self):
        catalog = load_catalog(Path("outputs/event-catalog.json"))
        articles = {
            "checked_at_utc": "2026-10-13T12:00:00+00:00",
            "leads": [
                {
                    "title": "Recent Trump article",
                    "publisher": "example.com",
                    "url": "https://example.com/article",
                    "seen_date_utc_metadata": "20261013T110000Z",
                    "language": "English",
                    "source_country": "United States",
                    "assignment_status": "unassigned_event_lead",
                    "evidence_status": "article_metadata_only",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "event-sources.xlsx"
            build_workbook(catalog, output, gdelt_discovery=articles)
            workbook = load_workbook(output, read_only=False, data_only=True)

        self.assertIn("GDELT Article Leads", workbook.sheetnames)
        rows = list(workbook["GDELT Article Leads"].values)
        headers = rows[0]
        lead = rows[1]
        self.assertIsNone(lead[headers.index("Event ID")])
        self.assertEqual(lead[headers.index("Evidence status")], "article_metadata_only")
        self.assertIn("not verify event occurrence", lead[headers.index("Source/search limitations")])
        workbook.close()


if __name__ == "__main__":
    unittest.main()
