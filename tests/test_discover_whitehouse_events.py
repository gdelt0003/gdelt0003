import unittest

from scripts.discover_whitehouse_events import normalize_entries


class WhiteHouseDiscoveryTests(unittest.TestCase):
    def test_upload_dates_are_not_mapped_to_event_identity(self):
        result = normalize_entries(
            {
                "entries": [
                    {
                        "id": "noI4BbQ2wZQ",
                        "title": "President Trump Hosts a Columbus Day Celebration",
                        "channel": "The White House",
                        "upload_date": "20261010",
                        "timestamp": 1791623286,
                        "duration": 3764,
                    }
                ]
            },
            "2026-10-13T00:00:00+00:00",
        )
        lead = result["leads"][0]
        self.assertEqual(lead["event_id"], None)
        self.assertEqual(lead["event_date"], None)
        self.assertEqual(lead["upload_date_metadata"], "20261010")
        self.assertEqual(lead["assignment_status"], "unassigned_event_lead")
        self.assertEqual(lead["url"], "https://www.youtube.com/watch?v=noI4BbQ2wZQ")

    def test_rejects_empty_playlist_results(self):
        with self.assertRaisesRegex(ValueError, "no video entries"):
            normalize_entries({"entries": []}, "2026-10-13T00:00:00+00:00")

    def test_deduplicates_video_ids_and_ignores_malformed_entries(self):
        result = normalize_entries(
            {
                "entries": [
                    {"id": "first", "title": "First"},
                    {"id": "first", "title": "Duplicate"},
                    None,
                    {"title": "No ID"},
                ]
            },
            "2026-10-13T00:00:00+00:00",
        )
        self.assertEqual(len(result["leads"]), 1)
        self.assertEqual(result["leads"][0]["title"], "First")


if __name__ == "__main__":
    unittest.main()
