"""Verify and label the Rose Garden bilingual review render."""

from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime
import hashlib
import json
import math
import re
import subprocess
import tempfile
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
SUBTITLE_LAYOUT = "rose-garden-source-aware-bilingual"
CAPTION_SAFE_WIDTH_PERCENT = 68
USER_PROVIDED_STILL_BANNER_BBOX = {
    "left": 68,
    "top": 885,
    "right": 1850,
    "bottom": 1020,
}
USER_PROVIDED_STILL_RESOLUTION = {"width": 1920, "height": 1080}
USER_PROVIDED_STILL_MASK_PADDING_PX_PER_EDGE = 2
FRAME_REVIEW_SIGNATURE_NAMESPACE = "rose-garden-frame-review"
FRAME_REVIEW_ALLOWED_SIGNERS = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "rose-garden-frame-review-allowed-signers"
)


def user_provided_still_measurement() -> dict[str, Any]:
    source_bbox = USER_PROVIDED_STILL_BANNER_BBOX
    padding = USER_PROVIDED_STILL_MASK_PADDING_PX_PER_EDGE
    return {
        "measurement_source": "user_provided_still",
        "evidence_type": "user_provided_still_measurement",
        "measurement_status": "unverified_still_estimate",
        "source_resolution_px": dict(USER_PROVIDED_STILL_RESOLUTION),
        "source_banner_bbox_px_half_open": dict(source_bbox),
        "proposed_mask_bbox_px_half_open": {
            "left": source_bbox["left"] - padding,
            "top": source_bbox["top"] - padding,
            "right": source_bbox["right"] + padding,
            "bottom": source_bbox["bottom"] + padding,
        },
        "proposed_mask_dimensions_px": {
            "width": (
                source_bbox["right"] - source_bbox["left"] + 2 * padding
            ),
            "height": (
                source_bbox["bottom"] - source_bbox["top"] + 2 * padding
            ),
        },
        "padding_px_per_edge": padding,
        "source_timecode": "not_verified",
        "source_provenance": "not_verified",
        "timecode_status": "not_verified",
        "provenance_status": "not_verified",
        "video_wide_position_stability": "not_verified",
        "controlled_cloud_frame_review": "not_verified",
        "production_bbox_input": False,
    }


def user_still_source_graphics_regions(width: int, height: int) -> list[dict[str, Any]]:
    if (width, height) != (
        USER_PROVIDED_STILL_RESOLUTION["width"],
        USER_PROVIDED_STILL_RESOLUTION["height"],
    ):
        raise RuntimeError(
            "The user still estimate is only defined for its 1920x1080 resolution."
        )
    bbox = USER_PROVIDED_STILL_BANNER_BBOX
    return [
        {
            "label": "source-lower-third-user-still-estimate",
            "human_verified": False,
            "x": bbox["left"] / width,
            "y": bbox["top"] / height,
            "width": (bbox["right"] - bbox["left"]) / width,
            "height": (bbox["bottom"] - bbox["top"]) / height,
        }
    ]


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
    caption_region: dict[str, int],
    mask_bbox: dict[str, int] | None = None,
) -> dict[str, int]:
    expected_size = width * height * 3
    if len(frame) != expected_size:
        raise RuntimeError("Caption geometry frame has an invalid RGB size.")
    min_x, min_y = width, height
    max_x = max_y = -1
    for y in range(height):
        row_offset = y * width * 3
        for x in range(width):
            offset = row_offset + x * 3
            red, green, blue = frame[offset:offset + 3]
            if red > 200 and green > 200 and blue > 200:
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
    if max_x < 0:
        raise RuntimeError("Rendered caption text pixels were not detected.")
    if (
        min_x < caption_region["left"]
        or min_y < caption_region["top"]
        or max_x >= caption_region["right"]
        or max_y >= caption_region["bottom"]
    ):
        raise RuntimeError(
            "Rendered caption text pixels exceed the reviewed caption region: "
            f"bbox=({min_x},{min_y})-({max_x},{max_y}), "
            f"region={caption_region}."
        )
    result = {
        "left": min_x,
        "top": min_y,
        "right": max_x,
        "bottom": max_y,
    }
    if mask_bbox is None:
        return result

    def pixel(x: int, y: int) -> tuple[int, int, int]:
        offset = (y * width + x) * 3
        return tuple(frame[offset:offset + 3])

    for x, y in (
        (mask_bbox["left"], mask_bbox["top"]),
        (mask_bbox["right"] - 1, mask_bbox["top"]),
        (mask_bbox["left"], mask_bbox["bottom"] - 1),
        (mask_bbox["right"] - 1, mask_bbox["bottom"] - 1),
    ):
        if max(pixel(x, y)) > 80:
            raise RuntimeError("Rendered opaque mask does not cover its exact BBox.")
    for x, y in (
        (mask_bbox["left"] - 1, mask_bbox["top"]),
        (mask_bbox["right"], mask_bbox["top"]),
        (mask_bbox["left"], mask_bbox["top"] - 1),
        (mask_bbox["left"], mask_bbox["bottom"]),
    ):
        if 0 <= x < width and 0 <= y < height and pixel(x, y) != (255, 0, 0):
            raise RuntimeError("Rendered opaque mask exceeds its exact BBox.")
    result["mask_left"] = mask_bbox["left"]
    result["mask_top"] = mask_bbox["top"]
    result["mask_right"] = mask_bbox["right"]
    result["mask_bottom"] = mask_bbox["bottom"]
    return result


def validate_caption_layout(
    manifest: dict[str, Any],
    *,
    expected_source_sha256: str | None = None,
) -> None:
    checks = manifest.get("quality_checks")
    readability = checks.get("subtitle_readability") if isinstance(checks, dict) else None
    if not isinstance(readability, dict):
        raise RuntimeError("Caption layout verification is missing.")
    if readability.get("layout_profile") != SUBTITLE_LAYOUT:
        raise RuntimeError("Render does not use the required Rose Garden caption layout.")
    if readability.get("layout_configuration") != "passed":
        raise RuntimeError("Rose Garden caption layout configuration did not pass.")
    if readability.get("caption_region_validation") != "not_verified":
        raise RuntimeError(
            "Rose Garden caption-region visual clearance must remain not_verified."
        )
    if readability.get("caption_position_review") != "pending":
        raise RuntimeError("Rose Garden caption-position review must remain pending.")
    source_graphics_review = readability.get("source_graphics_review")
    if not isinstance(source_graphics_review, dict) or readability.get(
        "visual_frame_review"
    ) != "not_verified":
        raise RuntimeError(
            "Rose Garden source-frame or visual review state is invalid."
        )
    trusted_review = source_graphics_review.get("trusted_frame_review")
    if (
        source_graphics_review.get("status") == "trusted_bbox_verified"
        and source_graphics_review.get("review_status") == "verified"
        and source_graphics_review.get("production_bbox_input") is True
        and isinstance(trusted_review, dict)
        and isinstance(trusted_review.get("record"), dict)
        and isinstance(trusted_review.get("signature_base64"), str)
    ):
        record = trusted_review["record"]
        if (
            expected_source_sha256 is None
            or record.get("source_sha256") != expected_source_sha256
            or record.get("source_resolution")
            != {
                "width": int(str(manifest.get("resolution", "0x0")).split("x")[0]),
                "height": int(str(manifest.get("resolution", "0x0")).split("x")[1]),
            }
        ):
            raise RuntimeError(
                "Trusted BBox review does not match the verified source SHA/resolution."
            )
        regions = source_graphics_review.get("regions")
        signed_regions = [
            {
                "label": region["label"],
                "human_verified": region.get("human_verified") is True,
                **region["normalized_bbox"],
            }
            for region in regions
            if isinstance(region, dict)
            and isinstance(region.get("normalized_bbox"), dict)
        ] if isinstance(regions, list) else []
        validate_review_gates(
            caption_position="mask-lower-third",
            independent_rights_review_passed=False,
            event_match_review_passed=False,
            event_time_timezone_review_passed=False,
            source_lineage_review_passed=False,
            source_frame_review_record_json=json.dumps(record),
            source_frame_review_signature=trusted_review["signature_base64"],
            source_graphics_regions_json=json.dumps(signed_regions),
            dispatch_actor="",
            rights_evidence_url="",
            event_match_evidence_url="",
            event_time_timezone_evidence_url="",
            source_lineage_evidence_url="",
        )
    elif source_graphics_review.get("status") == "user_provided_still_estimate":
        expected_measurement = user_provided_still_measurement()
        source_measurement = manifest.get("source_frame_measurement")
        expected_regions = user_still_source_graphics_regions(
            USER_PROVIDED_STILL_RESOLUTION["width"],
            USER_PROVIDED_STILL_RESOLUTION["height"],
        )
        bbox = USER_PROVIDED_STILL_BANNER_BBOX
        expected_pixel_bbox = {
            "left": bbox["left"],
            "top": bbox["top"],
            "right": bbox["right"],
            "bottom": bbox["bottom"],
            "width": bbox["right"] - bbox["left"],
            "height": bbox["bottom"] - bbox["top"],
        }
        expected_manifest_regions = [
            {
                "label": region["label"],
                "human_verified": False,
                "bbox_px": expected_pixel_bbox,
                "normalized_bbox": {
                    key: region[key] for key in ("x", "y", "width", "height")
                },
            }
            for region in expected_regions
        ]
        if (
            manifest.get("frame_review_mode") != "unverified-review-draft"
            or source_graphics_review.get("review_status") != "pending"
            or source_graphics_review.get("measurement_source")
            != "user_provided_still"
            or source_graphics_review.get("measurement_status")
            != "unverified_still_estimate"
            or source_graphics_review.get("production_bbox_input") is not False
            or source_graphics_review.get("source_timecode") != "not_verified"
            or source_graphics_review.get("source_provenance") != "not_verified"
            or source_graphics_review.get("source_frame_review") != "pending"
            or source_graphics_review.get("visual_review") != "pending"
            or source_graphics_review.get("source_resolution_px")
            != USER_PROVIDED_STILL_RESOLUTION
            or source_graphics_review.get("user_provided_still_measurement")
            != expected_measurement
            or not isinstance(source_measurement, dict)
            or any(
                source_measurement.get(key) != value
                for key, value in expected_measurement.items()
            )
            or source_measurement.get("review_status") != "pending"
        ):
            raise RuntimeError(
                "User-still estimate metadata must remain unverified, pending, "
                "and excluded from production BBox input."
            )
        regions = source_graphics_review.get("regions")
        if regions != expected_manifest_regions:
            raise RuntimeError(
                "Rendered user-still estimate BBox does not match the fixed unverified input."
            )
        if expected_measurement.get("production_bbox_input") is not False:
            raise RuntimeError("Still estimate cannot be production BBox input.")
    elif (
        source_graphics_review.get("status") != "not_verified"
        or source_graphics_review.get("review_status") != "pending"
        or source_graphics_review.get("production_bbox_input") is not False
    ):
        raise RuntimeError("Untrusted source-frame review cannot be production input.")
    if readability.get("horizontal_safe_width_percent") != CAPTION_SAFE_WIDTH_PERCENT:
        raise RuntimeError("Rose Garden captions do not use the BBC-referenced 68% line width.")
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
    if not isinstance(occlusion, dict):
        raise RuntimeError("Caption overlap/occlusion disclosure is missing.")
    if readability.get("caption_position") == "mask-lower-third":
        source_bbox = occlusion.get("source_banner_bbox_px")
        mask_bbox = occlusion.get("mask_bbox_px")
        padding = occlusion.get("padding_px_per_edge")
        source_graphics = readability.get("source_graphics_review")
        dimensions = (
            source_graphics.get("source_resolution_px")
            if isinstance(source_graphics, dict)
            else None
        )
        if (
            occlusion.get("status") != "source_lower_third_occluded_in_derivative"
            or occlusion.get("status_label") != "masked_not_clean"
            or occlusion.get("background") != "opaque"
            or occlusion.get("original_source_unchanged") is not True
            or occlusion.get("user_authorized_rose_exception") is not True
            or occlusion.get("visual_review") != "pending"
            or occlusion.get("padding_selection")
            != "implementation choice, not user-specified"
            or not isinstance(source_bbox, dict)
            or not isinstance(mask_bbox, dict)
            or not isinstance(dimensions, dict)
            or not isinstance(padding, int)
            or isinstance(padding, bool)
            or not 1 <= padding <= 5
        ):
            raise RuntimeError("Rose mask authorization, geometry, or pending disclosure is invalid.")
        for edge, expected in (
            ("left", source_bbox.get("left", -1) - padding),
            ("top", source_bbox.get("top", -1) - padding),
            ("right", source_bbox.get("right", -1) + padding),
            ("bottom", source_bbox.get("bottom", -1) + padding),
        ):
            if mask_bbox.get(edge) != expected:
                raise RuntimeError(
                    f"Rose mask BBox is not exactly {padding}px outward at {edge}."
                )
        if (
            mask_bbox.get("left", -1) < 0
            or mask_bbox.get("top", -1) < 0
            or mask_bbox.get("right", 0) > dimensions.get("width", 0)
            or mask_bbox.get("bottom", 0) > dimensions.get("height", 0)
            or occlusion.get("output_resolution_px") != dimensions
            or occlusion.get("expansion_direction")
            != "outward on each of four edges"
        ):
            raise RuntimeError("Rose mask BBox exceeds or mismatches the frame geometry.")
    elif (
        occlusion.get("status") != "non_mask_layout_selected"
        or occlusion.get("original_source_unchanged") is not True
        or occlusion.get("visual_review") != "pending"
    ):
        raise RuntimeError("Non-mask Rose layout has an invalid occlusion disclosure.")

    source_evidence = readability.get("rose_source_evidence")
    if (
        not isinstance(source_evidence, dict)
        or source_evidence.get("classification") != "official_event_anchor_only"
        or source_evidence.get("whitehouse_search", {}).get("status")
        != "no_verifiable_event_article_or_embedded_video_found"
        or source_evidence.get("event_match") != "pending"
        or source_evidence.get("exact_event_time_and_timezone") != "pending"
        or source_evidence.get("source_url_to_release_lineage") != "pending"
        or source_evidence.get("source_graphics_and_frame_review") != "pending"
        or source_evidence.get("controlled_cloud_frame_review_route")
        != "not_found_in_repository; confirmation_pending"
        or source_evidence.get("independent_reuse_rights_review") != "pending"
        or source_evidence.get("general_whitehouse_copyright_policy", {}).get(
            "specific_video_clearance"
        )
        != "not_established"
    ):
        raise RuntimeError("M2 event/source evidence must remain explicitly pending.")


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
    readability = manifest["quality_checks"]["subtitle_readability"]
    position = readability.get("caption_position")
    source_review = readability.get("source_graphics_review")
    allow_unverified_estimate = (
        isinstance(source_review, dict)
        and source_review.get("status") == "user_provided_still_estimate"
        and manifest.get("frame_review_mode") == "unverified-review-draft"
    )
    regions = (
        [
            {
                "label": region["label"],
                "human_verified": region.get("human_verified") is True,
                **region["normalized_bbox"],
            }
            for region in source_review["regions"]
        ]
        if isinstance(source_review, dict)
        and isinstance(source_review.get("regions"), list)
        else []
    )
    occlusion = readability.get("caption_band_occlusion")
    try:
        _verify_rose_garden_ass(
            ass_path,
            cues,
            int(manifest["resolution"].split("x", maxsplit=1)[0]),
            int(manifest["resolution"].split("x", maxsplit=1)[1]),
            position,
            regions,
            isinstance(occlusion, dict)
            and occlusion.get("user_authorized_rose_exception") is True,
            occlusion.get("padding_px_per_edge")
            if isinstance(occlusion, dict)
            else None,
            allow_unverified_estimate,
        )
    except (KeyError, ValueError, RuntimeError) as error:
        raise RuntimeError(f"Generated ASS caption geometry is invalid: {error}") from error
    import pysubs2

    ass_subtitles = pysubs2.load(str(ass_path), encoding="utf-8")
    caption_events = (
        ass_subtitles.events[1::2]
        if position == "mask-lower-third"
        else ass_subtitles.events
    )
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
        readability["caption_region_box_px"],
        (
            readability["caption_band_occlusion"]["mask_bbox_px"]
            if position == "mask-lower-third"
            else None
        ),
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
    event_identity_evidence_url: str = "",
    event_match_evidence_url: str = "",
    event_time_timezone_evidence_url: str = "",
    source_lineage_evidence_url: str = "",
    exact_event_match_confirmed: bool = False,
    reuse_rights_confirmed: bool = False,
    require_processing_evidence: bool = False,
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

    if require_processing_evidence:
        evidence = {
            "event identity": event_identity_evidence_url,
            "exact source/event match": event_match_evidence_url,
            "source-specific reuse rights": rights_evidence_url,
        }
        for name, value in evidence.items():
            parsed_url = urlparse(value)
            if parsed_url.scheme != "https" or not parsed_url.netloc:
                raise RuntimeError(
                    f"{name} evidence URL must be an absolute HTTPS URL before processing."
                )
        if exact_event_match_confirmed is not True:
            raise RuntimeError(
                "Explicit exact-event match confirmation is required before processing."
            )
        if reuse_rights_confirmed is not True:
            raise RuntimeError(
                "Explicit source-specific reuse-rights confirmation is required before processing."
            )
    elif rights_evidence_url:
        parsed_url = urlparse(rights_evidence_url)
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise RuntimeError("Rights evidence URL must be an absolute HTTPS URL.")


def validate_layout_inputs(
    *,
    caption_position: str,
    caption_safe_region_reviewed: bool,
    source_graphics_regions_json: str,
    rose_mask_authorized: bool,
    mask_padding_px_per_edge: int,
    frame_review_mode: str = "trusted-signed-review",
) -> list[dict[str, Any]]:
    if caption_position not in {"top", "center", "mask-lower-third"}:
        raise RuntimeError("caption_position is not a supported Rose layout.")
    masking = caption_position == "mask-lower-third"
    if frame_review_mode not in {
        "trusted-signed-review",
        "unverified-review-draft",
    }:
        raise RuntimeError("frame_review_mode is not supported.")
    if masking and frame_review_mode == "unverified-review-draft":
        try:
            regions = json.loads(source_graphics_regions_json)
        except json.JSONDecodeError as error:
            raise RuntimeError(
                "source_graphics_regions_json must be valid JSON."
            ) from error
        if regions != []:
            raise RuntimeError(
                "Unverified draft mode uses only the fixed user-still estimate; "
                "do not supply a dispatch BBox."
            )
        if caption_safe_region_reviewed or not rose_mask_authorized:
            raise RuntimeError(
                "Unverified draft mode must stay pending and use the authorized Rose mask."
            )
        if (
            not isinstance(mask_padding_px_per_edge, int)
            or isinstance(mask_padding_px_per_edge, bool)
            or mask_padding_px_per_edge != USER_PROVIDED_STILL_MASK_PADDING_PX_PER_EDGE
        ):
            raise RuntimeError(
                "Unverified still-estimate masking requires exactly 2 px padding."
            )
        return []
    if masking and caption_safe_region_reviewed is not True:
        raise RuntimeError("Mask mode requires human review of the source banner BBox.")
    try:
        regions = json.loads(source_graphics_regions_json)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "source_graphics_regions_json must be valid JSON."
        ) from error
    if not isinstance(regions, list):
        raise RuntimeError("source_graphics_regions_json must be a JSON array.")
    if not regions:
        if masking:
            raise RuntimeError(
                "Mask mode requires a real production source-banner BBox; no defaults are inferred."
            )
        if rose_mask_authorized:
            raise RuntimeError("The Rose masking exception is only valid in mask mode.")
        if not isinstance(mask_padding_px_per_edge, int) or isinstance(
            mask_padding_px_per_edge, bool
        ) or not 1 <= mask_padding_px_per_edge <= 5:
            raise RuntimeError("mask_padding_px_per_edge must be an integer from 1 to 5.")
        return []
    labels = set()
    lower_third_count = 0
    for index, region in enumerate(regions, start=1):
        if not isinstance(region, dict):
            raise RuntimeError(f"Source graphics region {index} must be an object.")
        label = region.get("label")
        if not isinstance(label, str) or not label.strip() or label in labels:
            raise RuntimeError(f"Source graphics region {index} needs a unique label.")
        labels.add(label)
        human_verified = region.get("human_verified", False)
        if type(human_verified) is not bool:
            raise RuntimeError(
                f"Source graphics BBox {label!r} human_verified must be boolean."
            )
        if masking and human_verified is not True:
            raise RuntimeError(f"Source graphics BBox {label!r} is not human-verified.")
        coordinates = []
        for key in ("x", "y", "width", "height"):
            value = region.get(key)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
            ):
                raise RuntimeError(f"Source graphics BBox {label!r} has invalid {key}.")
            coordinates.append(float(value))
        x, y, box_width, box_height = coordinates
        if (
            x < 0
            or y < 0
            or box_width <= 0
            or box_height <= 0
            or x + box_width > 1
            or y + box_height > 1
        ):
            raise RuntimeError(f"Source graphics BBox {label!r} is outside frame bounds.")
        if "lower-third" in label.lower():
            lower_third_count += 1
    if masking and lower_third_count != 1:
        raise RuntimeError("Exactly one human-verified lower-third BBox is required.")
    if masking != (rose_mask_authorized is True):
        raise RuntimeError(
            "Mask mode requires the explicit Rose exception authorization."
        )
    if masking and (
        not isinstance(mask_padding_px_per_edge, int)
        or isinstance(mask_padding_px_per_edge, bool)
        or not 1 <= mask_padding_px_per_edge <= 5
    ):
        raise RuntimeError("mask_padding_px_per_edge must be an integer from 1 to 5.")
    if not masking and rose_mask_authorized:
        raise RuntimeError("The Rose masking exception is only valid in mask mode.")
    return regions


def validate_review_gates(
    *,
    caption_position: str,
    independent_rights_review_passed: bool,
    event_match_review_passed: bool,
    event_time_timezone_review_passed: bool,
    source_lineage_review_passed: bool,
    source_frame_review_record_json: str,
    source_frame_review_signature: str = "",
    source_graphics_regions_json: str,
    dispatch_actor: str,
    rights_evidence_url: str,
    event_match_evidence_url: str,
    event_time_timezone_evidence_url: str,
    source_lineage_evidence_url: str,
    frame_review_mode: str = "trusted-signed-review",
) -> dict[str, str]:
    if caption_position not in {"top", "center", "mask-lower-third"}:
        raise RuntimeError("caption_position is not a supported Rose layout.")
    if frame_review_mode not in {
        "trusted-signed-review",
        "unverified-review-draft",
    }:
        raise RuntimeError("frame_review_mode is not supported.")

    evidence = {
        "independent_rights_review": rights_evidence_url,
        "event_match_review": event_match_evidence_url,
        "event_time_timezone_review": event_time_timezone_evidence_url,
        "source_lineage_review": source_lineage_evidence_url,
    }
    for name, value in evidence.items():
        if not value:
            continue
        parsed_url = urlparse(value)
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise RuntimeError(
                f"{name} evidence URL must be absolute HTTPS when provided."
            )

    if caption_position != "mask-lower-third":
        return {
            "source_frame_review": "pending",
            "production_bbox_input": "false",
        }
    if frame_review_mode == "unverified-review-draft":
        if source_frame_review_record_json not in {"", "{}"}:
            raise RuntimeError(
                "Unverified draft mode must not include a claimed frame-review record."
            )
        if source_frame_review_signature:
            raise RuntimeError(
                "Unverified draft mode must not include a production review signature."
            )
        if json.loads(source_graphics_regions_json) != []:
            raise RuntimeError(
                "Unverified draft mode uses only the fixed user-still estimate."
            )
        return {
            "source_frame_review": "pending",
            "production_bbox_input": "false",
        }

    try:
        frame_review = json.loads(source_frame_review_record_json)
    except json.JSONDecodeError as error:
        raise RuntimeError("source_frame_review_record_json must be valid JSON.") from error
    required = {
        "reviewer_identity",
        "reviewed_at",
        "source_timecode",
        "source_resolution",
        "source_banner_bbox_px",
        "evidence_ref",
        "source_sha256",
    }
    if not isinstance(frame_review, dict) or not required.issubset(frame_review):
        raise RuntimeError(
            "Source-frame review evidence must identify reviewer, timestamp, "
            "source timecode, resolution, banner BBox, and evidence reference."
        )
    reviewer = frame_review["reviewer_identity"]
    if (
        not isinstance(reviewer, str)
        or not reviewer.strip()
        or reviewer.casefold() == dispatch_actor.casefold()
    ):
        raise RuntimeError(
            "Source-frame BBox review must identify a reviewer other than the dispatcher."
        )
    try:
        reviewed_at = datetime.fromisoformat(
            str(frame_review["reviewed_at"]).replace("Z", "+00:00")
        )
    except ValueError as error:
        raise RuntimeError("Source-frame review timestamp must be ISO-8601.") from error
    if reviewed_at.tzinfo is None:
        raise RuntimeError("Source-frame review timestamp must include a timezone.")
    timecode = frame_review["source_timecode"]
    if not isinstance(timecode, str) or not re.fullmatch(
        r"\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?", timecode
    ):
        raise RuntimeError("Source-frame evidence needs an exact HH:MM:SS[.mmm] timecode.")
    dimensions = frame_review["source_resolution"]
    bbox = frame_review["source_banner_bbox_px"]
    if (
        not isinstance(dimensions, dict)
        or type(dimensions.get("width")) is not int
        or type(dimensions.get("height")) is not int
        or dimensions["width"] < 1920
        or dimensions["height"] < 1080
        or not isinstance(bbox, dict)
        or any(type(bbox.get(key)) is not int for key in ("left", "top", "right", "bottom"))
        or bbox["left"] < 0
        or bbox["top"] < 0
        or bbox["right"] <= bbox["left"]
        or bbox["bottom"] <= bbox["top"]
        or bbox["right"] > dimensions["width"]
        or bbox["bottom"] > dimensions["height"]
    ):
        raise RuntimeError("Source-frame review BBox/resolution is invalid or out of bounds.")
    evidence_ref = frame_review["evidence_ref"]
    parsed_ref = urlparse(evidence_ref) if isinstance(evidence_ref, str) else None
    if parsed_ref is None or parsed_ref.scheme != "https" or not parsed_ref.netloc:
        raise RuntimeError("Source-frame review requires an HTTPS evidence reference.")
    if frame_review["source_sha256"] != SOURCE_SHA256:
        raise RuntimeError("Source-frame review must be bound to the pinned source SHA-256.")

    try:
        regions = json.loads(source_graphics_regions_json)
    except json.JSONDecodeError as error:
        raise RuntimeError("Source graphics regions must be valid JSON.") from error
    lower_thirds = (
        [
            region
            for region in regions
            if isinstance(region, dict)
            and "lower-third" in str(region.get("label", "")).lower()
        ]
        if isinstance(regions, list)
        else []
    )
    if len(lower_thirds) != 1 or lower_thirds[0].get("human_verified") is not True:
        raise RuntimeError(
            "Mask mode requires exactly one human-verified production source-banner BBox."
        )
    region = lower_thirds[0]
    try:
        input_bbox = {
            "left": round(float(region["x"]) * dimensions["width"]),
            "top": round(float(region["y"]) * dimensions["height"]),
            "right": round(
                (float(region["x"]) + float(region["width"]))
                * dimensions["width"]
            ),
            "bottom": round(
                (float(region["y"]) + float(region["height"]))
                * dimensions["height"]
            ),
        }
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            "Human-verified production BBox coordinates are invalid."
        ) from error
    expected_bbox = {
        key: bbox[key] for key in ("left", "top", "right", "bottom")
    }
    if input_bbox != expected_bbox:
        raise RuntimeError(
            "Mask source BBox does not match the independent source-frame review record."
        )

    verify_frame_review_signature(
        frame_review,
        source_frame_review_signature,
        FRAME_REVIEW_ALLOWED_SIGNERS,
    )
    return {
        "source_frame_review": "verified_by_trusted_signature",
        "production_bbox_input": "true",
    }


def canonical_frame_review_payload(frame_review: dict[str, Any]) -> bytes:
    return json.dumps(
        frame_review,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def verify_frame_review_signature(
    frame_review: dict[str, Any],
    signature_base64: str,
    allowed_signers_path: Path = FRAME_REVIEW_ALLOWED_SIGNERS,
) -> None:
    if not signature_base64:
        raise RuntimeError(
            "Trusted frame review requires a valid base64 OpenSSH signature."
        )
    reviewer = frame_review.get("reviewer_identity")
    if not isinstance(reviewer, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._@+-]{0,99}", reviewer
    ):
        raise RuntimeError(
            "Trusted frame review requires a reviewer identity usable as an SSH principal."
        )
    try:
        signature = base64.b64decode(signature_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise RuntimeError(
            "Trusted frame review requires a valid base64 OpenSSH signature."
        ) from error
    if not allowed_signers_path.is_file():
        raise RuntimeError(
            "Trusted frame review is unavailable: the SSH allowed-signers file "
            "has not been configured."
        )
    allowed_entries = [
        line for line in allowed_signers_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not allowed_entries:
        raise RuntimeError(
            "Trusted frame review is unavailable: no reviewer public keys are configured."
        )

    with tempfile.TemporaryDirectory(prefix="rose-frame-review-") as directory:
        signature_path = Path(directory) / "frame-review.sig"
        signature_path.write_bytes(signature)
        result = subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "verify",
                "-f",
                str(allowed_signers_path),
                "-I",
                reviewer,
                "-n",
                FRAME_REVIEW_SIGNATURE_NAMESPACE,
                "-s",
                str(signature_path),
            ],
            input=canonical_frame_review_payload(frame_review),
            check=False,
            capture_output=True,
        )
    if result.returncode:
        details = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            "Trusted frame review signature is invalid or not signed by the "
            f"allowlisted reviewer {reviewer!r}: {details}"
        )


def validate_trusted_frame_review_for_render(
    *,
    source_path: Path,
    source_width: int,
    source_height: int,
    source_duration: float,
    source_frame_review_record_json: str,
    source_frame_review_signature: str,
    source_graphics_regions_json: str,
    dispatch_actor: str,
) -> dict[str, str]:
    source_sha256, _ = file_sha256_and_size(source_path)
    if source_sha256 != SOURCE_SHA256:
        raise RuntimeError(
            "Trusted frame review is bound to a different source SHA-256."
        )
    try:
        record = json.loads(source_frame_review_record_json)
    except json.JSONDecodeError as error:
        raise RuntimeError("source_frame_review_record_json must be valid JSON.") from error
    if not isinstance(record, dict) or record.get("source_resolution") != {
        "width": source_width,
        "height": source_height,
    }:
        raise RuntimeError(
            "Trusted frame review resolution does not match the probed source stream."
        )
    hours, minutes, seconds = (
        float(part) for part in record["source_timecode"].split(":")
    )
    if hours * 3600 + minutes * 60 + seconds > source_duration:
        raise RuntimeError("Trusted frame review timecode exceeds the source duration.")
    return validate_review_gates(
        caption_position="mask-lower-third",
        independent_rights_review_passed=False,
        event_match_review_passed=False,
        event_time_timezone_review_passed=False,
        source_lineage_review_passed=False,
        source_frame_review_record_json=source_frame_review_record_json,
        source_frame_review_signature=source_frame_review_signature,
        source_graphics_regions_json=source_graphics_regions_json,
        dispatch_actor=dispatch_actor,
        rights_evidence_url="",
        event_match_evidence_url="",
        event_time_timezone_evidence_url="",
        source_lineage_evidence_url="",
    )


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
    event_identity_evidence_url: str = "",
    event_match_evidence_url: str = "",
    event_time_timezone_evidence_url: str = "",
    source_lineage_evidence_url: str = "",
    exact_event_match_confirmed: bool = False,
    reuse_rights_confirmed: bool = False,
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
        event_identity_evidence_url=event_identity_evidence_url,
        event_match_evidence_url=event_match_evidence_url,
        event_time_timezone_evidence_url=event_time_timezone_evidence_url,
        source_lineage_evidence_url=source_lineage_evidence_url,
        exact_event_match_confirmed=exact_event_match_confirmed,
        reuse_rights_confirmed=reuse_rights_confirmed,
        require_processing_evidence=True,
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
    validate_caption_layout(
        manifest,
        expected_source_sha256=source_details["sha256"],
    )

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
        "url_to_release_lineage_review": "pending",
        "size_bytes": source_details["size_bytes"],
        "sha256": source_details["sha256"],
        "duration_seconds": round(source_details["duration_seconds"], 3),
        "resolution": f'{source_details["width"]}x{source_details["height"]}',
    }
    manifest["user_provided_still_measurement"] = (
        user_provided_still_measurement()
    )
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
    manifest["processing_prerequisites"] = {
        "event_identity_evidence_url": event_identity_evidence_url,
        "exact_source_event_match_evidence_url": event_match_evidence_url,
        "event_time_timezone_evidence_url": event_time_timezone_evidence_url,
        "source_url_to_release_asset_lineage_evidence_url": (
            source_lineage_evidence_url
        ),
        "source_specific_reuse_rights_evidence_url": rights_evidence_url,
        "exact_event_match_operator_confirmation": "confirmed",
        "reuse_rights_operator_confirmation": "confirmed",
        "independent_evidence_review": "pending",
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
    readability = manifest["quality_checks"]["subtitle_readability"]
    occlusion = readability["caption_band_occlusion"]
    manifest["source_graphics_occlusion"] = {
        **occlusion,
        "source_graphics_review": "pending",
        "caption_band_masks_source_lower_third_in_derivative": (
            readability["caption_position"] == "mask-lower-third"
        ),
        "original_source_unchanged": True,
        "visual_review": "pending",
    }
    manifest["source_event_evidence"] = readability["rose_source_evidence"]
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-dispatch-inputs", action="store_true")
    parser.add_argument("--validate-layout-inputs", action="store_true")
    parser.add_argument("--validate-review-gates", action="store_true")
    parser.add_argument(
        "--caption-position",
        choices=("top", "center", "mask-lower-third"),
        default="top",
    )
    parser.add_argument(
        "--caption-safe-region-reviewed",
        action="store_true",
    )
    parser.add_argument("--source-graphics-regions-json", default="[]")
    parser.add_argument("--rose-mask-authorized", action="store_true")
    parser.add_argument("--mask-padding-px-per-edge", type=int, default=2)
    parser.add_argument("--source-frame-review-record-json", default="{}")
    parser.add_argument("--source-frame-review-signature", default="")
    parser.add_argument("--dispatch-actor", default="")
    parser.add_argument(
        "--frame-review-mode",
        choices=("trusted-signed-review", "unverified-review-draft"),
        default="trusted-signed-review",
    )
    parser.add_argument("--independent-rights-review-passed", action="store_true")
    parser.add_argument("--event-match-review-passed", action="store_true")
    parser.add_argument("--event-time-timezone-review-passed", action="store_true")
    parser.add_argument("--source-lineage-review-passed", action="store_true")
    parser.add_argument("--event-match-evidence-url", default="")
    parser.add_argument("--event-identity-evidence-url", default="")
    parser.add_argument(
        "--exact-event-match-confirmed",
        choices=("true", "false"),
        default="false",
    )
    parser.add_argument(
        "--reuse-rights-confirmed",
        choices=("true", "false"),
        default="false",
    )
    parser.add_argument("--event-time-timezone-evidence-url", default="")
    parser.add_argument("--source-lineage-evidence-url", default="")
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
        event_identity_evidence_url=args.event_identity_evidence_url,
        event_match_evidence_url=args.event_match_evidence_url,
        event_time_timezone_evidence_url=(
            args.event_time_timezone_evidence_url
        ),
        source_lineage_evidence_url=args.source_lineage_evidence_url,
        exact_event_match_confirmed=args.exact_event_match_confirmed == "true",
        reuse_rights_confirmed=args.reuse_rights_confirmed == "true",
        require_processing_evidence=args.validate_dispatch_inputs,
    )
    if args.validate_dispatch_inputs:
        return
    if args.validate_layout_inputs:
        validate_layout_inputs(
            caption_position=args.caption_position,
            caption_safe_region_reviewed=args.caption_safe_region_reviewed,
            source_graphics_regions_json=args.source_graphics_regions_json,
            rose_mask_authorized=args.rose_mask_authorized,
            mask_padding_px_per_edge=args.mask_padding_px_per_edge,
            frame_review_mode=args.frame_review_mode,
        )
        return
    if args.validate_review_gates:
        result = validate_review_gates(
            caption_position=args.caption_position,
            independent_rights_review_passed=args.independent_rights_review_passed,
            event_match_review_passed=args.event_match_review_passed,
            event_time_timezone_review_passed=args.event_time_timezone_review_passed,
            source_lineage_review_passed=args.source_lineage_review_passed,
            source_frame_review_record_json=args.source_frame_review_record_json,
            source_frame_review_signature=args.source_frame_review_signature,
            source_graphics_regions_json=args.source_graphics_regions_json,
            dispatch_actor=args.dispatch_actor,
            rights_evidence_url=args.rights_evidence_url,
            event_match_evidence_url=args.event_match_evidence_url,
            event_time_timezone_evidence_url=args.event_time_timezone_evidence_url,
            source_lineage_evidence_url=args.source_lineage_evidence_url,
            frame_review_mode=args.frame_review_mode,
        )
        print(json.dumps(result, ensure_ascii=False))
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
            event_identity_evidence_url=args.event_identity_evidence_url,
            event_match_evidence_url=args.event_match_evidence_url,
            event_time_timezone_evidence_url=(
                args.event_time_timezone_evidence_url
            ),
            source_lineage_evidence_url=args.source_lineage_evidence_url,
            exact_event_match_confirmed=args.exact_event_match_confirmed == "true",
            reuse_rights_confirmed=args.reuse_rights_confirmed == "true",
        )
        print(json.dumps(manifest["public_review"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
