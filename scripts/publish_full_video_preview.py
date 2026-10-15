"""Record provenance and publish a full-video test preview in the Pages catalog."""

from __future__ import annotations

import argparse
import json
import re
import uuid
from datetime import datetime
from pathlib import Path


EVENT_ID = "katie-zacharia-2026-10-13"
EVENT_DATE = "2026-10-13"
EVENT_TITLE = "Press Secretary Katie Zacharia Briefs Members of the Media, Oct. 13, 2026"
SOURCE_URL = "https://www.youtube.com/watch?v=g7we6gecwnc"
EVENT_EVIDENCE_URL = (
    "https://www.whitehouse.gov/videos/"
    "press-secretary-katie-zacharia-briefs-members-of-the-media-oct-13-2026/"
)
RIGHTS_EVIDENCE_URL = "https://www.whitehouse.gov/copyright/"
SOURCE_ASSET_ID = "642103215"
SOURCE_ASSET_NAME = "katie-zacharia-g7we6gecwnc-source.mp4"
SOURCE_SIZE_BYTES = 313019832
SOURCE_SHA256 = "97cbe4cf18e6fb2ab9e79acc21a7b8ebd9856099530fcc8e11ba1d61285e47f7"
SOURCE_RELEASE_ID = 413291052
ASSET_PREFIX = "katie-zacharia-g7we6gecwnc"
ASR_MODEL = "large-v3-turbo"
TRANSLATION_MODEL = "facebook/m2m100_1.2B"
REVIEW_STATUS = {
    "source_audio_and_asr_accuracy": "not_verified",
    "translation_accuracy": "not_verified",
    "source_frame_and_audio_event_match": "not_verified",
    "readability_and_visual_review": "not_verified",
    "release_gate": "blocked",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def validate_source_release(releases: list[dict], asset: dict) -> dict:
    """Resolve the pinned draft release from the releases list and verify its asset."""
    release = next(
        (
            item
            for item in releases
            if item.get("id") == SOURCE_RELEASE_ID
            and item.get("tag_name") == "g7we6gecwnc-source-intake-20261015"
        ),
        None,
    )
    if release is None:
        raise ValueError("Pinned draft source release was not found in the release list.")
    if release.get("draft") is not True:
        raise ValueError("Source intake release must remain a draft.")
    expected = {
        "id": 642103215,
        "name": SOURCE_ASSET_NAME,
        "size": SOURCE_SIZE_BYTES,
        "digest": f"sha256:{SOURCE_SHA256}",
        "state": "uploaded",
    }
    for key, value in expected.items():
        if asset.get(key) != value:
            raise ValueError(
                f"Source asset {key} mismatch: expected {value!r}, "
                f"got {asset.get(key)!r}"
            )
    if not any(item.get("id") == expected["id"] for item in release.get("assets", [])):
        raise ValueError("Pinned source asset is not attached to the draft release.")
    return release


def validate_source_verification(source: dict) -> None:
    expected = {
        "release_tag": "g7we6gecwnc-source-intake-20261015",
        "release_id": SOURCE_RELEASE_ID,
        "release_is_draft": True,
        "asset_id": SOURCE_ASSET_ID,
        "asset_name": SOURCE_ASSET_NAME,
        "size_bytes": SOURCE_SIZE_BYTES,
        "sha256": SOURCE_SHA256,
        "source_url": SOURCE_URL,
        "event_identity_evidence_url": EVENT_EVIDENCE_URL,
        "source_match_evidence_url": EVENT_EVIDENCE_URL,
        "rights_evidence_url": RIGHTS_EVIDENCE_URL,
        "same_event_source_match_confirmed": True,
        "reuse_rights_confirmed": True,
    }
    for key, value in expected.items():
        if source.get(key) != value:
            raise ValueError(
                f"Source verification {key} mismatch: expected {value!r}, "
                f"got {source.get(key)!r}"
            )
    if not isinstance(source.get("verified_at"), str):
        raise ValueError("Source verification timestamp is missing.")
    started_at = datetime.fromisoformat(
        source["verified_download_started_at"].replace("Z", "+00:00")
    )
    ended_at = datetime.fromisoformat(source["verified_at"].replace("Z", "+00:00"))
    if (
        started_at.tzinfo is None
        or ended_at.tzinfo is None
        or ended_at < started_at
    ):
        raise ValueError("Source verification timestamps are invalid.")
    if int(source.get("width", 0)) < 1920 or int(source.get("height", 0)) < 1080:
        raise ValueError("Source is below 1920x1080; upscaling is not permitted.")
    if abs(float(source.get("duration_seconds", 0)) - 866) > 3:
        raise ValueError("Source duration does not match the official event listing.")


def record_provenance(
    manifest_path: Path,
    audit_path: Path,
    source_verification_path: Path,
    workflow_run_id: str,
) -> None:
    if not re.fullmatch(r"[0-9]+", workflow_run_id):
        raise ValueError("Workflow run ID must contain only digits.")
    manifest = read_json(manifest_path)
    audit = read_json(audit_path)
    source = read_json(source_verification_path)
    validate_source_verification(source)

    if manifest.get("source_video") != SOURCE_ASSET_NAME:
        raise ValueError("Rendered manifest does not identify the pinned source file.")
    if manifest.get("asr_model") != ASR_MODEL:
        raise ValueError("Rendered manifest has an unexpected ASR model.")
    if manifest.get("translation_model") != TRANSLATION_MODEL:
        raise ValueError("Rendered manifest has an unexpected translation model.")
    if manifest.get("reused_existing_subtitles") is not False:
        raise ValueError("This preview must run ASR and translation, not reuse captions.")
    if manifest.get("duration_seconds") is None or abs(
        float(manifest["duration_seconds"]) - float(source["duration_seconds"])
    ) > 3:
        raise ValueError("Rendered manifest duration does not match the pinned source.")
    if manifest.get("resolution") != f"{source['width']}x{source['height']}":
        raise ValueError("Rendered manifest resolution differs from the source.")
    if not isinstance(audit.get("operations"), list) or not audit.get("task_id"):
        raise ValueError("Operation audit is incomplete.")

    source_record = {
        "operation_id": str(uuid.uuid4()),
        "task_id": audit["task_id"],
        "asset_id": SOURCE_ASSET_ID,
        "operation": "source_asset_download_and_integrity_verification",
        "tool": "GitHub Releases REST API and SHA-256",
        "version": "GitHub REST API v2022-11-28",
        "started_at": source["verified_download_started_at"],
        "ended_at": source["verified_at"],
        "duration_seconds": round(
            (
                datetime.fromisoformat(
                    source["verified_at"].replace("Z", "+00:00")
                )
                - datetime.fromisoformat(
                    source["verified_download_started_at"].replace("Z", "+00:00")
                )
            ).total_seconds(),
            3,
        ),
        "status": "succeeded",
        "retry_count": 0,
        "error": None,
        "details": {
            "release_tag": source["release_tag"],
            "release_id": source["release_id"],
            "release_is_draft": source["release_is_draft"],
            "asset_name": SOURCE_ASSET_NAME,
            "input_size_bytes": SOURCE_SIZE_BYTES,
            "input_sha256": SOURCE_SHA256,
            "source_url": SOURCE_URL,
            "event_identity_evidence_url": EVENT_EVIDENCE_URL,
            "source_match_evidence_url": EVENT_EVIDENCE_URL,
            "rights_evidence_url": RIGHTS_EVIDENCE_URL,
            "same_event_source_match_confirmed": True,
            "reuse_rights_confirmed": True,
            "source_resolution": f"{source['width']}x{source['height']}",
            "source_duration_seconds": source["duration_seconds"],
            "verified_before_media_processing": True,
        },
    }
    audit["operations"].insert(0, source_record)
    manifest.update(
        {
            "workflow_run_id": workflow_run_id,
            "event": {
                "event_id": EVENT_ID,
                "event_date": EVENT_DATE,
                "event_time_local": None,
                "time_precision": "date",
                "timezone": None,
                "location": None,
                "event_type": "White House press secretary media briefing",
                "title": EVENT_TITLE,
                "participants": ["Press Secretary Katie Zacharia"],
                "official_video_url": SOURCE_URL,
                "identity_evidence_url": EVENT_EVIDENCE_URL,
            },
            "source_url": SOURCE_URL,
            "source_match_status": "operator_attested_from_official_white_house_listing",
            "source_match_evidence_url": EVENT_EVIDENCE_URL,
            "source_frame_and_audio_match_review": "not_verified",
            "reuse_rights_status": source["reuse_rights_status"],
            "rights_evidence_url": RIGHTS_EVIDENCE_URL,
            "input_size_bytes": SOURCE_SIZE_BYTES,
            "input_sha256": SOURCE_SHA256,
            "source_resolution": f"{source['width']}x{source['height']}",
            "paid_api_used": False,
            "voice_cloning_used": False,
            "render_execution": "GitHub-hosted ubuntu-latest CPU runner",
            "review_status": REVIEW_STATUS,
            "known_limitations": [
                "English ASR has not been checked against the source audio.",
                "Chinese machine translation has not been independently reviewed.",
                "The rendered video has not received a complete frame/style review.",
                "The official listing matches the source URL and title, but the source frames/audio have not been independently checked for event match.",
                "The White House copyright policy notes transferred/third-party exceptions; those exceptions have not been independently checked.",
            ],
            "operation_audit_file": "operation-audit.json",
            "processing_operations": audit["operations"],
        }
    )
    write_json(audit_path, audit)
    write_json(manifest_path, manifest)


def publish_catalog_entry(
    manifest_path: Path,
    main_videos_path: Path,
    release_url: str,
    workflow_run_id: str,
) -> None:
    if not re.fullmatch(r"[0-9]+", workflow_run_id):
        raise ValueError("Workflow run ID must contain only digits.")
    expected_release_url = (
        "https://github.com/gdelt0003/gdelt0003/releases/download/"
        f"katie-zacharia-g7we6gecwnc-bilingual-preview-{workflow_run_id}"
    )
    if release_url.rstrip("/") != expected_release_url:
        raise ValueError("Release URL does not match this workflow's preview tag.")

    manifest = read_json(manifest_path)
    if manifest.get("input_sha256") != SOURCE_SHA256:
        raise ValueError("Rendered manifest does not match the pinned source SHA-256.")
    if manifest.get("workflow_run_id") != workflow_run_id:
        raise ValueError("Rendered manifest workflow run ID mismatch.")
    if manifest.get("review_status") != REVIEW_STATUS:
        raise ValueError("Preview review status must remain explicitly unverified.")
    release_url = expected_release_url
    video_name = f"{ASSET_PREFIX}-bilingual.mp4"
    subtitles = [
        ("English SRT · 未核验", f"{ASSET_PREFIX}.en.srt"),
        ("简体中文 SRT · 未核验", f"{ASSET_PREFIX}.zh-Hans.srt"),
        ("中英双语 SRT · 未核验", f"{ASSET_PREFIX}.en-zh.srt"),
        ("中英双语 WebVTT · 未核验", f"{ASSET_PREFIX}.en-zh.vtt"),
    ]

    catalog = read_json(main_videos_path)
    videos = catalog.get("videos")
    if not isinstance(videos, list):
        raise ValueError("Main video catalog must contain a videos array.")
    video_id = f"{EVENT_ID}-preview-{workflow_run_id}"
    videos[:] = [video for video in videos if video.get("id") != video_id]
    videos.append(
        {
            "id": video_id,
            "title": "Katie Zacharia · 未核验的机器生成中英双语完整视频预览",
            "event_date": EVENT_DATE,
            "publisher": "GDELT · process_full_video.py 机器生成预览",
            "render_engine": (
                "scripts/process_full_video.py · faster-whisper large-v3-turbo + "
                "facebook/m2m100_1.2B + FFmpeg"
            ),
            "resolution": manifest.get("resolution"),
            "duration_seconds": manifest.get("duration_seconds"),
            "video_url": f"{release_url}/{video_name}",
            "preview_release_url": release_url,
            "manifest_url": f"{release_url}/manifest.json",
            "operation_audit_url": f"{release_url}/operation-audit.json",
            "source_url": SOURCE_URL,
            "source_sha256": SOURCE_SHA256,
            "source_asset_id": SOURCE_ASSET_ID,
            "review_status": (
                "机器生成测试预览，未经人工核验；英语 ASR、中文翻译、源音/画面匹配"
                "及完整画面可读性均未验证，发布质量 gate 仍阻塞。"
            ),
            "note": (
                f"来源 SHA-256 {SOURCE_SHA256}。保留来源画面与音轨；未完成人工字幕、"
                "翻译或完整画面复核，不声称来源画面无内嵌图文。使用本地 runner "
                "ASR/翻译模型与 FFmpeg，无付费 API 或声音克隆。"
            ),
            "subtitles": [
                {"label": label, "url": f"{release_url}/{filename}"}
                for label, filename in subtitles
            ],
        }
    )
    write_json(main_videos_path, catalog)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--source-verification", type=Path)
    parser.add_argument("--main-videos", type=Path)
    parser.add_argument("--release-url")
    parser.add_argument("--workflow-run-id", required=True)
    args = parser.parse_args()

    if args.source_verification:
        record_provenance(
            args.manifest,
            args.audit,
            args.source_verification,
            args.workflow_run_id,
        )
    if args.main_videos:
        if not args.release_url:
            parser.error("--release-url is required with --main-videos")
        publish_catalog_entry(
            args.manifest,
            args.main_videos,
            args.release_url,
            args.workflow_run_id,
        )


if __name__ == "__main__":
    main()
