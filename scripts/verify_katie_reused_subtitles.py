"""Verify prior Katie subtitles belong to the exact pinned event source."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

if __package__:
    from .process_full_video import read_srt
    from .publish_full_video_preview import (
        EVENT_EVIDENCE_URL,
        EVENT_ID,
        SOURCE_SHA256,
        SOURCE_URL,
    )
else:
    from process_full_video import read_srt
    from publish_full_video_preview import (
        EVENT_EVIDENCE_URL,
        EVENT_ID,
        SOURCE_SHA256,
        SOURCE_URL,
    )


def verify_reusable_subtitles(
    artifact_dir: Path,
    source_verification_path: Path,
) -> dict[str, object]:
    verification = json.loads(
        source_verification_path.read_text(encoding="utf-8")
    )
    if (
        verification.get("sha256") != SOURCE_SHA256
        or verification.get("source_url") != SOURCE_URL
        or verification.get("event_identity_evidence_url") != EVENT_EVIDENCE_URL
        or verification.get("source_match_evidence_url") != EVENT_EVIDENCE_URL
        or verification.get("same_event_source_match_confirmed") is not True
        or verification.get("reuse_rights_confirmed") is not True
    ):
        raise ValueError(
            "Current source verification does not match the pinned Katie event "
            "and confirmed processing rights."
        )

    manifest = json.loads(
        (artifact_dir / "manifest.json").read_text(encoding="utf-8")
    )
    event = manifest.get("event")
    if (
        manifest.get("input_sha256") != SOURCE_SHA256
        or manifest.get("source_url") != SOURCE_URL
        or not isinstance(event, dict)
        or event.get("event_id") != EVENT_ID
        or event.get("official_video_url") != SOURCE_URL
    ):
        raise ValueError(
            "Reusable subtitle artifact is not tied to the pinned Katie "
            "source SHA-256 and event."
        )

    prefix = "katie-zacharia-g7we6gecwnc"
    english_path = artifact_dir / f"{prefix}.en.srt"
    chinese_path = artifact_dir / f"{prefix}.zh-Hans.srt"
    if not english_path.is_file() or not chinese_path.is_file():
        raise FileNotFoundError("Reusable English and Chinese SRT files are required.")
    english = read_srt(english_path)
    chinese = read_srt(chinese_path)
    if not english or len(english) != len(chinese):
        raise ValueError("Reusable English and Chinese SRTs must have matching cues.")
    for index, (en, zh) in enumerate(zip(english, chinese, strict=True), start=1):
        if abs(en[0] - zh[0]) > 0.01 or abs(en[1] - zh[1]) > 0.01:
            raise ValueError(
                f"Reusable bilingual subtitle cue {index} has mismatched timings."
            )
    return {
        "status": "verified_for_reuse",
        "source_sha256": SOURCE_SHA256,
        "event_id": EVENT_ID,
        "cue_count": len(english),
        "source_audio_alignment": "not_verified",
        "translation_accuracy": "not_verified",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--source-verification", type=Path, required=True)
    args = parser.parse_args()
    result = verify_reusable_subtitles(
        args.artifact_dir,
        args.source_verification,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
