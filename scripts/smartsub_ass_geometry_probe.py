"""Exercise SmartSub ASS hard-burn behavior using only generated fixture media."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable


WIDTH = 1920
HEIGHT = 1080
SOURCE_BANNER = (68, 885, 1850, 1020)
MASK = (66, 883, 1852, 1022)
FRAME_BYTES = WIDTH * HEIGHT * 3


def run(command: list[str], *, cwd: Path | None = None, timeout: int = 300) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


def ass_fixture() -> str:
    mask_width = MASK[2] - MASK[0]
    mask_height = MASK[3] - MASK[1]
    return f"""[Script Info]
Title: Synthetic SmartSub geometry fixture
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,Noto Sans CJK SC,36,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
Dialogue: 0,0:00:00.000,0:00:02.000,Default,,0,0,0,,{{\\an7\\pos({MASK[0]},{MASK[1]})\\p1\\bord0\\shad0\\1c&H000000&\\1a&H00&\\3a&HFF&}}m 0 0 l {mask_width} 0 {mask_width} {mask_height} 0 {mask_height}{{\\p0}}
Dialogue: 1,0:00:00.000,0:00:02.000,Default,,0,0,0,,{{\\an7\\pos(120,895)\\fs36\\1c&HFFFFFF&\\bord0\\shad0}}ENGLISH SIZE FIXTURE
Dialogue: 1,0:00:00.000,0:00:02.000,Default,,0,0,0,,{{\\an7\\pos(120,943)\\fs28\\1c&H00FFFF&\\bord0\\shad0}}简体中文尺寸测试
Dialogue: 1,0:00:00.000,0:00:02.000,Default,,0,0,0,,{{\\an7\\pos(900,978)\\fs22\\1c&HFF00FF&\\bord0\\shad0\\t(0,1000,\\fs40)}}FX
"""


def pixel(frame: bytes, x: int, y: int) -> tuple[int, int, int]:
    offset = (y * WIDTH + x) * 3
    return (
        frame[offset],
        frame[offset + 1],
        frame[offset + 2],
    )


def color_pixels(
    frame: bytes,
    *,
    region: tuple[int, int, int, int],
    predicate: Callable[[tuple[int, int, int]], bool],
) -> list[tuple[int, int]]:
    left, top, right, bottom = region
    return [
        (x, y)
        for y in range(top, bottom)
        for x in range(left, right)
        if predicate(pixel(frame, x, y))
    ]


def bounds(points: list[tuple[int, int]]) -> tuple[int, int, int, int]:
    if not points:
        raise RuntimeError("Expected ASS fixture text was not visible in the burn.")
    xs, ys = zip(*points)
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def capture_frame(ffmpeg: str, path: Path, seconds: float) -> bytes:
    result = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-ss",
            str(seconds),
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(
            f"Could not decode fixture frame from {path}: "
            f"{result.stderr.decode(errors='replace')}"
        )
    if len(result.stdout) != FRAME_BYTES:
        raise RuntimeError(
            f"Expected a {FRAME_BYTES}-byte 1080p RGB fixture frame, "
            f"got {len(result.stdout)} bytes."
        )
    return result.stdout


def capture_ass_reference(
    ffmpeg: str,
    source: Path,
    subtitle: Path,
    seconds: float,
) -> bytes:
    result = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-ss",
            str(seconds),
            "-i",
            str(source),
            "-vf",
            f"subtitles=filename='{subtitle}'",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(
            "Could not render the ASS reference frame: "
            f"{result.stderr.decode(errors='replace')}"
        )
    if len(result.stdout) != FRAME_BYTES:
        raise RuntimeError(
            f"Expected a {FRAME_BYTES}-byte ASS reference frame, "
            f"got {len(result.stdout)} bytes."
        )
    return result.stdout


def assert_close_pixels(
    actual: tuple[int, int, int], expected: tuple[int, int, int], *, tolerance: int
) -> None:
    if max(abs(a - e) for a, e in zip(actual, expected)) > tolerance:
        raise RuntimeError(
            f"Pixel differs beyond codec tolerance: {actual} vs {expected}."
        )


def assert_close_bounds(
    actual: tuple[int, int, int, int],
    expected: tuple[int, int, int, int],
    *,
    tolerance: int = 5,
) -> None:
    if any(abs(a - e) > tolerance for a, e in zip(actual, expected)):
        raise RuntimeError(
            "SmartSub changed ASS glyph geometry beyond codec tolerance: "
            f"actual={actual}, expected={expected}."
        )


def mask_edge_samples() -> list[tuple[int, int]]:
    points: set[tuple[int, int]] = set()
    for y in range(MASK[1] + 4, MASK[3] - 4, 13):
        for x in range(MASK[0] - 3, MASK[0] + 4):
            points.add((x, y))
        for x in range(MASK[2] - 4, MASK[2] + 3):
            points.add((x, y))
    for x in range(MASK[0] + 4, MASK[2] - 4, 29):
        for y in range(MASK[1] - 3, MASK[1] + 4):
            points.add((x, y))
        for y in range(MASK[3] - 4, MASK[3] + 3):
            points.add((x, y))
    return sorted(points)


def kill_backend(profile: Path) -> None:
    endpoint = profile / "automation" / "endpoint.json"
    if not endpoint.is_file():
        return
    pid = json.loads(endpoint.read_text(encoding="utf-8")).get("pid")
    if not isinstance(pid, int) or pid <= 0:
        raise RuntimeError(f"Invalid SmartSub backend PID in {endpoint}.")
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return


def verify_fixture(
    ffmpeg: str, source: Path, subtitle: Path, output: Path
) -> dict[str, Any]:
    source_frame = capture_frame(ffmpeg, source, 1.5)
    burned_frame = capture_frame(ffmpeg, output, 1.5)
    expected_frame = capture_ass_reference(ffmpeg, source, subtitle, 1.5)

    if pixel(source_frame, 100, 900)[1] < 100:
        raise RuntimeError("Synthetic source banner was not generated as expected.")
    edge_samples = mask_edge_samples()
    for point in edge_samples:
        assert_close_pixels(
            pixel(burned_frame, *point),
            pixel(expected_frame, *point),
            tolerance=40,
        )
    for point in (
        (MASK[0] + 4, MASK[1] + 4),
        (MASK[2] - 5, MASK[1] + 4),
        (MASK[0] + 4, MASK[3] - 5),
        (MASK[2] - 5, MASK[3] - 5),
    ):
        if max(pixel(expected_frame, *point)) > 70:
            raise RuntimeError(f"Synthetic ASS mask is not opaque at {point}.")
    for point in ((72, 890), (1844, 890), (72, 1014), (1844, 1014)):
        if max(pixel(burned_frame, *point)) > 70:
            raise RuntimeError(f"Opaque ASS mask missing at fixture point {point}.")

    for point in ((65, 950), (1854, 950), (300, 881), (300, 1023)):
        assert_close_pixels(
            pixel(burned_frame, *point),
            pixel(source_frame, *point),
            tolerance=40,
        )

    english_region = (100, 890, 700, 940)
    english_predicate = lambda rgb: min(rgb) > 175
    english = bounds(
        color_pixels(burned_frame, region=english_region, predicate=english_predicate)
    )
    expected_english = bounds(
        color_pixels(
            expected_frame,
            region=english_region,
            predicate=english_predicate,
        )
    )
    assert_close_bounds(english, expected_english)
    chinese_region = (100, 940, 700, 978)
    chinese_predicate = lambda rgb: (
        rgb[0] > 150 and rgb[1] > 150 and rgb[2] < 100
    )
    chinese = bounds(
        color_pixels(burned_frame, region=chinese_region, predicate=chinese_predicate)
    )
    expected_chinese = bounds(
        color_pixels(
            expected_frame,
            region=chinese_region,
            predicate=chinese_predicate,
        )
    )
    assert_close_bounds(chinese, expected_chinese)
    if english[0] < 115 or english[1] < 890 or english[3] > 940:
        raise RuntimeError(f"English inline position/style changed: {english}")
    if chinese[0] < 115 or chinese[1] < 940 or chinese[3] > 978:
        raise RuntimeError(f"Chinese inline position/style changed: {chinese}")
    if english[3] - english[1] <= chinese[3] - chinese[1]:
        raise RuntimeError(
            "Per-language ASS inline font sizes were not preserved: "
            f"English={english}, Chinese={chinese}."
        )

    early = capture_frame(ffmpeg, output, 0.2)
    late = capture_frame(ffmpeg, output, 1.8)
    magenta = lambda rgb: rgb[0] > 130 and rgb[2] > 130 and rgb[1] < 120
    effect_region = (880, 970, 1180, 1030)
    early_fx = bounds(color_pixels(early, region=effect_region, predicate=magenta))
    late_fx = bounds(color_pixels(late, region=effect_region, predicate=magenta))
    expected_early = bounds(
        color_pixels(
            capture_ass_reference(ffmpeg, source, subtitle, 0.2),
            region=effect_region,
            predicate=magenta,
        )
    )
    expected_late = bounds(
        color_pixels(
            capture_ass_reference(ffmpeg, source, subtitle, 1.8),
            region=effect_region,
            predicate=magenta,
        )
    )
    assert_close_bounds(early_fx, expected_early)
    assert_close_bounds(late_fx, expected_late)
    if late_fx[3] - late_fx[1] <= early_fx[3] - early_fx[1]:
        raise RuntimeError(
            f"ASS transform effect was not preserved: early={early_fx}, late={late_fx}."
        )

    return {
        "fixture_source": source.name,
        "fixture_output": output.name,
        "source_bbox": list(SOURCE_BANNER),
        "mask_bbox": list(MASK),
        "mask_points_checked": 4,
        "mask_edge_points_compared": len(edge_samples),
        "outside_mask_points_checked": 4,
        "english_text_bbox": list(english),
        "chinese_text_bbox": list(chinese),
        "animated_effect_early_bbox": list(early_fx),
        "animated_effect_late_bbox": list(late_fx),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smartsub-root", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()

    smartsub_root = args.smartsub_root.resolve()
    if not (smartsub_root / "scripts" / "smartsub.mjs").is_file():
        parser.error("--smartsub-root must point to the checked-out SmartSub repo.")
    if not os.environ.get("DISPLAY"):
        parser.error("Run this fixture under Xvfb; DISPLAY is missing.")

    work_root = args.work_dir.resolve() if args.work_dir else None
    if work_root:
        work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="smartsub-ass-fixture-",
        dir=str(work_root) if work_root else None,
    ) as temp:
        work = Path(temp)
        source = work / "fixture-source.mp4"
        subtitle = work / "fixture-subtitles.ass"
        output = work / "fixture-burned.mp4"
        input_json = work / "compose-input.json"
        profile = work / "smartsub-profile"
        ffmpeg = run(
            [
                "node",
                "-e",
                "process.stdout.write(require('ffmpeg-static'))",
            ],
            cwd=smartsub_root,
        ).strip()
        if not ffmpeg or not Path(ffmpeg).is_file():
            raise RuntimeError("Pinned SmartSub ffmpeg-static executable is missing.")

        run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=0x326496:s={WIDTH}x{HEIGHT}:r=25:d=2",
                "-vf",
                "drawbox=x=68:y=885:w=1782:h=135:color=0x00cc00:t=fill",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "10",
                "-pix_fmt",
                "yuv420p",
                str(source),
            ],
            cwd=smartsub_root,
        )
        subtitle.write_text(ass_fixture(), encoding="utf-8")
        payload = {
            "videoPath": str(source),
            "subtitlePath": str(subtitle),
            "outputPath": str(output),
            "config": {
                "outputMode": "hardcode",
                "videoQuality": "original",
                "encoderMode": "cpu",
                "style": {
                    "fontName": "Noto Sans CJK SC",
                    "fontSize": 36,
                    "primaryColor": "#FFFFFF",
                    "outlineColor": "#000000",
                    "backColor": "#000000",
                    "backOpacity": 0,
                    "bold": False,
                    "italic": False,
                    "underline": False,
                    "borderStyle": 1,
                    "outline": 0,
                    "shadow": 0,
                    "alignment": 7,
                    "marginL": 0,
                    "marginR": 0,
                    "marginV": 0,
                },
            },
        }
        input_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        env = {
            **os.environ,
            "SMARTSUB_DEV": "1",
            "SMARTSUB_DATA_DIR": str(profile),
        }
        try:
            cli_result = subprocess.run(
                [
                    "node",
                    "scripts/smartsub.mjs",
                    "compose",
                    "run",
                    "--input-json",
                    str(input_json),
                    "--wait",
                    "--json",
                    "--data-dir",
                    str(profile),
                ],
                cwd=smartsub_root,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if cli_result.returncode:
                raise RuntimeError(
                    "SmartSub compose.run failed.\n"
                    f"stdout:\n{cli_result.stdout}\nstderr:\n{cli_result.stderr}"
                )
            try:
                result = json.loads(cli_result.stdout)
            except json.JSONDecodeError as error:
                raise RuntimeError(
                    "SmartSub CLI did not return one JSON result.\n"
                    f"stdout:\n{cli_result.stdout}\nstderr:\n{cli_result.stderr}"
                ) from error
            if result.get("status") != "completed":
                raise RuntimeError(f"SmartSub compose.run did not complete: {result}")
            if not output.is_file() or output.stat().st_size == 0:
                raise RuntimeError("SmartSub reported completion without fixture output.")
            evidence = verify_fixture(ffmpeg, source, subtitle, output)
            evidence["smartsub_commit"] = "607376a51a748602712145e2386b13e91bbc2e6d"
            evidence["compose_mode"] = payload["config"]["outputMode"]
            evidence["subtitle_format"] = "ASS"
            print(json.dumps(evidence, ensure_ascii=False, indent=2))
        finally:
            kill_backend(profile)


if __name__ == "__main__":
    main()
