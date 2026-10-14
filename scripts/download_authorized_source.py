"""Download only a reviewed, direct HTTPS event source on a hosted runner."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_SOURCE_BYTES = 2_000_000_000
EVIDENCE_KEYS = (
    "identity_evidence_url",
    "source_match_evidence_url",
    "rights_evidence_url",
)


def validate_https_url(
    value: object,
    label: str,
    *,
    disallow_youtube: bool = False,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an HTTPS URL.")
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username
        or parsed.password
        or (
            disallow_youtube
            and (
                hostname == "youtube.com"
                or hostname.endswith(".youtube.com")
                or hostname == "youtu.be"
                or hostname.endswith(".youtu.be")
                or hostname == "youtube-nocookie.com"
                or hostname.endswith(".youtube-nocookie.com")
                or hostname == "googlevideo.com"
                or hostname.endswith(".googlevideo.com")
            )
        )
    ):
        raise ValueError(f"{label} must be a direct HTTPS URL, not a YouTube URL.")
    return value


def validate_manifest(manifest: dict[str, object]) -> str:
    event = manifest.get("event")
    if not isinstance(event, dict):
        raise ValueError("Manifest event record is missing.")
    event_id = event.get("event_id")
    if not isinstance(event_id, str) or not event_id.startswith("evt-"):
        raise ValueError("A reviewed event_id is required before processing.")
    if event.get("identity_status") != "verified":
        raise ValueError("Event identity must be marked verified before processing.")
    if event.get("source_match_status") != "verified":
        raise ValueError("Exact source/event match must be reviewed before processing.")
    if event.get("same_event_match_confirmed") is not True:
        raise ValueError("Explicit exact-event confirmation is required.")
    if event.get("source_reuse_rights_confirmed") is not True:
        raise ValueError("Source reuse rights must be confirmed before processing.")
    validate_https_url(event.get("official_anchor_url"), "event.official_anchor_url")
    source_url = validate_https_url(
        event.get("selected_source_url"),
        "event.selected_source_url",
        disallow_youtube=True,
    )
    evidence = [
        validate_https_url(event.get(key), f"event.{key}")
        for key in EVIDENCE_KEYS
    ]
    if len(set(evidence)) != len(EVIDENCE_KEYS):
        raise ValueError("Identity, event-match, and rights evidence URLs must be distinct.")
    return source_url


class HTTPSOnlyRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        validate_https_url(newurl, "redirect target", disallow_youtube=True)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def download_source(source_url: str, output: Path) -> None:
    opener = build_opener(HTTPSOnlyRedirectHandler())
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".part")
    try:
        request = Request(source_url, headers={"User-Agent": "gdelt0003-event-review/1.0"})
        with opener.open(request, timeout=60) as response, temporary.open("wb") as target:
            validate_https_url(
                response.geturl(), "final source URL", disallow_youtube=True
            )
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_SOURCE_BYTES:
                raise ValueError("Source exceeds the configured 2 GB download safety limit.")
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_SOURCE_BYTES:
                    raise ValueError("Source exceeds the configured 2 GB download safety limit.")
                target.write(chunk)
        if total == 0:
            raise ValueError("Downloaded source is empty.")
        temporary.replace(output)
    except (OSError, ValueError):
        temporary.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        source_url = validate_manifest(manifest)
        download_source(source_url, args.output)
        print(f"Downloaded reviewed source to {args.output}")
        return 0
    except (OSError, ValueError, URLError, json.JSONDecodeError) as error:
        print(f"Source download blocked: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
