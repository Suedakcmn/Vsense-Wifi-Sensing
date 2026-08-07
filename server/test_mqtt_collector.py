import io
import json
import time
import unittest
from contextlib import redirect_stdout

from mqtt_collector import Collector
from vsense_binary import encode_csi_packet


class Message:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = json.dumps(payload).encode()


class RawMessage:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload


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

    def test_binary_csi_is_normalized_to_the_existing_json_schema(self):
        binary_payload = encode_csi_packet(
            frame_count=42,
            ts_us=123456,
            rssi=-41,
            channel=1,
            csi=[-2, 3, -4, 5],
        )

        with redirect_stdout(self.output):
            self.collector.on_message(
                None,
                None,
                RawMessage("vsense/rx_01/csi", binary_payload),
            )

        csi_record = next(
            record
            for record in self.records()
            if record["message_type"] == "csi"
        )
        self.assertEqual(csi_record["node_id"], "rx_01")
        self.assertEqual(csi_record["frame_count"], 42)
        self.assertEqual(csi_record["ts_us"], 123456)
        self.assertEqual(csi_record["rssi"], -41)
        self.assertEqual(csi_record["channel"], 1)
        self.assertEqual(csi_record["len"], 4)
        self.assertEqual(csi_record["csi"], [-2, 3, -4, 5])

    def test_invalid_binary_csi_is_rejected_without_marking_node_online(self):
        binary_payload = bytearray(encode_csi_packet(
            frame_count=42,
            ts_us=123456,
            rssi=-41,
            channel=1,
            csi=[-2, 3],
        ))
        binary_payload[4] = 99

        with redirect_stdout(self.output):
            self.collector.on_message(
                None,
                None,
                RawMessage("vsense/rx_01/csi", bytes(binary_payload)),
            )

        self.assertEqual(self.records(), [])
        self.assertNotIn("rx_01", self.collector.last_seen)


if __name__ == "__main__":
    unittest.main()
