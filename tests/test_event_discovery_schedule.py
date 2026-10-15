import unittest
from pathlib import Path


class EventDiscoveryScheduleTests(unittest.TestCase):
    def test_two_daily_passes_and_manual_source_limits_are_documented(self):
        workflow = Path(".github/workflows/weekly-event-discovery.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn('- cron: "15 2 * * *"', workflow)
        self.assertIn('- cron: "15 12 * * *"', workflow)
        self.assertIn("Daytime latest-event discovery (10:15 China Standard Time)", workflow)
        self.assertIn("Evening cross-source review (20:15 China Standard Time)", workflow)
        self.assertIn("Roll Call and other manual-review sources are not fetched.", workflow)
        self.assertIn("label=\"Manual discovery run\"", workflow)


if __name__ == "__main__":
    unittest.main()
