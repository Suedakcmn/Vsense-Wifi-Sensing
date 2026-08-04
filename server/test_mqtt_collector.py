import io
import json
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from mqtt_collector import Collector


class Message:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = json.dumps(payload).encode()


class CollectorTest(unittest.TestCase):
    def setUp(self):
        self.collector = Collector([], offline_timeout=0.02)
        self.output = io.StringIO()

    def tearDown(self):
        self.collector.close()

    def send(self, node, kind, payload):
        self.collector.on_message(None, None, Message(
            f"vsense/{node}/{kind}", payload
        ))

    def records(self):
        return [json.loads(line) for line in self.output.getvalue().splitlines()]

    def test_topic_node_id_is_authoritative_and_nodes_are_independent(self):
        with redirect_stdout(self.output):
            self.send("rx_01", "csi", {"node_id": "wrong", "csi": [1, 2]})
            self.send("rx_02", "csi", {"csi": [3, 4]})
        records = self.records()
        self.assertEqual([r["status"] for r in records if r["message_type"] == "node_status"], ["online", "online"])
        self.assertEqual([r["node_id"] for r in records if r["message_type"] == "csi"], ["rx_01", "rx_02"])

    def test_retained_status_and_timeout_emit_offline_once(self):
        with redirect_stdout(self.output):
            self.send("rx_01", "status", {"status": "online"})
            time.sleep(0.03)
            self.collector.watchdog = None
            now = time.monotonic()
            for node, seen in list(self.collector.last_seen.items()):
                if now - seen >= self.collector.offline_timeout:
                    self.collector.node_status(node, "offline", "timeout")
            self.collector.node_status("rx_01", "offline", "timeout")
        self.assertEqual([r["status"] for r in self.records()], ["online", "offline"])

    def test_ground_truth_topic_is_normalized(self):
        with redirect_stdout(self.output):
            self.send("gt", "ld2450_01", {
                "node_id": "wrong",
                "ts_us": 123456789,
                "frame_seq": 42,
                "targets": [{
                    "target_id": 1,
                    "x_mm": -782,
                    "y_mm": 1713,
                    "speed_cm_s": -16,
                    "distance_mm": 1883,
                    "resolution_mm": 320,
                }],
            })
        records = self.records()
        ground_truth = [
            record for record in records
            if record["message_type"] == "ground_truth"
        ][0]
        self.assertEqual(ground_truth["node_id"], "ld2450_01")
        self.assertEqual(ground_truth["schema_version"], 1)
        self.assertIsInstance(ground_truth["collector_ts_us"], int)
        self.assertEqual(ground_truth["mqtt_topic"], "vsense/gt/ld2450_01")

    def test_empty_target_list_is_valid(self):
        with redirect_stdout(self.output):
            self.send("gt", "ld2450_01", {
                "ts_us": 1,
                "frame_seq": 1,
                "targets": [],
            })
        self.assertEqual(
            [r["targets"] for r in self.records() if r["message_type"] == "ground_truth"],
            [[]],
        )

    def test_invalid_ground_truth_is_not_emitted(self):
        with redirect_stdout(self.output):
            self.send("gt", "ld2450_01", {
                "ts_us": 1,
                "frame_seq": 1,
                "targets": "not-a-list",
            })
        self.assertEqual(self.records(), [])

    def test_session_files_are_split_by_message_type(self):
        self.collector.close()
        with TemporaryDirectory() as temporary_directory:
            session_dir = Path(temporary_directory)
            self.collector = Collector(
                [],
                session_dir=session_dir,
                session_id="test_session",
            )
            with redirect_stdout(self.output):
                self.send("node_01", "csi", {"ts_us": 1, "csi": [1, 2]})
                self.send("gt", "ld2450_01", {
                    "ts_us": 2,
                    "frame_seq": 1,
                    "targets": [],
                })
            self.collector.close()
            self.assertEqual(
                len((session_dir / "csi.jsonl").read_text().splitlines()),
                1,
            )
            self.assertEqual(
                len((session_dir / "ground_truth.jsonl").read_text().splitlines()),
                1,
            )
            telemetry = (session_dir / "telemetry.jsonl").read_text().splitlines()
            self.assertEqual(len(telemetry), 2)


if __name__ == "__main__":
    unittest.main()
