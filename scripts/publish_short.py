"""Publish selected Pages-hosted short assets through official platform APIs."""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urlparse
from urllib.request import Request, urlopen

MAX_VIDEO_BYTES = 20 * 1024 * 1024
MAX_CATALOG_BYTES = 90 * 1024 * 1024
PLATFORMS = {"youtube", "tiktok", "instagram", "facebook", "x"}
LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}-[A-Z]{2,3}$")

REQUIRED_SECRETS = {
    "youtube": ("YT_OAUTH_CLIENT_ID", "YT_OAUTH_CLIENT_SECRET", "YT_OAUTH_REFRESH_TOKEN"),
    "tiktok": ("TIKTOK_ACCESS_TOKEN",),
    "instagram": ("INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_USER_ID"),
    "facebook": ("FACEBOOK_PAGE_ACCESS_TOKEN", "FACEBOOK_PAGE_ID"),
    "x": ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"),
}


class PublishError(Exception):
    """An expected platform API or media transfer failure."""


def parse_platforms(value):
    result = []
    for item in (value or "").split(","):
        platform = item.strip().lower()
        if not platform:
            continue
        if platform not in PLATFORMS:
            raise ValueError(f"Unsupported publishing platform: {platform}")
        if platform not in result:
            result.append(platform)
    return result


def missing_credentials(platform, environ):
    return [name for name in REQUIRED_SECRETS[platform] if not environ.get(name, "").strip()]


def _http(
    url, method="GET", headers=None, body=None, timeout=90,
    opener=urlopen, max_response_bytes=MAX_VIDEO_BYTES + 1024 * 1024,
):
    request = Request(url, method=method, headers=headers or {}, data=body)
    try:
        with opener(request, timeout=timeout) as response:
            final_url = response.geturl()
            if urlparse(final_url).hostname != urlparse(url).hostname:
                raise PublishError("Refused HTTP redirect to a different host")
            result = (response.status, response.headers, response.read(max_response_bytes + 1))
        if len(result[2]) > max_response_bytes:
            raise PublishError(f"Response exceeded the {max_response_bytes}-byte limit")
        return result
    except HTTPError as error:
        detail = error.read(2000).decode("utf-8", errors="replace")
        raise PublishError(f"HTTP {error.code}: {detail[:500]}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise PublishError(str(error)) from error


def _json_response(status, raw):
    if status < 200 or status >= 300:
        raise PublishError(f"Provider returned HTTP {status}")
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as error:
        raise PublishError(f"Provider returned invalid JSON: {error}") from error
    if not isinstance(result, dict):
        raise PublishError("Provider returned an unexpected response shape")
    provider_error = result.get("error")
    if provider_error and not (
        isinstance(provider_error, dict) and provider_error.get("code") in {"ok", ""}
    ):
        raise PublishError(json.dumps(provider_error, ensure_ascii=False)[:500])
    return result


def _json_call(url, method, headers, value=None, timeout=90, opener=urlopen):
    body = json.dumps(value).encode("utf-8") if value is not None else None
    request_headers = {"Accept": "application/json", **headers}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    status, _, raw = _http(url, method, request_headers, body, timeout, opener)
    return _json_response(status, raw)


def _form_call(url, method, headers, fields, timeout=90, opener=urlopen):
    request_headers = {"Accept": "application/json", **headers, "Content-Type": "application/x-www-form-urlencoded"}
    status, _, raw = _http(
        url, method, request_headers, urlencode(fields).encode("utf-8"), timeout, opener,
    )
    return _json_response(status, raw)


def load_assets(base_url, video_id, languages, opener=urlopen):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", video_id):
        raise ValueError("Invalid video ID")
    catalog_url = f"{base_url}/data/catalog.json"
    status, headers, raw = _http(
        catalog_url, timeout=30, opener=opener, max_response_bytes=MAX_CATALOG_BYTES,
    )
    content_length = headers.get("Content-Length")
    if content_length and int(content_length) > MAX_CATALOG_BYTES:
        raise PublishError("Pages catalog exceeds the 90 MiB read limit")
    if status < 200 or status >= 300 or len(raw) > MAX_CATALOG_BYTES:
        raise PublishError(f"Could not read the published catalog (HTTP {status})")
    try:
        catalog = json.loads(raw)
    except json.JSONDecodeError as error:
        raise PublishError(f"Published catalog is invalid: {error}") from error
    video = next((item for item in catalog.get("videos", []) if str(item.get("id")) == video_id), None)
    short = next(
        (item for item in catalog.get("shorts", [])
         if item.get("videoId") == video_id and item.get("status") == "available"),
        None,
    )
    if not video or not short:
        raise PublishError("The authorized video's short is not available in the published Pages catalog")
    assets = [{
        **short,
        "language": "en",
        "clipPath": f"clips/{video_id}-short.mp4",
    }]
    if short.get("clipPath") != assets[0]["clipPath"] or short.get("clipFile") != f"{video_id}-short.mp4":
        raise PublishError("Published short path does not match the requested video ID")
    for localized in short.get("localizations", []):
        language = localized.get("language", "")
        if (
            localized.get("status") in {"skipped", "failed"}
            and LANGUAGE_PATTERN.fullmatch(language)
            and (not languages or language in languages)
        ):
            assets.append({**short, **localized, "language": language})
            continue
        if (
            localized.get("status") == "available"
            and LANGUAGE_PATTERN.fullmatch(language)
            and localized.get("clipPath") == f"clips/{video_id}-{language}-short.mp4"
            and localized.get("clipFile") == f"{video_id}-{language}-short.mp4"
            and (not languages or language in languages)
        ):
            assets.append({**short, **localized, "language": language})
    if languages:
        selected = [asset for asset in assets if asset["language"] == "en" or asset["language"] in languages]
        assets = selected
    return video, assets


def download_asset(base_url, asset, opener=urlopen):
    path = asset.get("clipPath", "")
    language = asset.get("language", "")
    if not isinstance(path, str) or not re.fullmatch(r"[a-z]{2,3}-[A-Z]{2,3}|en", str(language)):
        raise PublishError("Refused invalid Pages clip metadata")
    expected = re.fullmatch(
        rf"clips/{re.escape(str(asset.get('videoId') or ''))}"
        rf"{'-' + re.escape(language) if language != 'en' else ''}-short\.mp4",
        path,
    )
    if not expected:
        raise PublishError("Refused invalid Pages clip path")
    url = f"{base_url}/{path}"
    status, headers, data = _http(
        url,
        headers={"User-Agent": "OpenVideoCatalog/1.0"},
        timeout=60,
        opener=opener,
    )
    if status < 200 or status >= 300 or len(data) > MAX_VIDEO_BYTES:
        raise PublishError("Pages clip response was missing or exceeded 20 MiB")
    content_length = headers.get("Content-Length")
    if content_length and int(content_length) != len(data):
        raise PublishError("Pages clip Content-Length does not match the downloaded size")
    if len(data) < 12 or data[4:8] != b"ftyp":
        raise PublishError("Pages did not return a valid MP4 clip")
    return data


def _privacy_value(platform, privacy):
    if platform == "tiktok":
        return "PUBLIC_TO_EVERYONE" if privacy == "public" else "SELF_ONLY"
    return {"public": "public", "unlisted": "unlisted", "private": "private"}[privacy]


def publish_youtube(asset, video, media, environ, opener=urlopen, privacy="unlisted"):
    token = _form_call(
        "https://oauth2.googleapis.com/token",
        "POST",
        {},
        {
            "client_id": environ["YT_OAUTH_CLIENT_ID"],
            "client_secret": environ["YT_OAUTH_CLIENT_SECRET"],
            "refresh_token": environ["YT_OAUTH_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        },
        opener=opener,
    )
    metadata = {
        "snippet": {
            "title": str(asset.get("clipTitle") or video.get("title") or "Short")[:100],
            "description": f"Derived from: {video.get('url', '')}\nLanguage: {asset.get('language', 'en')}",
            "categoryId": "22",
        },
        "status": {"privacyStatus": _privacy_value("youtube", privacy)},
    }
    status, headers, _ = _http(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        "POST",
        {
            "Authorization": f"Bearer {token['access_token']}",
            "Content-Type": "application/json",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(len(media)),
        },
        json.dumps(metadata).encode("utf-8"),
        opener=opener,
    )
    if status < 200 or status >= 300:
        raise PublishError(f"YouTube upload session failed (HTTP {status})")
    upload_url = headers.get("Location")
    if not upload_url or urlparse(upload_url).hostname != "www.googleapis.com":
        raise PublishError("YouTube returned an invalid upload URL")
    status, _, raw = _http(
        upload_url,
        "PUT",
        {"Authorization": f"Bearer {token['access_token']}", "Content-Type": "video/mp4"},
        media,
        timeout=180,
        opener=opener,
    )
    result = _json_response(status, raw)
    return f"https://www.youtube.com/watch?v={result.get('id', '')}"


def publish_tiktok(asset, video, media, environ, opener=urlopen, privacy="unlisted"):
    title = str(asset.get("clipTitle") or video.get("title") or "Short")[:2200]
    chunk_size = len(media)
    initialized = _json_call(
        "https://open.tiktokapis.com/v2/post/publish/video/init/",
        "POST",
        {"Authorization": f"Bearer {environ['TIKTOK_ACCESS_TOKEN']}"},
        {
            "post_info": {
                "title": title,
                "privacy_level": _privacy_value("tiktok", privacy),
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": len(media),
                "chunk_size": chunk_size,
                "total_chunk_count": 1,
            },
        },
        opener=opener,
    )
    data = initialized.get("data", {})
    upload_url = data.get("upload_url", "")
    host = urlparse(upload_url).hostname or ""
    if urlparse(upload_url).scheme != "https" or not (
        host == "tiktok.com"
        or host.endswith(".tiktok.com")
        or host.endswith(".tiktokcdn.com")
        or host.endswith(".tiktokapis.com")
    ):
        raise PublishError("TikTok returned an invalid upload URL")
    status, _, _ = _http(
        upload_url,
        "PUT",
        {
            "Content-Type": "video/mp4",
            "Content-Length": str(len(media)),
            "Content-Range": f"bytes 0-{len(media) - 1}/{len(media)}",
        },
        media,
        timeout=180,
        opener=opener,
    )
    if status < 200 or status >= 300:
        raise PublishError(f"TikTok media upload failed (HTTP {status})")
    publish_id = data.get("publish_id", "")
    return f"TikTok accepted upload {publish_id}; check the creator inbox for final status"


def publish_instagram(asset, video, media_url, environ, opener=urlopen, privacy="unlisted"):
    version = os.environ.get("META_GRAPH_API_VERSION", "v22.0")
    if not re.fullmatch(r"v\d{2}\.0", version):
        raise ValueError("META_GRAPH_API_VERSION must look like v22.0")
    account_id = environ["INSTAGRAM_USER_ID"]
    headers = {"Authorization": f"Bearer {environ['INSTAGRAM_ACCESS_TOKEN']}"}
    caption = f"{asset.get('clipTitle') or video.get('title') or 'Short'}\n{video.get('url', '')}"
    created = _form_call(
        f"https://graph.facebook.com/{version}/{account_id}/media",
        "POST",
        {"Authorization": headers["Authorization"]},
        {"media_type": "REELS", "video_url": media_url, "caption": caption},
        opener=opener,
    )
    container_id = created.get("id")
    if not container_id:
        raise PublishError("Instagram did not return a media container ID")
    for _ in range(30):
        time.sleep(2)
        status, _, raw = _http(
            f"https://graph.facebook.com/{version}/{container_id}?fields=status_code",
            headers=headers,
            timeout=30,
            opener=opener,
        )
        state = _json_response(status, raw).get("status_code")
        if state == "FINISHED":
            break
        if state in {"ERROR", "EXPIRED"}:
            raise PublishError(f"Instagram media processing status: {state}")
    else:
        raise PublishError("Instagram media processing timed out")
    published = _form_call(
        f"https://graph.facebook.com/{version}/{account_id}/media_publish",
        "POST",
        headers,
        {"creation_id": container_id},
        opener=opener,
    )
    if not published.get("id"):
        raise PublishError("Instagram did not confirm the Reel publication")
    return f"Instagram media ID {published['id']}"


def publish_facebook(asset, video, media, environ, opener=urlopen, privacy="unlisted"):
    version = os.environ.get("META_GRAPH_API_VERSION", "v22.0")
    if not re.fullmatch(r"v\d{2}\.0", version):
        raise ValueError("META_GRAPH_API_VERSION must look like v22.0")
    page_id = environ["FACEBOOK_PAGE_ID"]
    token = environ["FACEBOOK_PAGE_ACCESS_TOKEN"]
    headers = {"Authorization": f"Bearer {token}"}
    started = _form_call(
        f"https://graph.facebook.com/{version}/{page_id}/video_reels?upload_phase=start",
        "POST",
        headers,
        {},
        opener=opener,
    )
    video_id = started.get("video_id")
    upload_url = started.get("upload_url", "")
    upload_host = urlparse(upload_url).hostname or ""
    if not video_id or urlparse(upload_url).scheme != "https" or not (
        upload_host == "facebook.com" or upload_host.endswith(".facebook.com")
    ):
        raise PublishError("Facebook returned an invalid Reel upload session")
    status, _, _ = _http(
        upload_url,
        "POST",
        {"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(media))},
        media,
        timeout=180,
        opener=opener,
    )
    if status < 200 or status >= 300:
        raise PublishError(f"Facebook Reel upload failed (HTTP {status})")
    finish = _form_call(
        f"https://graph.facebook.com/{version}/{page_id}/video_reels?upload_phase=finish",
        "POST",
        headers,
        {
            "video_id": video_id,
            "video_state": "PUBLISHED" if privacy != "private" else "DRAFT",
            "description": f"{asset.get('clipTitle') or video.get('title') or 'Short'}\n{video.get('url', '')}",
        },
        opener=opener,
    )
    if finish.get("success") is not True:
        raise PublishError("Facebook did not confirm the Reel publication")
    return f"Facebook Reel {video_id}"


def _oauth1_header(method, url, consumer_key, consumer_secret, access_token, token_secret):
    oauth = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": access_token,
        "oauth_version": "1.0",
    }
    all_params = parse_qsl(urlparse(url).query, keep_blank_values=True) + list(oauth.items())
    normalized = "&".join(
        f"{quote(key, safe='')}={quote(value, safe='')}"
        for key, value in sorted(all_params)
    )
    base = "&".join(quote(part, safe="") for part in (method.upper(), url.split("?", 1)[0], normalized))
    signing_key = f"{quote(consumer_secret, safe='')}&{quote(token_secret, safe='')}".encode()
    oauth["oauth_signature"] = base64.b64encode(
        hmac.new(signing_key, base.encode("utf-8"), hashlib.sha1).digest()
    ).decode()
    return "OAuth " + ", ".join(
        f'{quote(key, safe="")}="{quote(value, safe="")}"' for key, value in sorted(oauth.items())
    )


def publish_x(asset, video, media, environ, opener=urlopen, privacy="unlisted"):
    def signed(method, url, body=None, content_type=None):
        headers = {
            "Authorization": _oauth1_header(
                method, url, environ["X_API_KEY"], environ["X_API_SECRET"],
                environ["X_ACCESS_TOKEN"], environ["X_ACCESS_TOKEN_SECRET"],
            )
        }
        if content_type:
            headers["Content-Type"] = content_type
        return _http(url, method, headers, body, timeout=180, opener=opener)

    init_url = "https://upload.twitter.com/1.1/media/upload.json?" + urlencode({
        "command": "INIT",
        "media_type": "video/mp4",
        "total_bytes": len(media),
        "media_category": "tweet_video",
    })
    status, _, raw = signed("POST", init_url)
    media_id = str(_json_response(status, raw).get("media_id_string") or "")
    if not media_id:
        raise PublishError("X did not return a media upload ID")
    boundary = "----OpenVideo" + secrets.token_hex(12)
    for index, offset in enumerate(range(0, len(media), 4 * 1024 * 1024)):
        chunk = media[offset:offset + 4 * 1024 * 1024]
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"command\"\r\n\r\nAPPEND\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"media_id\"\r\n\r\n{media_id}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"segment_index\"\r\n\r\n{index}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"media\"; filename=\"chunk.mp4\"\r\n"
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + chunk + f"\r\n--{boundary}--\r\n".encode()
        append_url = "https://upload.twitter.com/1.1/media/upload.json?" + urlencode({
            "command": "APPEND", "media_id": media_id, "segment_index": index,
        })
        status, _, _ = signed("POST", append_url, body, f"multipart/form-data; boundary={boundary}")
        if status < 200 or status >= 300:
            raise PublishError(f"X media chunk {index} failed (HTTP {status})")
    finalize_url = "https://upload.twitter.com/1.1/media/upload.json?" + urlencode({
        "command": "FINALIZE", "media_id": media_id,
    })
    status, _, raw = signed("POST", finalize_url)
    _json_response(status, raw)
    payload = {
        "text": f"{asset.get('clipTitle') or video.get('title') or 'Short'}\n{video.get('url', '')}",
        "media": {"media_ids": [media_id]},
    }
    status, _, raw = signed(
        "POST",
        "https://api.x.com/2/tweets",
        json.dumps(payload).encode("utf-8"),
        "application/json",
    )
    tweet = _json_response(status, raw).get("data", {})
    if not tweet.get("id"):
        raise PublishError("X did not confirm the post")
    return f"https://x.com/i/status/{tweet['id']}"


PROVIDERS = {
    "youtube": publish_youtube,
    "tiktok": publish_tiktok,
    "instagram": publish_instagram,
    "facebook": publish_facebook,
    "x": publish_x,
}


def publish_assets(platforms, assets, video, environ=None, opener=urlopen, privacy="unlisted"):
    environ = environ or os.environ
    results = []
    for platform in platforms:
        missing = missing_credentials(platform, environ)
        if missing:
            results.append({
                "platform": platform,
                "language": "-",
                "status": "skipped",
                "message": "Missing Actions Secrets: " + ", ".join(missing),
            })
            continue
        for asset in assets:
            if asset.get("status") != "available":
                results.append({
                    "platform": platform,
                    "language": asset.get("language", "unknown"),
                    "status": "skipped",
                    "message": asset.get("error") or "The localized asset is not available",
                })
                continue
            try:
                media = download_asset(environ["PAGES_BASE_URL"].rstrip("/"), asset, opener)
                if platform == "instagram":
                    media_url = f"{environ['PAGES_BASE_URL'].rstrip('/')}/{asset['clipPath']}"
                    details = PROVIDERS[platform](asset, video, media_url, environ, opener, privacy)
                else:
                    details = PROVIDERS[platform](asset, video, media, environ, opener, privacy)
                results.append({
                    "platform": platform,
                    "language": asset.get("language", "en"),
                    "status": "published",
                    "message": details,
                })
            except (OSError, ValueError, PublishError) as error:
                results.append({
                    "platform": platform,
                    "language": asset.get("language", "en"),
                    "status": "failed",
                    "message": str(error)[:500],
                })
    return results


def write_summary(results):
    lines = ["## Short publishing results", "", "| Platform | Language | Status | Result |", "|---|---|---|---|"]
    for result in results:
        message = result["message"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {result['platform']} | {result['language']} | {result['status']} | {message} |")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write("\n".join(lines) + "\n")
    for result in results:
        print(f"{result['platform']} [{result['language']}]: {result['status']} — {result['message']}")


def main():
    try:
        from create_short import video_id_from_url
        from media_enhancements import parse_languages
        from preserve_pages_clips import validate_base_url

        platforms = parse_platforms(os.environ.get("PUBLISH_PLATFORMS", ""))
        if not platforms:
            print("No publishing platforms selected; skipping.")
            return 0
        languages = parse_languages(os.environ.get("PUBLISH_LANGUAGES", ""))
        video_url = os.environ.get("SHORT_VIDEO_URL", "")
        video_id = video_id_from_url(video_url)
        if not video_id:
            raise ValueError("Invalid source video URL for publishing")
        base_url = os.environ.get("PAGES_BASE_URL", "").strip()
        if not base_url:
            owner, separator, repository = os.environ.get("GITHUB_REPOSITORY", "").partition("/")
            if not separator or not owner or not repository:
                raise ValueError("PAGES_BASE_URL or GITHUB_REPOSITORY is required")
            base_url = f"https://{owner.lower()}.github.io/{repository}"
        base_url = validate_base_url(base_url)
        video, assets = load_assets(base_url, video_id, languages)
        publish_env = dict(os.environ)
        publish_env["PAGES_BASE_URL"] = base_url
        privacy = os.environ.get("PUBLISH_PRIVACY", "unlisted")
        if privacy not in {"public", "unlisted", "private"}:
            raise ValueError("PUBLISH_PRIVACY must be public, unlisted, or private")
        results = publish_assets(
            platforms,
            assets,
            video,
            environ=publish_env,
            privacy=privacy,
        )
        write_summary(results)
        return 1 if any(result["status"] == "failed" for result in results) else 0
    except (OSError, ValueError, PublishError) as error:
        print(f"Publishing setup failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
