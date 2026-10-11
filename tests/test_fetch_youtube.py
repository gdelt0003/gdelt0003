import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fetch_youtube.py"
SPEC = importlib.util.spec_from_file_location("fetch_youtube", SCRIPT)
fetch_youtube = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetch_youtube)


class ReadSourcesTests(unittest.TestCase):
    def test_comments_blanks_and_duplicates_are_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.txt"
            path.write_text(
                "# comment\nhttps://www.youtube.com/@WhiteHouse\n\n"
                "https://www.youtube.com/@WhiteHouse\n",
                encoding="utf-8",
            )
            self.assertEqual(fetch_youtube.read_sources(path), ["https://www.youtube.com/@WhiteHouse"])

    def test_non_youtube_and_non_https_urls_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.txt"
            for url in ("http://youtube.com/@WhiteHouse", "https://example.com/channel"):
                path.write_text(url + "\n", encoding="utf-8")
                with self.subTest(url=url), self.assertRaises(ValueError):
                    fetch_youtube.read_sources(path)

    def test_source_count_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.txt"
            path.write_text(
                "".join(f"https://www.youtube.com/@channel{i}\n" for i in range(fetch_youtube.MAX_SOURCES + 1)),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "maximum is 1000"):
                fetch_youtube.read_sources(path)


class FetchCatalogTests(unittest.TestCase):
    def test_success_empty_and_failure_are_recorded_per_source(self):
        sources = ["https://youtube.com/@one", "https://youtube.com/@two", "https://youtube.com/@three"]
        outputs = [
            SimpleNamespace(
                returncode=0,
                stdout=json.dumps({
                    "id": "video-a", "title": "Example", "channel": "Channel",
                    "webpage_url": "https://youtube.com/watch?v=video-a", "upload_date": "20260101",
                }) + "\n",
                stderr="",
            ),
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            SimpleNamespace(returncode=1, stdout="", stderr="private or unavailable"),
        ]
        runner = Mock(side_effect=outputs)
        pause = Mock()

        catalog = fetch_youtube.fetch_catalog(sources, 10, runner=runner, pause=pause)

        self.assertEqual([item["status"] for item in catalog["sources"]], ["success", "empty", "failed"])
        self.assertEqual(catalog["sources"][2]["error"], "private or unavailable")
        self.assertEqual([item["id"] for item in catalog["videos"]], ["video-a"])
        self.assertEqual(runner.call_args_list[0].kwargs["timeout"], 90)
        self.assertEqual(pause.call_count, 2)

    def test_duplicate_video_ids_are_only_listed_once(self):
        entry = json.dumps({"id": "same", "title": "Video", "webpage_url": "https://youtube.com/watch?v=same"})
        runner = Mock(return_value=SimpleNamespace(returncode=0, stdout=entry + "\n", stderr=""))
        catalog = fetch_youtube.fetch_catalog(
            ["https://youtube.com/@one", "https://youtube.com/@two"],
            10,
            runner=runner,
            pause=Mock(),
        )
        self.assertEqual(len(catalog["videos"]), 1)

    def test_total_budget_marks_unvisited_sources_as_failed(self):
        sources = ["https://youtube.com/@one", "https://youtube.com/@two", "https://youtube.com/@three"]
        now = [0]

        def runner(*_args, **_kwargs):
            now[0] = 11
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        catalog = fetch_youtube.fetch_catalog(
            sources,
            10,
            runner=runner,
            pause=Mock(),
            fetch_budget_seconds=10,
            clock=lambda: now[0],
        )

        self.assertEqual([source["status"] for source in catalog["sources"]], ["empty", "failed", "failed"])
        self.assertIn("time budget", catalog["sources"][1]["error"])


if __name__ == "__main__":
    unittest.main()
