"""Persist timestamped records for media-processing operations."""

from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class OperationAudit:
    def __init__(
        self,
        path: Path,
        *,
        task_id: str,
        pipeline_version: str,
    ) -> None:
        self.path = path
        self.task_id = task_id
        self.pipeline_version = pipeline_version
        self.records: list[dict[str, object]] = []
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(
                {
                    "task_id": self.task_id,
                    "pipeline_version": self.pipeline_version,
                    "operations": self.records,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(self.path)

    @contextmanager
    def record(
        self,
        operation: str,
        *,
        asset_id: str,
        tool: str,
        version: str,
        details: dict[str, object] | None = None,
    ) -> Iterator[dict[str, object]]:
        started_at = utc_now()
        started_clock = time.monotonic()
        record: dict[str, object] = {
            "operation_id": str(uuid.uuid4()),
            "task_id": self.task_id,
            "asset_id": asset_id,
            "operation": operation,
            "tool": tool,
            "version": version,
            "started_at": started_at,
            "ended_at": None,
            "duration_seconds": None,
            "status": "running",
            "retry_count": 0,
            "error": None,
            "details": details or {},
        }
        self.records.append(record)
        self._save()
        try:
            yield record
        except BaseException as error:
            record["status"] = "failed"
            record["error"] = f"{type(error).__name__}: {error}"[:2000]
            raise
        else:
            record["status"] = "succeeded"
        finally:
            record["ended_at"] = utc_now()
            record["duration_seconds"] = round(
                time.monotonic() - started_clock,
                3,
            )
            self._save()


def current_task_id() -> str:
    run_id = os.environ.get("GITHUB_RUN_ID")
    if run_id:
        return f"{run_id}.{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}"
    return f"local-{uuid.uuid4()}"


def current_pipeline_version() -> str:
    return os.environ.get("GITHUB_SHA", "working-tree")
