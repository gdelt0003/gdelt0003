"""Validate persisted timestamps and outcomes for a media operation audit."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


REQUIRED_FIELDS = {
    "operation_id",
    "task_id",
    "asset_id",
    "operation",
    "tool",
    "version",
    "started_at",
    "ended_at",
    "duration_seconds",
    "status",
    "retry_count",
    "error",
}


def parse_timestamp(value: object, *, field: str, index: int) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"Operation {index} has no {field} timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"Operation {index} has invalid {field}: {value!r}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"Operation {index} {field} timestamp has no timezone.")
    return parsed


def validate_operation_audit(path: Path, manifest_path: Path | None = None) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Operation audit root must be a JSON object.")
    for field in ("task_id", "pipeline_version"):
        if not isinstance(data.get(field), str) or not data[field]:
            raise ValueError(f"Operation audit is missing {field}.")
    operations = data.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValueError("Operation audit has no operation records.")

    operation_ids: set[str] = set()
    for index, operation in enumerate(operations, start=1):
        if not isinstance(operation, dict):
            raise ValueError(f"Operation {index} must be a JSON object.")
        missing = REQUIRED_FIELDS - operation.keys()
        if missing:
            raise ValueError(
                f"Operation {index} is missing fields: {', '.join(sorted(missing))}"
            )
        if not isinstance(operation["operation_id"], str) or not operation["operation_id"]:
            raise ValueError(f"Operation {index} has an empty operation_id.")
        if operation["operation_id"] in operation_ids:
            raise ValueError(f"Operation {index} repeats an operation_id.")
        operation_ids.add(operation["operation_id"])
        if operation["task_id"] != data["task_id"]:
            raise ValueError(f"Operation {index} has a mismatched task_id.")
        for field in ("asset_id", "operation", "tool", "version"):
            if not isinstance(operation[field], str) or not operation[field]:
                raise ValueError(f"Operation {index} has an empty {field}.")
        started_at = parse_timestamp(
            operation["started_at"],
            field="started_at",
            index=index,
        )
        ended_at = parse_timestamp(
            operation["ended_at"],
            field="ended_at",
            index=index,
        )
        if ended_at < started_at:
            raise ValueError(f"Operation {index} ended before it started.")
        duration = operation["duration_seconds"]
        if not isinstance(duration, (int, float)) or duration < 0:
            raise ValueError(f"Operation {index} has an invalid duration.")
        if operation["status"] != "succeeded":
            raise ValueError(
                f"Operation {index} did not succeed: {operation['status']!r}"
            )
        retries = operation["retry_count"]
        if not isinstance(retries, int) or retries < 0:
            raise ValueError(f"Operation {index} has an invalid retry_count.")
        if operation["error"] is not None:
            raise ValueError(f"Successful operation {index} contains an error.")
    if manifest_path is not None:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("Processing manifest root must be a JSON object.")
        if manifest.get("operation_audit_file") != path.name:
            raise ValueError("Processing manifest names a different audit file.")
        if manifest.get("processing_operations") != operations:
            raise ValueError("Processing manifest and operation audit differ.")
    return len(operations)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    count = validate_operation_audit(args.audit, args.manifest)
    print(f"Validated {count} completed operation audit records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
