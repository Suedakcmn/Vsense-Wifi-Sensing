import io
import json
import time
import unittest
from contextlib import redirect_stdout

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


if __name__ == "__main__":
    unittest.main()
