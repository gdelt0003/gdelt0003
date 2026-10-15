import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _evidence_file(
    record: dict[str, Any],
    evidence_root: Path | None,
    blockers: list[str],
    label: str,
) -> None:
    relative_path = record.get("evidence_file")
    expected_hash = record.get("sha256")
    if (
        evidence_root is None
        or not isinstance(relative_path, str)
        or not relative_path.strip()
        or not isinstance(expected_hash, str)
        or len(expected_hash) != 64
    ):
        blockers.append(f"{label} is missing a local evidence file and SHA-256")
        return
    path = (evidence_root / relative_path).resolve()
    try:
        path.relative_to(evidence_root.resolve())
    except ValueError:
        blockers.append(f"{label} evidence path escapes the manifest directory")
        return
    if not path.is_file():
        blockers.append(f"{label} evidence file does not exist")
        return
    actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual_hash != expected_hash.lower():
        blockers.append(f"{label} evidence SHA-256 does not match")


def _validate_translation_evidence(
    manifest: dict[str, Any],
    evidence_root: Path | None,
    blockers: list[str],
) -> None:
    review = manifest.get("translation_review")
    if not isinstance(review, dict):
        blockers.append("translation_review evidence records are missing")
        return

    model_records = review.get("models")
    valid_models = [
        row for row in model_records if isinstance(row, dict)
    ] if isinstance(model_records, list) else []
    model_ids = {
        row.get("model_id")
        for row in valid_models
        if isinstance(row.get("model_id"), str) and row["model_id"].strip()
    }
    if len(model_ids) < 10:
        blockers.append("fewer than 10 distinct model output records are present")
    for row in valid_models:
        if (
            not isinstance(row.get("translated_cues"), int)
            or row["translated_cues"] < 1
        ):
            blockers.append("a model output record has no translated cue count")
        _evidence_file(row, evidence_root, blockers, "model output")

    judge_records = review.get("judges")
    valid_judges = [
        row for row in judge_records if isinstance(row, dict)
    ] if isinstance(judge_records, list) else []
    judge_ids = {
        row.get("judge_id")
        for row in valid_judges
        if isinstance(row.get("judge_id"), str) and row["judge_id"].strip()
    }
    if len(judge_ids) < 3:
        blockers.append("fewer than 3 distinct judge reports are present")
    for row in valid_judges:
        if not isinstance(row.get("sampled_cues"), int) or row["sampled_cues"] < 1:
            blockers.append("a judge record has no reviewed cue count")
        _evidence_file(row, evidence_root, blockers, "judge report")

    cross_checks = review.get("source_cross_checks")
    valid_checks = [
        row for row in cross_checks if isinstance(row, dict)
    ] if isinstance(cross_checks, list) else []
    domains = set()
    publishers = set()
    for row in valid_checks:
        source_url = row.get("url")
        domain = urlparse(source_url).hostname if isinstance(source_url, str) else None
        if (
            not is_http_url(source_url)
            or not isinstance(row.get("publisher"), str)
            or not row["publisher"].strip()
            or not isinstance(row.get("checked_at"), str)
            or not isinstance(row.get("finding"), str)
            or not row["finding"].strip()
            or not domain
        ):
            blockers.append("a source cross-check lacks attributable details")
        else:
            domains.add(domain.lower().removeprefix("www."))
            publishers.add(row["publisher"].strip().lower())
        _evidence_file(row, evidence_root, blockers, "source cross-check")
    if len(domains) < 3 or len(publishers) < 3:
        blockers.append("fewer than 3 independent source domains are documented")

    audio_passes = review.get("source_audio_passes")
    valid_passes = [
        row for row in audio_passes if isinstance(row, dict)
    ] if isinstance(audio_passes, list) else []
    pass_numbers = set()
    duration = manifest.get("duration_seconds")
    for row in valid_passes:
        number = row.get("pass_number")
        if isinstance(number, int) and not isinstance(number, bool):
            pass_numbers.add(number)
        if (
            not isinstance(row.get("reviewer"), str)
            or not row["reviewer"].strip()
            or row.get("start_seconds") != 0
            or not isinstance(row.get("end_seconds"), (int, float))
            or not isinstance(duration, (int, float))
            or row["end_seconds"] < duration
            or not isinstance(row.get("notes"), str)
            or not row["notes"].strip()
        ):
            blockers.append("a source-audio pass does not document full-span review")
        _evidence_file(row, evidence_root, blockers, "source-audio pass")
    if not {1, 2, 3}.issubset(pass_numbers):
        blockers.append("three numbered full-span source-audio passes are missing")


def is_http_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.hostname)


def _validate_visual_evidence(
    manifest: dict[str, Any],
    evidence_root: Path | None,
    blockers: list[str],
) -> None:
    review = manifest.get("visual_review")
    frames = review.get("frames") if isinstance(review, dict) else None
    valid_frames = [
        frame for frame in frames if isinstance(frame, dict)
    ] if isinstance(frames, list) else []
    duration = manifest.get("duration_seconds")
    timestamps = [
        frame.get("timestamp_seconds")
        for frame in valid_frames
        if isinstance(frame.get("timestamp_seconds"), (int, float))
    ]
    if (
        not isinstance(duration, (int, float))
        or len(timestamps) < 3
        or any(item < 0 or item > duration for item in timestamps)
        or min(timestamps) > 60
        or max(timestamps) < duration - 60
        or not any(duration * 0.15 <= item <= duration * 0.85 for item in timestamps)
    ):
        blockers.append("opening, middle, and ending visual evidence is incomplete")
    for frame in valid_frames:
        if (
            not isinstance(frame.get("notes"), str)
            or not frame["notes"].strip()
        ):
            blockers.append("a visual frame record has no inspection notes")
        _evidence_file(frame, evidence_root, blockers, "visual frame")


def release_blockers(
    manifest: dict[str, Any],
    evidence_root: Path | None = None,
) -> list[str]:
    checks = manifest.get("quality_checks")
    if not isinstance(checks, dict):
        return ["quality_checks is missing"]

    blockers = []
    sync = checks.get("bilingual_cue_sync")
    readability = checks.get("subtitle_readability")
    accuracy = checks.get("translation_accuracy")
    if not isinstance(sync, dict):
        sync = {}
    if not isinstance(readability, dict):
        readability = {}
    if not isinstance(accuracy, dict):
        accuracy = {}

    if checks.get("structural_checks") != "passed":
        blockers.append("structural checks have not passed")
    if sync.get("status") != "passed":
        blockers.append("bilingual cue synchronization has not passed")
    if sync.get("audio_level_alignment") != "passed":
        blockers.append("audio-level alignment has not passed")
    if checks.get("cue_timing") != "passed":
        blockers.append("cue timing has not passed")
    if checks.get("source_resolution") != "passed":
        blockers.append("source resolution has not passed")
    if readability.get("status") != "style_contract_passed":
        blockers.append("subtitle readability checks have not passed")
    if readability.get("layout_profile") == "katie-fixed-lower-third-zh-first":
        ratio = readability.get("english_to_chinese_size_ratio")
        if not isinstance(ratio, (int, float)) or ratio < 1.2:
            blockers.append(
                "English subtitle font is less than 1.20x Chinese font "
                "for the Katie layout"
            )
    else:
        ratio = readability.get("english_to_chinese_size_ratio")
        if not isinstance(ratio, (int, float)) or ratio < 1.2:
            blockers.append("English subtitle font is less than 1.20x Chinese font")
    if readability.get("visual_frame_review") != "passed":
        blockers.append("visual frame review has not passed")
    if readability.get("english_reading_speed_over_20_cps_cues"):
        blockers.append("English reading-speed flags remain")
    if readability.get("chinese_reading_speed_over_10_cps_cues"):
        blockers.append("Chinese reading-speed flags remain")

    if accuracy.get("status") != "verified":
        blockers.append("translation accuracy has not been verified")
    for field, minimum, label in (
        ("translation_models_compared", 10, "translation models"),
        ("llm_judges", 3, "independent LLM judges"),
        ("source_cross_check_passes", 3, "source cross-checks"),
    ):
        count = accuracy.get(field)
        if not isinstance(count, int) or isinstance(count, bool) or count < minimum:
            blockers.append(f"fewer than {minimum} {label} completed")
    if accuracy.get("audio_level_alignment") != "passed":
        blockers.append("translation review has not passed audio-level alignment")
    if accuracy.get("source_audio_review") != "passed":
        blockers.append("source-audio review has not passed")
    if accuracy.get("independent_translation_review") != "passed":
        blockers.append("independent translation review has not passed")
    _validate_translation_evidence(manifest, evidence_root, blockers)
    _validate_visual_evidence(manifest, evidence_root, blockers)
    return blockers


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise SystemExit("Release blocked: manifest root must be a JSON object.")
    blockers = release_blockers(manifest, manifest_path.parent)
    if blockers:
        for blocker in blockers:
            print(f"Release blocked: {blocker}.")
        raise SystemExit(1)
    print("Full-video release verification passed.")


if __name__ == "__main__":
    main()
