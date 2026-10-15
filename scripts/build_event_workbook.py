"""Export the event/source evidence catalog to a reviewable Excel workbook."""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


DEFAULT_CATALOG = Path("outputs/event-catalog.json")
DEFAULT_OUTPUT = Path("outputs/event-source-review.xlsx")

EVENT_HEADERS = [
    "Event ID",
    "Identity status",
    "Event title",
    "Event date",
    "Event local time",
    "Timezone",
    "Location",
    "Event type",
    "Participants",
    "Official reference",
    "Source count",
    "Verified same-time sources",
    "Identity/evidence notes",
]
SOURCE_HEADERS = [
    "Event ID",
    "Event title",
    "Publisher",
    "Source title",
    "Source URL",
    "Role",
    "Match status",
    "Published metadata (UTC; not event time)",
    "Page-published local display (not event time)",
    "Duration (seconds)",
    "Thumbnail resolution (not video resolution)",
    "Video resolution",
    "Frame review",
    "Clean-source status",
    "Independence/lineage",
    "Evidence and limitations",
]
EVENT_TRACKING_HEADERS = [
    "President attendance duration (minutes; verified)",
    "Speech word count (verified; language/method)",
    "Topics (source-backed)",
    "First discovered UTC",
    "Last verified UTC",
    "Same-event source rows (not independence count)",
    "Confidence",
    "User-mentioned source links",
    "User session annotations/explanations associated with source (verbatim)",
    "Operator notes (suggested field)",
]
SOURCE_DIRECTORY_HEADERS = [
    "Source ID",
    "Category",
    "Source",
    "URL",
    "Enabled",
    "Collection mode",
    "Target frequency",
    "Last attempt UTC",
    "Last result",
    "Access status",
    "Added by",
    "Notes",
    "Last run URL",
    "User-provided URL (verbatim)",
    "User annotation on this source (verbatim)",
]
VIDEO_CANDIDATE_HEADERS = [
    "Event ID",
    "Event title",
    "Queue rank (not a trust score)",
    "Current source path",
    "Publisher",
    "Candidate title",
    "Source URL",
    "Same-event evidence",
    "Clean-source status",
    "Observed stream resolution (not thumbnail/source-master resolution)",
    "Duration (seconds)",
    "Difference from official runtime (seconds)",
    "Source provenance / lineage (reported)",
    "Embedded graphics / occlusion review",
    "Reuse rights review",
    "User-provided characterization (claim; unverified)",
    "User subjective rating (not independent score)",
    "User feature score (not independent; rubric unspecified)",
    "User angle opinion (not verified)",
    "Camera/event-time match",
    "Camera location",
    "Camera coordinates WGS84",
    "Camera azimuth (degrees)",
    "Camera height (meters)",
    "Camera pitch (degrees)",
    "Camera equipment",
    "Media/camera department",
    "Publicly confirmed professional crew",
    "Media-seat annotation",
    "Camera evidence URL",
    "Camera method",
    "Camera uncertainty/error",
    "Camera confidence",
    "Camera verification status",
    "Repeated/static-scene review",
    "Source credibility review",
    "Independent camera review",
    "Cross-lead angle/lineage comparison",
    "Evidence and limitations",
]

_MATCH_EVIDENCE_ORDER = (
    "same_speech_moment_observed",
    "same_event_contiguous_speech_observed",
    "same_event_scene_verified",
    "same_event_context_only",
    "verified_event_anchor",
)
_CLEAN_STATUS_ORDER = {"passed": 0, "unverified": 1, "failed": 2}


def _video_resolution_pixels(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"(?<!\d)(\d{3,5})\s*[x×]\s*(\d{3,5})(?!\d)", value)
    if not match:
        return None
    width, height = (int(part) for part in match.groups())
    return width * height if width > 0 and height > 0 else None


def _positive_duration(value: Any) -> float | None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        return None
    return float(value)


def _candidate_order(
    source: dict[str, Any], official_duration: float | None
) -> tuple[Any, ...]:
    match_status = str(source.get("match_status", "")).casefold()
    match_rank = next(
        (
            rank
            for rank, evidence in enumerate(_MATCH_EVIDENCE_ORDER)
            if evidence in match_status
        ),
        len(_MATCH_EVIDENCE_ORDER),
    )
    clean_rank = _CLEAN_STATUS_ORDER.get(
        str(source.get("clean_source_status", "unverified")).casefold(), 1
    )
    resolution_pixels = _video_resolution_pixels(source.get("video_resolution"))
    duration = _positive_duration(source.get("duration_seconds"))
    duration_delta = (
        abs(duration - official_duration)
        if duration is not None and official_duration is not None
        else math.inf
    )
    return (
        match_rank,
        clean_rank,
        -(resolution_pixels or 0),
        duration_delta,
        str(source.get("publisher", "")).casefold(),
        str(source.get("url", "")).casefold(),
    )


def _has_observed_embedded_graphics(source: dict[str, Any]) -> bool:
    graphics = ("banner", "logo", "emblem", "qr code", "lower-third", "watermark", "ticker")
    observations = ("visible", "present", "observed", "shows", "seen")
    for clause in re.split(r"[.;]", str(source.get("evidence", "")).casefold()):
        if re.search(r"\b(?:no|not|never|absent)\b", clause):
            continue
        if any(term in clause for term in graphics) and any(
            term in clause for term in observations
        ):
            return True
    return False


def _candidate_path(
    candidate: dict[str, Any],
    anchor: dict[str, Any] | None,
    selected_alternate: dict[str, Any] | None,
) -> str:
    if selected_alternate is candidate:
        return (
            "Preferred alternate: same speech moment, clean status passed, and "
            "stream resolution observed; reuse rights and source lineage still "
            "require review."
        )
    if selected_alternate is not None:
        return (
            "Another candidate meets the same-moment, clean-status, and observed-"
            "resolution checks; this row is a comparator."
        )
    if anchor is None:
        return "No official video anchor recorded; manual review required."
    if candidate is anchor:
        if _has_observed_embedded_graphics(anchor):
            return (
                "Use White House YouTube event anchor for identity; embedded "
                "graphics reported, not a clean editing source."
            )
        if str(anchor.get("clean_source_status", "")).casefold() == "failed":
            return (
                "Use White House YouTube event anchor for identity; it failed "
                "the clean-source check and is not a clean editing source."
            )
        return (
            "Use White House YouTube event anchor for identity; cleanliness is "
            "unverified, do not call it clean."
        )
    return "No suitable alternate verified; this row remains a review lead."


def _candidate_review_rows(catalog: dict[str, Any]) -> list[list[Any]]:
    rows = []
    for event in catalog["events"]:
        identity = event.get("identity") or {}
        event_title = identity.get("title", "")
        event_id = event.get("event_id") or ""
        official_reference = event.get("official_reference") or {}
        official_duration = _positive_duration(
            official_reference.get("duration_seconds")
        )
        sources = [
            source
            for source in event.get("sources") or []
            if isinstance(source, dict)
            and isinstance(source.get("url"), str)
            and source.get("url")
            and (
                source.get("source_role") == "official_event_anchor"
                or str(source.get("source_role", "")).startswith("same_event_")
            )
        ]
        anchor = next(
            (source for source in sources if source.get("source_role") == "official_event_anchor"),
            None,
        )
        ordered = sorted(
            sources,
            key=lambda source: _candidate_order(source, official_duration),
        )
        selected_alternate = next(
            (
                source
                for source in ordered
                if source is not anchor
                and source.get("match_status") == "same_speech_moment_observed"
                and source.get("clean_source_status") == "passed"
                and _video_resolution_pixels(source.get("video_resolution"))
                is not None
            ),
            None,
        )
        for rank, source in enumerate(ordered[:10], start=1):
            duration = _positive_duration(source.get("duration_seconds"))
            duration_delta = (
                round(abs(duration - official_duration), 3)
                if duration is not None and official_duration is not None
                else ""
            )
            rows.append(
                [
                    event_id,
                    event_title,
                    rank,
                    _candidate_path(source, anchor, selected_alternate),
                    source.get("publisher", ""),
                    source.get("title", ""),
                    source.get("url", ""),
                    source.get("match_status", "unverified"),
                    source.get("clean_source_status", "unverified"),
                    source.get("video_resolution", "unknown"),
                    source.get("duration_seconds")
                    if source.get("duration_seconds") is not None
                    else "",
                    duration_delta,
                    source.get("independence_status", "unverified"),
                    source.get(
                        "graphics_occlusion_status",
                        source.get("frame_review_status", "pending_direct_frame_review"),
                    ),
                    source.get("reuse_rights_status", "pending_rights_review"),
                    source.get("user_claims_verbatim")
                    or source.get("user_observations_verbatim", ""),
                    source.get("user_rating", ""),
                    source.get("user_feature_rating", ""),
                    source.get("user_angle_opinion_verbatim", ""),
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    source.get("repeat_or_static_scene_review", "pending_direct_frame_review"),
                    source.get("credibility_review", "pending_source_review"),
                    source.get("camera_independence_status", "pending_source_lineage_review"),
                    source.get(
                        "comparison_with_other_user_leads",
                        "pending_exact_event_angle_and_lineage_confirmation",
                    ),
                    source.get("evidence", ""),
                ]
            )
    for lead in catalog.get("unassigned_video_leads", []):
        if not isinstance(lead, dict) or not lead.get("url"):
            continue
        camera = lead.get("camera_position_review") or {}
        rows.append(
            [
                "",
                "Unassigned video lead (event match pending)",
                "pending",
                "Unassigned lead only; do not compare or substitute until the "
                "exact event and time are independently matched. Do not mix with "
                "the October 13 Katie event absent that match.",
                lead.get("publisher", "not reviewed"),
                lead.get("title", "User-provided video lead; title not reviewed"),
                lead.get("url", ""),
                lead.get("event_match_status", "pending_manual_review"),
                lead.get("clean_source_status", "unverified"),
                lead.get("video_resolution", "unknown"),
                lead.get("duration_seconds")
                if lead.get("duration_seconds") is not None
                else "",
                "",
                lead.get(
                    "provenance_independence_status",
                    "pending_source_provenance_review",
                ),
                lead.get(
                    "graphics_occlusion_status", "pending_direct_frame_review"
                ),
                lead.get("reuse_rights_status", "pending_rights_review"),
                lead.get("user_claims_verbatim")
                or lead.get("user_observations_verbatim", ""),
                lead.get("user_rating", ""),
                lead.get("user_feature_rating", ""),
                lead.get("user_angle_opinion_verbatim", ""),
                camera.get("event_time_match_status", "pending_exact_event_and_time_match"),
                camera.get("location", "unknown"),
                camera.get("coordinates_wgs84", "unknown"),
                camera.get("azimuth_degrees", "unknown"),
                camera.get("height_meters", "unknown"),
                camera.get("pitch_degrees", "unknown"),
                camera.get("equipment", "unknown"),
                camera.get("media_camera_department", "unknown"),
                camera.get("publicly_confirmed_crew", "unknown"),
                camera.get("media_seat_annotation", "pending_verified_position"),
                camera.get("evidence_url") or "",
                camera.get("method", "not_assessed"),
                camera.get("uncertainty_or_error", "unknown"),
                camera.get("confidence", "unknown"),
                camera.get("verification_status", "pending"),
                lead.get("repeat_or_static_scene_review", "pending_direct_frame_review"),
                lead.get("credibility_review", "pending_source_review"),
                lead.get("camera_independence_status", "pending_source_lineage_review"),
                lead.get(
                    "comparison_with_other_user_leads",
                    "pending_exact_event_angle_and_lineage_confirmation",
                ),
                lead.get("evidence", "Evidence not yet reviewed."),
            ]
        )
    return rows


def published_at_utc(timestamp: Any) -> str | None:
    if not isinstance(timestamp, (int, float)) or isinstance(timestamp, bool):
        return None
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(
        timespec="seconds"
    )


def load_catalog(path: Path) -> dict[str, Any]:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(catalog, dict) or not isinstance(catalog.get("events"), list):
        raise ValueError("Event catalog must contain an events list.")
    if not catalog.get("matching_rule"):
        raise ValueError("Event catalog is missing its event-matching rule.")
    return catalog


def load_source_registry(path: Path) -> dict[str, Any]:
    registry = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or not isinstance(registry.get("sources"), list):
        raise ValueError("Source registry must contain a sources list.")
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    for source in registry["sources"]:
        if not isinstance(source, dict):
            raise ValueError("Each source registry row must be an object.")
        source_id = source.get("source_id")
        url = source.get("url")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("Each source registry row needs a source_id.")
        if source_id in seen_ids:
            raise ValueError(f"Duplicate source_id: {source_id}")
        parsed_url = urlparse(url) if isinstance(url, str) else None
        if (
            parsed_url is None
            or parsed_url.scheme != "https"
            or not parsed_url.netloc
        ):
            raise ValueError(f"Source {source_id} must have an HTTPS URL.")
        if url in seen_urls:
            raise ValueError(f"Duplicate source URL: {url}")
        seen_ids.add(source_id)
        seen_urls.add(url)
    return registry


def style_sheet(sheet, widths: list[int]) -> None:
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.row_dimensions[1].height = 34
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="17324D")
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width


def build_workbook(
    catalog: dict[str, Any],
    output: Path,
    discovery: dict[str, Any] | None = None,
    source_registry: dict[str, Any] | None = None,
    gdelt_discovery: dict[str, Any] | None = None,
) -> None:
    workbook = Workbook()
    events_sheet = workbook.active
    events_sheet.title = "Events"
    events_sheet.append(EVENT_HEADERS + EVENT_TRACKING_HEADERS)
    sources_sheet = workbook.create_sheet("Sources")
    sources_sheet.append(SOURCE_HEADERS)
    source_directory_sheet = workbook.create_sheet("Source Directory")
    source_directory_sheet.append(SOURCE_DIRECTORY_HEADERS)
    candidate_review_sheet = workbook.create_sheet("Candidate Review")
    candidate_review_sheet.append(VIDEO_CANDIDATE_HEADERS)
    notes_sheet = workbook.create_sheet("Read me")
    instructions_sheet = workbook.create_sheet("User Instructions")
    instructions_sheet.append(["Item", "User-provided text (verbatim)"])
    registry = source_registry or {}
    for label, key in (
        ("Source-list request", "user_source_list_instruction_verbatim"),
        ("Terminology", "user_terminology_verbatim"),
        ("Terminology clarification", "user_terminology_clarification_verbatim"),
        ("Terminology correction", "user_terminology_correction_verbatim"),
        ("Permission to expand fields", "user_field_expansion_permission_verbatim"),
        ("Additional sources may be proposed", "user_additional_source_request_verbatim"),
    ):
        if registry.get(key):
            instructions_sheet.append([label, registry[key]])

    for event in catalog["events"]:
        identity = event.get("identity") or {}
        sources = event.get("sources") or []
        event_title = identity.get("title", "")
        event_id = event.get("event_id") or ""
        official = event.get("official_reference") or {}
        verified_same_time = sum(
            source.get("match_status") == "same_speech_moment_observed"
            and source.get("clean_source_status") == "passed"
            for source in sources
        )
        events_sheet.append(
            [
                event_id,
                event.get("identity_status", ""),
                event_title,
                identity.get("event_date") or "",
                identity.get("event_time_local") or "",
                identity.get("timezone") or "",
                identity.get("location") or "",
                identity.get("event_type") or "",
                ", ".join(identity.get("participants") or []),
                official.get("video_url", ""),
                len(sources),
                verified_same_time,
                identity.get("notes", ""),
            ]
        )
        event_notes = event.get("operator_notes") or []
        user_annotations = event.get("user_source_annotations") or []
        user_source_links = event.get("user_source_links") or []
        user_links = [
            annotation.get("url", "")
            for annotation in user_source_links
            if isinstance(annotation, dict) and annotation.get("url")
        ]
        annotation_text = "\n".join(
            annotation.get("annotation_verbatim") or ""
            for annotation in user_annotations
            if isinstance(annotation, dict)
        )
        event_facts = event.get("verified_facts") or {}
        topics = event_facts.get("topics") or []
        if isinstance(topics, str):
            topics_text = topics
        else:
            topics_text = ", ".join(str(topic) for topic in topics)
        source_search = event.get("source_search") or {}
        facts = [
            event_facts.get("attendance_duration_minutes")
            if event_facts.get("attendance_duration_minutes") is not None
            else "",
            event_facts.get("speech_word_count")
            if event_facts.get("speech_word_count") is not None
            else "",
            topics_text,
            event.get("first_discovered_utc") or "",
            event.get("last_verified_utc")
            or source_search.get("checked_at")
            or "",
            sum(source.get("match_status", "").startswith("same_") for source in sources),
            event.get("confidence") or "unverified",
            "\n".join(user_links),
            annotation_text,
            "\n".join(str(note) for note in event_notes),
        ]
        for column, value in enumerate(facts, start=len(EVENT_HEADERS) + 1):
            events_sheet.cell(events_sheet.max_row, column, value)
        for source in sources:
            sources_sheet.append(
                [
                    event_id,
                    event_title,
                    source.get("publisher", ""),
                    source.get("title", ""),
                    source.get("url", ""),
                    source.get("source_role", ""),
                    source.get("match_status", ""),
                    published_at_utc(source.get("published_timestamp_unix")) or "",
                    source.get("page_published_local", ""),
                    source.get("duration_seconds")
                    if source.get("duration_seconds") is not None
                    else "",
                    source.get("thumbnail_resolution", ""),
                    source.get("video_resolution", "unknown"),
                    source.get("frame_review_status", "not_inspected"),
                    source.get("clean_source_status", "unverified"),
                    source.get("independence_status", "unverified"),
                    source.get("evidence", ""),
                ]
            )
            link_cell = sources_sheet.cell(sources_sheet.max_row, 5)
            if link_cell.value:
                link_cell.hyperlink = link_cell.value
                link_cell.style = "Hyperlink"

    for source in (source_registry or {}).get("sources", []):
        source_directory_sheet.append(
            [
                source.get("source_id", ""),
                source.get("category", ""),
                source.get("name", ""),
                source.get("url", ""),
                source.get("enabled", False),
                source.get("collection_mode", "manual_review"),
                source.get("frequency", ""),
                source.get("last_attempt_utc") or "",
                source.get("last_result", "not_run"),
                source.get("access_status", "not_independently_checked"),
                source.get("added_by", ""),
                source.get("notes", ""),
                source.get("last_run_url", ""),
                source.get("user_provided_url_verbatim")
                or (
                    source.get("url", "")
                    if source.get("added_by") == "user"
                    else ""
                ),
                source.get("user_source_annotation_verbatim", ""),
            ]
        )
        link_cell = source_directory_sheet.cell(source_directory_sheet.max_row, 4)
        if link_cell.value:
            link_cell.hyperlink = link_cell.value
            link_cell.style = "Hyperlink"
        run_link_cell = source_directory_sheet.cell(source_directory_sheet.max_row, 13)
        if run_link_cell.value:
            run_link_cell.hyperlink = run_link_cell.value
            run_link_cell.style = "Hyperlink"

    notes_sheet.append(["Evidence handling"])
    notes_sheet.append(
        [
            "This workbook distinguishes event time from publisher upload metadata. "
            "A published timestamp is never used to fill an unknown event date/time."
        ]
    )
    notes_sheet.append(
        [
            "President attendance minutes, speech word counts, topics and personal "
            "annotations are left blank unless supported by cited event evidence. "
            "Do not infer them from page titles, upload time, prediction markets, "
            "or estimated video duration."
        ]
    )
    notes_sheet.append(
        [
            "The Source Directory is the editable registry. To preserve manual "
            "spreadsheet additions, commit the edited workbook; the scheduled "
            "workflow imports this sheet before rebuilding it. Only sources with "
            "an implemented connector are automatically collected."
        ]
    )
    notes_sheet.append(
        [
            "The user clarified that “为御注” refers to links personally mentioned "
            "by the user and the user's own session annotations/explanations, not "
            "annotations by a leader. The User Instructions sheet preserves the "
            "verbatim text. No per-source annotation is inferred where none exists."
        ]
    )
    notes_sheet.append(
        [
            "Search-result titles, durations, and thumbnail dimensions are leads "
            "only. They do not verify moving-frame content, stream resolution, "
            "clean graphics, same-time matching, continuity, or camera position."
        ]
    )
    notes_sheet.append(
        [
            "Only rows with direct frame/audio/time evidence should be accepted as "
            "same-event footage. Check reuse rights and source terms before "
            "rehosting or publishing any video."
        ]
    )
    notes_sheet.append(
        [
            "Candidate Review contains up to ten existing video-source rows per "
            "event. Queue order is same-event evidence, clean status, observed "
            "stream resolution, duration closeness to the official runtime, then "
            "publisher/URL for stable ties. It is not a trust score; unknown "
            "resolution is not inferred from thumbnails, and rows are never "
            "invented to fill the limit. An alternate is selected only when the "
            "same speech moment, clean status, and observed stream resolution are "
            "all explicitly recorded. Otherwise the White House YouTube anchor "
            "remains the identity reference and is not called clean."
        ]
    )
    notes_sheet.append(
        [
            "User-submitted video leads without an exact event/time match appear "
            "as unassigned rows. User claims and subjective ratings are not "
            "verification. Camera location, coordinates, azimuth, height, pitch, "
            "equipment, department, publicly confirmed crew, and media-seat "
            "annotations require direct evidence, method, uncertainty, confidence, "
            "and a verification status; unknowns remain unknown. Do not infer "
            "private identities or mix an unassigned lead into a named event."
        ]
    )
    notes_sheet.append(
        [
            "Do not rank a source as superior based on runtime alone. Assess "
            "repeated/static scenes, embedded logos/banners, actual stream "
            "resolution, exact event/time match, source credibility, independent "
            "camera status, and source lineage separately. Comparing two "
            "user-submitted links requires first confirming the same event/time "
            "and then checking angle and lineage; neither same-event nor "
            "different-angle status is assumed."
        ]
    )
    for row in _candidate_review_rows(catalog):
        candidate_review_sheet.append(row)
        link_cell = candidate_review_sheet.cell(candidate_review_sheet.max_row, 7)
        if link_cell.value:
            link_cell.hyperlink = link_cell.value
            link_cell.style = "Hyperlink"
    if discovery is not None:
        discovery_sheet = workbook.create_sheet("New White House leads")
        discovery_sheet.append(
            [
                "Video ID",
                "Title",
                "Publisher",
                "URL",
                "Published metadata (UTC; not event time)",
                "Upload date metadata",
                "Duration (seconds)",
                "Event ID",
                "Assignment status",
                "Evidence status",
                "Verified event date",
                "Verified event local time / timezone",
                "Verified location",
                "President attendance duration (minutes; verified)",
                "Speech word count (verified; language/method)",
                "Topics (source-backed)",
                "First discovered UTC",
                "Last event verification UTC",
                "Page/source count (not corroboration)",
                "Confidence",
                "User annotation / explanation tied to source",
            ]
        )
        for lead in discovery.get("leads", []):
            discovery_sheet.append(
                [
                    lead.get("video_id", ""),
                    lead.get("title", ""),
                    lead.get("publisher", ""),
                    lead.get("url", ""),
                    published_at_utc(lead.get("published_timestamp_unix")) or "",
                    lead.get("upload_date_metadata") or "",
                    lead.get("duration_seconds")
                    if lead.get("duration_seconds") is not None
                    else "",
                    lead.get("event_id") or "",
                    lead.get("assignment_status", ""),
                    lead.get("evidence_status", ""),
                    lead.get("event_date") or "",
                    (
                        f"{lead.get('event_time_local')} {lead.get('timezone') or ''}".strip()
                        if lead.get("event_time_local")
                        else ""
                    ),
                    lead.get("location") or "",
                    lead.get("attendance_duration_minutes") or "",
                    lead.get("speech_word_count") or "",
                    ", ".join(lead.get("topics") or []),
                    lead.get("first_discovered_utc")
                    or discovery.get("checked_at_utc")
                    or "",
                    lead.get("last_event_verified_utc") or "",
                    1,
                    lead.get("confidence") or "low: metadata-only",
                    lead.get("user_source_annotation_verbatim") or "",
                ]
            )
            link_cell = discovery_sheet.cell(discovery_sheet.max_row, 4)
            if link_cell.value:
                link_cell.hyperlink = link_cell.value
                link_cell.style = "Hyperlink"
        style_sheet(
            discovery_sheet,
            [18, 58, 30, 58, 36, 24, 20, 28, 30, 22, 18, 32, 42, 40, 42, 40, 28, 28, 30, 24, 72],
        )
    if gdelt_discovery is not None:
        news_sheet = workbook.create_sheet("GDELT Article Leads")
        news_sheet.append(
            [
                "Title",
                "Publisher domain",
                "Article URL",
                "Article seen date UTC (metadata; not event time)",
                "Language",
                "Source country",
                "Event ID",
                "Assignment status",
                "Evidence status",
                "First discovered UTC",
                "Source/search limitations",
            ]
        )
        for lead in gdelt_discovery.get("leads", []):
            news_sheet.append(
                [
                    lead.get("title", ""),
                    lead.get("publisher", ""),
                    lead.get("url", ""),
                    lead.get("seen_date_utc_metadata", ""),
                    lead.get("language", ""),
                    lead.get("source_country", ""),
                    lead.get("event_id") or "",
                    lead.get("assignment_status", ""),
                    lead.get("evidence_status", ""),
                    gdelt_discovery.get("checked_at_utc", ""),
                    "Article metadata only; title/date do not verify event occurrence, attendance, speech, or topic.",
                ]
            )
            link_cell = news_sheet.cell(news_sheet.max_row, 3)
            if link_cell.value:
                link_cell.hyperlink = link_cell.value
                link_cell.style = "Hyperlink"
        style_sheet(news_sheet, [64, 32, 76, 38, 20, 20, 28, 32, 28, 28, 72])
    style_sheet(
        source_directory_sheet,
        [28, 24, 42, 74, 14, 24, 18, 28, 24, 30, 18, 84, 74, 74, 82],
    )
    style_sheet(
        candidate_review_sheet,
        [
            28, 46, 24, 72, 28, 64, 70, 40, 22, 48, 20, 38, 42, 36, 28, 58,
            32, 24, 58, 40, 42, 28, 24, 24, 24, 24, 30, 30, 38, 34, 70, 28, 34,
            24, 30, 38, 30, 30, 44, 100,
        ],
    )
    style_sheet(instructions_sheet, [40, 150])
    notes_sheet["A1"].font = Font(bold=True, color="FFFFFF")
    notes_sheet["A1"].fill = PatternFill("solid", fgColor="17324D")
    notes_sheet.column_dimensions["A"].width = 120
    for row in notes_sheet.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    style_sheet(
        events_sheet,
        [28, 22, 46, 16, 18, 16, 42, 24, 26, 50, 14, 24, 74,
         38, 42, 40, 28, 28, 26, 18, 62, 72, 54],
    )
    style_sheet(
        sources_sheet,
        [28, 46, 26, 56, 60, 28, 38, 34, 36, 20, 36, 24, 20, 22, 32, 80],
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--discovery",
        type=Path,
        help="Optional JSON from discover_whitehouse_events.py.",
    )
    parser.add_argument(
        "--source-registry",
        type=Path,
        help="Optional editable source-directory JSON; the workbook sheet remains the human-facing registry.",
    )
    parser.add_argument(
        "--gdelt-discovery",
        type=Path,
        help="Optional JSON from discover_gdelt_articles.py.",
    )
    args = parser.parse_args()
    discovery = (
        json.loads(args.discovery.read_text(encoding="utf-8"))
        if args.discovery
        else None
    )
    source_registry = (
        load_source_registry(args.source_registry)
        if args.source_registry
        else None
    )
    gdelt_discovery = (
        json.loads(args.gdelt_discovery.read_text(encoding="utf-8"))
        if args.gdelt_discovery
        else None
    )
    build_workbook(
        load_catalog(args.catalog),
        args.output,
        discovery,
        source_registry,
        gdelt_discovery,
    )
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
