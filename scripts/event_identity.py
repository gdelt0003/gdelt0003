"""Deterministic event keys for grouping source footage without conflation."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date
from typing import Any


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def build_event_id(event: dict[str, Any]) -> str:
    required = ("event_date", "location", "event_type", "title", "participants")
    missing = [
        field
        for field in required
        if field not in event or event[field] in (None, "", [])
    ]
    if missing:
        raise ValueError(
            "Missing event identity fields: " + ", ".join(missing)
        )
    for field in ("location", "event_type", "title"):
        if not isinstance(event[field], str) or not event[field].strip():
            raise ValueError(f"{field} must be a non-empty string.")

    event_date = event["event_date"]
    if (
        not isinstance(event_date, str)
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}", event_date) is None
    ):
        raise ValueError("event_date must use ISO YYYY-MM-DD format.")
    try:
        date.fromisoformat(event_date)
    except ValueError as error:
        raise ValueError("event_date must use ISO YYYY-MM-DD format.") from error

    time_precision = event.get("time_precision")
    event_time = event.get("event_time_local")
    timezone = event.get("timezone")
    if time_precision not in {"minute", "day"}:
        raise ValueError("time_precision must be 'minute' or 'day'.")
    if time_precision == "minute":
        if (
            not isinstance(event_time, str)
            or re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", event_time) is None
            or not isinstance(timezone, str)
            or not timezone.strip()
        ):
            raise ValueError(
                "Minute-precision events require HH:MM local time and timezone."
            )
    elif event_time is not None:
        raise ValueError("Day-precision events must not invent a local time.")

    participants = event["participants"]
    if (
        not isinstance(participants, list)
        or not participants
        or any(not isinstance(person, str) or not person.strip() for person in participants)
    ):
        raise ValueError("participants must be a non-empty list of names.")

    normalized = {
        "event_date": event_date,
        "event_time_local": event_time,
        "time_precision": time_precision,
        "timezone": _normalize(timezone) if isinstance(timezone, str) else None,
        "location": _normalize(event["location"]),
        "event_type": _normalize(event["event_type"]),
        "title": _normalize(event["title"]),
        "participants": sorted({_normalize(person) for person in participants}),
    }
    digest = hashlib.sha256(
        json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"evt-{event_date.replace('-', '')}-{digest}"
