"""Fetch configured YouTube channels and playlists into a static site catalog."""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
SOURCES_PATH = ROOT / "sources.txt"
OUTPUT_PATH = ROOT / "site" / "data" / "catalog.json"
MAX_SOURCES = 1000
MAX_VIDEOS_PER_SOURCE = 50
REQUEST_PAUSE_SECONDS = 1
DEFAULT_FETCH_BUDGET_SECONDS = 5 * 60 * 60
YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}


def read_sources(path):
    sources = []
    seen = set()
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        source = raw.strip()
        if not source or source.startswith("#"):
            continue
        parsed = urlparse(source)
        if parsed.scheme != "https" or parsed.hostname not in YOUTUBE_HOSTS:
            raise ValueError(f"{path}:{line_number}: expected an https:// YouTube URL")
        if source not in seen:
            sources.append(source)
            seen.add(source)
    if len(sources) > MAX_SOURCES:
        raise ValueError(f"Source list has {len(sources)} entries; maximum is {MAX_SOURCES}")
    return sources


def parse_entries(stdout, source_url):
    videos = []
    for raw in stdout.splitlines():
        if not raw.strip():
            continue
        entry = json.loads(raw)
        video_id = entry.get("id")
        video_url = entry.get("webpage_url") or entry.get("original_url")
        if not video_url and video_id:
            video_url = f"https://www.youtube.com/watch?v={video_id}"
        if not video_url:
            continue
        parsed_url = urlparse(video_url)
        if parsed_url.scheme != "https" or parsed_url.hostname not in YOUTUBE_HOSTS:
            continue
        videos.append({
            "id": video_id or video_url,
            "title": entry.get("title") or "Untitled video",
            "author": entry.get("channel") or entry.get("uploader") or "YouTube",
            "duration": entry.get("duration_string") or "",
            "durationSeconds": entry.get("duration"),
            "url": video_url,
            "thumbnail": entry.get("thumbnail") or "",
            "source": source_url,
            "uploadDate": entry.get("upload_date") or "",
        })
    return videos


def fetch_catalog(
    sources,
    video_limit,
    runner=subprocess.run,
    pause=time.sleep,
    fetch_budget_seconds=DEFAULT_FETCH_BUDGET_SECONDS,
    clock=time.monotonic,
):
    videos = []
    statuses = []
    deadline = clock() + fetch_budget_seconds
    for index, source in enumerate(sources):
        if clock() >= deadline:
            statuses.extend({
                "url": pending,
                "status": "failed",
                "error": "Skipped because the configured total fetch time budget was reached",
                "videoCount": 0,
            } for pending in sources[index:])
            break
        if index:
            pause(REQUEST_PAUSE_SECONDS)
        command = [
            "yt-dlp",
            "--flat-playlist",
            "--dump-json",
            "--no-warnings",
            "--skip-download",
            "--socket-timeout",
            "20",
            "--retries",
            "2",
            "--extractor-retries",
            "2",
            "--playlist-end",
            str(video_limit),
            source,
        ]
        try:
            source_timeout = min(90, max(1, int(deadline - clock())))
            result = runner(command, capture_output=True, text=True, check=False, timeout=source_timeout)
        except (OSError, subprocess.TimeoutExpired) as error:
            statuses.append({
                "url": source,
                "status": "failed",
                "error": str(error)[:500],
                "videoCount": 0,
            })
            continue
        if result.returncode:
            statuses.append({
                "url": source,
                "status": "failed",
                "error": (result.stderr.strip() or "yt-dlp returned a non-zero exit code")[:500],
                "videoCount": 0,
            })
            continue
        try:
            entries = parse_entries(result.stdout, source)
        except (json.JSONDecodeError, TypeError) as error:
            statuses.append({
                "url": source,
                "status": "failed",
                "error": f"Invalid yt-dlp JSON output: {error}"[:500],
                "videoCount": 0,
            })
            continue
        videos.extend(entries)
        statuses.append({
            "url": source,
            "status": "success" if entries else "empty",
            "videoCount": len(entries),
        })

    unique = []
    seen_ids = set()
    for video in videos:
        if video["id"] not in seen_ids:
            unique.append(video)
            seen_ids.add(video["id"])
    unique.sort(key=lambda video: video["uploadDate"], reverse=True)
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "videos": unique,
        "sources": statuses,
    }


def main():
    try:
        sources = read_sources(SOURCES_PATH)
        video_limit = int(os.environ.get("VIDEO_LIMIT_PER_SOURCE", "12"))
        if not 1 <= video_limit <= MAX_VIDEOS_PER_SOURCE:
            raise ValueError(f"VIDEO_LIMIT_PER_SOURCE must be between 1 and {MAX_VIDEOS_PER_SOURCE}")
        catalog = fetch_catalog(sources, video_limit)
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        failures = [source for source in catalog["sources"] if source["status"] == "failed"]
        print(
            f"Fetched {len(catalog['videos'])} unique videos from {len(sources)} sources "
            f"({len(failures)} failed)."
        )
        for source in failures:
            print(f"Failed: {source['url']}: {source['error']}", file=sys.stderr)
    except (OSError, ValueError) as error:
        print(f"Fetch failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
