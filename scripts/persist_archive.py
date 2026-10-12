"""Merge this run's catalog into the durable metadata/clip manifest archive."""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ARCHIVE_PATH = Path("archive/catalog.json")
SITE_CATALOG_PATH = Path("site/data/catalog.json")
PREVIOUS_CATALOG_PATH = Path("site/data/previous-catalog.json")
PRESERVED_CLIPS_PATH = Path("site/data/preserved-clips.json")
MAX_ARCHIVE_BYTES = 90 * 1024 * 1024
MAX_SITE_MEDIA_BYTES = 950 * 1024 * 1024
MAX_CLIP_BYTES = 20 * 1024 * 1024
MAX_CLIP_COUNT = 100
MAX_CLIPS_BYTES = 700 * 1024 * 1024
CLIP_PATH_PATTERN = re.compile(r"^clips/[A-Za-z0-9_-]{1,64}-short\.mp4$")


def valid_clip_path(short):
    video_id = str(short.get("videoId") or "")
    clip_path = short.get("clipPath", "")
    if not isinstance(clip_path, str):
        return False
    return (
        re.fullmatch(r"[A-Za-z0-9_-]{1,64}", video_id)
        and clip_path == f"clips/{video_id}-short.mp4"
        and CLIP_PATH_PATTERN.fullmatch(clip_path)
        and Path(clip_path).name == short.get("clipFile")
    )


def merge_archive(current, previous, now=None):
    now = now or datetime.now(timezone.utc)
    observed_at = current.get("generatedAt") or now.isoformat()
    videos = {str(video["id"]): dict(video) for video in previous.get("videos", []) if video.get("id")}
    for video in current.get("videos", []):
        video_id = str(video.get("id") or "")
        if not video_id:
            continue
        prior = videos.get(video_id, {})
        sources = sorted((set(prior.get("sources", [])) | {video.get("source")}) - {None, ""})
        videos[video_id] = {
            **prior,
            **video,
            "firstSeen": prior.get("firstSeen") or video.get("firstSeen") or observed_at,
            "lastSeen": observed_at,
            "sources": sources,
        }

    shorts = {}
    for short in previous.get("shorts", []):
        video_id = str(short.get("videoId") or "")
        if video_id and short.get("status") == "available":
            shorts[video_id] = short
    for short in current.get("shorts", []):
        video_id = str(short.get("videoId") or "")
        if not video_id:
            continue
        if short.get("status") == "available":
            shorts[video_id] = short

    ordered_videos = sorted(
        videos.values(),
        key=lambda video: (video.get("uploadDate") or "", video.get("id") or ""),
        reverse=True,
    )
    ordered_shorts = sorted(
        shorts.values(),
        key=lambda short: (short.get("createdAt") or "", short.get("videoId") or ""),
        reverse=True,
    )
    result = {
        "generatedAt": current.get("generatedAt") or now.isoformat(),
        "videos": ordered_videos,
        "sources": current.get("sources", []),
        "shorts": ordered_shorts,
    }
    encoded_size = len((json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
    if encoded_size > MAX_ARCHIVE_BYTES:
        raise ValueError(f"Metadata archive would exceed the {MAX_ARCHIVE_BYTES // (1024 * 1024)} MiB safety limit")
    return result


def validate_site_media(catalog, site_dir):
    clips = catalog.get("shorts", [])
    if len(clips) > MAX_CLIP_COUNT:
        raise ValueError(f"Pages clip count exceeds {MAX_CLIP_COUNT}")
    total_clip_bytes = 0
    clips_dir = Path(site_dir) / "clips"
    for short in clips:
        if short.get("status") != "available":
            continue
        path = short.get("clipPath", "")
        if not valid_clip_path(short):
            raise ValueError(f"Invalid clip path in archive: {path}")
        clip = Path(site_dir) / path
        if not clip.is_file():
            raise ValueError(f"Referenced Pages clip is missing: {path}")
        size = clip.stat().st_size
        if size <= 0 or size > MAX_CLIP_BYTES:
            raise ValueError(f"Clip size is outside the allowed range: {path}")
        total_clip_bytes += size
    if total_clip_bytes > MAX_CLIPS_BYTES:
        raise ValueError("Pages clips exceed the 700 MiB retention budget")
    site_bytes = sum(path.stat().st_size for path in Path(site_dir).rglob("*") if path.is_file())
    if site_bytes > MAX_SITE_MEDIA_BYTES:
        raise ValueError("Pages output exceeds the 950 MiB deployment safety limit")


def filter_available_shorts(catalog, site_dir):
    site_dir = Path(site_dir)
    retained = []
    for short in catalog.get("shorts", []):
        clip_path = short.get("clipPath", "")
        if (
            short.get("status") == "available"
            and valid_clip_path(short)
            and (site_dir / clip_path).is_file()
        ):
            retained.append(short)
    retained.sort(key=lambda short: (short.get("createdAt") or "", short.get("videoId") or ""), reverse=True)
    accepted = []
    total_bytes = 0
    for short in retained:
        clip = site_dir / short["clipPath"]
        size = clip.stat().st_size
        if (
            len(accepted) >= MAX_CLIP_COUNT
            or size > MAX_CLIP_BYTES
            or total_bytes + size > MAX_CLIPS_BYTES
        ):
            clip.unlink()
            continue
        total_bytes += size
        accepted.append({**short, "clipBytes": size})
    catalog["shorts"] = accepted
    return catalog


def main():
    try:
        current = json.loads(SITE_CATALOG_PATH.read_text(encoding="utf-8"))
        previous = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8")) if ARCHIVE_PATH.exists() else {}
        live_previous = (
            json.loads(PREVIOUS_CATALOG_PATH.read_text(encoding="utf-8"))
            if PREVIOUS_CATALOG_PATH.exists()
            else {}
        )
        merged_previous = merge_archive(live_previous, previous) if live_previous else previous
        preserved_path = Path(os.environ.get(
            "PRESERVED_CLIPS_PATH",
            str(Path("site/data/preserved-clips.json")),
        ))
        preserved = (
            json.loads(preserved_path.read_text(encoding="utf-8"))
            if preserved_path.is_file()
            else []
        )
        current["shorts"] = preserved + current.get("shorts", [])
        merged = merge_archive(current, merged_previous)
        merged = filter_available_shorts(merged, "site")
        validate_site_media(merged, "site")
        ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
        archive_text = json.dumps(merged, ensure_ascii=False, indent=2) + "\n"
        if len(archive_text.encode("utf-8")) > MAX_ARCHIVE_BYTES:
            raise ValueError("Pretty-printed metadata archive exceeds the 200 MiB safety limit")
        ARCHIVE_PATH.write_text(archive_text, encoding="utf-8")
        SITE_CATALOG_PATH.write_text(archive_text, encoding="utf-8")
        for temporary_catalog in (PREVIOUS_CATALOG_PATH, PRESERVED_CLIPS_PATH):
            temporary_catalog.unlink(missing_ok=True)
        preserved_path.unlink(missing_ok=True)
        print(
            f"Persisted {len(merged['videos'])} original metadata entries and "
            f"{len(merged['shorts'])} retained clips."
        )
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as error:
        print(f"Archive persistence failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
