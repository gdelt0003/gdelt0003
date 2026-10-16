import unittest
from pathlib import Path

from scripts.smartsub_ass_geometry_probe import (
    MASK,
    SOURCE_BANNER,
    ass_fixture,
)


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "smartsub-ass-geometry-probe.yml"
SCRIPT = ROOT / "scripts" / "smartsub_ass_geometry_probe.py"


class SmartSubAssGeometryProbeTests(unittest.TestCase):
    def test_fixture_contains_proposed_geometry_only_as_synthetic_ass(self):
        self.assertEqual(SOURCE_BANNER, (68, 885, 1850, 1020))
        self.assertEqual(MASK, (66, 883, 1852, 1022))
        ass = ass_fixture()
        self.assertIn(r"\pos(66,883)", ass)
        self.assertIn("l 1786 0 1786 139 0 139", ass)
        self.assertIn(r"\pos(120,895)\fs36", ass)
        self.assertIn(r"\pos(120,943)\fs28", ass)
        self.assertIn(r"\t(0,1000,\fs40)", ass)

    def test_probe_is_pinned_and_cannot_publish_or_use_the_event_asset(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("repository: buxuku/SmartSub", workflow)
        self.assertIn("ref: 607376a51a748602712145e2386b13e91bbc2e6d", workflow)
        self.assertIn("contents: read", workflow)
        self.assertNotIn("gh release", workflow.lower())
        self.assertNotIn("rose-garden-lunch-source", workflow.lower())
        self.assertNotIn("RoseGardenLunch-IySF_8OArvw.mp4", script)
        self.assertNotIn("e0b04fb669fd0d09f1492de6a3160bb3b6dae2e3e396be77372f4b5635da5f73", script)
        self.assertIn('"fixture-source.mp4"', script)
        self.assertIn('"fixture-subtitles.ass"', script)
        self.assertIn('"fixture-burned.mp4"', script)


if __name__ == "__main__":
    unittest.main()
