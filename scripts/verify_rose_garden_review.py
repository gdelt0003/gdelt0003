"""Verify and label the Rose Garden bilingual review render."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


EVENT_ID = "rose-garden-lunch-2026-10-15"
EVENT_TITLE = "President Trump Participates in a Rose Garden Lunch"
EVENT_DATE = "2026-10-15"
EVENT_LOCATION = "White House Rose Garden"
SOURCE_ASSET = "RoseGardenLunch-IySF_8OArvw.mp4"
SOURCE_RELEASE_TAG = "rose-garden-lunch-source-2026-10-15"
SOURCE_URL = "https://www.youtube.com/watch?v=IySF_8OArvw"
SOURCE_SIZE_BYTES = 1_030_142_647
SOURCE_SHA256 = "e0b04fb669fd0d09f1492de6a3160bb3b6dae2e3e396be77372f4b5635da5f73"
ASSET_PREFIX = "RoseGardenLunch-IySF_8OArvw"
SUBTITLE_LAYOUT = "rose-garden-fixed-caption-band"
CAPTION_BAND_HEIGHT_PERCENT = 30
CAPTION_SAFE_WIDTH_PERCENT = 78
CAPTION_BAND_TOP_PADDING_PERCENT = 2
CAPTION_BAND_BOTTOM_PADDING_PERCENT = 4


def render_caption_geometry_frame(ass_path: Path, width: int, height: int, start: float) -> bytes:
    filter_path = str(ass_path.resolve()).replace("\\", "/").replace(":", r"\:")
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=red:s={width}x{height}:r=1:d=1",
            "-vf",
            f"setpts=PTS+{start:.3f}/TB,subtitles={filter_path}",
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
        details = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"FFmpeg ASS geometry render failed: {details}")
    expected_size = width * height * 3
    if len(result.stdout) != expected_size:
        raise RuntimeError(
            "FFmpeg ASS geometry render returned an invalid frame size: "
            f"expected {expected_size}, got {len(result.stdout)}."
        )
    return result.stdout


def inspect_caption_geometry_frame(
    frame: bytes,
    width: int,
    height: int,
) -> dict[str, int]:
    expected_size = width * height * 3
    if len(frame) != expected_size:
        raise RuntimeError("Caption geometry frame has an invalid RGB size.")
    band_height = round(height * CAPTION_BAND_HEIGHT_PERCENT / 100)
    band_top = height - band_height
    top_padding = round(height * CAPTION_BAND_TOP_PADDING_PERCENT / 100)
    bottom_padding = round(height * CAPTION_BAND_BOTTOM_PADDING_PERCENT / 100)
    safe_margin = round(width * (100 - CAPTION_SAFE_WIDTH_PERCENT) / 2 / 100)
    min_x, min_y = width, height
    max_x = max_y = -1
    for y in range(height):
        row_offset = y * width * 3
        for x in range(width):
            offset = row_offset + x * 3
            red, green, blue = frame[offset:offset + 3]
            if red > 180 and green > 100 and blue > 40:
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
    if max_x < 0:
        raise RuntimeError("Rendered caption text pixels were not detected.")
    if (
        min_x < safe_margin
        or max_x >= width - safe_margin
        or min_y < band_top + top_padding
        or max_y >= height - bottom_padding
    ):
        raise RuntimeError(
            "Rendered caption text pixels exceed the configured safe band: "
            f"bbox=({min_x},{min_y})-({max_x},{max_y}), "
            f"band_top={band_top}, width_margin={safe_margin}."
        )
    center_offset = ((band_top + top_padding) * width + width // 2) * 3
    panel_rgb = frame[center_offset:center_offset + 3]
    source_offset = ((band_top - 1) * width + width // 2) * 3
    source_rgb = frame[source_offset:source_offset + 3]
    if max(panel_rgb) > 80 or source_rgb[0] < 200 or max(source_rgb[1:]) > 80:
        raise RuntimeError(
            "Rendered caption panel is not opaque or its boundary is misplaced."
        )
    return {
        "left": min_x,
        "top": min_y,
        "right": max_x,
        "bottom": max_y,
        "band_top": band_top,
        "band_height": band_height,
    }


def validate_caption_layout(manifest: dict[str, Any]) -> None:
    checks = manifest.get("quality_checks")
    readability = checks.get("subtitle_readability") if isinstance(checks, dict) else None
    if not isinstance(readability, dict):
        raise RuntimeError("Caption layout verification is missing.")
    if readability.get("layout_profile") != SUBTITLE_LAYOUT:
        raise RuntimeError("Render does not use the required Rose Garden caption layout.")
    if readability.get("layout_configuration") != "passed":
        raise RuntimeError("Rose Garden caption layout configuration did not pass.")
    if readability.get("caption_region_validation") != "passed":
        raise RuntimeError("Rose Garden caption region geometry did not pass.")
    if readability.get("caption_region_height_percent") != CAPTION_BAND_HEIGHT_PERCENT:
        raise RuntimeError("Rose Garden caption band height is not the required 30%.")
    if readability.get("horizontal_safe_width_percent") != CAPTION_SAFE_WIDTH_PERCENT:
        raise RuntimeError("Rose Garden captions do not use the required 78% safe width.")
    if readability.get("max_lines_per_language") != 2:
        raise RuntimeError("Rose Garden captions exceed the two-line language limit.")
    english_size = readability.get("english_font_px")
    chinese_size = readability.get("chinese_font_px")
    if (
        not isinstance(english_size, (int, float))
        or isinstance(english_size, bool)
        or not isinstance(chinese_size, (int, float))
        or isinstance(chinese_size, bool)
        or chinese_size <= 0
        or english_size / chinese_size < 1.20
    ):
        raise RuntimeError("Rose Garden English captions are not 20% larger than Chinese.")
    occlusion = readability.get("caption_band_occlusion")
    if (
        not isinstance(occlusion, dict)
        or occlusion.get("status") != "source_lower_third_occluded_in_derivative"
        or occlusion.get("background") != "opaque"
        or occlusion.get("original_source_unchanged") is not True
        or occlusion.get("visual_review") != "pending"
    ):
        raise RuntimeError(
            "Caption band occlusion must be explicitly recorded with source preservation "
            "and visual review pending."
        )


def validate_caption_ass(manifest: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    ass_name = manifest.get("subtitle_ass_file")
    expected_name = f"{ASSET_PREFIX}.en-zh.ass"
    if ass_name != expected_name or Path(ass_name).name != ass_name:
        raise RuntimeError("Render manifest does not identify the expected ASS file.")
    ass_path = output_dir / ass_name
    if not ass_path.is_file() or ass_path.stat().st_size == 0:
        raise RuntimeError("The generated ASS subtitle file is missing or empty.")
    digest = hashlib.sha256(ass_path.read_bytes()).hexdigest()
    if manifest.get("subtitle_ass_sha256") != digest:
        raise RuntimeError("ASS subtitle SHA-256 does not match the render manifest.")

    from scripts.process_full_video import (
        Cue,
        _verify_rose_garden_ass,
        read_srt,
    )

    english = read_srt(output_dir / f"{ASSET_PREFIX}.en.srt")
    chinese = read_srt(output_dir / f"{ASSET_PREFIX}.zh-Hans.srt")
    if not english or len(english) != len(chinese):
        raise RuntimeError("English and Chinese SRT cue counts do not match.")
    cues = []
    for index, (en, zh) in enumerate(zip(english, chinese, strict=True), start=1):
        if abs(en[0] - zh[0]) > 0.01 or abs(en[1] - zh[1]) > 0.01:
            raise RuntimeError(f"Bilingual SRT timing mismatch at cue {index}.")
        cues.append(Cue(en[0], en[1], en[2].replace("\n", " "), zh[2].replace("\n", "")))
    try:
        _verify_rose_garden_ass(
            ass_path,
            cues,
            int(manifest["resolution"].split("x", maxsplit=1)[0]),
            int(manifest["resolution"].split("x", maxsplit=1)[1]),
        )
    except (KeyError, ValueError, RuntimeError) as error:
        raise RuntimeError(f"Generated ASS caption geometry is invalid: {error}") from error
    import pysubs2

    ass_subtitles = pysubs2.load(str(ass_path), encoding="utf-8")
    caption_events = ass_subtitles.events[1::2]
    longest_event = max(caption_events, key=lambda event: event.text.count(r"\N"))
    frame = render_caption_geometry_frame(
        ass_path,
        int(manifest["resolution"].split("x", maxsplit=1)[0]),
        int(manifest["resolution"].split("x", maxsplit=1)[1]),
        longest_event.start / 1000,
    )
    rendered_bounds = inspect_caption_geometry_frame(
        frame,
        int(manifest["resolution"].split("x", maxsplit=1)[0]),
        int(manifest["resolution"].split("x", maxsplit=1)[1]),
    )
    return {
        "status": "passed",
        "file": ass_name,
        "sha256": digest,
        "cue_count": len(cues),
        "synthetic_libass_geometry_render": "passed",
        "rendered_text_bounds_px": rendered_bounds,
        "visual_frame_review": "pending",
    }


def validate_dispatch_inputs(
    *,
    event_id: str,
    event_title: str,
    event_date: str,
    source_url: str,
    source_release_tag: str,
    source_asset: str,
    source_sha256: str,
    rights_evidence_url: str,
) -> None:
    expected = {
        "event_id": EVENT_ID,
        "event_title": EVENT_TITLE,
        "event_date": EVENT_DATE,
        "source_url": SOURCE_URL,
        "source_release_tag": SOURCE_RELEASE_TAG,
        "source_asset": SOURCE_ASSET,
        "source_sha256": SOURCE_SHA256,
    }
    supplied = {
        "event_id": event_id,
        "event_title": event_title,
        "event_date": event_date,
        "source_url": source_url,
        "source_release_tag": source_release_tag,
        "source_asset": source_asset,
        "source_sha256": source_sha256,
    }
    for name, expected_value in expected.items():
        if supplied[name] != expected_value:
            raise RuntimeError(
                f"Unexpected {name}; this workflow is pinned to {expected_value!r}."
            )

    if rights_evidence_url:
        parsed_url = urlparse(rights_evidence_url)
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise RuntimeError("Rights evidence URL must be an absolute HTTPS URL.")


def probe_media(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height",
            "-of",
            "json",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(
            f"ffprobe failed for {path}: {result.stderr.strip()}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"ffprobe returned invalid JSON for {path}") from error


def file_sha256_and_size(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest(), path.stat().st_size


def validate_probe(probe: dict[str, Any], *, label: str) -> tuple[float, int, int]:
    streams = probe.get("streams")
    if not isinstance(streams, list):
        raise RuntimeError(f"{label} has no readable media streams.")
    video_streams = [
        stream
        for stream in streams
        if isinstance(stream, dict) and stream.get("codec_type") == "video"
    ]
    if not video_streams:
        raise RuntimeError(f"{label} has no video stream.")
    audio_streams = [
        stream
        for stream in streams
        if isinstance(stream, dict) and stream.get("codec_type") == "audio"
    ]
    if not audio_streams:
        raise RuntimeError(f"{label} has no audio stream.")

    video = video_streams[0]
    width = video.get("width")
    height = video.get("height")
    try:
        duration = float(probe["format"]["duration"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(f"{label} has no valid duration.") from error
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError(f"{label} has no valid duration.")
    if not isinstance(width, int) or not isinstance(height, int):
        raise RuntimeError(f"{label} has no valid video dimensions.")
    if width < 1920 or height < 1080:
        raise RuntimeError(
            f"{label} is below the 1920x1080 minimum: {width}x{height}."
        )
    return duration, width, height


def verify_source(source: Path) -> dict[str, Any]:
    if source.name != SOURCE_ASSET:
        raise RuntimeError(f"Unexpected source asset name: {source.name}")
    if not source.is_file() or source.stat().st_size != SOURCE_SIZE_BYTES:
        actual_size = source.stat().st_size if source.is_file() else "missing"
        raise RuntimeError(
            f"Source size mismatch: expected {SOURCE_SIZE_BYTES}, got {actual_size}."
        )

    digest = hashlib.sha256()
    with source.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    source_sha256 = digest.hexdigest()
    if source_sha256 != SOURCE_SHA256:
        raise RuntimeError(
            f"Source SHA-256 mismatch: expected {SOURCE_SHA256}, got {source_sha256}."
        )

    duration, width, height = validate_probe(probe_media(source), label="Source")
    return {
        "duration_seconds": duration,
        "width": width,
        "height": height,
        "size_bytes": SOURCE_SIZE_BYTES,
        "sha256": source_sha256,
    }


def finalize_review_manifest(
    source: Path,
    output_dir: Path,
    *,
    rights_evidence_url: str = "",
) -> dict[str, Any]:
    validate_dispatch_inputs(
        event_id=EVENT_ID,
        event_title=EVENT_TITLE,
        event_date=EVENT_DATE,
        source_url=SOURCE_URL,
        source_release_tag=SOURCE_RELEASE_TAG,
        source_asset=SOURCE_ASSET,
        source_sha256=SOURCE_SHA256,
        rights_evidence_url=rights_evidence_url,
    )
    source_details = verify_source(source)
    manifest_path = output_dir / "manifest.json"
    audit_path = output_dir / "operation-audit.json"
    if not manifest_path.is_file() or not audit_path.is_file():
        raise RuntimeError("The render manifest and operation audit are required.")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError("The render manifest is invalid JSON.") from error
    if not isinstance(manifest, dict):
        raise RuntimeError("The render manifest must be a JSON object.")
    if audit_path.stat().st_size == 0:
        raise RuntimeError("The media operation audit is empty.")
    if manifest.get("source_video") != SOURCE_ASSET:
        raise RuntimeError(f"Unexpected source video in manifest: {manifest.get('source_video')}")

    expected_video = f"{ASSET_PREFIX}-bilingual.mp4"
    if manifest.get("video_file") != expected_video:
        raise RuntimeError(f"Unexpected rendered video name: {manifest.get('video_file')}")
    video_path = output_dir / expected_video
    if not video_path.is_file() or video_path.stat().st_size == 0:
        raise RuntimeError(f"Rendered video is missing or empty: {video_path}")
    video_sha256, video_size_bytes = file_sha256_and_size(video_path)

    output_probe = probe_media(video_path)
    output_duration, output_width, output_height = validate_probe(
        output_probe,
        label="Rendered video",
    )
    if (output_width, output_height) != (
        source_details["width"],
        source_details["height"],
    ):
        raise RuntimeError("Rendered video resolution differs from the source.")
    if abs(output_duration - source_details["duration_seconds"]) > 3:
        raise RuntimeError("Rendered video duration differs from the source by over 3s.")
    if (
        not isinstance(manifest.get("duration_seconds"), (int, float))
        or abs(manifest["duration_seconds"] - source_details["duration_seconds"]) > 3
        or manifest.get("resolution")
        != f'{source_details["width"]}x{source_details["height"]}'
    ):
        raise RuntimeError("Render manifest duration or resolution does not match source.")
    if manifest.get("languages") != ["en", "zh-Hans"]:
        raise RuntimeError("Render manifest does not describe English and Simplified Chinese.")
    validate_caption_layout(manifest)

    subtitle_files = manifest.get("subtitle_files")
    if not isinstance(subtitle_files, list) or not subtitle_files:
        raise RuntimeError("Render manifest has no subtitle files.")
    for filename in subtitle_files:
        if not isinstance(filename, str) or not (output_dir / filename).is_file():
            raise RuntimeError(f"Manifest subtitle file is missing: {filename}")
    if manifest.get("subtitle_ass_file") not in subtitle_files:
        raise RuntimeError("Manifest subtitle files do not include the validated ASS.")
    manifest["quality_checks"]["subtitle_readability"][
        "caption_ass_validation"
    ] = validate_caption_ass(manifest, output_dir)

    manifest["source_provenance"] = {
        "url": SOURCE_URL,
        "release_tag": SOURCE_RELEASE_TAG,
        "asset_name": SOURCE_ASSET,
        "size_bytes": source_details["size_bytes"],
        "sha256": source_details["sha256"],
        "duration_seconds": round(source_details["duration_seconds"], 3),
        "resolution": f'{source_details["width"]}x{source_details["height"]}',
    }
    manifest["event_identity"] = {
        "event_id": EVENT_ID,
        "title": EVENT_TITLE,
        "date": EVENT_DATE,
        "location": EVENT_LOCATION,
        "review_status": "pending",
    }
    manifest["rendered_video"] = {
        "file": expected_video,
        "size_bytes": video_size_bytes,
        "sha256": video_sha256,
    }
    manifest["rights_review"] = {
        "requester_authorization": "confirmed_for_this_run",
        "authorization_scope": (
            "cloud processing and public external-review publication"
        ),
        "rights_evidence_url": rights_evidence_url or None,
        "independent_rights_review": "pending",
    }
    manifest["public_review"] = {
        "status": "public_external_review_draft",
        "requester_authorization": "confirmed_for_this_run",
        "independent_rights_review": "pending",
        "source_event_match_review": "pending",
        "source_frame_review": "pending",
        "source_audio_asr_review": "pending",
        "translation_review": "pending",
        "final_release_approval": "not_granted",
    }
    manifest["source_graphics_occlusion"] = {
        "source_graphics_review": "pending",
        "caption_band_masks_source_lower_third_in_derivative": True,
        "original_source_unchanged": True,
        "visual_review": "pending",
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-dispatch-inputs", action="store_true")
    parser.add_argument("--event-id", default=EVENT_ID)
    parser.add_argument("--event-title", default=EVENT_TITLE)
    parser.add_argument("--event-date", default=EVENT_DATE)
    parser.add_argument("--source-url", default=SOURCE_URL)
    parser.add_argument("--source-release-tag", default=SOURCE_RELEASE_TAG)
    parser.add_argument("--source-asset", default=SOURCE_ASSET)
    parser.add_argument("--source-sha256", default=SOURCE_SHA256)
    parser.add_argument("--rights-evidence-url", default="")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    validate_dispatch_inputs(
        event_id=args.event_id,
        event_title=args.event_title,
        event_date=args.event_date,
        source_url=args.source_url,
        source_release_tag=args.source_release_tag,
        source_asset=args.source_asset,
        source_sha256=args.source_sha256,
        rights_evidence_url=args.rights_evidence_url,
    )
    if args.validate_dispatch_inputs:
        return
    if args.source is None:
        parser.error("--source is required unless --validate-dispatch-inputs is used.")

    if args.output_dir is None:
        print(json.dumps(verify_source(args.source), indent=2))
    else:
        manifest = finalize_review_manifest(
            args.source,
            args.output_dir,
            rights_evidence_url=args.rights_evidence_url,
        )
        print(json.dumps(manifest["public_review"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
