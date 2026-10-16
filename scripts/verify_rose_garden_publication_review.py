"""Validate post-render review evidence before public Rose Garden publication."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit


REVIEW_CATEGORIES = (
    "source_event_match",
    "reuse_rights",
    "clean_source_frames",
    "english_asr",
    "chinese_translation",
)
EVENT_ID = "rose-garden-lunch-2026-10-15"
SOURCE_ASSET = "RoseGardenLunch-IySF_8OArvw.mp4"
RENDERED_ASSET = "RoseGardenLunch-IySF_8OArvw-bilingual.mp4"


def _https_url(
    value: Any, category: str
) -> tuple[str, str, int | None, str, tuple[tuple[str, str], ...]]:
    if not isinstance(value, str):
        raise RuntimeError(f"{category} evidence URL must be an HTTPS URL.")
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as error:
        raise RuntimeError(f"{category} evidence URL has an invalid port.") from error
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise RuntimeError(f"{category} evidence URL must be an absolute HTTPS URL.")
    host = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    if port == 443:
        port = None
    path = unquote(parsed.path or "/").rstrip("/") or "/"
    query = tuple(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return host, parsed.scheme.lower(), port, path, query


def validate_publication_review(
    *,
    artifact_dir: Path,
    review_record: dict[str, Any],
    render_run_id: str,
    reviewed_by: str,
) -> dict[str, Any]:
    if not re.fullmatch(r"\d{1,20}", render_run_id):
        raise RuntimeError("render_run_id must be a numeric GitHub Actions run ID.")
    if not reviewed_by.strip():
        raise RuntimeError("The GitHub reviewer identity is required.")
    manifest_path = artifact_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("The downloaded render manifest is missing or invalid.") from error
    if not isinstance(manifest, dict):
        raise RuntimeError("The render manifest must be a JSON object.")
    event_identity = manifest.get("event_identity")
    if not isinstance(event_identity, dict) or event_identity.get("event_id") != EVENT_ID:
        raise RuntimeError("The artifact manifest is not for the pinned Rose Garden event.")
    if manifest.get("source_video") != SOURCE_ASSET:
        raise RuntimeError("The artifact manifest does not identify the pinned source video.")
    rendered = manifest.get("rendered_video")
    if not isinstance(rendered, dict) or rendered.get("file") != RENDERED_ASSET:
        raise RuntimeError("The artifact manifest does not identify the expected review MP4.")
    expected_digest = rendered.get("sha256")
    if not isinstance(expected_digest, str) or not re.fullmatch(
        r"[0-9a-f]{64}", expected_digest
    ):
        raise RuntimeError("The manifest MP4 SHA-256 is invalid.")
    mp4_path = artifact_dir / RENDERED_ASSET
    if not mp4_path.is_file():
        raise RuntimeError("The downloaded review MP4 is missing.")
    digest = hashlib.sha256()
    with mp4_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    actual_digest = digest.hexdigest()
    if actual_digest != expected_digest or mp4_path.stat().st_size != rendered.get(
        "size_bytes"
    ):
        raise RuntimeError("The downloaded MP4 does not match its artifact manifest.")
    audit_path = artifact_dir / "operation-audit.json"
    if not audit_path.is_file() or audit_path.stat().st_size == 0:
        raise RuntimeError("The render operation audit is missing or empty.")
    subtitle_files = manifest.get("subtitle_files")
    if not isinstance(subtitle_files, list) or not subtitle_files:
        raise RuntimeError("The render manifest has no subtitle files.")
    for filename in subtitle_files:
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise RuntimeError("The manifest contains an unsafe subtitle filename.")
        subtitle_path = artifact_dir / filename
        if not subtitle_path.is_file() or subtitle_path.stat().st_size == 0:
            raise RuntimeError(f"The rendered subtitle file is missing or empty: {filename}")
    if review_record.get("render_run_id") != render_run_id:
        raise RuntimeError("The review record does not identify the selected render run.")
    if review_record.get("rendered_mp4_sha256") != actual_digest:
        raise RuntimeError("The review record is not bound to this built MP4 SHA-256.")
    checks = review_record.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(REVIEW_CATEGORIES):
        raise RuntimeError("Review evidence must contain exactly the five required checks.")
    source_graphics = manifest.get("source_graphics_occlusion")
    if not isinstance(source_graphics, dict):
        raise RuntimeError("The artifact manifest has no source-frame/graphics state.")

    seen_urls: set[tuple[str, str, str]] = set()
    evidence: dict[str, dict[str, str]] = {}
    for category in REVIEW_CATEGORIES:
        check = checks[category]
        if (
            not isinstance(check, dict)
            or check.get("reviewed") is not True
            or check.get("status") != "passed"
        ):
            raise RuntimeError(
                f"{category} must be explicitly reviewed and marked passed."
            )
        if category == "clean_source_frames" and (
            source_graphics.get("status_label") == "masked_not_clean"
            or source_graphics.get("caption_band_masks_source_lower_third_in_derivative")
            is True
        ):
            raise RuntimeError(
                "A derivative labeled masked_not_clean cannot pass clean_source_frames."
            )
        url = check.get("evidence_url")
        url_key = _https_url(url, category)
        if url_key in seen_urls:
            raise RuntimeError("The five review checks must use distinct HTTPS evidence URLs.")
        seen_urls.add(url_key)
        evidence[category] = {"status": "passed", "evidence_url": url}

    return {
        "render_run_id": render_run_id,
        "event_id": EVENT_ID,
        "rendered_mp4_sha256": actual_digest,
        "reviewed_by": reviewed_by,
        "verification_method": "operator_attestation_not_independent_proof",
        "reviewed_checks": evidence,
        "release_approval": "approved_for_public_review_only",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--review-json", type=Path, required=True)
    parser.add_argument("--render-run-id", required=True)
    parser.add_argument("--reviewed-by", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        review_record = json.loads(args.review_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("The publication review JSON is missing or invalid.") from error
    if not isinstance(review_record, dict):
        raise RuntimeError("The publication review JSON must be an object.")
    result = validate_publication_review(
        artifact_dir=args.artifact_dir,
        review_record=review_record,
        render_run_id=args.render_run_id,
        reviewed_by=args.reviewed_by,
    )
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
