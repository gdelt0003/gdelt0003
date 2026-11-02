"""Collect recent White House channel uploads as unassigned event leads."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CHANNEL_URL = "https://www.youtube.com/@WhiteHouse/videos"


def run(command: list[str]) -> str:
    result = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n"
            f"{result.stderr.strip()}"
        )
    return result.stdout


def normalize_entries(payload: dict[str, Any], checked_at: str) -> dict[str, Any]:
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("White House channel returned no video entries.")

    leads = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        video_id = entry.get("id")
        if not isinstance(video_id, str) or not video_id or video_id in seen:
            continue
        seen.add(video_id)
        leads.append(
            {
                "video_id": video_id,
                "title": entry.get("title") or "",
                "publisher": entry.get("channel") or entry.get("uploader") or "The White House",
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "published_timestamp_unix": entry.get("timestamp"),
                "upload_date_metadata": entry.get("upload_date"),
                "duration_seconds": entry.get("duration"),
                "event_id": None,
                "event_date": None,
                "event_time_local": None,
                "assignment_status": "unassigned_event_lead",
                "evidence_status": "metadata_only",
            }
        )
    if not leads:
        raise ValueError("No valid YouTube video IDs were returned.")
    return {
        "schema_version": 1,
        "checked_at_utc": checked_at,
        "channel_url": CHANNEL_URL,
        "identity_rule": (
            "Upload metadata is not event time. Leads stay unassigned until "
            "event date/time, location, people, and content are independently checked."
        ),
        "leads": leads,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yt-dlp", default="yt-dlp")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 100:
        parser.error("--limit must be between 1 and 100.")
    raw = run(
        [
            args.yt_dlp,
            "--dump-single-json",
            "--flat-playlist",
            "--playlist-end",
            str(args.limit),
            "--js-runtimes",
            "node",
            "--no-warnings",
            CHANNEL_URL,
        ]
    )
    payload = json.loads(raw)
    discovery = normalize_entries(
        payload,
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(discovery, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(discovery['leads'])} unassigned leads to {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
