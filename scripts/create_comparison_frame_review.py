import argparse
import html
import json
import re
import subprocess
from pathlib import Path


SOURCE_SIZE = 262338614
SOURCE_SHA256 = "33bf25655531190a2d73510649b780b21343481b308f993c107d87053e067171"


def parse_cues(vtt_path: Path, duration: float) -> list[dict]:
    cues = []
    for block in re.split(r"\n\s*\n", vtt_path.read_text(encoding="utf-8").strip()):
        lines = block.splitlines()
        timing_position = next(
            (index for index, line in enumerate(lines) if "-->" in line),
            None,
        )
        if timing_position is None:
            continue

        timing = lines[timing_position]
        match = re.match(
            r"(\d{2}):(\d{2}):(\d{2})\.(\d{3}) --> "
            r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})",
            timing,
        )
        if match is None:
            raise ValueError(f"Invalid WebVTT timing line: {timing!r}")
        values = [int(value) for value in match.groups()]
        start = values[0] * 3600 + values[1] * 60 + values[2] + values[3] / 1000
        end = values[4] * 3600 + values[5] * 60 + values[6] + values[7] / 1000
        if not 0 <= start < end <= duration:
            raise ValueError(f"Out-of-range WebVTT cue timing: {timing!r}")

        cue_id = lines[timing_position - 1].strip()
        if not cue_id.isdigit():
            raise ValueError(f"Missing numeric cue ID before {timing!r}")
        cues.append(
            {
                "index": int(cue_id),
                "start": start,
                "end": end,
                "midpoint": (start + end) / 2,
            }
        )
    return cues


def validate_manifest(manifest: dict) -> None:
    expected = {
        "source_video": "pvXbHQrIvTw-source.mp4",
        "input_size_bytes": SOURCE_SIZE,
        "input_sha256": SOURCE_SHA256,
        "source_match_status": "operator_attested_exact_event",
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(
                f"Review artifact {key} mismatch: expected {value!r}, "
                f"got {manifest.get(key)!r}"
            )


def probe_video(video_path: Path, expected_duration: float) -> tuple[dict, float]:
    probe = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,size:stream=codec_type,width,height",
                "-of",
                "json",
                str(video_path),
            ],
            text=True,
        )
    )
    video_stream = next(
        (
            stream
            for stream in probe.get("streams", [])
            if stream["codec_type"] == "video"
        ),
        None,
    )
    if video_stream is None:
        raise ValueError("Rendered artifact has no video stream.")
    if (video_stream.get("width"), video_stream.get("height")) != (1920, 1080):
        raise ValueError(
            "Rendered resolution mismatch: "
            f"{video_stream.get('width')}x{video_stream.get('height')}"
        )
    if not any(
        stream.get("codec_type") == "audio" for stream in probe.get("streams", [])
    ):
        raise ValueError("Rendered artifact has no audio stream.")

    duration = float(probe["format"]["duration"])
    if abs(duration - expected_duration) > 0.5:
        raise ValueError(
            f"Rendered duration mismatch: expected {expected_duration}, got {duration}"
        )
    return video_stream, duration


def select_frames(
    cues: list[dict], manifest: dict, duration: float
) -> tuple[list[dict], dict[str, set[int]]]:
    if len(cues) != manifest["subtitle_cues"]:
        raise ValueError(
            f"WebVTT cue count mismatch: expected {manifest['subtitle_cues']}, "
            f"got {len(cues)}"
        )

    cue_by_index = {cue["index"]: cue for cue in cues}
    if set(cue_by_index) != set(range(1, len(cues) + 1)):
        raise ValueError("WebVTT cue IDs are not a contiguous 1-based sequence.")

    readability = manifest["quality_checks"]["subtitle_readability"]
    flags = {
        "english_over_20_cps": set(
            readability.get("english_reading_speed_over_20_cps_cues", [])
        ),
        "chinese_over_10_cps": set(
            readability.get("chinese_reading_speed_over_10_cps_cues", [])
        ),
    }
    flagged_cues = set().union(*flags.values())
    if any(index not in cue_by_index for index in flagged_cues):
        raise ValueError("Reading-speed review refers to a missing cue.")

    selected = [
        {"label": "opening", "timestamp": min(1.0, duration / 2), "cue": None},
        {"label": "middle", "timestamp": duration / 2, "cue": None},
        {"label": "ending", "timestamp": duration - 1.0, "cue": None},
    ]
    representative_indexes = {
        1,
        (len(cues) + 3) // 4,
        (len(cues) + 1) // 2,
        (3 * len(cues) + 3) // 4,
        len(cues),
    }
    for cue_index in sorted(representative_indexes):
        selected.append(
            {
                "label": "representative-cue",
                "timestamp": cue_by_index[cue_index]["midpoint"],
                "cue": cue_index,
            }
        )
    for cue_index in sorted(flagged_cues):
        if cue_index in representative_indexes:
            continue
        labels = [
            label for label, indexes in flags.items() if cue_index in indexes
        ]
        selected.append(
            {
                "label": "+".join(labels),
                "timestamp": cue_by_index[cue_index]["midpoint"],
                "cue": cue_index,
            }
        )

    return selected, flags


def extract_frames(
    selected: list[dict],
    flags: dict[str, set[int]],
    video_path: Path,
    frame_dir: Path,
    duration: float,
) -> list[dict]:
    frame_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for index, sample in enumerate(selected, start=1):
        timestamp = min(max(0.0, sample["timestamp"]), duration - 0.1)
        cue_index = sample["cue"]
        cue_part = f"-cue-{cue_index:03d}" if cue_index is not None else ""
        frame_path = frame_dir / (
            f"{index:03d}{cue_part}-{timestamp:09.3f}s-{sample['label']}.jpg"
        )
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{timestamp:.3f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(frame_path),
            ],
            check=True,
        )
        if not frame_path.is_file() or frame_path.stat().st_size == 0:
            raise ValueError(f"Frame extraction failed at {timestamp:.3f}s.")

        frames.append(
            {
                "file": frame_path.name,
                "timestamp_seconds": round(timestamp, 3),
                "cue_index": cue_index,
                "flags": (
                    [label for label, indexes in flags.items() if cue_index in indexes]
                    if cue_index is not None
                    else []
                ),
                "review_status": "not_verified",
            }
        )
    return frames


def write_review_html(path: Path, source_run_id: str, frames: list[dict]) -> None:
    rows = "\n".join(
        (
            f"<figure><img src=\"frames/{html.escape(frame['file'])}\" "
            f"loading=\"lazy\"><figcaption>{html.escape(frame['file'])}"
            f"<br>{frame['timestamp_seconds']:.3f}s"
            + (
                f", cue {frame['cue_index']}"
                if frame["cue_index"] is not None
                else ""
            )
            + (
                f"<br>Flags: {html.escape(', '.join(frame['flags']))}"
                if frame["flags"]
                else ""
            )
            + "</figcaption></figure>"
        )
        for frame in frames
    )
    path.write_text(
        "<!doctype html><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>pvXbHQrIvTw private frame review</title>"
        "<style>body{font:16px system-ui;margin:2rem;background:#111;color:#eee}"
        ".blocked{padding:1rem;background:#5a1a1a}main{display:grid;"
        "grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:1rem}"
        "figure{margin:0}img{width:100%;height:auto}figcaption{overflow-wrap:anywhere}"
        "</style><h1>pvXbHQrIvTw rendered frame review</h1>"
        "<p class=\"blocked\"><strong>Release blocked:</strong> source audio, "
        "translation accuracy, and rendered frames still require human review.</p>"
        f"<p>Source run {html.escape(source_run_id)}; {len(frames)} "
        "frames include representative times and every reading-speed-flagged cue.</p>"
        f"<main>{rows}</main>\n",
        encoding="utf-8",
    )


def create_review(
    manifest_path: Path,
    video_path: Path,
    vtt_path: Path,
    output_dir: Path,
    source_run_id: str,
) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    video_stream, duration = probe_video(video_path, float(manifest["duration_seconds"]))
    cues = parse_cues(vtt_path, duration)
    selected, flags = select_frames(cues, manifest, duration)
    frames = extract_frames(
        selected,
        flags,
        video_path,
        output_dir / "frames",
        duration,
    )
    report = {
        "release_status": "blocked",
        "blocking_reason": (
            "Publication requires actual source-audio/ASR review, "
            "independent translation review, and rendered-frame review."
        ),
        "source_run_id": source_run_id,
        "source_video": manifest["source_video"],
        "input_size_bytes": manifest["input_size_bytes"],
        "input_sha256": manifest["input_sha256"],
        "checks": {
            "source_asset_fingerprint": {
                "status": "passed",
                "evidence": "Source size and SHA-256 recorded in processing manifest.",
            },
            "rendered_output_integrity": {
                "status": "passed",
                "duration_seconds": duration,
                "resolution": f"{video_stream['width']}x{video_stream['height']}",
                "audio_stream_present": True,
            },
            "subtitle_structure_and_phrase_timing": {
                "status": manifest["quality_checks"]["structural_checks"],
                "subtitle_cues": len(cues),
                "phrase_level_timing": manifest["quality_checks"][
                    "bilingual_cue_sync"
                ]["status"],
                "audio_level_alignment": "not_verified",
            },
            "source_audio_and_asr_accuracy": {
                "status": "not_verified",
                "blocking": True,
                "reason": "No reviewer has checked the captions against source audio.",
            },
            "translation_accuracy": {
                "status": "not_verified",
                "blocking": True,
                "reason": (
                    "No independent translation comparison or adjudication is recorded."
                ),
                "translation_models_compared": 0,
                "independent_judges": 0,
            },
            "readability_and_visual_style": {
                "status": "not_verified",
                "blocking": True,
                "english_over_20_cps_cues": sorted(flags["english_over_20_cps"]),
                "chinese_over_10_cps_cues": sorted(flags["chinese_over_10_cps"]),
                "frame_review": "not_verified",
            },
        },
        "frame_count": len(frames),
        "frames": frames,
    }
    (output_dir / "release-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_review_html(output_dir / "frame-review.html", source_run_id, frames)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create private rendered-frame review evidence for a comparison artifact."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--vtt", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-run-id", required=True)
    args = parser.parse_args()
    if not args.source_run_id.isdigit():
        parser.error("--source-run-id must be a numeric Actions run ID.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    create_review(
        args.manifest,
        args.video,
        args.vtt,
        args.output_dir,
        args.source_run_id,
    )


if __name__ == "__main__":
    main()
