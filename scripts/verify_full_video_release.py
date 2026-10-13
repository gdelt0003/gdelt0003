import argparse
import json
from pathlib import Path
from typing import Any


def release_blockers(manifest: dict[str, Any]) -> list[str]:
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
    return blockers


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise SystemExit("Release blocked: manifest root must be a JSON object.")
    blockers = release_blockers(manifest)
    if blockers:
        for blocker in blockers:
            print(f"Release blocked: {blocker}.")
        raise SystemExit(1)
    print("Full-video release verification passed.")


if __name__ == "__main__":
    main()
