"""Prepare an existing bilingual SRT pair as styled ASS for SmartSub compose."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

if __package__:
    from .process_full_video import Cue, read_srt, verify_cues, write_ass
else:
    from process_full_video import Cue, read_srt, verify_cues, write_ass


def prepare(
    english_path: Path,
    chinese_path: Path,
    output_path: Path,
    report_path: Path,
    *,
    width: int,
    height: int,
    duration: float,
) -> dict[str, object]:
    english = read_srt(english_path)
    chinese = read_srt(chinese_path)
    if not english or len(english) != len(chinese):
        raise ValueError("English and Chinese SRTs must have the same nonzero cue count.")

    cues = []
    for index, (en, zh) in enumerate(zip(english, chinese, strict=True), start=1):
        if abs(en[0] - zh[0]) > 0.001 or abs(en[1] - zh[1]) > 0.001:
            raise ValueError(f"Subtitle cue {index} has mismatched language timings.")
        cues.append(Cue(en[0], en[1], en[2], zh[2]))

    write_ass(output_path, cues, width, height)
    checks = verify_cues(cues, duration=duration, width=width, height=height)
    readability = checks["subtitle_readability"]
    report = {
        "subtitle_cues": len(cues),
        "resolution": f"{width}x{height}",
        "duration_seconds": round(duration, 3),
        "input_srt_timings_match": True,
        "source_audio_alignment": "not_verified",
        "translation_accuracy": "not_verified",
        "style": {
            "authoring_library": "pysubs2",
            "english_to_chinese_font_ratio": readability[
                "english_to_chinese_size_ratio"
            ],
            "english_reading_speed_over_20_cps_cues": readability[
                "english_reading_speed_over_20_cps_cues"
            ],
            "chinese_reading_speed_over_10_cps_cues": readability[
                "chinese_reading_speed_over_10_cps_cues"
            ],
        },
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--english-srt", type=Path, required=True)
    parser.add_argument("--chinese-srt", type=Path, required=True)
    parser.add_argument("--output-ass", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--duration", type=float, required=True)
    args = parser.parse_args()
    report = prepare(
        args.english_srt,
        args.chinese_srt,
        args.output_ass,
        args.report,
        width=args.width,
        height=args.height,
        duration=args.duration,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
