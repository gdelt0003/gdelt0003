"""Extract representative frames from an authorized Katie subtitle render."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from pathlib import Path


TIMESTAMP = re.compile(
    r"(?P<start>\d{2}):(?P<start_minute>\d{2}):"
    r"(?P<start_second>\d{2})[,.](?P<start_ms>\d{3})\s+-->\s+"
    r"(?P<end>\d{2}):(?P<end_minute>\d{2}):"
    r"(?P<end_second>\d{2})[,.](?P<end_ms>\d{3})"
)


def _seconds(hours: str, minutes: str, seconds: str, millis: str) -> float:
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(millis) / 1000
    )


def select_review_times(subtitle_text: str, duration: float) -> list[dict[str, object]]:
    if not math.isfinite(duration) or duration <= 1:
        raise ValueError("Video duration must be finite and greater than one second.")

    cue_scores = []
    for block in re.split(r"\n\s*\n", subtitle_text.strip()):
        lines = block.splitlines()
        timing_line = next(
            (line.strip() for line in lines if "-->" in line),
            None,
        )
        if timing_line is None:
            continue
        match = TIMESTAMP.search(timing_line)
        if match is None:
            raise ValueError(f"Malformed subtitle timing: {timing_line}")
        start = _seconds(
            match["start"],
            match["start_minute"],
            match["start_second"],
            match["start_ms"],
        )
        end = _seconds(
            match["end"],
            match["end_minute"],
            match["end_second"],
            match["end_ms"],
        )
        if start < 0 or end <= start:
            raise ValueError(f"Invalid subtitle cue timing: {timing_line}")
        text_lines = [
            line.strip()
            for line in lines
            if line.strip() and "-->" not in line and not line.strip().isdigit()
        ]
        if not text_lines:
            continue
        density = sum(len(line) for line in text_lines) / (end - start)
        cue_scores.append((density, start, end))

    if not cue_scores:
        raise ValueError("No valid bilingual subtitle cues found for frame sampling.")

    inset = min(2.0, duration / 4)
    samples = [
        {"label": "start", "time_seconds": inset},
        {"label": "middle", "time_seconds": duration / 2},
        {"label": "end", "time_seconds": duration - inset},
    ]
    _density, dense_start, dense_end = max(cue_scores, key=lambda cue: cue[0])
    samples.append({
        "label": "densest_caption",
        "time_seconds": (dense_start + dense_end) / 2,
    })

    unique_samples = []
    samples_by_time = {}
    for sample in samples:
        seconds = round(
            min(max(float(sample["time_seconds"]), 0.1), duration - 0.1),
            3,
        )
        if seconds in samples_by_time:
            existing = samples_by_time[seconds]
            existing.setdefault("also_labels", []).append(sample["label"])
            continue
        unique_sample = {
            "label": sample["label"],
            "time_seconds": seconds,
        }
        samples_by_time[seconds] = unique_sample
        unique_samples.append(unique_sample)
    return unique_samples


def extract_review_frames(
    video: Path,
    subtitle_srt: Path,
    manifest_path: Path,
    output_dir: Path,
) -> list[dict[str, object]]:
    if not video.is_file() or not subtitle_srt.is_file():
        raise FileNotFoundError("Rendered video or bilingual subtitle SRT is missing.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    duration = manifest.get("duration_seconds")
    if not isinstance(duration, (int, float)) or isinstance(duration, bool):
        raise ValueError("Manifest has no numeric duration_seconds.")
    samples = select_review_times(
        subtitle_srt.read_text(encoding="utf-8"),
        float(duration),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    for sample in samples:
        seconds = float(sample["time_seconds"])
        frame_path = output_dir / f"{sample['label']}.jpg"
        timestamp = f"{seconds:.3f}"
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                timestamp,
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(frame_path),
            ],
            check=True,
        )
        if not frame_path.is_file() or frame_path.stat().st_size == 0:
            raise RuntimeError(f"FFmpeg did not produce review frame {frame_path}.")
        sample["file"] = frame_path.name
    report = {
        "status": "sampled_not_reviewed",
        "sampling_method": (
            "rendered video at start, midpoint, end, and midpoint of the "
            "highest combined bilingual character-per-second cue"
        ),
        "frames": samples,
        "manual_visual_review": "not_verified",
    }
    (output_dir / "sampling-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return samples


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--subtitle-srt", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    samples = extract_review_frames(
        args.video,
        args.subtitle_srt,
        args.manifest,
        args.output_dir,
    )
    print(json.dumps(samples, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
