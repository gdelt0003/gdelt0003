"""Collect recent GDELT article metadata as unassigned event-discovery leads."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from typing import Any


API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def normalize_articles(payload: dict[str, Any], checked_at: str) -> dict[str, Any]:
    articles = payload.get("articles")
    if not isinstance(articles, list) or not articles:
        raise ValueError("GDELT returned no article entries.")

    leads = []
    seen_urls = set()
    for article in articles:
        if not isinstance(article, dict):
            continue
        url = article.get("url")
        if not isinstance(url, str) or url in seen_urls:
            continue
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            continue
        seen_urls.add(url)
        leads.append(
            {
                "title": article.get("title") or "",
                "publisher": article.get("domain") or parsed.netloc,
                "url": url,
                "seen_date_utc_metadata": article.get("seendate") or "",
                "language": article.get("language") or "",
                "source_country": article.get("sourcecountry") or "",
                "event_id": None,
                "event_date": None,
                "assignment_status": "unassigned_event_lead",
                "evidence_status": "article_metadata_only",
            }
        )
    if not leads:
        raise ValueError("GDELT returned no valid HTTPS article URLs.")
    return {
        "schema_version": 1,
        "checked_at_utc": checked_at,
        "source_url": (
            "https://gdelt.github.io/#api=doc&query=trump%20&contentmode="
            "ArtList&maxrecords=250&sort=DateDesc&format=html&timespan=1w"
        ),
        "api_url": API_URL,
        "query": "trump",
        "identity_rule": (
            "GDELT seen dates describe article metadata, not event time. "
            "Article titles and snippets do not independently verify an event."
        ),
        "leads": leads,
    }


def fetch_articles(query: str, max_records: int, timespan: str) -> dict[str, Any]:
    parameters = urlencode(
        {
            "query": query,
            "mode": "ArtList",
            "maxrecords": max_records,
            "format": "json",
            "sort": "DateDesc",
            "timespan": timespan,
        }
    )
    request = Request(
        f"{API_URL}?{parameters}",
        headers={"User-Agent": "event-discovery-metadata/1.0"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        retry_after = error.headers.get("Retry-After")
        suffix = f"; Retry-After: {retry_after}" if retry_after else ""
        raise RuntimeError(
            f"GDELT article metadata request failed: HTTP {error.code} "
            f"{error.reason}{suffix}"
        ) from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(f"GDELT article metadata request failed: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="trump")
    parser.add_argument("--max-records", type=int, default=250)
    parser.add_argument("--timespan", default="1w")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.query.strip():
        parser.error("--query must not be empty.")
    if args.max_records < 1 or args.max_records > 250:
        parser.error("--max-records must be between 1 and 250.")
    if not args.timespan.strip():
        parser.error("--timespan must not be empty.")
    try:
        payload = fetch_articles(args.query, args.max_records, args.timespan)
        discovery = normalize_articles(
            payload,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(discovery, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {len(discovery['leads'])} unassigned article leads to {args.output}")
        return 0
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
