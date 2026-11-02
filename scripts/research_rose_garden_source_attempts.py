"""Attempt each registered Rose Garden source URL and broader public searches."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SOURCE_INVENTORY = ROOT / "config" / "event-discovery-sources.json"
EVENT_ID = "rose-garden-lunch-2026-10-15"
EVENT_TITLE = "President Trump Participates in a Rose Garden Lunch"
EVENT_REFERENCE_VIDEO_ID = "IySF_8OArvw"
EXPECTED_SOURCE_COUNT = 13
USER_AGENT = "gdelt0003-rose-garden-source-attempts/1.0"
TIMEOUT_SECONDS = 15
MAX_RESPONSE_BYTES = 256 * 1024
MAX_RESULTS_PER_QUERY = 10

SEARCH_AVENUES = (
    {
        "id": "media-news",
        "queries": (
            f'"{EVENT_TITLE}" "October 15, 2026"',
            f'"{EVENT_REFERENCE_VIDEO_ID}" "Rose Garden" Trump',
            '"Rose Garden Lunch" Trump "October 15, 2026" video AP Reuters PBS',
            'site:apnews.com OR site:reuters.com OR site:pbs.org "Rose Garden" Trump "October 15, 2026"',
        ),
    },
    {
        "id": "social",
        "queries": (
            'site:x.com "Rose Garden" Trump "October 15, 2026" video',
            'site:truthsocial.com "Rose Garden" Trump "October 15, 2026"',
            'site:youtube.com/watch "Rose Garden Lunch" Trump "October 15, 2026"',
        ),
    },
    {
        "id": "congress",
        "queries": (
            'site:congress.gov OR site:house.gov OR site:senate.gov "Rose Garden" Trump "October 15, 2026"',
            'site:c-span.org "Rose Garden" Trump "October 15, 2026" video',
        ),
    },
    {
        "id": "think-tanks",
        "queries": (
            'site:brookings.edu OR site:heritage.org OR site:aei.org "Rose Garden" Trump "October 15, 2026"',
        ),
    },
    {
        "id": "archives",
        "queries": (
            'site:archive.org/details "Rose Garden" Trump "October 15, 2026"',
            'site:c-span.org/video "Rose Garden" Trump "October 15, 2026"',
        ),
    },
)

GENERAL_LIMITATIONS = (
    "Checks only the listed landing-page URL and bounded HTML metadata; does not execute "
    "JavaScript, authenticate, bypass access controls, crawl linked pages, or establish "
    "complete source coverage. A successful page fetch does not prove event relevance, "
    "accuracy, source credibility, rights, or availability of footage.",
    "Search results are unverified leads only. Search-engine coverage, indexing, ranking, "
    "and query interpretation are unknown and non-exhaustive.",
    "No video, audio, image, stream, or other media was downloaded or inspected. No event "
    "attendance duration, location, spoken-word count, or topic is verified by this report.",
)


class PageMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.description = ""
        self.links: list[dict[str, str]] = []
        self._inside_title = False
        self._active_link: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "title":
            self._inside_title = True
        elif tag == "meta":
            key = (values.get("name") or values.get("property") or "").lower()
            if key in {"description", "og:description", "twitter:description"}:
                self.description = self.description or (values.get("content") or "").strip()
        elif tag == "a":
            href = values.get("href") or ""
            if urllib.parse.urlsplit(href).scheme in {"http", "https"} or href.startswith("/"):
                self._active_link = {"href": href, "text": ""}

    def handle_data(self, data: str) -> None:
        if self._inside_title:
            self.title += data
        if self._active_link is not None:
            self._active_link["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._inside_title = False
        elif tag == "a" and self._active_link is not None:
            self._active_link["text"] = " ".join(self._active_link["text"].split())
            self.links.append(self._active_link)
            self._active_link = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _markdown_escape(value: object) -> str:
    text = str(value)
    return (
        text.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("`", "\\`")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _relevant_to_event(text: str) -> bool:
    normalized = text.casefold()
    return (
        EVENT_REFERENCE_VIDEO_ID.casefold() in normalized
        or ("rose garden" in normalized and ("lunch" in normalized or "trump" in normalized))
        or "2026-10-15" in normalized
        or "october 15, 2026" in normalized
    )


def _read_html(url: str) -> tuple[int, str, str, str, bool, bool, int]:
    request_url, fragment_separator, _fragment = url.partition("#")
    request = urllib.request.Request(
        request_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/xml",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        content_type = response.headers.get_content_type().lower()
        is_html = content_type in {"text/html", "application/xhtml+xml"}
        body = response.read(MAX_RESPONSE_BYTES + 1) if is_html else b""
        truncated = len(body) > MAX_RESPONSE_BYTES
        bytes_read = len(body)
        body = body[:MAX_RESPONSE_BYTES]
        charset = response.headers.get_content_charset() or "utf-8"
        return (
            response.status,
            response.geturl(),
            content_type,
            body.decode(charset, errors="replace"),
            bool(fragment_separator),
            truncated,
            bytes_read,
        )


def _source_attempt(source: dict[str, object]) -> dict[str, object]:
    attempted_at = _utc_now()
    record: dict[str, object] = {
        "source_id": source["source_id"],
        "source_name": source["name"],
        "category": source["category"],
        "url": source["url"],
        "attempted": True,
        "attempted_at_utc": attempted_at,
        "access_status": "not_determined",
        "transport_result": "not_determined",
        "error": None,
        "page_title": None,
        "page_description": None,
        "extracted_candidate_page_urls": [],
        "coverage_limit": (
            "Only this exact landing page and up to "
            f"{MAX_RESPONSE_BYTES} bytes of HTML metadata were checked."
        ),
    }
    try:
        (
            status,
            final_url,
            content_type,
            html,
            had_fragment,
            truncated,
            response_bytes_read,
        ) = _read_html(str(source["url"]))
        record.update(
            {
                "http_status": status,
                "final_url": final_url,
                "request_url": str(source["url"]).split("#", 1)[0],
                "url_fragment_excluded_from_http_request": had_fragment,
                "content_type": content_type,
            }
        )
        if content_type not in {"text/html", "application/xhtml+xml"}:
            record.update(
                {
                    "access_status": "non_html_response",
                    "transport_result": "http_success_non_html",
                    "error": f"Refused non-HTML response content type: {content_type}",
                }
            )
            return record
        parser = PageMetadataParser()
        parser.feed(html)
        event_links = []
        for link in parser.links:
            absolute_url = urllib.parse.urljoin(final_url, link["href"])
            if _relevant_to_event(f"{absolute_url} {link['text']}"):
                event_links.append(
                    {
                        "url": absolute_url,
                        "title_or_anchor_text": link["text"],
                        "discovered_from_url": str(source["url"]),
                        "discovered_at_utc": attempted_at,
                        "lead_status": "unverified_page_link_lead",
                        "event_match": "not_verified",
                        "video_content_review": "not_performed",
                    }
                )
        record.update(
            {
                "response_bytes_read": response_bytes_read,
                "response_truncated": truncated,
                "access_status": "page_accessible",
                "transport_result": "http_success_truncated" if truncated else "http_success",
                "page_title": " ".join(parser.title.split()) or None,
                "page_description": parser.description or None,
                "extracted_candidate_page_urls": event_links,
            }
        )
    except urllib.error.HTTPError as error:
        record.update(
            {
                "http_status": error.code,
                "access_status": "http_error",
                "transport_result": "http_error",
                "error": f"HTTP {error.code}: {error.reason}",
            }
        )
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as error:
        record.update(
            {
                "access_status": "fetch_error",
                "transport_result": "fetch_error",
                "error": str(error),
            }
        )
    return record


def _rss_results(xml_text: str) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    items = [
        element
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1].lower() == "item"
    ]
    results: list[dict[str, str]] = []
    for item in items[:MAX_RESULTS_PER_QUERY]:
        fields = {
            child.tag.rsplit("}", 1)[-1].lower(): "".join(child.itertext()).strip()
            for child in item
        }
        url = fields.get("link", "")
        if urllib.parse.urlsplit(url).scheme not in {"http", "https"}:
            continue
        results.append(
            {
                "url": url,
                "title": " ".join(fields.get("title", "").split()),
                "snippet": " ".join(fields.get("description", "").split()),
            }
        )
    return results


def _search_attempt(avenue: str, query: str) -> tuple[dict[str, object], list[dict[str, object]]]:
    attempted_at = _utc_now()
    search_url = "https://www.bing.com/search?format=rss&" + urllib.parse.urlencode(
        {"q": query}
    )
    record: dict[str, object] = {
        "avenue": avenue,
        "provider": "Bing RSS",
        "query": query,
        "url": search_url,
        "attempted": True,
        "attempted_at_utc": attempted_at,
        "access_status": "not_determined",
        "transport_result": "not_determined",
        "error": None,
        "result_count": 0,
        "candidate_lead_count": 0,
        "coverage_limit": (
            "One query sent to Bing RSS; first "
            f"{MAX_RESULTS_PER_QUERY} results at most. Search indexing is non-exhaustive."
        ),
    }
    leads: list[dict[str, object]] = []
    try:
        request = urllib.request.Request(
            search_url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml,application/xml"},
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            content_type = response.headers.get_content_type().lower()
            if content_type not in {"application/rss+xml", "application/xml", "text/xml"}:
                record.update(
                    {
                        "http_status": response.status,
                        "final_url": response.geturl(),
                        "content_type": content_type,
                        "access_status": "unexpected_content_type",
                        "transport_result": "http_success_unexpected_content_type",
                        "error": f"Refused unexpected search response type: {content_type}",
                    }
                )
                return record, leads
            body = response.read(MAX_RESPONSE_BYTES + 1)
            truncated = len(body) > MAX_RESPONSE_BYTES
            body = body[:MAX_RESPONSE_BYTES]
            charset = response.headers.get_content_charset() or "utf-8"
            results = _rss_results(body.decode(charset, errors="replace"))
            record.update(
                {
                    "http_status": response.status,
                    "final_url": response.geturl(),
                    "content_type": content_type,
                    "response_truncated": truncated,
                    "access_status": "search_accessible",
                    "transport_result": "http_success_truncated" if truncated else "http_success",
                    "result_count": len(results),
                }
            )
            for result in results:
                if not _relevant_to_event(
                    f"{result['url']} {result['title']} {result['snippet']}"
                ):
                    continue
                leads.append(
                    {
                        "url": result["url"],
                        "title": result["title"],
                        "snippet": result["snippet"],
                        "discovered_from_url": response.geturl(),
                        "query": query,
                        "avenue": avenue,
                        "provider": "Bing RSS",
                        "discovered_at_utc": attempted_at,
                        "lead_status": "unverified_search_result_lead",
                        "event_match": "not_verified",
                        "video_content_review": "not_performed",
                    }
                )
            record["candidate_lead_count"] = len(leads)
    except urllib.error.HTTPError as error:
        record.update(
            {
                "http_status": error.code,
                "access_status": "http_error",
                "transport_result": "http_error",
                "error": f"HTTP {error.code}: {error.reason}",
            }
        )
    except (urllib.error.URLError, TimeoutError, ValueError, ET.ParseError, OSError) as error:
        record.update(
            {
                "access_status": "invalid_search_response" if isinstance(error, ET.ParseError) else "fetch_error",
                "transport_result": "invalid_search_response" if isinstance(error, ET.ParseError) else "fetch_error",
                "error": str(error),
            }
        )
    return record, leads


def research(output_dir: Path) -> dict[str, object]:
    inventory = json.loads(SOURCE_INVENTORY.read_text(encoding="utf-8"))
    sources = inventory["sources"]
    source_records = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        source_records.extend(pool.map(_source_attempt, sources))

    query_jobs = [
        (avenue["id"], query)
        for avenue in SEARCH_AVENUES
        for query in avenue["queries"]
    ]
    with ThreadPoolExecutor(max_workers=5) as pool:
        search_results = list(pool.map(lambda job: _search_attempt(*job), query_jobs))
    search_records = [record for record, _ in search_results]
    leads = [
        lead
        for _record, avenue_leads in search_results
        for lead in avenue_leads
    ]
    leads.extend(
        lead
        for record in source_records
        for lead in record["extracted_candidate_page_urls"]
    )

    attempted_source_ids = {str(record["source_id"]) for record in source_records}
    not_attempted_sources = [
        {
            "source_id": source["source_id"],
            "source_name": source["name"],
            "url": source["url"],
            "attempted": False,
            "reason": "No attempt record was produced for this inventory row.",
        }
        for source in sources
        if source["source_id"] not in attempted_source_ids
    ]
    report: dict[str, object] = {
        "schema_version": 1,
        "event_id": EVENT_ID,
        "event_title": EVENT_TITLE,
        "event_date": "2026-10-15",
        "event_reference_url": f"https://www.youtube.com/watch?v={EVENT_REFERENCE_VIDEO_ID}",
        "started_at_utc": min(
            [str(row["attempted_at_utc"]) for row in source_records + search_records],
            default=_utc_now(),
        ),
        "completed_at_utc": _utc_now(),
        "source_inventory_count": len(sources),
        "source_inventory_expected_count": EXPECTED_SOURCE_COUNT,
        "source_inventory_count_matches_expected": len(sources) == EXPECTED_SOURCE_COUNT,
        "source_attempt_count": sum(bool(row["attempted"]) for row in source_records),
        "source_not_attempted_count": len(not_attempted_sources),
        "source_attempts": source_records,
        "source_not_attempted": not_attempted_sources,
        "search_avenues": [avenue["id"] for avenue in SEARCH_AVENUES],
        "search_query_attempt_count": sum(bool(row["attempted"]) for row in search_records),
        "search_not_attempted_count": 0,
        "search_attempts": search_records,
        "candidate_lead_count": len(leads),
        "candidate_leads": leads,
        "media_downloaded": False,
        "media_frames_audio_inspected": False,
        "event_facts_verified": False,
        "coverage_limits": list(GENERAL_LIMITATIONS),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "rose-garden-source-attempts.json"
    markdown_path = output_dir / "rose-garden-source-attempts.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown_report(report), encoding="utf-8")
    return report


def _markdown_report(report: dict[str, object]) -> str:
    lines = [
        "# Rose Garden source-by-source research attempts",
        "",
        f"- Event: `{report['event_id']}` — {report['event_title']}",
        f"- Event reference: {report['event_reference_url']}",
        f"- Exact inventory rows attempted: {report['source_attempt_count']} / {report['source_inventory_count']}",
        f"- Inventory rows not attempted: {report['source_not_attempted_count']}",
        f"- Broader search queries attempted: {report['search_query_attempt_count']}",
        f"- Search queries not attempted: {report['search_not_attempted_count']}",
        f"- Unverified candidate-page leads extracted: {report['candidate_lead_count']}",
        "- Media downloaded or inspected: no",
        "- Event facts verified: no",
        "",
        "Every candidate URL below is an unverified lead. Page access and search snippets do not establish event match, video contents, source credibility, rights, or absence of other sources.",
        "",
        "## Registered source URL attempts",
        "",
        "| Source | URL | Attempted at (UTC) | State | Result | Error | Coverage limit |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in report["source_attempts"]:
        attempted = "yes" if row["attempted"] else "no"
        result = row.get("http_status", row["transport_result"])
        error = _markdown_escape(row.get("error") or "")
        lines.append(
            f"| {_markdown_escape(row['source_name'])} (`{_markdown_escape(row['source_id'])}`) | "
            f"`{_markdown_escape(row['url'])}` | `{row['attempted_at_utc']}` | {attempted} | "
            f"{result} / {row['access_status']} | {error} | "
            f"{_markdown_escape(row['coverage_limit'])} |"
        )
    lines.extend(
        [
            "",
            "## Registered sources not attempted",
            "",
        ]
    )
    if report["source_not_attempted"]:
        for row in report["source_not_attempted"]:
            lines.append(f"- {row['source_id']}: {row['url']} — {row['reason']}")
    else:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "## Broader media, news, social, congress, think-tank, and archive searches",
            "",
            "| Avenue | Query URL | Query | Attempted at (UTC) | State | Results | Leads | Error |",
            "|---|---|---|---|---|---:|---:|---|",
        ]
    )
    for row in report["search_attempts"]:
        lines.append(
            f"| {row['avenue']} | `{_markdown_escape(row['url'])}` | "
            f"{_markdown_escape(row['query'])} | `{row['attempted_at_utc']}` | "
            f"{'yes' if row['attempted'] else 'no'} / {row['access_status']} | "
            f"{row['result_count']} | {row['candidate_lead_count']} | "
            f"{_markdown_escape(row.get('error') or '')} |"
        )
    lines.extend(["", "## Candidate page URLs (unverified leads)", ""])
    if report["candidate_leads"]:
        for index, lead in enumerate(report["candidate_leads"], start=1):
            lines.extend(
                [
                    f"{index}. **UNVERIFIED — {_markdown_escape(lead.get('title') or lead.get('title_or_anchor_text') or lead['url'])}**",
                    f"   - URL: `{_markdown_escape(lead['url'])}`",
                    f"   - Provenance: `{_markdown_escape(lead.get('discovered_from_url'))}`",
                    f"   - Avenue/query: {_markdown_escape(lead.get('avenue', 'source page link'))} / "
                    f"{_markdown_escape(lead.get('query', 'not applicable'))}",
                ]
            )
    else:
        lines.append("- No candidate-page URL passed the event-term extraction filter; this does not establish source absence.")
    lines.extend(["", "## Coverage and verification limits", ""])
    lines.extend(f"- {limitation}" for limitation in report["coverage_limits"])
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    result = research(arguments.output_dir)
    print(
        "Source attempts: "
        f"{result['source_attempt_count']}/{result['source_inventory_count']}; "
        f"not attempted: {result['source_not_attempted_count']}; "
        f"search queries: {result['search_query_attempt_count']}; "
        f"unverified leads: {result['candidate_lead_count']}"
    )
    if (
        not result["source_inventory_count_matches_expected"]
        or result["source_not_attempted_count"]
        or result["search_not_attempted_count"]
    ):
        raise SystemExit("The complete source inventory/search-attempt set was not produced.")


if __name__ == "__main__":
    main()
