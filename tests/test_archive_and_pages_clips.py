import importlib.util
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    script = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


archive = load_script("persist_archive")
preserve = load_script("preserve_pages_clips")


class ArchiveTests(unittest.TestCase):
    def test_bootstrap_merges_existing_pages_feed_and_archive_by_id(self):
        previous = {
            "generatedAt": "2026-10-01T00:00:00+00:00",
            "videos": [
                {"id": "existing01", "title": "Existing", "source": "https://youtube.com/@old",
                 "firstSeen": "2026-09-01T00:00:00+00:00", "sources": ["https://youtube.com/@old"]}
            ],
            "shorts": [{"videoId": "clip001", "status": "available", "clipPath": "clips/clip001-short.mp4"}],
        }
        current = {
            "generatedAt": "2026-10-02T00:00:00+00:00",
            "videos": [
                {"id": "existing01", "title": "Updated", "source": "https://youtube.com/@new"},
                {"id": "newvideo1", "title": "New", "source": "https://youtube.com/@new"},
            ],
            "sources": [{"url": "https://youtube.com/@new", "status": "success"}],
        }

        result = archive.merge_archive(current, previous)

        videos = {video["id"]: video for video in result["videos"]}
        self.assertEqual(set(videos), {"existing01", "newvideo1"})
        self.assertEqual(videos["existing01"]["firstSeen"], "2026-09-01T00:00:00+00:00")
        self.assertEqual(videos["existing01"]["lastSeen"], "2026-10-02T00:00:00+00:00")
        self.assertEqual(videos["existing01"]["sources"], ["https://youtube.com/@new", "https://youtube.com/@old"])
        self.assertEqual(result["shorts"][0]["videoId"], "clip001")

    def test_archive_metadata_limit_is_enforced(self):
        original_limit = archive.MAX_ARCHIVE_BYTES
        try:
            archive.MAX_ARCHIVE_BYTES = 1
            with self.assertRaisesRegex(ValueError, "safety limit"):
                archive.merge_archive(
                    {"videos": [{"id": "video001", "title": "A title"}], "sources": []},
                    {},
                )
        finally:
            archive.MAX_ARCHIVE_BYTES = original_limit

    def test_rejects_invalid_or_mismatched_clip_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            clips = site / "clips"
            clips.mkdir()
            (clips / "clip001-short.mp4").write_bytes(b"valid-placeholder")
            for clip_path, video_id in (("../escape.mp4", "clip001"), ("clips/clip001-short.mp4", "different1")):
                with self.subTest(clip_path=clip_path, video_id=video_id):
                    catalog = {"shorts": [{
                        "status": "available", "videoId": video_id, "clipPath": clip_path,
                        "clipFile": Path(clip_path).name,
                    }]}
                    with self.assertRaises(ValueError):
                        archive.validate_site_media(catalog, site)

    def test_valid_localized_assets_share_the_same_site_budgets(self):
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            clips = site / "clips"
            clips.mkdir()
            (clips / "clip001-short.mp4").write_bytes(b"valid-placeholder")
            (clips / "clip001-es-ES-short.mp4").write_bytes(b"valid-localized")
            catalog = {"shorts": [{
                "videoId": "clip001",
                "clipPath": "clips/clip001-short.mp4",
                "clipFile": "clip001-short.mp4",
                "status": "available",
                "localizations": [{
                    "videoId": "clip001",
                    "language": "es-ES",
                    "clipPath": "clips/clip001-es-ES-short.mp4",
                    "clipFile": "clip001-es-ES-short.mp4",
                    "status": "available",
                }],
            }]}
            archive.validate_site_media(catalog, site)


class FakeResponse(io.BytesIO):
    def __init__(self, data, url, headers=None):
        super().__init__(data)
        self.url = url
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def geturl(self):
        return self.url


class PagesClipRestoreTests(unittest.TestCase):
    def test_only_public_github_pages_urls_are_allowed(self):
        for url in (
            "http://gdelt0003.github.io/repo",
            "https://localhost/repo",
            "https://github.io.attacker.example/repo",
            "https://gdelt0003.github.io.evil.test/repo",
            "https://user@gdelt0003.github.io/repo",
            "https://gdelt0003.github.io:8443/repo",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                preserve.validate_base_url(url)

    def test_response_rejects_oversize_content_length_and_external_redirect(self):
        opener = Mock(return_value=FakeResponse(b"", "https://gdelt0003.github.io/repo/clip"))
        request = preserve.Request("https://gdelt0003.github.io/repo/clip")
        with self.assertRaisesRegex(ValueError, "exceeds"):
            preserve.read_limited_response(
                request, 3, lambda *_args, **_kwargs: FakeResponse(
                    b"", "https://gdelt0003.github.io/repo/clip", {"Content-Length": "4"}
                ), timeout=1,
            )
        with self.assertRaisesRegex(ValueError, "redirect"):
            preserve.read_limited_response(
                request, 100, lambda *_args, **_kwargs: opener.return_value.__class__(
                    b"data", "https://127.0.0.1/private"
                ), timeout=1,
            )

    def test_restore_checks_clip_id_and_preserves_bounded_mp4(self):
        base_url = "https://gdelt0003.github.io/repo"
        mp4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00"
        opener = Mock(return_value=FakeResponse(
            mp4,
            f"{base_url}/clips/clip001-short.mp4",
            {"Content-Length": str(len(mp4))},
        ))
        catalog = {"shorts": [
            {
                "videoId": "clip001",
                "clipPath": "clips/clip001-short.mp4",
                "clipFile": "clip001-short.mp4",
                "status": "available",
                "createdAt": "2026-10-01T00:00:00+00:00",
            },
            {
                "videoId": "clip002",
                "clipPath": "../clip002-short.mp4",
                "clipFile": "clip002-short.mp4",
                "status": "available",
            },
        ]}
        with tempfile.TemporaryDirectory() as directory:
            restored = preserve.preserve_clips(catalog, base_url, directory, opener=opener)
            clip = Path(directory) / "clips" / "clip001-short.mp4"
            self.assertEqual(clip.read_bytes(), mp4)
            self.assertEqual([item["videoId"] for item in restored], ["clip001"])
            self.assertEqual(restored[0]["clipBytes"], len(mp4))
        self.assertEqual(opener.call_count, 1)
        self.assertEqual(opener.call_args.kwargs["timeout"], 45)

    def test_restore_carries_localized_files_within_shared_budget(self):
        base_url = "https://gdelt0003.github.io/repo"
        base_mp4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00"
        locale_mp4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00"
        opener = Mock(side_effect=[
            FakeResponse(base_mp4, f"{base_url}/clips/clip001-short.mp4",
                         {"Content-Length": str(len(base_mp4))}),
            FakeResponse(locale_mp4, f"{base_url}/clips/clip001-es-ES-short.mp4",
                         {"Content-Length": str(len(locale_mp4))}),
        ])
        catalog = {"shorts": [{
            "videoId": "clip001",
            "clipPath": "clips/clip001-short.mp4",
            "clipFile": "clip001-short.mp4",
            "status": "available",
            "localizations": [{
                "language": "es-ES",
                "clipPath": "clips/clip001-es-ES-short.mp4",
                "clipFile": "clip001-es-ES-short.mp4",
                "status": "available",
            }],
        }]}
        with tempfile.TemporaryDirectory() as directory:
            restored = preserve.preserve_clips(catalog, base_url, directory, opener=opener)
            self.assertEqual(
                (Path(directory) / "clips" / "clip001-es-ES-short.mp4").read_bytes(),
                locale_mp4,
            )
        self.assertEqual(len(restored[0]["localizations"]), 1)
        self.assertEqual(opener.call_count, 2)

    def test_restore_refuses_mismatched_video_id_before_network_access(self):
        opener = Mock()
        catalog = {"shorts": [{
            "videoId": "otherid1",
            "clipPath": "clips/clip001-short.mp4",
            "clipFile": "clip001-short.mp4",
            "status": "available",
        }]}
        with tempfile.TemporaryDirectory() as directory:
            restored = preserve.preserve_clips(
                catalog, "https://gdelt0003.github.io/repo", directory, opener=opener,
            )
        self.assertEqual(restored, [])
        opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
