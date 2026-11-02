import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "events" / "columbus-day-2026" / "index.html"


class ColumbusEventPageTests(unittest.TestCase):
    def test_page_has_event_sources_and_explicit_evidence_limits(self):
        html = PAGE.read_text(encoding="utf-8")
        for expected in (
            "https://www.youtube.com/watch?v=noI4BbQ2wZQ",
            "https://www.youtube.com/watch?v=Ubivu0AQHXo",
            "https://www.youtube.com/watch?v=eteny1ES3wk",
            "https://www.youtube.com/watch?v=n1MfxwIvAs0",
            "https://www.youtube.com/watch?v=Os4aPmvxZjA",
            "https://www.youtube.com/watch?v=-6mZSshfpAc",
            "https://www.youtube.com/watch?v=OysrZCjorfE",
            "事件日期</dt><dd>未核实",
            "Event ID</dt><dd>未核实",
            "机位地图</dt><dd>不可用",
            "播放器字幕",
            "复用权",
            "不可数字擦除",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, html)

    def test_page_does_not_embed_or_host_video(self):
        html = PAGE.read_text(encoding="utf-8").lower()
        self.assertNotIn("<video", html)
        self.assertNotIn("<iframe", html)
        self.assertNotIn("youtube.com/embed/", html)

    def test_homepage_links_to_evidence_page(self):
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="events/columbus-day-2026/"', homepage)


if __name__ == "__main__":
    unittest.main()
