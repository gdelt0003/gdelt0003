import json
import unittest
from pathlib import Path

from scripts.event_identity import build_event_id


def shipyard_event():
    return {
        "event_date": "2026-10-06",
        "event_time_local": "10:00",
        "time_precision": "minute",
        "timezone": "America/New_York",
        "location": "Baltimore, Maryland",
        "event_type": "shipyard groundbreaking remarks",
        "title": "President Trump Delivers Remarks",
        "participants": ["President Trump", "Secretary of the Navy"],
        "upload_date": "2026-10-07",
    }


class EventIdentityTests(unittest.TestCase):
    def test_catalog_key_matches_the_canonical_event_identity(self):
        catalog_path = Path(__file__).parents[1] / "outputs" / "event-catalog.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        shipyard = catalog["events"][0]
        self.assertEqual(
            build_event_id(shipyard["identity"]),
            shipyard["event_id"],
        )
        self.assertIsNone(catalog["events"][1]["event_id"])

    def test_same_canonical_event_is_stable_and_order_independent(self):
        event = shipyard_event()
        event["participants"] = list(reversed(event["participants"]))
        self.assertEqual(build_event_id(event), build_event_id(shipyard_event()))

    def test_different_date_location_time_or_people_get_different_ids(self):
        original = shipyard_event()
        original_id = build_event_id(original)
        changes = (
            {"event_date": "2026-10-10"},
            {"event_time_local": "11:00"},
            {"location": "Washington, DC"},
            {"participants": ["President Trump", "Another speaker"]},
            {"event_type": "Columbus Day celebration"},
        )
        for change in changes:
            with self.subTest(change=change):
                self.assertNotEqual(
                    original_id,
                    build_event_id({**original, **change}),
                )

    def test_day_precision_never_fabricates_time(self):
        event = shipyard_event()
        event.update(
            event_time_local=None,
            time_precision="day",
            timezone=None,
        )
        self.assertTrue(build_event_id(event).startswith("evt-20261006-"))
        with self.assertRaisesRegex(ValueError, "must not invent"):
            build_event_id({**event, "event_time_local": "00:00"})

    def test_rejects_incomplete_or_invalid_event_identity(self):
        with self.assertRaisesRegex(ValueError, "Missing event identity fields"):
            build_event_id({"event_date": "2026-10-06"})
        with self.assertRaisesRegex(ValueError, "ISO YYYY-MM-DD"):
            build_event_id({**shipyard_event(), "event_date": "10/06/2026"})
        with self.assertRaisesRegex(ValueError, "local time and timezone"):
            build_event_id({**shipyard_event(), "timezone": ""})


if __name__ == "__main__":
    unittest.main()
