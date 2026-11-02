"""Create and validate the versioned contract for a workflow run manifest."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone


SCHEMA_VERSION = 1
PROCESSING_STATUSES = frozenset({"running", "succeeded", "failed"})
PUBLICATION_STATUSES = frozenset({"not_published", "published", "failed"})
CONTENT_REVIEW_STATUSES = frozenset(
    {"not_verified", "in_progress", "passed", "failed"}
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_UTC_TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)
_MANIFEST_FIELDS = {
    "schema_version",
    "run_id",
    "started_at",
    "ended_at",
    "processing_status",
    "publication_status",
    "content_review_status",
    "failed_at",
    "failure_reason",
    "inputs",
    "tool_versions",
}


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def create_run_manifest(
    *,
    run_id: str,
    inputs: Sequence[Mapping[str, str]],
    tool_versions: Mapping[str, str],
    started_at: str | None = None,
) -> dict[str, object]:
    """Create an in-progress manifest with every outcome state explicit."""
    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "started_at": utc_now() if started_at is None else started_at,
        "ended_at": None,
        "processing_status": "running",
        "publication_status": "not_published",
        "content_review_status": "not_verified",
        "failed_at": None,
        "failure_reason": None,
        "inputs": [dict(record) for record in inputs],
        "tool_versions": dict(tool_versions),
    }
    validate_run_manifest(manifest)
    return manifest


def _require_non_empty_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string.")
    return value


def _parse_utc_timestamp(value: object, *, field: str) -> datetime:
    if not isinstance(value, str) or not _UTC_TIMESTAMP_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must be a UTC timestamp ending in 'Z'.")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError(f"{field} is not a valid UTC timestamp.") from error


def _require_object(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a JSON object.")
    if any(not isinstance(key, str) for key in value):
        raise ValueError(f"{field} keys must be strings.")
    return value


def _require_exact_fields(
    value: Mapping[str, object],
    expected: set[str],
    *,
    field: str,
) -> None:
    missing = expected - value.keys()
    unexpected = value.keys() - expected
    if missing:
        raise ValueError(f"{field} is missing fields: {', '.join(sorted(missing))}.")
    if unexpected:
        raise ValueError(
            f"{field} has unknown fields: {', '.join(sorted(unexpected))}."
        )


def _require_status(value: object, *, field: str, allowed: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{field} has an unknown status: {value!r}.")
    return value


def validate_run_manifest(manifest: object) -> None:
    """Raise ValueError unless a run manifest satisfies the complete contract."""
    root = _require_object(manifest, field="Run manifest")
    _require_exact_fields(root, _MANIFEST_FIELDS, field="Run manifest")

    if (
        type(root["schema_version"]) is not int
        or root["schema_version"] != SCHEMA_VERSION
    ):
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}.")
    _require_non_empty_string(root["run_id"], field="run_id")

    started_at = _parse_utc_timestamp(root["started_at"], field="started_at")
    ended_value = root["ended_at"]
    ended_at = (
        None
        if ended_value is None
        else _parse_utc_timestamp(ended_value, field="ended_at")
    )

    processing_status = _require_status(
        root["processing_status"],
        field="processing_status",
        allowed=PROCESSING_STATUSES,
    )
    _require_status(
        root["publication_status"],
        field="publication_status",
        allowed=PUBLICATION_STATUSES,
    )
    _require_status(
        root["content_review_status"],
        field="content_review_status",
        allowed=CONTENT_REVIEW_STATUSES,
    )

    if processing_status == "running" and ended_at is not None:
        raise ValueError("ended_at must be null while processing_status is running.")
    if processing_status != "running" and ended_at is None:
        raise ValueError("ended_at is required when processing has finished.")
    if ended_at is not None and ended_at < started_at:
        raise ValueError("ended_at cannot be earlier than started_at.")

    failed_states = (
        processing_status == "failed"
        or root["publication_status"] == "failed"
        or root["content_review_status"] == "failed"
    )
    failed_at_value = root["failed_at"]
    failure_reason_value = root["failure_reason"]
    if failed_states:
        failed_at = _parse_utc_timestamp(failed_at_value, field="failed_at")
        _require_non_empty_string(failure_reason_value, field="failure_reason")
        if failed_at < started_at:
            raise ValueError("failed_at cannot be earlier than started_at.")
        if ended_at is None or failed_at > ended_at:
            raise ValueError("failed_at must be at or before ended_at.")
    elif failed_at_value is not None or failure_reason_value is not None:
        raise ValueError(
            "failed_at and failure_reason must be null when no status is failed."
        )

    inputs_value = root["inputs"]
    if not isinstance(inputs_value, list) or not inputs_value:
        raise ValueError("inputs must be a non-empty array.")
    input_ids: set[str] = set()
    for index, input_value in enumerate(inputs_value, start=1):
        input_record = _require_object(input_value, field=f"inputs[{index}]")
        _require_exact_fields(
            input_record,
            {"id", "sha256"},
            field=f"inputs[{index}]",
        )
        input_id = _require_non_empty_string(
            input_record["id"],
            field=f"inputs[{index}].id",
        )
        if input_id in input_ids:
            raise ValueError(f"inputs repeats id {input_id!r}.")
        input_ids.add(input_id)
        digest = input_record["sha256"]
        if not isinstance(digest, str) or not _SHA256_PATTERN.fullmatch(digest):
            raise ValueError(
                f"inputs[{index}].sha256 must be a lowercase SHA-256 digest."
            )

    tools = _require_object(root["tool_versions"], field="tool_versions")
    if not tools:
        raise ValueError("tool_versions must contain at least one tool.")
    for tool, version in tools.items():
        _require_non_empty_string(tool, field="tool_versions key")
        _require_non_empty_string(version, field=f"tool_versions[{tool!r}]")
