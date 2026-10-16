"""Collect public search and landing-page metadata as unverified Rose Garden leads."""

from __future__ import annotations

import argparse
import concurrent.futures
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


EVENT_ID = "rose-garden-lunch-2026-10-15"
EVENT_TITLE = "President Trump Participates in a Rose Garden Lunch"
EVENT_REFERENCE_VIDEO_ID = "IySF_8OArvw"
SEARCH_QUERIES = (
    f'"{EVENT_TITLE}" "Oct. 15, 2026"',
    f'"{EVENT_REFERENCE_VIDEO_ID}" Rose Garden',
    '"Rose Garden Lunch" Trump White House October 15 2026',
)
SEARCH_PROVIDERS = ("duckduckgo_html", "bing_rss")
USER_AGENT = "gdelt0003-rose-garden-metadata-research/1.0"
MAX_RESULTS_PER_QUERY = 5
MAX_LANDING_PAGE_BYTES = 512 * 1024


class SearchResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._active: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            target = attributes.get("href") or ""
            parsed = urllib.parse.urlsplit(target)
            if "duckduckgo.com" in parsed.netloc:
                target = urllib.parse.parse_qs(parsed.query).get("uddg", [target])[0]
            if urllib.parse.urlsplit(target).scheme in {"http", "https"}:
                self._active = {"url": target, "title": ""}

    def handle_data(self, data: str) -> None:
        if self._active is not None:
            self._active["title"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._active is not None:
            self._active["title"] = " ".join(self._active["title"].split())
            self.results.append(self._active)
            self._active = None


class MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.description = ""
        self.site_name = ""
        self.canonical_url = ""
        self.open_graph_type = ""
        self.video_metadata: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            key = (attributes.get("name") or attributes.get("property") or "").lower()
            content = attributes.get("content") or ""
            if key in {"description", "og:description", "twitter:description"} and not self.description:
                self.description = content.strip()
            elif key in {"og:site_name", "application-name"} and not self.site_name:
                self.site_name = content.strip()
            elif key == "og:type":
                self.open_graph_type = content.strip()
            elif key in {"og:video", "og:video:url", "og:video:secure_url", "twitter:player"} and content.strip():
                self.video_metadata.append(key)
        if tag == "link" and "canonical" in (attributes.get("rel") or "").lower().split():
            self.canonical_url = attributes.get("href") or ""

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False


def _parse_bing_rss(payload: str, query: str) -> list[dict[str, str]]:
    root = ET.fromstring(payload)
    items = []
    for item in root.findall("./channel/item")[:MAX_RESULTS_PER_QUERY]:
        url = (item.findtext("link") or "").strip()
        if urllib.parse.urlsplit(url).scheme not in {"http", "https"}:
            continue
        items.append(
            {
                "url": url,
                "title": " ".join((item.findtext("title") or "").split()),
                "search_snippet": " ".join(
                    (item.findtext("description") or "").split()
                ),
                "query": query,
            }
        )
    return items


def _request_html(
    url: str,
    timeout: int = 20,
    allowed_content_types: tuple[str, ...] = ("text/html", "application/xhtml+xml"),
) -> tuple[str, int, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/xml",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get_content_type().lower()
        if content_type not in allowed_content_types:
            raise ValueError(f"Refused non-HTML response content type: {content_type}")
        payload = response.read(MAX_LANDING_PAGE_BYTES + 1)
        if len(payload) > MAX_LANDING_PAGE_BYTES:
            raise ValueError("HTML response exceeded the metadata read limit.")
        charset = response.headers.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace"), response.status, response.geturl()


def search_query(
    provider: str, query: str, checked_at: str
) -> tuple[list[dict[str, str]], dict[str, str] | None]:
    if provider == "duckduckgo_html":
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode(
            {"q": query}
        )
    elif provider == "bing_rss":
        url = "https://www.bing.com/search?format=rss&" + urllib.parse.urlencode(
            {"q": query}
        )
    else:
        raise ValueError(f"Unsupported public search provider: {provider}")
    try:
        allowed_types = (
            ("application/rss+xml", "application/xml", "text/xml")
            if provider == "bing_rss"
            else ("text/html", "application/xhtml+xml")
        )
        html, status, final_url = _request_html(
            url,
            allowed_content_types=allowed_types,
        )
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        return [], {"provider": provider, "query": query, "error": str(error)}
    if provider == "bing_rss":
        try:
            results = _parse_bing_rss(html, query)
        except ET.ParseError as error:
            return [], {
                "provider": provider,
                "query": query,
                "error": f"Invalid search feed: {error}",
            }
    else:
        parser = SearchResultParser()
        parser.feed(html)
        results = parser.results[:MAX_RESULTS_PER_QUERY]
    tagged_results: list[dict[str, str]] = []
    for item in results:
        tagged_results.append(
            {
                "query": query,
                "search_provider": provider,
                "search_url": final_url,
                "search_http_status": str(status),
                "search_checked_at": checked_at,
                **item,
            }
        )
    return tagged_results, None


def inspect_landing_page(result: dict[str, str], checked_at: str) -> dict[str, object]:
    record: dict[str, object] = {
        "candidate_status": "landing_page_metadata_unavailable",
        "event_match": "unverified",
        "video_source_credibility": "not_assessed",
        "video_content_credibility": "not_assessed",
        "human_video_content_review": "not_performed",
        "media_frames_audio_inspected": False,
        **result,
        "landing_page_checked_at": checked_at,
    }
    try:
        html, status, final_url = _request_html(result["url"])
        parser = MetadataParser()
        parser.feed(html)
        record.update(
            {
                "landing_page_http_status": status,
                "landing_page_url": final_url,
                "page_title": " ".join(parser.title.split()),
                "page_description": parser.description,
                "site_name": parser.site_name,
                "open_graph_type": parser.open_graph_type or None,
                "video_metadata": parser.video_metadata,
                "canonical_url": urllib.parse.urljoin(final_url, parser.canonical_url)
                if parser.canonical_url
                else None,
            }
        )
        event_evidence = _event_relevance_evidence(record)
        video_evidence = _video_page_evidence(record)
        record["event_relevance_evidence"] = event_evidence
        record["video_page_evidence"] = video_evidence
        has_page_metadata = bool(parser.title.strip() or parser.description.strip())
        if not has_page_metadata and not event_evidence:
            record["candidate_status"] = "landing_page_metadata_insufficient"
        elif not event_evidence:
            record["candidate_status"] = "irrelevant_search_result"
        elif not video_evidence:
            record["candidate_status"] = "event_relevant_non_video_page"
        else:
            record["candidate_status"] = "event_relevant_video_page_lead_unverified"
            record["full_video_review_status"] = "not_performed"
            record["full_video_review_blocker"] = (
                "Exact-video media-review authorization and rights evidence are not established; "
                "this workflow is restricted to page metadata and does not retrieve or inspect media."
            )
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        record["landing_page_metadata_error"] = str(error)
    return record


def _event_relevance_evidence(record: dict[str, object]) -> list[str]:
    page_metadata = " ".join(
        str(record.get(field) or "") for field in ("page_title", "page_description")
    ).casefold()
    evidence = []
    if (
        "rose garden" in page_metadata
        and "lunch" in page_metadata
        and "trump" in page_metadata
    ):
        evidence.append("landing-page title or description mentions Trump, Rose Garden, and lunch")
    if EVENT_REFERENCE_VIDEO_ID.casefold() in str(record.get("landing_page_url") or "").casefold():
        evidence.append("landing-page URL contains the known event-reference video ID")
    return evidence


def _video_page_evidence(record: dict[str, object]) -> list[str]:
    evidence = []
    url = str(record.get("landing_page_url") or record.get("url") or "")
    parsed = urllib.parse.urlsplit(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path_segments = {segment.casefold() for segment in parsed.path.split("/") if segment}
    query = urllib.parse.parse_qs(parsed.query)
    if (
        (host == "youtube.com" and (parsed.path == "/watch" and query.get("v")))
        or host == "youtu.be"
        or (host.endswith(".youtube.com") and path_segments.intersection({"embed", "shorts", "live"}))
    ):
        evidence.append("video-platform URL")
    if path_segments.intersection({"video", "videos", "watch", "live", "embed"}):
        evidence.append("video path in landing-page URL")
    open_graph_type = str(record.get("open_graph_type") or "").casefold()
    if open_graph_type == "video" or open_graph_type.startswith("video."):
        evidence.append(f"Open Graph video type: {record['open_graph_type']}")
    for key in record.get("video_metadata", []):
        evidence.append(f"video metadata: {key}")
    return evidence


def research(output_dir: Path) -> tuple[Path, Path, dict[str, object]]:
    checked_at = datetime.now(timezone.utc).isoformat()
    search_jobs = [
        (provider, query)
        for provider in SEARCH_PROVIDERS
        for query in SEARCH_QUERIES
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        search_results = list(
            pool.map(
                lambda job: search_query(job[0], job[1], checked_at),
                search_jobs,
            )
        )

    query_errors = [error for _, error in search_results if error is not None]
    unique: dict[str, dict[str, str]] = {}
    for results, _ in search_results:
        for result in results:
            observation = {
                "provider": result["search_provider"],
                "query": result["query"],
                "search_url": result["search_url"],
                "checked_at": result["search_checked_at"],
                "title": result.get("title", ""),
                "snippet": result.get("search_snippet", ""),
            }
            if result["url"] not in unique:
                unique[result["url"]] = {
                    **result,
                    "search_observations": [observation],
                }
            else:
                unique[result["url"]]["search_observations"].append(observation)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        leads = list(pool.map(lambda item: inspect_landing_page(item, checked_at), unique.values()))

    candidates_by_page: dict[str, dict[str, object]] = {}
    for lead in leads:
        if lead["candidate_status"] != "event_relevant_video_page_lead_unverified":
            continue
        page_identity = str(
            lead.get("canonical_url") or lead.get("landing_page_url") or lead["url"]
        )
        if page_identity not in candidates_by_page:
            candidates_by_page[page_identity] = lead
        else:
            candidates_by_page[page_identity]["search_observations"].extend(
                lead["search_observations"]
            )
    candidates = list(candidates_by_page.values())
    report: dict[str, object] = {
        "schema_version": 2,
        "event_id": EVENT_ID,
        "event_title": EVENT_TITLE,
        "research_phase": "metadata_only_source_page_discovery",
        "full_video_research_status": "not_performed",
        "full_video_research_blocker": (
            "This workflow is restricted to page metadata. Exact-video media-review "
            "authorization and rights evidence are not established."
        ),
        "research_status": (
            "event_relevant_video_page_leads_found_unverified"
            if candidates
            else "no_qualifying_video_page_leads_found"
        ),
        "search_providers": list(SEARCH_PROVIDERS),
        "search_query_count": len(search_jobs),
        "search_queries": list(SEARCH_QUERIES),
        "search_coverage": "two public search providers x the listed event-scoped queries; not an exhaustive web census",
        "search_started_at": checked_at,
        "runner_hosted_only": True,
        "media_downloaded": False,
        "media_frames_audio_inspected": False,
        "human_video_content_review": "not_performed",
        "lead_count": len(leads),
        "candidate_count": len(candidates),
        "query_errors": query_errors,
        "candidates": candidates,
        "search_leads": leads,
        "limitations": (
            "Candidate qualification uses landing-page HTML metadata and URL patterns only. "
            "Search results and metadata are leads only; they do not establish event match, "
            "source credibility, video-content credibility, rights, video duration, resolution, "
            "camera angle, or visual/audio cleanliness. "
            "No video/audio/media was downloaded or inspected."
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "rose-garden-source-search.json"
    markdown_path = output_dir / "rose-garden-source-search-summary.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_lines = [
        "# Rose Garden source metadata search",
        "",
        f"- Event scope: `{EVENT_ID}`",
        "- Research phase: metadata/source-page discovery only; full video research was not performed.",
        "- Full video review blocker: exact-video media-review authorization and rights evidence are not established.",
        f"- Search and landing-page metadata leads: {len(leads)}",
        f"- Unique event-relevant video landing-page leads (unverified): {len(candidates)}",
        f"- Search provider/query combinations: {len(search_jobs)}",
        f"- Provider/query errors: {len(query_errors)}",
        "- Candidate status: qualifying pages are unverified leads; event match and both credibility dimensions are not assessed.",
        "- Human video-content review: not performed.",
        "- Media downloaded or frames/audio inspected: no.",
        "",
        "Search results and HTML metadata are leads only, not proof of event match, credibility, rights, or video content. ",
        "This metadata-only qualification does not approve reuse or publication.",
        "",
    ]
    if candidates:
        summary_lines.extend(["## Event-relevant video landing pages", ""])
    else:
        summary_lines.extend(
            [
                "## Event-relevant video landing pages",
                "",
                "Not found: no search result met both the event-metadata and video-page metadata checks.",
                "",
            ]
        )
    for index, lead in enumerate(candidates, start=1):
        summary_lines.extend(
            [
                f"### Candidate lead {index}: {lead.get('page_title') or lead['title'] or lead['url']}",
                f"- URL: {lead.get('landing_page_url') or lead['url']}",
                f"- Query: {lead['query']}",
                f"- Search observations: {len(lead['search_observations'])}",
                f"- Site metadata: {lead.get('site_name') or 'not provided'}",
                f"- Description metadata: {lead.get('page_description') or 'not provided'}",
                f"- Event relevance evidence: {'; '.join(lead['event_relevance_evidence'])}",
                f"- Video-page evidence: {'; '.join(lead['video_page_evidence'])}",
                f"- Full video review blocker: {lead['full_video_review_blocker']}",
                "- Status: unverified page lead; no human video-content review.",
                "",
            ]
        )
    other_leads = [
        lead
        for lead in leads
        if lead["candidate_status"] != "event_relevant_video_page_lead_unverified"
    ]
    if other_leads:
        summary_lines.extend(["## Other search leads (not counted as candidates)", ""])
        for index, lead in enumerate(other_leads, start=1):
            summary_lines.extend(
                [
                    f"### Lead {index}: {lead.get('page_title') or lead['title'] or lead['url']}",
                    f"- URL: {lead.get('landing_page_url') or lead['url']}",
                    f"- Status: {lead['candidate_status']}",
                    f"- Query: {lead['query']}",
                    f"- Search observations: {len(lead['search_observations'])}",
                    "",
                ]
            )
    if query_errors:
        summary_lines.extend(["## Search errors", ""])
        summary_lines.extend(f"- {error['query']}: {error['error']}" for error in query_errors)
    markdown_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    return json_path, markdown_path, report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    _, markdown_path, report = research(args.output_dir)
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    summary_path = Path(summary_file) if summary_file else None
    if summary_path:
        with summary_path.open("a", encoding="utf-8") as summary:
            summary.write(markdown_path.read_text(encoding="utf-8"))
            summary.write(
                f"\nProvider/query errors: {len(report['query_errors'])}.\n"
            )


if __name__ == "__main__":
    main()
