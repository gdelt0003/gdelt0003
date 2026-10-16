"""Poll the configured White House channel and record safe per-video research status."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from scripts.discover_gdelt_articles import API_URL as GDELT_API_URL
from scripts.discover_gdelt_articles import fetch_articles, normalize_articles


CHANNEL_URL = "https://www.youtube.com/@WhiteHouse/videos"
VIDEO_URL_TEMPLATE = "https://www.youtube.com/watch?v={video_id}"
VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")
STATE_SCHEMA_VERSION = 1
PAGE_TIMEOUT_SECONDS = 20
PAGE_READ_LIMIT_BYTES = 2 * 1024 * 1024
GDELT_MAX_RECORDS_PER_VIDEO = 10
GDELT_TIMESPAN = "1w"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def video_url(video_id: str) -> str:
    if not VIDEO_ID_PATTERN.fullmatch(video_id):
        raise ValueError(f"Invalid YouTube video ID: {video_id!r}")
    return VIDEO_URL_TEMPLATE.format(video_id=video_id)


class _OpenGraphMetadata(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "meta":
            key = attributes.get("property") or attributes.get("name")
            value = attributes.get("content")
            if key in {"og:title", "og:description"} and value:
                self.values[key] = value.strip()
        elif tag == "link" and attributes.get("rel") == "canonical":
            href = attributes.get("href")
            if href:
                self.values["canonical_url"] = href


def research_official_video_page(
    video_id: str, researched_at_utc: str
) -> dict[str, Any]:
    """Read only the official watch page HTML; never request video or media streams."""
    url = video_url(video_id)
    request = Request(
        url,
        headers={"User-Agent": "gdelt0003-official-video-metadata-monitor/1.0"},
    )
    with urlopen(request, timeout=PAGE_TIMEOUT_SECONDS) as response:
        final_url = response.geturl()
        parsed_final_url = urlparse(final_url)
        if (
            parsed_final_url.scheme != "https"
            or not parsed_final_url.hostname
            or not (
                parsed_final_url.hostname == "youtube.com"
                or parsed_final_url.hostname.endswith(".youtube.com")
            )
        ):
            raise ValueError("Official video page redirected outside HTTPS YouTube.")
        body = response.read(PAGE_READ_LIMIT_BYTES)
        metadata = _OpenGraphMetadata()
        metadata.feed(body.decode("utf-8", errors="replace"))
        title = metadata.values.get("og:title")
        canonical_url = metadata.values.get("canonical_url")
        result = {
            "status": "completed" if title or canonical_url else "incomplete",
            "requested_url": url,
            "final_url": final_url,
            "http_status": response.status,
            "researched_at_utc": researched_at_utc,
            "research_scope": "official watch-page HTML metadata only",
            "page_title": title,
            "page_description": metadata.values.get("og:description"),
            "canonical_url": canonical_url,
        }
        if result["status"] == "incomplete":
            result["error"] = "Page returned no recognized title or canonical URL metadata."
        return result


def research_related_source_metadata(title: str, researched_at_utc: str) -> dict[str, Any]:
    """Search the configured GDELT metadata source; results remain unverified leads."""
    query_title = " ".join(title.split()).replace('"', "")[:180]
    if not query_title:
        return {
            "status": "blocked_missing_official_title",
            "api_url": GDELT_API_URL,
            "query": None,
            "researched_at_utc": researched_at_utc,
            "research_scope": "GDELT article metadata search only",
            "candidate_count": 0,
            "candidates": [],
            "error": "Official upload metadata provided no title for a source search.",
        }

    query = f'"{query_title}"'
    try:
        payload = fetch_articles(query, GDELT_MAX_RECORDS_PER_VIDEO, GDELT_TIMESPAN)
        articles = payload.get("articles") if isinstance(payload, dict) else None
        if not isinstance(articles, list):
            raise ValueError("GDELT metadata response must contain an articles list.")
        candidates = (
            normalize_articles(payload, researched_at_utc)["leads"] if articles else []
        )
        return {
            "status": "completed_with_candidates" if candidates else "completed_no_results",
            "api_url": GDELT_API_URL,
            "query": query,
            "timespan": GDELT_TIMESPAN,
            "max_records": GDELT_MAX_RECORDS_PER_VIDEO,
            "researched_at_utc": researched_at_utc,
            "research_scope": "GDELT article metadata search only; candidates are unverified leads",
            "candidate_count": len(candidates),
            "candidates": candidates,
        }
    except (OSError, RuntimeError, TimeoutError, ValueError) as error:
        return {
            "status": "failed",
            "api_url": GDELT_API_URL,
            "query": query,
            "timespan": GDELT_TIMESPAN,
            "researched_at_utc": researched_at_utc,
            "research_scope": "GDELT article metadata search only",
            "candidate_count": 0,
            "candidates": [],
            "error": str(error),
        }


def empty_state() -> dict[str, Any]:
    return {"schema_version": STATE_SCHEMA_VERSION, "videos": {}, "last_run": None}


def validate_state(state: Any) -> dict[str, Any]:
    if (
        not isinstance(state, dict)
        or state.get("schema_version") != STATE_SCHEMA_VERSION
        or not isinstance(state.get("videos"), dict)
    ):
        raise ValueError("Monitoring state must be a version 1 object with a videos map.")
    for video_id, record in state["videos"].items():
        if not VIDEO_ID_PATTERN.fullmatch(video_id) or not isinstance(record, dict):
            raise ValueError("Monitoring state contains an invalid video record.")
    state.setdefault("last_run", None)
    return state


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_state()
    try:
        return validate_state(json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as error:
        raise ValueError(f"Monitoring state is not valid JSON: {path}") from error


def discover_channel(yt_dlp: str, limit: int) -> dict[str, Any]:
    result = subprocess.run(
        [
            yt_dlp,
            "--dump-single-json",
            "--flat-playlist",
            "--playlist-end",
            str(limit),
            "--js-runtimes",
            "node",
            "--no-warnings",
            CHANNEL_URL,
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise RuntimeError(
            f"Channel metadata collector failed ({result.returncode}): "
            f"{result.stderr.strip()}"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("Channel metadata collector returned invalid JSON.") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        raise ValueError("Channel metadata response must contain an entries list.")
    return payload


def record_new_video(
    entry: dict[str, Any],
    *,
    metadata_started_at_utc: str,
    metadata_completed_at_utc: str,
    run_id: str,
    run_url: str,
    page_researcher: Callable[[str, str], dict[str, Any]],
    source_researcher: Callable[[str, str], dict[str, Any]],
) -> dict[str, Any]:
    video_id = entry["id"]
    title = entry.get("title")
    if not isinstance(title, str):
        title = ""
    official_url = video_url(video_id)
    event_source_research_started_at_utc = utc_now()
    official_page_started_at_utc = event_source_research_started_at_utc
    try:
        page_research = page_researcher(video_id, official_page_started_at_utc)
    except (OSError, TimeoutError, URLError, ValueError) as error:
        page_research = {
            "status": "failed",
            "requested_url": official_url,
            "researched_at_utc": official_page_started_at_utc,
            "research_scope": "official watch-page HTML metadata only",
            "error": str(error),
        }

    additional_source_search_started_at_utc = utc_now()
    source_search = source_researcher(title, additional_source_search_started_at_utc)
    source_research_completed_at_utc = utc_now()
    if source_search["status"] == "completed_with_candidates":
        source_research_status = "completed_with_unverified_leads"
    elif source_search["status"] == "completed_no_results":
        source_research_status = "completed_metadata_search_no_candidates"
    elif source_search["status"] == "blocked_missing_official_title":
        source_research_status = "completed_with_missing_query_terms"
    else:
        source_research_status = "completed_with_search_failure"
    source_research_missing_items = [
        "any GDELT article-metadata candidates remain unverified leads; independent source pages and candidate footage have not been opened or inspected",
        "event date, local time/timezone, location, event type, and participants remain unverified; upload timestamps are not event time",
        "no configured source provides source-specific reuse-rights evidence; rights have not been established or reviewed",
    ]
    if page_research["status"] != "completed":
        source_research_missing_items.insert(
            0, "successful official video watch-page metadata retrieval"
        )
    if source_search["status"] not in {"completed_with_candidates", "completed_no_results"}:
        source_research_missing_items.insert(
            0, "successful GDELT additional-source metadata search"
        )
    media_review_missing_items = [
        f"explicit processing authorization naming video ID {video_id}",
        "source-specific reuse-rights evidence and confirmation; the polling request does not grant reuse rights",
        "verified event identity and same-event/source match",
        "direct frame/audio inspection on an authorized GitHub-hosted runner",
    ]

    return {
        "video_id": video_id,
        "title": title,
        "publisher": entry.get("channel") or entry.get("uploader") or "The White House",
        "official_video_url": official_url,
        "official_channel_url": CHANNEL_URL,
        "published_timestamp_unix": entry.get("timestamp"),
        "upload_date_metadata": entry.get("upload_date"),
        "duration_seconds": entry.get("duration"),
        "metadata_discovery": {
            "started_status": "metadata_discovery_started",
            "status": "metadata_discovery_completed",
            "started_at_utc": metadata_started_at_utc,
            "completed_at_utc": metadata_completed_at_utc,
            "source_url": CHANNEL_URL,
            "run_id": run_id,
            "run_url": run_url,
        },
        "official_source_page_research": page_research,
        "event_source_research": {
            "status": source_research_status,
            "started_at_utc": event_source_research_started_at_utc,
            "completed_at_utc": source_research_completed_at_utc,
            "run_id": run_id,
            "run_url": run_url,
            "official_page_research_status": page_research["status"],
            "additional_source_search": source_search,
            "additional_source_search_started_at_utc": additional_source_search_started_at_utc,
            "missing_items": source_research_missing_items,
            "event_identity_status": "unassigned_event_lead",
            "event_identity_evidence_gaps": [
                "event date",
                "local event time and timezone or stated day-level precision",
                "location",
                "event type/title confirmation",
                "participant confirmation",
            ],
            "reuse_rights_research_status": "not_attempted_no_configured_evidence_source",
            "reuse_rights_research_blocker": (
                "No configured source provides source-specific reuse-rights evidence; "
                "public availability and GDELT article metadata do not establish rights."
            ),
            "reuse_rights_evidence_urls": [],
        },
        "media_review_gate": {
            "status": "not_started_blocked_waiting_for_authorization_and_rights",
            "blocked_at_utc": metadata_completed_at_utc,
            "run_id": run_id,
            "run_url": run_url,
            "missing_items": media_review_missing_items,
            "media_inspection_status": "blocked_not_attempted",
            "authorization_status": "not_provided_for_this_video",
            "reuse_rights_status": "unknown_not_inferred",
            "publication_status": "not_published",
        },
    }


def format_run_summary(run: dict[str, Any]) -> str:
    lines = [
        "## Official White House video monitor",
        "",
        f"- Poll status: **{run['status']}**",
        f"- Actual poll start (UTC): `{run['started_at_utc']}`",
        f"- Trigger: `{run['trigger']}`; scheduled cadence: every 5 minutes.",
        "- GitHub Actions may queue or delay scheduled runs; this timestamp is the actual run start, not a guaranteed poll time.",
        f"- Provenance: {run['run_url']}",
        f"- Metadata discovery: {run.get('metadata_discovery_status', 'not_started')}",
        f"- New videos: {len(run.get('new_video_ids', []))}; previously seen: {len(run.get('already_seen_video_ids', []))}.",
        "- Notices below are limited to this Actions run's summary and warning annotations; no external push notification is configured.",
        "",
    ]
    if run.get("error"):
        lines.extend(("- Collector failed; inspect the linked Actions run for details.", ""))
    for video_id in run.get("new_video_ids", []):
        record = run["video_records"][video_id]
        event_research = record["event_source_research"]
        source_search = event_research["additional_source_search"]
        media_review = record["media_review_gate"]
        lines.extend(
            (
                f"### Research notice: {video_id}",
                "",
                f"- Official source: {record['official_video_url']}",
                f"- Metadata discovery: **{record['metadata_discovery']['status']}**.",
                "- Official source-page metadata: "
                f"**{record['official_source_page_research']['status']}**.",
                f"- Event/source metadata research: **{event_research['status']}**.",
                f"- GDELT source search: **{source_search['status']}**; "
                f"{source_search['candidate_count']} unverified candidate(s).",
                "- This is source-metadata research only; full event/source research is not complete.",
                "- Event identity and reuse rights: **unverified**; no identity or rights are inferred from metadata.",
                "- Remaining event/source research gaps:",
            )
        )
        lines.extend(f"  - {item}" for item in event_research["missing_items"])
        if source_search.get("error"):
            detail = (
                str(source_search["error"])
                .replace("`", "\\`")
                .replace("\n", " ")
                .replace("\r", " ")
            )
            lines.append(f"- GDELT search detail: `{detail}`.")
        lines.append("- Media review: **not started; blocked pending exact-video authorization and reuse-rights evidence**.")
        lines.extend(f"  - {item}" for item in media_review["missing_items"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def format_warning_annotations(run: dict[str, Any]) -> list[str]:
    annotations = []
    if run.get("status") == "failure":
        error = str(run.get("error", "Unknown metadata collection failure"))
        message = error.replace("%", "%25").replace("\n", "%0A").replace("\r", "%0D")
        annotations.append(
            f"::error title=Official video metadata discovery failed::{message}"
        )
    for video_id in run.get("new_video_ids", []):
        record = run["video_records"][video_id]
        missing_items = [
            *record["event_source_research"]["missing_items"],
            *record["media_review_gate"]["missing_items"],
        ]
        for item in missing_items:
            message = (
                f"Video {video_id}: {item}"
                .replace("%", "%25")
                .replace("\n", "%0A")
                .replace("\r", "%0D")
            )
            annotations.append(f"::warning title=Research blocker (source or media review)::{message}")
    return annotations


def run_monitor(
    *,
    state: dict[str, Any],
    run_id: str,
    run_url: str,
    trigger: str,
    poller: Callable[[], dict[str, Any]],
    page_researcher: Callable[[str, str], dict[str, Any]],
    source_researcher: Callable[[str, str], dict[str, Any]],
    started_at_utc: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = validate_state(state)
    videos = state["videos"]
    run: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "run_url": run_url,
        "trigger": trigger,
        "scheduled_cadence_minutes": 5,
        "queue_delay_note": (
            "GitHub Actions schedule timing is best-effort; actual start may be delayed."
        ),
        "started_at_utc": started_at_utc,
        "source_url": CHANNEL_URL,
        "status": "success",
        "metadata_discovery_status": "metadata_discovery_started",
        "new_video_ids": [],
        "already_seen_video_ids": [],
        "invalid_entry_count": 0,
        "video_records": {},
    }

    metadata_completed_at_utc = started_at_utc
    try:
        payload = poller()
        entries = payload.get("entries") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            raise ValueError("Channel metadata response must contain an entries list.")
        if not entries:
            raise ValueError("White House channel returned no video entries.")
        metadata_completed_at_utc = utc_now()
    except (OSError, RuntimeError, ValueError, URLError, TimeoutError) as error:
        run["status"] = "failure"
        run["metadata_discovery_status"] = "metadata_discovery_failed"
        run["error"] = str(error)
        entries = []

    if run["status"] == "success":
        run["metadata_discovery_status"] = "metadata_discovery_completed"
        run["metadata_discovery_completed_at_utc"] = metadata_completed_at_utc
    new_entries = []
    seen_in_poll = set()
    for entry in entries:
        if not isinstance(entry, dict):
            run["invalid_entry_count"] += 1
            continue
        video_id = entry.get("id")
        if not isinstance(video_id, str) or not VIDEO_ID_PATTERN.fullmatch(video_id):
            run["invalid_entry_count"] += 1
            continue
        if video_id in videos or video_id in seen_in_poll:
            run["already_seen_video_ids"].append(video_id)
            continue
        seen_in_poll.add(video_id)
        new_entries.append(entry)

    def research(entry: dict[str, Any]) -> dict[str, Any]:
        return record_new_video(
            entry,
            metadata_started_at_utc=started_at_utc,
            metadata_completed_at_utc=metadata_completed_at_utc,
            run_id=run_id,
            run_url=run_url,
            page_researcher=page_researcher,
            source_researcher=source_researcher,
        )

    if new_entries:
        with ThreadPoolExecutor(max_workers=min(8, len(new_entries))) as executor:
            records = executor.map(research, new_entries)
            for entry, record in zip(new_entries, records):
                video_id = entry["id"]
                videos[video_id] = record
                run["new_video_ids"].append(video_id)
                run["video_records"][video_id] = record

    run["completed_at_utc"] = utc_now()
    state["last_run"] = {
        "run_id": run_id,
        "run_url": run_url,
        "started_at_utc": started_at_utc,
        "completed_at_utc": run["completed_at_utc"],
        "status": run["status"],
    }
    return state, run


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--run-file", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--trigger", default="schedule")
    parser.add_argument("--yt-dlp", default="yt-dlp")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--summary-file", type=Path)
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 500:
        parser.error("--limit must be between 1 and 500.")
    if not args.run_url.startswith("https://"):
        parser.error("--run-url must be HTTPS.")

    try:
        state = load_state(args.state_file)
        started_at_utc = utc_now()
        updated_state, run = run_monitor(
            state=state,
            run_id=args.run_id,
            run_url=args.run_url,
            trigger=args.trigger,
            poller=lambda: discover_channel(args.yt_dlp, args.limit),
            page_researcher=research_official_video_page,
            source_researcher=research_related_source_metadata,
            started_at_utc=started_at_utc,
        )
        write_json(args.state_file, updated_state)
        write_json(args.run_file, run)
        summary = format_run_summary(run)
        if args.summary_file:
            args.summary_file.parent.mkdir(parents=True, exist_ok=True)
            with args.summary_file.open("a", encoding="utf-8") as output:
                output.write(summary)
        for annotation in format_warning_annotations(run):
            print(annotation)
        print(summary, end="")
        return 0 if run["status"] == "success" else 1
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
