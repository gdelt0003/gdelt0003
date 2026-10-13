import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from scripts.build_event_workbook import (
    build_workbook,
    load_catalog,
    load_source_registry,
)
from scripts.import_event_source_registry import import_registry
from scripts.record_event_source_attempt import record_attempt


class EventSourceRegistryTests(unittest.TestCase):
    def test_manual_excel_additions_and_user_annotations_round_trip(self):
        catalog = load_catalog(Path("outputs/event-catalog.json"))
        registry_path = Path("config/event-discovery-sources.json")
        registry = load_source_registry(registry_path)
        with tempfile.TemporaryDirectory() as directory:
            workbook_path = Path(directory) / "event-sources.xlsx"
            build_workbook(catalog, workbook_path, source_registry=registry)
            workbook = load_workbook(workbook_path)
            sheet = workbook["Source Directory"]
            sheet.append(
                [
                    "manual-added-source",
                    "news",
                    "Example source",
                    "https://example.com/event",
                    True,
                    "manual_review",
                    "weekly",
                    None,
                    "not_connected",
                    "not_independently_checked",
                    "user",
                    "Added during manual review",
                    None,
                    "https://example.com/event",
                    "用户在会话中对该来源的原始注解。",
                ]
            )
            workbook.save(workbook_path)
            workbook.close()

            imported = import_registry(workbook_path, registry_path)

        manual = next(
            source
            for source in imported["sources"]
            if source["source_id"] == "manual-added-source"
        )
        self.assertEqual(manual["url"], "https://example.com/event")
        self.assertEqual(
            manual["user_source_annotation_verbatim"],
            "用户在会话中对该来源的原始注解。",
        )
        self.assertEqual(
            imported["user_terminology_verbatim"],
            "为御注",
        )
        self.assertEqual(
            imported["user_field_expansion_permission_verbatim"],
            "你们乐意添加",
        )

    def test_source_registry_rejects_duplicate_ids_and_non_https_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(
                json.dumps(
                    {
                        "sources": [
                            {"source_id": "same", "url": "https://example.com/one"},
                            {"source_id": "same", "url": "https://example.com/two"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Duplicate source_id"):
                load_source_registry(path)

            path.write_text(
                json.dumps(
                    {
                        "sources": [
                            {"source_id": "bad", "url": "http://example.com"}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                load_source_registry(path)

    def test_attempt_record_updates_status_and_run_link(self):
        registry = json.loads(
            Path("config/event-discovery-sources.json").read_text(encoding="utf-8")
        )
        record_attempt(
            registry,
            source_id="white-house-youtube",
            result="success",
            attempted_at_utc="2026-10-13T12:00:00+00:00",
            run_url="https://github.com/example/repo/actions/runs/123",
        )
        source = next(
            entry
            for entry in registry["sources"]
            if entry["source_id"] == "white-house-youtube"
        )
        self.assertEqual(source["last_result"], "success_metadata_only")
        self.assertEqual(source["access_status"], "metadata_endpoint_reached")
        self.assertEqual(
            source["last_run_url"],
            "https://github.com/example/repo/actions/runs/123",
        )

    def test_disabled_source_attempt_is_recorded_as_skipped(self):
        registry = {
            "sources": [
                {"source_id": "disabled", "enabled": False},
            ]
        }
        record_attempt(
            registry,
            source_id="disabled",
            result="skipped",
            attempted_at_utc="2026-10-13T12:00:00+00:00",
            run_url="https://github.com/example/repo/actions/runs/124",
        )
        self.assertEqual(registry["sources"][0]["last_result"], "skipped_disabled")
        self.assertEqual(registry["sources"][0]["access_status"], "disabled_by_user")

    def test_attempt_record_rejects_unknown_source_and_invalid_result(self):
        registry = {"sources": []}
        with self.assertRaisesRegex(ValueError, "Expected one registered source"):
            record_attempt(
                registry,
                source_id="missing",
                result="success",
                attempted_at_utc="2026-10-13T12:00:00+00:00",
                run_url="https://github.com/example/repo/actions/runs/123",
            )
        with self.assertRaisesRegex(ValueError, "result must"):
            record_attempt(
                {"sources": [{"source_id": "known"}]},
                source_id="known",
                result="unknown",
                attempted_at_utc="2026-10-13T12:00:00+00:00",
                run_url="https://github.com/example/repo/actions/runs/123",
            )


if __name__ == "__main__":
    unittest.main()
