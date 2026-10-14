"""Attach runner-verified SmartSub preview URLs to the event Pages manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


SOURCE_SIZE = 262338614
SOURCE_SHA256 = "33bf25655531190a2d73510649b780b21343481b308f993c107d87053e067171"


def publish(manifest_path: Path, comparison_path: Path, release_url: str) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("input_size_bytes") != SOURCE_SIZE
        or manifest.get("input_sha256") != SOURCE_SHA256
        or manifest.get("source_match_status") != "operator_attested_exact_event"
    ):
        raise ValueError("SmartSub manifest does not match the attested pvX source.")

    release_url = release_url.rstrip("/")
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    comparison["event"]["source_match_status"] = "operator_attested_exact_event"
    comparison["event"]["reuse_rights_status"] = (
        "operator_attested_for_processing_and_public_adaptation"
    )
    comparison["event"]["input_sha256"] = SOURCE_SHA256
    comparison["event"]["input_size_bytes"] = SOURCE_SIZE
    comparison["smartsub_preview"] = {
        "status": "public_unverified_preview",
        "video_url": f"{release_url}/pvXbHQrIvTw-smartsub-draft.mp4",
        "subtitles": {
            "english": f"{release_url}/pvXbHQrIvTw-smartsub-draft.en.srt",
            "chinese": f"{release_url}/pvXbHQrIvTw-smartsub-draft.zh-Hans.srt",
            "bilingual": f"{release_url}/pvXbHQrIvTw-smartsub-draft.en-zh.srt",
        },
        "manifest_url": f"{release_url}/pvXbHQrIvTw-smartsub-draft-manifest.json",
        "source_sha256": SOURCE_SHA256,
        "source_size_bytes": SOURCE_SIZE,
        "review_status": {
            "source_audio_and_asr_accuracy": "not_verified",
            "translation_accuracy": "not_verified",
            "clean_frame_and_style_review": "not_verified",
            "release_gate": "blocked",
        },
        "render": manifest.get("render"),
        "measurements": manifest.get("measurements"),
    }
    render = manifest.get("render") or {}
    render_summary = (
        f"{render.get('application', 'SmartSub')} {render.get('version', 'unknown')} "
        f"hard-burn via {render.get('compose', 'compose')} "
        f"({render.get('encoder', 'encoder not recorded')}); "
        f"{render.get('subtitle_authoring', 'subtitle authoring not recorded')}"
    )
    prior_models = manifest.get("prior_subtitle_models") or {}
    open_variant = next(
        variant
        for variant in comparison["variants"]
        if variant["id"] == "open-source-baseline"
    )
    open_variant.update(
        {
            "status": "preview_unverified",
            "models": {
                "asr": prior_models.get("asr") or "not recorded in prior manifest",
                "translation": prior_models.get("translation") or "not recorded in prior manifest",
            },
            "render": render_summary,
            "video_url": comparison["smartsub_preview"]["video_url"],
            "subtitles": comparison["smartsub_preview"]["subtitles"],
            "quality_checks": {
                "source_audio_and_asr_accuracy": "not_verified",
                "translation_accuracy": "not_verified",
                "clean_frame_and_style_review": "not_verified",
                "release_gate": "blocked",
            },
            "metrics": {
                "processed_input_size_bytes": SOURCE_SIZE,
                "duration_seconds": manifest.get("measurements", {}).get(
                    "duration_seconds"
                ),
                "resolution": manifest.get("measurements", {}).get("resolution"),
                "processing_seconds": manifest.get("measurements", {}).get(
                    "processing_seconds"
                ),
                "cost_usd": 0,
                "wer": None,
                "translation_score": None,
                "cue_sync_error_ms": None,
            },
        }
    )
    comparison_path.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--release-url", required=True)
    args = parser.parse_args()
    publish(args.manifest, args.comparison, args.release_url)


if __name__ == "__main__":
    main()
