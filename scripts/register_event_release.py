"""Register immutable, reviewed event-production assets for the Pages site."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse


def asset_url(release_url: str, tag: str, filename: str) -> str:
    return (
        release_url.rstrip("/")
        + "/download/"
        + quote(tag, safe="")
        + "/"
        + quote(filename, safe="")
    )


def publication_record(
    metadata: dict[str, Any],
    manifest: dict[str, Any],
    review: dict[str, Any],
    *,
    tag: str,
    release_url: str,
    repository: str,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    if metadata.get("event_id") != manifest.get("event_id"):
        raise ValueError("Event ID in the run manifest does not match its identity record.")
    required_reviews = (
        "reuse_rights_confirmed",
        "same_event_match_confirmed",
        "source_frames_clean",
        "captions_reviewed",
        "translation_reviewed",
    )
    if any(review.get(key) is not True for key in required_reviews):
        raise ValueError(
            "Publication requires affirmative reuse-rights, event-match, source-frame, "
            "caption, and translation review."
        )
    evidence_urls = review.get("evidence_urls")
    normalized_evidence_urls = (
        [url.strip() for url in evidence_urls if isinstance(url, str)]
        if isinstance(evidence_urls, list)
        else []
    )
    if (
        len(normalized_evidence_urls) < len(required_reviews)
        or len(set(normalized_evidence_urls)) < len(required_reviews)
        or any(
            not isinstance(url, str)
            or urlparse(url).scheme != "https"
            or not urlparse(url).netloc
            for url in normalized_evidence_urls
        )
    ):
        raise ValueError(
            "Publication requires at least five distinct HTTPS evidence URLs for "
            "the rights, event match, frame, ASR, and translation reviews."
        )
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", tag):
        raise ValueError("Release tag contains unsupported characters.")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Repository must be owner/name.")
    highlights = manifest.get("highlights")
    if not isinstance(highlights, list) or not highlights:
        raise ValueError("Production manifest contains no highlight outputs.")
    clips = []
    for highlight in highlights:
        variants = highlight.get("variants")
        if not isinstance(variants, list) or not variants:
            raise ValueError(f"Highlight {highlight.get('id')} has no rendered variants.")
        subtitle_file = highlight.get("subtitles")
        for variant in variants:
            filename = variant.get("file")
            if not isinstance(filename, str) or Path(filename).name != filename:
                raise ValueError("Clip filenames must be plain asset basenames.")
            clips.append(
                {
                    "highlight_id": highlight.get("id"),
                    "title": highlight.get("title"),
                    "reason": highlight.get("reason"),
                    "source_start": highlight.get("source_start"),
                    "source_end": highlight.get("source_end"),
                    "style": variant.get("style"),
                    "duration_seconds": variant.get("duration_seconds"),
                    "resolution": variant.get("resolution"),
                    "video_url": asset_url(release_url, tag, filename),
                    "subtitle_url": (
                        asset_url(release_url, tag, subtitle_file)
                        if isinstance(subtitle_file, str)
                        and Path(subtitle_file).name == subtitle_file
                        else None
                    ),
                }
            )
    return {
        "event_id": metadata["event_id"],
        "identity": metadata["identity"],
        "source_url": metadata["source_url"],
        "official_video_url": metadata["official_video_url"],
        "identity_evidence_url": metadata["identity_evidence_url"],
        "source_match_evidence_url": metadata["source_match_evidence_url"],
        "same_event_match_confirmed": review["same_event_match_confirmed"],
        "rights_evidence_url": metadata["rights_evidence_url"],
        "review": review,
        "release_tag": tag,
        "release_url": release_url.rstrip("/") + "/tag/" + quote(tag, safe=""),
        "repository": repository,
        "published_at_utc": reviewed_at
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "caption_review_status": "operator_attested_after_artifact_review",
        "translation_status": "machine_translation_operator_reviewed",
        "source_frame_review_status": "operator_attested_clean_after_frame_review",
        "source_match_review_status": "operator_attested_same_event_after_artifact_review",
        "voice": "original source audio; no voice cloning",
        "clips": clips,
    }


def update_registry(path: Path, record: dict[str, Any]) -> None:
    if path.is_file():
        registry = json.loads(path.read_text(encoding="utf-8"))
    else:
        registry = {"schema_version": 1, "publications": []}
    if not isinstance(registry, dict) or not isinstance(
        registry.get("publications"), list
    ):
        raise ValueError("Published event registry must contain a publications list.")
    publications = registry["publications"]
    publications[:] = [
        item for item in publications if item.get("release_tag") != record["release_tag"]
    ]
    publications.append(record)
    registry["publications"] = publications
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--release-url", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--registry", type=Path, required=True)
    args = parser.parse_args()
    try:
        metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        review = json.loads(args.review.read_text(encoding="utf-8"))
        record = publication_record(
            metadata,
            manifest,
            review,
            tag=args.tag,
            release_url=args.release_url,
            repository=args.repository,
        )
        update_registry(args.registry, record)
        print(f"Registered release {args.tag} for {record['event_id']}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
