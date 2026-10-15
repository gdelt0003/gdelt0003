"""Persist the latest automated source collector attempt in the source registry."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


def record_attempt(
    registry: dict,
    *,
    source_id: str,
    result: str,
    attempted_at_utc: str,
    run_url: str,
) -> dict:
    if result not in {"success", "failure", "skipped"}:
        raise ValueError("result must be 'success', 'failure', or 'skipped'.")
    parsed_run_url = urlparse(run_url)
    if parsed_run_url.scheme != "https" or not parsed_run_url.netloc:
        raise ValueError("run_url must be an HTTPS URL.")
    try:
        parsed_attempt_time = datetime.fromisoformat(
            attempted_at_utc.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise ValueError("attempted_at_utc must be an ISO timestamp.") from error
    if parsed_attempt_time.tzinfo is None:
        raise ValueError("attempted_at_utc must include a timezone.")
    if not isinstance(registry, dict):
        raise ValueError("Source registry must be a JSON object.")
    sources = registry.get("sources")
    if not isinstance(sources, list):
        raise ValueError("Source registry must contain a sources list.")
    matches = [
        source
        for source in sources
        if isinstance(source, dict) and source.get("source_id") == source_id
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one registered source with ID {source_id!r}.")
    source = matches[0]
    source["last_attempt_utc"] = attempted_at_utc
    status = {
        "success": ("success_metadata_only", "metadata_endpoint_reached"),
        "failure": ("fetch_failed", "fetch_failed_check_run_log"),
        "skipped": ("skipped_disabled", "disabled_by_user"),
    }[result]
    source["last_result"], source["access_status"] = status
    source["last_run_url"] = run_url
    return registry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument(
        "--result", choices=("success", "failure", "skipped"), required=True
    )
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--attempted-at-utc")
    args = parser.parse_args()
    try:
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
        timestamp = args.attempted_at_utc or datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        )
        updated = record_attempt(
            registry,
            source_id=args.source_id,
            result=args.result,
            attempted_at_utc=timestamp,
            run_url=args.run_url,
        )
        temporary = args.registry.with_suffix(args.registry.suffix + ".tmp")
        temporary.write_text(
            json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(args.registry)
        print(f"Recorded {args.result} collector attempt for {args.source_id}.")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
