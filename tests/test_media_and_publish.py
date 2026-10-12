import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


media = load_script("media_enhancements")
publisher = load_script("publish_short")


class FakeResponse(io.BytesIO):
    def __init__(self, body=b"", url="", status=200, headers=None):
        super().__init__(body)
        self.url = url
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def geturl(self):
        return self.url


class EnhancementTests(unittest.TestCase):
    def test_language_and_voice_inputs_are_bounded_and_validated(self):
        self.assertEqual(media.parse_languages("es-ES, fr-FR,es-ES"), ["es-ES", "fr-FR"])
        self.assertEqual(
            media.parse_voice_overrides("es-ES=es-ES-ElviraNeural"),
            {"es-ES": "es-ES-ElviraNeural"},
        )
        with self.assertRaises(ValueError):
            media.parse_languages("es-ES,fr-FR,de-DE,it-IT,ja-JP")
        with self.assertRaises(ValueError):
            media.parse_voice_overrides("es-ES=fr-FR-DeniseNeural")

    def test_deepl_translation_uses_authenticated_https_api(self):
        response = {"translations": [{"text": "Hola"}]}
        opener = Mock(return_value=FakeResponse(
            json.dumps(response).encode(),
            "https://api-free.deepl.com/v2/translate",
        ))
        result = media.translate_cues(
            [{"start": 0, "end": 2, "text": "Hello"}],
            "es-ES",
            "test-key:fx",
            opener=opener,
        )
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, "https://api-free.deepl.com/v2/translate")
        self.assertEqual(request.get_header("Authorization"), "DeepL-Auth-Key test-key:fx")
        self.assertEqual(result[0]["text"], "Hola")

    def test_azure_speech_writes_only_validated_wav_response(self):
        wav = b"RIFF" + b"\x00" * 12
        opener = Mock(return_value=FakeResponse(
            wav,
            "https://eastus.tts.speech.microsoft.com/cognitiveservices/v1",
        ))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "voice.wav"
            media.synthesize_speech(
                "Hola <script>", "es-ES", "es-ES-ElviraNeural",
                "test-speech-key", "eastus", output, opener=opener,
            )
            self.assertEqual(output.read_bytes(), wav)
        self.assertIn("&lt;script&gt;", opener.call_args.args[0].data.decode())

    def test_pexels_asset_requires_approved_cdn_host_and_valid_mp4(self):
        mp4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00"
        responses = [
            FakeResponse(json.dumps({
                "videos": [{
                    "id": 12,
                    "url": "https://www.pexels.com/video/12/",
                    "user": {"name": "Contributor"},
                    "video_files": [{"width": 720, "link": "https://videos.pexels.com/video-files/12.mp4"}],
                }]
            }).encode(), "https://api.pexels.com/videos/search"),
            FakeResponse(mp4, "https://videos.pexels.com/video-files/12.mp4",
                         headers={"Content-Length": str(len(mp4))}),
        ]
        opener = Mock(side_effect=responses)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broll.mp4"
            attribution = media.download_pexels_broll("launch", "pexels-key", path, opener=opener)
            self.assertEqual(path.read_bytes(), mp4)
        self.assertEqual(attribution["photographer"], "Contributor")
        self.assertEqual(opener.call_args_list[1].kwargs["timeout"], 45)

    def test_localization_without_provider_secrets_is_explicitly_skipped(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"SHORT_LANGUAGES": "es-ES"}, clear=True,
        ):
            results = media.create_localizations(
                Path(directory) / "source.mp4",
                [{"start": 0, "end": 2, "text": "Hello"}],
                {"startSeconds": 0, "durationSeconds": 20},
                "video01",
                Path(directory),
                Path(directory),
            )
        self.assertEqual(results[0]["status"], "skipped")
        self.assertIn("DEEPL_AUTH_KEY", results[0]["error"])

    def test_localization_translates_only_selected_cues_and_keeps_failures_isolated(self):
        source_cues = [
            {"start": 0, "end": 2, "text": "Outside the segment"},
            {"start": 12, "end": 14, "text": "Inside the segment"},
        ]
        translated_cues = []
        def translate(cues, language, _key):
            translated_cues.extend(cues)
            return [{**cue, "text": "Texto traducido"} for cue in cues]

        def synthesize(_text, _language, _voice, _key, _region, output_path):
            Path(output_path).write_bytes(b"RIFF" + b"\x00" * 12)

        def clip_writer(_source, output_path, *_args):
            Path(output_path).write_bytes(b"clip")

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {
                "SHORT_LANGUAGES": "es-ES",
                "DEEPL_AUTH_KEY": "translation-key",
                "AZURE_SPEECH_KEY": "speech-key",
                "AZURE_SPEECH_REGION": "eastus",
            },
            clear=True,
        ), patch.object(media, "translate_cues", side_effect=translate), patch.object(
            media, "synthesize_speech", side_effect=synthesize,
        ):
            results = media.create_localizations(
                Path(directory) / "source.mp4",
                source_cues,
                {"startSeconds": 10, "durationSeconds": 20},
                "video01",
                Path(directory),
                Path(directory),
                clip_writer=clip_writer,
                subtitle_writer=Mock(return_value=True),
            )
            self.assertEqual([cue["text"] for cue in translated_cues], ["Inside the segment"])
            self.assertEqual(results[0]["status"], "available")
            self.assertTrue((Path(directory) / "video01-es-ES-short.mp4").is_file())


class PublishingTests(unittest.TestCase):
    def test_platform_selection_and_missing_credentials_skip_without_requests(self):
        self.assertEqual(publisher.parse_platforms("youtube, tiktok, youtube"), ["youtube", "tiktok"])
        with self.assertRaises(ValueError):
            publisher.parse_platforms("unknown")
        opener = Mock()
        results = publisher.publish_assets(
            ["youtube"],
            [{"language": "en"}],
            {"title": "Video"},
            environ={},
            opener=opener,
        )
        self.assertEqual(results[0]["status"], "skipped")
        self.assertIn("YT_OAUTH_CLIENT_ID", results[0]["message"])
        opener.assert_not_called()

    def test_youtube_upload_refresh_preserves_form_content_type(self):
        responses = [
            FakeResponse(
                b'{"access_token":"temporary"}',
                "https://oauth2.googleapis.com/token",
            ),
            FakeResponse(
                b"",
                "https://www.googleapis.com/upload/youtube/v3/videos",
                headers={"Location": "https://www.googleapis.com/upload/youtube/v3/videos/session"},
            ),
            FakeResponse(
                b'{"id":"published01"}',
                "https://www.googleapis.com/upload/youtube/v3/videos/session",
            ),
        ]
        opener = Mock(side_effect=responses)
        result = publisher.publish_youtube(
            {"clipTitle": "A short", "language": "en"},
            {"title": "Original", "url": "https://youtube.com/watch?v=video01"},
            b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00",
            {
                "YT_OAUTH_CLIENT_ID": "id",
                "YT_OAUTH_CLIENT_SECRET": "secret",
                "YT_OAUTH_REFRESH_TOKEN": "refresh",
            },
            opener=opener,
        )
        token_request = opener.call_args_list[0].args[0]
        self.assertEqual(token_request.get_header("Content-type"), "application/x-www-form-urlencoded")
        self.assertEqual(parse_qs(token_request.data.decode())["grant_type"], ["refresh_token"])
        self.assertEqual(result, "https://www.youtube.com/watch?v=published01")

    def test_tiktok_allows_official_tiktokapis_upload_hosts(self):
        responses = [
            FakeResponse(
                json.dumps({"error": {"code": "ok"}, "data": {
                    "publish_id": "publish01",
                    "upload_url": "https://open-upload.tiktokapis.com/video/upload",
                }}).encode(),
                "https://open.tiktokapis.com/v2/post/publish/video/init/",
            ),
            FakeResponse(b"", "https://open-upload.tiktokapis.com/video/upload"),
        ]
        opener = Mock(side_effect=responses)
        result = publisher.publish_tiktok(
            {"clipTitle": "Short"},
            {"title": "Original"},
            b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00",
            {"TIKTOK_ACCESS_TOKEN": "access"},
            opener=opener,
        )
        upload_request = opener.call_args_list[1].args[0]
        self.assertEqual(upload_request.get_method(), "PUT")
        self.assertIn("bytes 0-15/16", upload_request.get_header("Content-range"))
        self.assertIn("publish01", result)

    def test_invalid_pages_clip_path_is_refused_before_http(self):
        opener = Mock()
        with self.assertRaisesRegex(publisher.PublishError, "path"):
            publisher.download_asset(
                "https://gdelt0003.github.io/gdelt0003",
                {"videoId": "video01", "language": "en", "clipPath": "https://evil.test/video.mp4"},
                opener=opener,
            )
        opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
