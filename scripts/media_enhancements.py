"""Optional hosted-runner translation, narration, and licensed B-roll helpers."""

import html
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

MAX_LANGUAGES = 4
MAX_TRANSLATION_CUES = 100
MAX_BROLL_BYTES = 40 * 1024 * 1024
LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}-[A-Z]{2,3}$")
VOICE_PATTERN = re.compile(r"^[a-z]{2,3}-[A-Z]{2,3}-[A-Za-z]+Neural$")
DEEPL_TARGETS = {
    "en-US": "EN-US",
    "en-GB": "EN-GB",
    "es-ES": "ES",
    "fr-FR": "FR",
    "de-DE": "DE",
    "it-IT": "IT",
    "ja-JP": "JA",
    "ko-KR": "KO",
    "pt-BR": "PT-BR",
    "zh-CN": "ZH",
}
DEFAULT_VOICES = {
    "en-US": "en-US-JennyNeural",
    "en-GB": "en-GB-SoniaNeural",
    "es-ES": "es-ES-ElviraNeural",
    "fr-FR": "fr-FR-DeniseNeural",
    "de-DE": "de-DE-KatjaNeural",
    "it-IT": "it-IT-ElsaNeural",
    "ja-JP": "ja-JP-NanamiNeural",
    "ko-KR": "ko-KR-SunHiNeural",
    "pt-BR": "pt-BR-FranciscaNeural",
    "zh-CN": "zh-CN-XiaoxiaoNeural",
}


class EnhancementError(Exception):
    """An expected third-party media enhancement failure."""


def parse_languages(value):
    languages = []
    for language in (value or "").split(","):
        language = language.strip()
        if not language:
            continue
        if not LANGUAGE_PATTERN.fullmatch(language) or language not in DEEPL_TARGETS:
            raise ValueError(f"Unsupported target language: {language}")
        if language not in languages:
            languages.append(language)
    if len(languages) > MAX_LANGUAGES:
        raise ValueError(f"Choose no more than {MAX_LANGUAGES} target languages")
    return languages


def parse_voice_overrides(value):
    voices = {}
    for pair in (value or "").split(","):
        if not pair.strip():
            continue
        language, separator, voice = pair.partition("=")
        language = language.strip()
        voice = voice.strip()
        if not separator or language not in DEFAULT_VOICES or not VOICE_PATTERN.fullmatch(voice):
            raise ValueError(f"Invalid voice override: {pair}")
        if not voice.startswith(language + "-"):
            raise ValueError(f"Voice {voice} does not match language {language}")
        voices[language] = voice
    return voices


def _json_request(url, headers, body=None, timeout=30, opener=urlopen):
    request = Request(url, headers=headers, data=body)
    try:
        with opener(request, timeout=timeout) as response:
            final_host = urlparse(response.geturl()).hostname
            original_host = urlparse(url).hostname
            if final_host != original_host:
                raise EnhancementError("Refused provider redirect to a different host")
            raw = response.read(5 * 1024 * 1024 + 1)
        if len(raw) > 5 * 1024 * 1024:
            raise EnhancementError("Provider response exceeded 5 MiB")
        return json.loads(raw)
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise EnhancementError(str(error)) from error


def translate_cues(cues, language, auth_key, opener=urlopen):
    if language not in DEEPL_TARGETS:
        raise ValueError(f"Unsupported target language: {language}")
    translated = []
    target = DEEPL_TARGETS[language]
    endpoint = "https://api-free.deepl.com/v2/translate" if auth_key.endswith(":fx") else "https://api.deepl.com/v2/translate"
    for start in range(0, len(cues), 50):
        batch = cues[start:start + 50]
        payload = json.dumps({
            "text": [cue["text"] for cue in batch],
            "target_lang": target,
        }).encode("utf-8")
        response = _json_request(
            endpoint,
            {"Authorization": f"DeepL-Auth-Key {auth_key}", "Content-Type": "application/json"},
            payload,
            opener=opener,
        )
        if not isinstance(response, dict):
            raise EnhancementError("Translation provider returned an invalid response")
        results = response.get("translations", [])
        if len(results) != len(batch):
            raise EnhancementError("Translation provider returned an incomplete cue batch")
        translated.extend({
            **cue,
            "text": str(result.get("text") or ""),
        } for cue, result in zip(batch, results))
    return translated


def synthesize_speech(text, language, voice, api_key, region, output_path, opener=urlopen):
    if not VOICE_PATTERN.fullmatch(voice) or not voice.startswith(language + "-"):
        raise ValueError(f"Voice does not match target language {language}")
    if not re.fullmatch(r"[a-z0-9-]{2,32}", region):
        raise ValueError("Invalid Azure Speech region")
    if not text.strip() or len(text) > 10_000:
        raise EnhancementError("Narration text is empty or exceeds the 10,000-character limit")
    ssml = (
        f"<speak version='1.0' xml:lang='{language}'>"
        f"<voice name='{voice}'>{html.escape(text)}</voice></speak>"
    ).encode("utf-8")
    request = Request(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        data=ssml,
        headers={
            "Ocp-Apim-Subscription-Key": api_key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm",
            "User-Agent": "OpenVideoCatalog",
        },
    )
    try:
        with opener(request, timeout=60) as response:
            audio = response.read(15 * 1024 * 1024 + 1)
        if len(audio) > 15 * 1024 * 1024 or len(audio) < 12 or audio[:4] != b"RIFF":
            raise EnhancementError("Speech provider returned an invalid or oversized WAV")
        Path(output_path).write_bytes(audio)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise EnhancementError(str(error)) from error


def download_pexels_broll(query, api_key, output_path, opener=urlopen):
    url = "https://api.pexels.com/videos/search?" + urlencode({
        "query": query[:120],
        "per_page": 1,
        "orientation": "portrait",
    })
    response = _json_request(url, {"Authorization": api_key}, opener=opener)
    videos = response.get("videos", [])
    if not videos:
        raise EnhancementError("Pexels returned no B-roll for this query")
    video = videos[0]
    files = sorted(
        video.get("video_files", []),
        key=lambda item: (item.get("width", 0) > 1080, item.get("width", 0)),
    )
    selected = next(
        (item for item in files if (urlparse(item.get("link", "")).hostname or "") == "videos.pexels.com"),
        None,
    )
    if not selected:
        raise EnhancementError("Pexels response had no approved video CDN URL")
    request = Request(selected["link"], headers={"User-Agent": "OpenVideoCatalog/1.0"})
    try:
        with opener(request, timeout=45) as media:
            final_host = urlparse(media.geturl()).hostname
            if final_host != "videos.pexels.com":
                raise EnhancementError("Refused B-roll redirect outside videos.pexels.com")
            content_length = media.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_BROLL_BYTES:
                raise EnhancementError("Pexels B-roll exceeds the 40 MiB limit")
            data = media.read(MAX_BROLL_BYTES + 1)
            if content_length and len(data) != int(content_length):
                raise EnhancementError("Pexels B-roll size does not match Content-Length")
        if not data or len(data) > MAX_BROLL_BYTES or len(data) < 12 or data[4:8] != b"ftyp":
            raise EnhancementError("Pexels returned an invalid or oversized MP4")
        Path(output_path).write_bytes(data)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        if isinstance(error, EnhancementError):
            raise
        raise EnhancementError(str(error)) from error
    return {
        "provider": "Pexels",
        "videoId": str(video.get("id") or ""),
        "photographer": str(video.get("user", {}).get("name") or "Unknown"),
        "attributionUrl": str(video.get("url") or "https://www.pexels.com/license/"),
        "license": "Pexels license; review terms before redistribution",
    }


def create_localizations(
    source_path, cues, segment, video_id, clip_dir, scratch_dir,
    broll_path=None, style_preset="auto-hook", clip_writer=None, subtitle_writer=None,
):
    languages = parse_languages(os.environ.get("SHORT_LANGUAGES", ""))
    if not languages:
        return []
    translation_key = os.environ.get("DEEPL_AUTH_KEY", "").strip()
    speech_key = os.environ.get("AZURE_SPEECH_KEY", "").strip()
    region = os.environ.get("AZURE_SPEECH_REGION", "").strip()
    if not cues:
        reason = "No English captions were available to translate or narrate"
        return [{"language": lang, "status": "skipped", "error": reason} for lang in languages]
    if not translation_key or not speech_key or not region:
        reason = "Set DEEPL_AUTH_KEY, AZURE_SPEECH_KEY, and AZURE_SPEECH_REGION"
        print(f"Localization skipped: {reason}", file=sys.stderr)
        return [{"language": lang, "status": "skipped", "error": reason} for lang in languages]
    if clip_writer is None or subtitle_writer is None:
        raise ValueError("Hosted clip and subtitle writers must be provided")
    clip_start = segment["startSeconds"]
    clip_end = clip_start + segment["durationSeconds"]
    selected_cues = [
        cue for cue in cues if cue["end"] > clip_start and cue["start"] < clip_end
    ]
    if len(selected_cues) > MAX_TRANSLATION_CUES:
        return [{
            "language": lang,
            "status": "failed",
            "error": f"Selected segment exceeds the {MAX_TRANSLATION_CUES}-cue translation limit",
        } for lang in languages]

    overrides = parse_voice_overrides(os.environ.get("TTS_VOICE_OVERRIDES", ""))
    localizations = []
    for language in languages:
        try:
            translated = translate_cues(selected_cues, language, translation_key)
            subtitle_path = Path(scratch_dir) / f"{video_id}-{language}.srt"
            if not subtitle_writer(translated, segment, subtitle_path):
                raise EnhancementError("No translated subtitle cues overlap the chosen segment")
            narration_text = " ".join(cue["text"] for cue in translated if cue["text"]).strip()
            if not narration_text:
                raise EnhancementError("Translation returned empty narration text")
            voice = overrides.get(language, DEFAULT_VOICES[language])
            with tempfile.TemporaryDirectory(prefix=f"voice-{language}-", dir=scratch_dir) as temp_dir:
                narration_path = Path(temp_dir) / "narration.wav"
                synthesize_speech(narration_text, language, voice, speech_key, region, narration_path)
                output_name = f"{video_id}-{language}-short.mp4"
                output_path = clip_dir / output_name
                clip_writer(
                    source_path, output_path, segment, subtitle_path, narration_path,
                    broll_path, style_preset,
                )
            localizations.append({
                "videoId": video_id,
                "language": language,
                "voice": voice,
                "clipFile": output_name,
                "clipPath": f"clips/{output_name}",
                "clipBytes": output_path.stat().st_size,
                "status": "available",
                "captions": "Translated subtitles burned in",
                "narration": "Azure Speech",
            })
        except (OSError, ValueError, EnhancementError) as error:
            print(f"Localization {language} failed: {error}", file=sys.stderr)
            localizations.append({
                "language": language,
                "status": "failed",
                "error": str(error)[:400],
            })
    return localizations
