import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from session_cli import make_session_id
from validate_session import validate_session


def write_jsonl(path, records):
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


class SessionToolsTest(unittest.TestCase):
    def test_session_id_uses_canonical_format(self):
        now = datetime(2026, 8, 3, 10, 20, 30, tzinfo=timezone.utc)
        session_id = make_session_id(now, "lab_room", "walking", 2)
        self.assertRegex(
            session_id,
            r"^20260803_\d{6}_lab_room_walking_r02$",
        )

    def test_validator_accepts_synchronized_two_node_session(self):
        with TemporaryDirectory() as temporary_directory:
            session_dir = Path(temporary_directory)
            (session_dir / "metadata.json").write_text(
                json.dumps({"session_id": "test", "status": "completed"}),
                encoding="utf-8",
            )
            write_jsonl(session_dir / "csi.jsonl", [
                {
                    "message_type": "csi",
                    "node_id": "node_01",
                    "collector_ts_us": 1_000_000,
                },
                {
                    "message_type": "csi",
                    "node_id": "node_02",
                    "collector_ts_us": 1_020_000,
                },
                {
                    "message_type": "csi",
                    "node_id": "node_01",
                    "collector_ts_us": 2_000_000,
                },
                {
                    "message_type": "csi",
                    "node_id": "node_02",
                    "collector_ts_us": 2_020_000,
                },
            ])
            write_jsonl(session_dir / "ground_truth.jsonl", [
                {
                    "message_type": "ground_truth",
                    "node_id": "ld2450_01",
                    "frame_seq": 1,
                    "collector_ts_us": 1_010_000,
                },
                {
                    "message_type": "ground_truth",
                    "node_id": "ld2450_01",
                    "frame_seq": 2,
                    "collector_ts_us": 2_010_000,
                },
            ])
            result = validate_session(
                session_dir,
                ["node_01", "node_02"],
                max_delta_us=200_000,
                min_duration_seconds=0,
            )
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["synchronization"]["node_01"]["max_delta_ms"], 10.0)
            self.assertEqual(result["synchronization"]["node_02"]["max_delta_ms"], 10.0)

    def test_validator_rejects_missing_rx_node(self):
        with TemporaryDirectory() as temporary_directory:
            session_dir = Path(temporary_directory)
            (session_dir / "metadata.json").write_text(
                json.dumps({"session_id": "test", "status": "completed"}),
                encoding="utf-8",
            )
            write_jsonl(session_dir / "csi.jsonl", [{
                "message_type": "csi",
                "node_id": "node_01",
                "collector_ts_us": 1_000_000,
            }])
            write_jsonl(session_dir / "ground_truth.jsonl", [{
                "message_type": "ground_truth",
                "node_id": "ld2450_01",
                "frame_seq": 1,
                "collector_ts_us": 1_000_000,
            }])
            result = validate_session(
                session_dir,
                ["node_01", "node_02"],
                max_delta_us=200_000,
                min_duration_seconds=0,
            )
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("node_02" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
