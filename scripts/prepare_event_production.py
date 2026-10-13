"""Validate an operator-supplied event identity before cloud video processing."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from scripts.event_identity import build_event_id


def https_url(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an HTTPS URL.")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{label} must be an HTTPS URL.")
    return value


def prepare_metadata(
    identity: dict[str, Any],
    *,
    source_url: str,
    identity_evidence_url: str,
    source_match_evidence_url: str,
    same_event_match_confirmed: bool,
    rights_evidence_url: str,
    prepared_at: str | None = None,
) -> dict[str, Any]:
    canonical_source_url = https_url(source_url, "source_url")
    official_video_url = https_url(
        identity.get("official_video_url"), "identity.official_video_url"
    )
    verified_sources = identity.get("verified_source_urls", [])
    if (
        not isinstance(verified_sources, list)
        or any(not isinstance(url, str) for url in verified_sources)
    ):
        raise ValueError("identity.verified_source_urls must be a list of source URLs.")
    verified_sources = [
        https_url(url, "identity.verified_source_urls item")
        for url in verified_sources
    ]
    if canonical_source_url != official_video_url and canonical_source_url not in verified_sources:
        raise ValueError(
            "A non-anchor source must be explicitly listed in "
            "identity.verified_source_urls after same-event review."
        )
    if same_event_match_confirmed is not True:
        raise ValueError(
            "The operator must confirm that the selected source shows this exact event."
        )
    identity_evidence_url = https_url(
        identity_evidence_url, "identity_evidence_url"
    )
    source_match_evidence_url = https_url(
        source_match_evidence_url, "source_match_evidence_url"
    )
    rights_evidence_url = https_url(rights_evidence_url, "rights_evidence_url")
    event_fields = {
        key: value for key, value in identity.items() if key != "official_video_url"
    }
    event_id = build_event_id(event_fields)
    return {
        "schema_version": 1,
        "event_id": event_id,
        "identity": event_fields,
        "source_url": canonical_source_url,
        "official_video_url": official_video_url,
        "identity_evidence_url": identity_evidence_url,
        "source_match_evidence_url": source_match_evidence_url,
        "same_event_match_confirmed": True,
        "rights_evidence_url": rights_evidence_url,
        "prepared_at_utc": prepared_at
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "review_status": "identity_source_match_and_reuse_rights_operator_attested",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity-json", type=Path, required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--identity-evidence-url", required=True)
    parser.add_argument("--source-match-evidence-url", required=True)
    parser.add_argument(
        "--confirm-same-event-match",
        action="store_true",
        required=True,
        help="Attest that the selected source is this exact event.",
    )
    parser.add_argument("--rights-evidence-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        identity = json.loads(args.identity_json.read_text(encoding="utf-8"))
        if not isinstance(identity, dict):
            raise ValueError("Event identity JSON must be an object.")
        prepared = prepare_metadata(
            identity,
            source_url=args.source_url,
            identity_evidence_url=args.identity_evidence_url,
            source_match_evidence_url=args.source_match_evidence_url,
            same_event_match_confirmed=args.confirm_same_event_match,
            rights_evidence_url=args.rights_evidence_url,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(prepared, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Validated production identity {prepared['event_id']}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
