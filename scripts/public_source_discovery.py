"""Collect public search metadata as unassigned, unverified event leads.

Only unauthenticated public endpoints are used. This collector does not bypass
robots policies, login, CAPTCHA, blocks, or rate limits.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

USER_AGENT = "gdelt-public-discovery/1.0 (+https://github.com/gdelt0003/gdelt0003)"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def request_public(url: str) -> tuple[str, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, application/rss+xml, text/html;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read(2_000_000)
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace"), {
            "http_status": response.status,
            "content_type": response.headers.get("Content-Type", ""),
            "response_url": response.geturl(),
        }


def attempt(service: str, query: str, url: str) -> tuple[dict[str, Any], str | None]:
    record: dict[str, Any] = {
        "service": service,
        "query": query,
        "request_url": url,
        "attempted_at_utc": now_utc(),
        "status": "failed",
        "http_status": None,
        "error": None,
        "result_count": 0,
    }
    try:
        body, metadata = request_public(url)
        record.update(metadata)
        record["status"] = "reached"
        return record, body
    except urllib.error.HTTPError as error:
        retry_after = error.headers.get("Retry-After") if error.headers else None
        record["http_status"] = error.code
        record["status"] = "rate_limited" if error.code == 429 else "blocked_or_failed"
        record["error"] = f"HTTP {error.code} {error.reason}" + (
            f"; Retry-After={retry_after}" if retry_after else ""
        )
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        record["status"] = "unavailable_or_failed"
        record["error"] = f"{type(error).__name__}: {error}"
    return record, None


def robots_allows(url: str) -> tuple[bool | None, str | None]:
    parsed = urllib.parse.urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        body, _ = request_public(robots_url)
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(body.splitlines())
        return parser.can_fetch(USER_AGENT, url), None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        return None, f"{type(error).__name__}: {error}"


def html_results(body: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for href, snippet in re.findall(
        r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', body, flags=re.I | re.S
    ):
        match = re.search(r"/url\?q=([^&]+)", href)
        url = urllib.parse.unquote(match.group(1)) if match else href
        if not url.startswith("http") or "google.com" in urllib.parse.urlparse(url).netloc:
            continue
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", snippet)).strip()
        if title:
            results.append(
                {
                    "title": title[:300],
                    "url": url,
                    "publisher": urllib.parse.urlparse(url).netloc,
                    "published_at_raw": None,
                    "raw_date_metadata": {"not_exposed_by_search_result": True},
                }
            )
        if len(results) == 10:
            break
    return results


def parse(service: str, body: str) -> list[dict[str, Any]]:
    if service in {"google-news-rss", "google-news-newspaper-search"}:
        root = ET.fromstring(body)
        return [
            {
                "title": (item.findtext("title") or "").strip(),
                "url": (item.findtext("link") or "").strip(),
                "publisher": (item.findtext("source") or "Google News").strip(),
                "published_at_raw": item.findtext("pubDate") or None,
                "raw_date_metadata": {"pubDate": item.findtext("pubDate")},
            }
            for item in root.findall(".//item")
        ]
    if service in {"google-web", "google-scholar"}:
        return html_results(body)
    data = json.loads(body)
    if service == "gdelt":
        return [
            {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "publisher": item.get("domain") or "",
                "published_at_raw": item.get("seendate") or None,
                "raw_date_metadata": {
                    "seendate": item.get("seendate"),
                    "sourcecountry": item.get("sourcecountry"),
                    "language": item.get("language"),
                },
            }
            for item in data.get("articles", [])
            if isinstance(item, dict)
        ]
    if service == "bluesky":
        results = []
        for item in data.get("posts", []):
            post = item.get("record") or {}
            author = item.get("author") or {}
            handle = author.get("handle") or ""
            uri = item.get("uri") or ""
            rkey = uri.rsplit("/", 1)[-1]
            results.append(
                {
                    "title": (post.get("text") or "")[:240]
                    or f"Bluesky post by {handle}",
                    "url": f"https://bsky.app/profile/{handle}/post/{rkey}"
                    if handle and rkey
                    else "",
                    "publisher": f"@{handle}" if handle else "Bluesky",
                    "published_at_raw": post.get("createdAt")
                    or item.get("indexedAt"),
                    "raw_date_metadata": {
                        "createdAt": post.get("createdAt"),
                        "indexedAt": item.get("indexedAt"),
                    },
                }
            )
        return results
    if service in {"reddit", "reddit-forums"}:
        children = data.get("data", {}).get("children", [])
        results = []
        for child in children:
            item = child.get("data") or {}
            permalink = item.get("permalink") or ""
            results.append(
                {
                    "title": item.get("title") or "",
                    "url": f"https://www.reddit.com{permalink}" if permalink else "",
                    "publisher": f"r/{item.get('subreddit', '')}",
                    "published_at_raw": item.get("created_utc"),
                    "raw_date_metadata": {"created_utc": item.get("created_utc")},
                }
            )
        return results
    if service == "hacker-news":
        return [
            {
                "title": item.get("title") or "",
                "url": item.get("url")
                or (
                    f"https://news.ycombinator.com/item?id={item['objectID']}"
                    if item.get("objectID")
                    else ""
                ),
                "publisher": "Hacker News",
                "published_at_raw": item.get("created_at"),
                "raw_date_metadata": {
                    "created_at": item.get("created_at"),
                    "created_at_i": item.get("created_at_i"),
                },
            }
            for item in data.get("hits", [])
            if isinstance(item, dict)
        ]
    if service == "archive":
        results = []
        for item in data.get("response", {}).get("docs", []):
            identifier = item.get("identifier")
            results.append(
                {
                    "title": (item.get("title") or ["Internet Archive item"])[0]
                    if isinstance(item.get("title"), list)
                    else item.get("title", "Internet Archive item"),
                    "url": f"https://archive.org/details/{identifier}"
                    if identifier
                    else "",
                    "publisher": item.get("creator") or "Internet Archive",
                    "published_at_raw": item.get("date") or None,
                    "raw_date_metadata": {
                        "date": item.get("date"),
                        "publicdate": item.get("publicdate"),
                    },
                }
            )
        return results
    if service == "loc":
        return [
            {
                "title": item.get("title") or "Library of Congress item",
                "url": item.get("url") or "",
                "publisher": item.get("publisher") or "Library of Congress",
                "published_at_raw": item.get("date") or None,
                "raw_date_metadata": {
                    "date": item.get("date"),
                    "date_created": item.get("date_created"),
                },
            }
            for item in data.get("results", [])
            if isinstance(item, dict)
        ]
    if service == "openlibrary":
        return [
            {
                "title": item.get("title") or "Open Library record",
                "url": f"https://openlibrary.org{item['key']}"
                if item.get("key")
                else "",
                "publisher": "Open Library",
                "published_at_raw": item.get("first_publish_year"),
                "raw_date_metadata": {
                    "first_publish_year": item.get("first_publish_year")
                },
            }
            for item in data.get("docs", [])
            if isinstance(item, dict)
        ]
    if service == "openalex":
        results = []
        for item in data.get("results", []):
            location = item.get("primary_location") or {}
            authorships = item.get("authorships") or []
            author = (authorships[0].get("author") or {}) if authorships else {}
            results.append(
                {
                    "title": item.get("title") or "OpenAlex work",
                    "url": location.get("landing_page_url") or item.get("doi") or "",
                    "publisher": author.get("display_name") or "OpenAlex",
                    "published_at_raw": item.get("publication_date")
                    or item.get("publication_year"),
                    "raw_date_metadata": {
                        "publication_date": item.get("publication_date"),
                        "publication_year": item.get("publication_year"),
                    },
                }
            )
        return results
    if service == "crossref":
        return [
            {
                "title": (item.get("title") or ["Crossref work"])[0],
                "url": item.get("URL")
                or (
                    f"https://doi.org/{item['DOI']}" if item.get("DOI") else ""
                ),
                "publisher": item.get("publisher") or "Crossref",
                "published_at_raw": item.get("published-print", {}).get("date-time")
                or item.get("published-online", {}).get("date-time"),
                "raw_date_metadata": {
                    "published_print": item.get("published-print"),
                    "published_online": item.get("published-online"),
                },
            }
            for item in data.get("message", {}).get("items", [])
            if isinstance(item, dict)
        ]
    return []


def endpoints(query: str) -> dict[str, list[tuple[str, str]]]:
    encoded = urllib.parse.quote(query)
    return {
        "news": [
            (
                "gdelt",
                f"https://api.gdeltproject.org/api/v2/doc/doc?query={encoded}&mode=ArtList&maxrecords=20&format=json&sort=DateDesc&timespan=30d",
            ),
            (
                "google-news-rss",
                f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en",
            ),
        ],
        "newspapers": [
            (
                "google-news-newspaper-search",
                f"https://news.google.com/rss/search?q={encoded}+newspaper&hl=en-US&gl=US&ceid=US:en",
            )
        ],
        "social": [
            (
                "bluesky",
                f"https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q={encoded}&limit=20",
            ),
            (
                "reddit",
                f"https://www.reddit.com/search.json?q={encoded}&limit=10&sort=relevance",
            ),
        ],
        "forums": [
            (
                "hacker-news",
                f"https://hn.algolia.com/api/v1/search?query={encoded}&tags=story&hitsPerPage=10",
            ),
            (
                "reddit-forums",
                f"https://www.reddit.com/search.json?q={encoded}&limit=10&sort=relevance",
            ),
        ],
        "internet-archive": [
            (
                "archive",
                f"https://archive.org/advancedsearch.php?q={encoded}&fl[]=title&fl[]=creator&fl[]=date&fl[]=publicdate&fl[]=identifier&rows=10&output=json",
            )
        ],
        "library-catalog": [
            ("loc", f"https://www.loc.gov/search/?q={encoded}&fo=json&c=10"),
            ("openlibrary", f"https://openlibrary.org/search.json?q={encoded}&limit=10"),
        ],
        "google-search": [
            ("google-web", f"https://www.google.com/search?hl=en&q={encoded}&num=10"),
            ("google-scholar", f"https://scholar.google.com/scholar?q={encoded}"),
        ],
        "scholarly-metadata": [
            ("openalex", f"https://api.openalex.org/works?search={encoded}&per-page=10"),
            ("crossref", f"https://api.crossref.org/works?query.bibliographic={encoded}&rows=10"),
        ],
    }


def run_lane(lane: str, query: str, run_url: str) -> dict[str, Any]:
    retrieved_at = now_utc()
    attempts = []
    leads = []
    for index, (service, url) in enumerate(endpoints(query)[lane]):
        if index:
            time.sleep(1)
        if service in {"google-web", "google-scholar"}:
            allowed, robots_error = robots_allows(url)
            if allowed is not True:
                attempt_record = {
                    "service": service,
                    "query": query,
                    "request_url": url,
                    "attempted_at_utc": now_utc(),
                    "status": "robots_disallowed"
                    if allowed is False
                    else "robots_unavailable_not_attempted",
                    "http_status": None,
                    "error": robots_error
                    or "robots.txt disallows this URL; search request was not made.",
                    "result_count": 0,
                }
                attempts.append(attempt_record)
                continue
        attempt_record, body = attempt(service, query, url)
        parsed = []
        if body is not None:
            if service in {"google-web", "google-scholar"} and re.search(
                r"captcha|unusual traffic|automated queries", body, flags=re.I
            ):
                attempt_record["status"] = "blocked_or_captcha"
                attempt_record["error"] = (
                    "Search endpoint returned a challenge/interstitial; not bypassed."
                )
            else:
                try:
                    parsed = parse(service, body)
                except (
                    ET.ParseError,
                    json.JSONDecodeError,
                    TypeError,
                    KeyError,
                ) as error:
                    attempt_record["status"] = "parse_failed"
                    attempt_record["error"] = f"{type(error).__name__}: {error}"
        attempt_record["result_count"] = len(parsed)
        attempts.append(attempt_record)
        for item in parsed:
            direct_url = item.get("url")
            if not isinstance(direct_url, str) or not direct_url.startswith("https://"):
                continue
            leads.append(
                {
                    **item,
                    "source": service,
                    "lane": lane,
                    "category": lane,
                    "query": query,
                    "retrieved_at_utc": retrieved_at,
                    "record_status": "unassigned/unverified lead",
                    "event_assignment": "unassigned",
                    "event_match_status": "unverified",
                    "attempt_url": run_url,
                }
            )
    unique = []
    seen = set()
    for lead in leads:
        if lead["url"] not in seen:
            seen.add(lead["url"])
            unique.append(lead)
    reached = any(item["status"] == "reached" for item in attempts)
    status = (
        "results_unverified"
        if unique
        else "reached_no_parseable_results"
        if reached
        else "unavailable_or_blocked"
    )
    return {
        "schema_version": 1,
        "event_query": query,
        "lane": lane,
        "retrieved_at_utc": retrieved_at,
        "workflow_run_url": run_url,
        "status": status,
        "attempts": attempts,
        "lead_count": len(unique),
        "leads": unique,
        "promotion_policy": "All records are unassigned/unverified leads; none is confirmed or written to the event catalog.",
        "access_policy": "Public unauthenticated endpoints only; no paid APIs, credentials, login, CAPTCHA bypass, or rate-limit bypass.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lane",
        required=True,
        choices=sorted(endpoints("Katie Zacharia White House briefing 2026-10-13")),
    )
    parser.add_argument("--query", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-url", required=True)
    args = parser.parse_args()
    report = run_lane(args.lane, args.query, args.run_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "lane": report["lane"],
                "status": report["status"],
                "lead_count": report["lead_count"],
                "artifact": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
