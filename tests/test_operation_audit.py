import json
import tempfile
import unittest
from pathlib import Path

from scripts.operation_audit import OperationAudit
from scripts.verify_operation_audit import validate_operation_audit


class OperationAuditTests(unittest.TestCase):
    def test_persists_timezone_aware_operation_timing_and_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "operation-audit.json"
            audit = OperationAudit(
                path,
                task_id="run-123.1",
                pipeline_version="abc123",
            )

            with audit.record(
                "asr",
                asset_id="source.mp4",
                tool="faster-whisper",
                version="large-v3-turbo; faster-whisper=1.0",
            ):
                in_progress = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(in_progress["operations"][0]["status"], "running")

            self.assertEqual(validate_operation_audit(path), 1)
            operation = json.loads(path.read_text(encoding="utf-8"))["operations"][0]
            self.assertTrue(operation["started_at"].endswith("Z"))
            self.assertTrue(operation["ended_at"].endswith("Z"))
            self.assertEqual(operation["status"], "succeeded")
            self.assertEqual(operation["retry_count"], 0)

    def test_records_failures_and_retry_count(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "operation-audit.json"
            audit = OperationAudit(
                path,
                task_id="run-123.1",
                pipeline_version="abc123",
            )

            with self.assertRaisesRegex(RuntimeError, "translation failed"):
                with audit.record(
                    "translation",
                    asset_id="clip-1",
                    tool="MyMemory HTTP API",
                    version="en|zh-CN",
                ) as operation:
                    operation["retry_count"] = 2
                    raise RuntimeError("translation failed")

            operation = json.loads(path.read_text(encoding="utf-8"))["operations"][0]
            self.assertEqual(operation["status"], "failed")
            self.assertEqual(operation["retry_count"], 2)
            self.assertIn("translation failed", operation["error"])

    def test_validator_requires_manifest_to_reference_the_same_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audit_path = root / "operation-audit.json"
            manifest_path = root / "manifest.json"
            audit = OperationAudit(
                audit_path,
                task_id="run-123.1",
                pipeline_version="abc123",
            )
            with audit.record(
                "subtitle_burn",
                asset_id="output.mp4",
                tool="ffmpeg",
                version="ffmpeg version test",
            ):
                pass
            manifest_path.write_text(
                json.dumps(
                    {
                        "operation_audit_file": audit_path.name,
                        "processing_operations": [],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "manifest and operation audit differ"):
                validate_operation_audit(audit_path, manifest_path)


if __name__ == "__main__":
    unittest.main()
