"""Subscribe to all VSense nodes and expose one normalized JSONL stream."""

import argparse
import json
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def collector_timestamp_us():
    return time.time_ns() // 1_000


class Collector:
    def __init__(self, topics, offline_timeout=5.0, record=None):
        self.topics = topics
        self.offline_timeout = offline_timeout
        self.last_seen = {}
        self.states = {}
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.record_file = None
        if record is not None:
            record.parent.mkdir(parents=True, exist_ok=True)
            self.record_file = record.open("a", encoding="utf-8")

    def emit(self, message):
        line = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        with self.lock:
            print(line, flush=True)
            if self.record_file is not None:
                self.record_file.write(line + "\n")
                self.record_file.flush()

    def node_status(self, node_id, status, source):
        if self.states.get(node_id) == status:
            return
        self.states[node_id] = status
        self.emit({
            "schema_version": 2,
            "message_type": "node_status",
            "node_id": node_id,
            "status": status,
            "source": source,
            "recorded_at": utc_now(),
            "collector_ts_us": collector_timestamp_us(),
        })

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            print(f"MQTT connection failed: {reason_code}", file=sys.stderr)
            return
        for topic in self.topics:
            client.subscribe(topic)
        print("MQTT connected; subscribed to " + ", ".join(self.topics), file=sys.stderr)

    def on_message(self, client, userdata, msg):
        parts = msg.topic.split("/")
        if len(parts) != 3 or parts[0] != "vsense":
            print(f"Skipping unexpected topic: {msg.topic}", file=sys.stderr)
            return
        node_id, message_type = parts[1], parts[2]
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(f"Skipping invalid payload on {msg.topic}: {exc}", file=sys.stderr)
            return
        if not isinstance(payload, dict):
            print(f"Skipping non-object payload on {msg.topic}", file=sys.stderr)
            return

        now = time.monotonic()
        self.last_seen[node_id] = now
        payload["node_id"] = node_id  # topic identity is authoritative
        payload.setdefault("schema_version", 2)
        payload["message_type"] = message_type
        payload["mqtt_topic"] = msg.topic
        payload["recorded_at"] = utc_now()
        payload["collector_ts_us"] = collector_timestamp_us()

        if message_type == "status":
            status = payload.get("status")
            if status in {"online", "offline"}:
                self.node_status(node_id, status, "mqtt_status")
            return

        self.node_status(node_id, "online", message_type)
        self.emit(payload)

    def watchdog(self):
        while not self.stop_event.wait(min(0.5, self.offline_timeout / 2)):
            now = time.monotonic()
            for node_id, last_seen in list(self.last_seen.items()):
                if now - last_seen >= self.offline_timeout:
                    self.node_status(node_id, "offline", "timeout")

    def close(self):
        self.stop_event.set()
        if self.record_file is not None:
            self.record_file.close()


def parse_args():
    parser = argparse.ArgumentParser(description="Multi-node VSense MQTT collector")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--client-id", default="vsense-collector")
    parser.add_argument("--csi-topic", default="vsense/+/csi")
    parser.add_argument("--health-topic", default="vsense/+/health")
    parser.add_argument("--status-topic", default="vsense/+/status")
    parser.add_argument("--offline-timeout", type=float, default=5.0)
    parser.add_argument("--keepalive", type=int, default=30)
    parser.add_argument("--record", type=Path, help="Append all normalized messages to JSONL")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.offline_timeout <= 0:
        raise SystemExit("--offline-timeout must be positive")
    if not 15 <= args.keepalive <= 60:
        raise SystemExit("--keepalive must be between 15 and 60 seconds")
    collector = Collector(
        [args.csi_topic, args.health_topic, args.status_topic],
        args.offline_timeout,
        args.record,
    )
<<<<<<< Updated upstream
=======

    parser.add_argument(
        "--host",
        default="192.168.128.167",
        help="MQTT broker hostname or IP.",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=1883,
        help="MQTT broker port.",
    )

    parser.add_argument(
        "--topic",
        default="vsense/+/csi",
        help="MQTT CSI topic pattern.",
    )

    args = parser.parse_args()

    userdata = {
        "topic": args.topic,
    }

>>>>>>> Stashed changes
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=args.client_id,
        userdata=collector,
    )
    if args.username:
        client.username_pw_set(args.username, args.password)
    client.on_connect = collector.on_connect
    client.on_message = collector.on_message
    watchdog = threading.Thread(target=collector.watchdog, daemon=True)
    watchdog.start()
    print(f"Connecting to MQTT broker at {args.host}:{args.port}", file=sys.stderr)
    try:
        client.connect(args.host, args.port, keepalive=args.keepalive)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nStopping MQTT collector.", file=sys.stderr)
    finally:
        collector.close()
        client.disconnect()


if __name__ == "__main__":
    main()
