"""Carry forward published clip files within a bounded Pages media budget."""

import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MAX_CLIP_BYTES = 20 * 1024 * 1024
MAX_TOTAL_CLIP_BYTES = 700 * 1024 * 1024
MAX_CLIP_COUNT = 100
MAX_CATALOG_BYTES = 90 * 1024 * 1024
CLIP_PATH_PATTERN = re.compile(
    r"^clips/[A-Za-z0-9_-]{1,64}(?:-[a-z]{2,3}-[A-Z]{2,3})?-short\.mp4$"
)
LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}-[A-Z]{2,3}$")


def validate_base_url(value):
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".github.io")
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Pages restore URL must be a public HTTPS *.github.io URL")
    return value.rstrip("/")


def read_limited_response(request, maximum_bytes, opener, timeout):
    with opener(request, timeout=timeout) as response:
        final_host = urlparse(response.geturl()).hostname
        if not final_host or not final_host.endswith(".github.io"):
            raise ValueError("Refused Pages redirect outside *.github.io")
        content_length = response.headers.get("Content-Length")
        expected_length = int(content_length) if content_length else None
        if expected_length is not None and (expected_length < 0 or expected_length > maximum_bytes):
            raise ValueError(f"Response exceeds {maximum_bytes} bytes")
        data = response.read(maximum_bytes + 1)
    if len(data) > maximum_bytes:
        raise ValueError(f"Response exceeds {maximum_bytes} bytes")
    if expected_length is not None and len(data) != expected_length:
        raise ValueError("Response size does not match Content-Length")
    return data


def read_catalog(base_url, opener=urlopen):
    request = Request(
        f"{base_url}/data/catalog.json",
        headers={"User-Agent": "OpenVideoCatalog/1.0"},
    )
    try:
        raw = read_limited_response(request, MAX_CATALOG_BYTES, opener, timeout=20)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        print(f"No prior Pages catalog available: {error}", file=sys.stderr)
        return {}
    if len(raw) > MAX_CATALOG_BYTES:
        print("Prior Pages catalog exceeded the 20 MiB read limit; skipping preservation.", file=sys.stderr)
        return {}
    try:
        catalog = json.loads(raw)
        if not isinstance(catalog, dict):
            raise ValueError("Catalog root is not an object")
        return catalog
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"Prior Pages catalog is invalid; skipping preservation: {error}", file=sys.stderr)
        return {}


def preserve_clips(catalog, base_url, site_dir, opener=urlopen):
    site_dir = Path(site_dir)
    clips_dir = site_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    output = []
    total_bytes = 0
    file_count = 0
    attempted_downloads = 0
    entries = sorted(
        catalog.get("shorts", []),
        key=lambda short: short.get("createdAt", ""),
        reverse=True,
    )
    seen_video_ids = set()
    for short in entries:
        if short.get("status") != "available":
            continue
        video_id = str(short.get("videoId") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", video_id):
            continue
        if video_id in seen_video_ids:
            continue
        seen_video_ids.add(video_id)

        def restore_asset(asset, language=None):
            nonlocal total_bytes, file_count, attempted_downloads
            if file_count >= MAX_CLIP_COUNT:
                return None
            if not isinstance(asset, dict):
                return None
            suffix = f"-{language}" if language else ""
            clip_path = asset.get("clipPath", "")
            expected_path = f"clips/{video_id}{suffix}-short.mp4"
            if (
                not isinstance(clip_path, str)
                or not CLIP_PATH_PATTERN.fullmatch(clip_path)
                or clip_path != expected_path
                or asset.get("clipFile") != Path(clip_path).name
                or (language and not LANGUAGE_PATTERN.fullmatch(language))
            ):
                return None
            existing = site_dir / clip_path
            if existing.is_file():
                size = existing.stat().st_size
                with existing.open("rb") as clip_file:
                    header = clip_file.read(12)
                if size <= 0 or size > MAX_CLIP_BYTES or len(header) < 12 or header[4:8] != b"ftyp":
                    existing.unlink()
                    return None
            else:
                if attempted_downloads >= MAX_CLIP_COUNT:
                    return None
                url = f"{base_url}/{clip_path}"
                request = Request(url, headers={"User-Agent": "OpenVideoCatalog/1.0"})
                attempted_downloads += 1
                try:
                    data = read_limited_response(request, MAX_CLIP_BYTES, opener, timeout=45)
                except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
                    print(f"Could not preserve {clip_path}: {error}", file=sys.stderr)
                    return None
                if not data or len(data) < 12 or data[4:8] != b"ftyp":
                    print(f"Skipping {clip_path}: response is not a valid MP4 file.", file=sys.stderr)
                    return None
                size = len(data)
                if total_bytes + size > MAX_TOTAL_CLIP_BYTES:
                    return None
                existing.parent.mkdir(parents=True, exist_ok=True)
                existing.write_bytes(data)
            if total_bytes + size > MAX_TOTAL_CLIP_BYTES:
                existing.unlink(missing_ok=True)
                return None
            total_bytes += size
            file_count += 1
            return {**asset, "clipBytes": size}

        main_clip = restore_asset(short)
        if not main_clip:
            continue
        localizations = []
        for localization in short.get("localizations", []):
            if not isinstance(localization, dict) or localization.get("status") != "available":
                if (
                    isinstance(localization, dict)
                    and localization.get("status") in {"skipped", "failed"}
                    and LANGUAGE_PATTERN.fullmatch(str(localization.get("language") or ""))
                ):
                    localizations.append(localization)
                continue
            language = localization.get("language")
            restored = restore_asset(localization, language)
            if restored:
                localizations.append(restored)
        output.append({
            **short,
            **main_clip,
            "localizations": localizations,
        })
    print(f"Preserved {len(output)} clips ({total_bytes} bytes) for the Pages site.")
    return output


def main():
    base_url = os.environ.get("PAGES_BASE_URL", "").strip()
    if not base_url:
        repository = os.environ.get("GITHUB_REPOSITORY", "")
        owner, separator, name = repository.partition("/")
        if not separator or not owner or not name:
            print("PAGES_BASE_URL or a valid GITHUB_REPOSITORY is required.", file=sys.stderr)
            return 1
        base_url = f"https://{owner.lower()}.github.io/{name}"
    try:
        base_url = validate_base_url(base_url)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1

    site_dir = Path(os.environ.get("SITE_DIR", "site"))
    previous_catalog = site_dir / "data" / "previous-catalog.json"
    previous_catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog = read_catalog(base_url)
    archive_path = Path("archive/catalog.json")
    if archive_path.is_file():
        try:
            archived = json.loads(archive_path.read_text(encoding="utf-8"))
            if not isinstance(archived, dict):
                raise ValueError("Archive root is not an object")
            seen = {short.get("videoId") for short in catalog.get("shorts", [])}
            catalog["shorts"] = list(catalog.get("shorts", [])) + [
                short for short in archived.get("shorts", [])
                if short.get("videoId") not in seen
            ]
        except (OSError, json.JSONDecodeError) as error:
            print(f"Could not read archive clip manifest: {error}", file=sys.stderr)
    previous_catalog.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    preserved = preserve_clips(catalog, base_url, site_dir)
    output = site_dir / "data" / "preserved-clips.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(preserved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
