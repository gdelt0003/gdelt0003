import importlib.util
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "create_short.py"
SPEC = importlib.util.spec_from_file_location("create_short", SCRIPT)
create_short = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(create_short)


class VideoUrlTests(unittest.TestCase):
    def test_accepts_public_video_links(self):
        self.assertEqual(
            create_short.validate_video_url("https://www.youtube.com/watch?v=video-id"),
            "https://www.youtube.com/watch?v=video-id",
        )

    def test_rejects_non_youtube_and_playlist_urls(self):
        for url in ("https://example.com/watch?v=x", "https://youtube.com/playlist?list=x"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                create_short.validate_video_url(url)

    def test_unconfirmed_request_is_refused_before_metadata_or_download(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog_path = Path(directory) / "catalog.json"
            catalog_path.write_text(json.dumps({"videos": [], "sources": []}), encoding="utf-8")
            output_path = Path(directory) / "github-output"
            with (
                patch.object(create_short, "CATALOG_PATH", catalog_path),
                patch.dict(os.environ, {
                    "CLIP_AUTHORIZED": "false",
                    "SHORT_VIDEO_URL": "https://youtube.com/watch?v=unapproved01",
                    "ACTIONS_RUN_URL": "https://github.com/example/repo/actions/runs/123",
                    "GITHUB_OUTPUT": str(output_path),
                }),
                patch.object(create_short, "create_short") as create,
            ):
                self.assertEqual(create_short.main(), 1)
            create.assert_not_called()
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            self.assertEqual(catalog["shorts"][0]["status"], "failed")
            self.assertIn("no metadata or subtitle request", catalog["shorts"][0]["error"])
            self.assertEqual(catalog["videos"][0]["id"], "unapproved01")


class SegmentTests(unittest.TestCase):
    def test_chapter_hook_heuristic_prefers_hook_over_intro(self):
        segment = create_short.choose_segment({
            "duration": 500,
            "chapters": [
                {"title": "Introduction", "start_time": 0, "end_time": 100},
                {"title": "What changed today? New plan announced!", "start_time": 100, "end_time": 220},
            ],
        }, 45)
        self.assertEqual(segment["startSeconds"], 100)
        self.assertIn("heuristic", segment["selectionReason"])

    def test_no_chapters_uses_explicit_fallback(self):
        segment = create_short.choose_segment({"duration": 120}, 45)
        self.assertEqual(segment["startSeconds"], 15)
        self.assertIn("No suitable chapter metadata", segment["selectionReason"])

    def test_transcript_window_prefers_more_hook_terms(self):
        cues = [
            {"start": index * 5, "end": index * 5 + 4, "text": "This is ordinary public information for everyone."}
            for index in range(9)
        ]
        cues.extend([
            {"start": 60 + index * 5, "end": 64 + index * 5,
             "text": "What changed today? The new plan was announced, and here is why it matters."}
            for index in range(9)
        ])
        segment = create_short.choose_transcript_segment(cues, 200, 45)
        self.assertIsNotNone(segment)
        self.assertGreaterEqual(segment["startSeconds"], 60)
        self.assertIn("Transcript-window heuristic", segment["selectionReason"])

    def test_webvtt_caption_parsing_and_srt_clipping(self):
        cues = create_short.parse_webvtt(
            "WEBVTT\n\n00:00:10.000 --> 00:00:12.500\n<c>First &amp; second line.</c>\n\n"
            "00:00:12.500 --> 00:00:15.000\nAnother line.\n"
        )
        self.assertEqual(cues[0]["text"], "First & second line.")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.srt"
            written = create_short.write_srt(
                cues,
                {"startSeconds": 11, "durationSeconds": 3},
                path,
            )
            self.assertTrue(written)
            contents = path.read_text(encoding="utf-8")
            self.assertIn("00:00:00,000 --> 00:00:01,500", contents)
            self.assertIn("First & second line.", contents)

    def test_short_metadata_adds_an_original_card_when_not_in_feed(self):
        now = datetime.now(timezone.utc)
        short = {
            "videoId": "outside01",
            "title": "Standalone original",
            "author": "Publisher",
            "originalDuration": "10:00",
            "originalDurationSeconds": 600,
            "thumbnail": "",
            "uploadDate": "20261001",
            "sourceUrl": "https://youtube.com/watch?v=outside01",
            "status": "available",
            "expiresAt": (now + timedelta(days=14)).isoformat(),
        }
        result = create_short.update_catalog({"videos": [], "sources": []}, short, now=now)
        self.assertEqual(result["videos"][0]["id"], "outside01")
        self.assertEqual(result["shorts"][0]["videoId"], "outside01")


if __name__ == "__main__":
    unittest.main()
