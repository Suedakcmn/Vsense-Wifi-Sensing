"""Subscribe to VSense CSI/radar nodes and expose normalized JSONL streams."""

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt

from vsense_binary import MAGIC as CSI_BINARY_MAGIC
from vsense_binary import decode_csi_packet


def collector_timestamp_us():
    return time.time_ns() // 1_000


def utc_from_timestamp_us(timestamp_us):
    return datetime.fromtimestamp(
        timestamp_us / 1_000_000,
        tz=timezone.utc,
    ).isoformat()


class Collector:
    def __init__(
        self,
        topics,
        offline_timeout=5.0,
        record=None,
        session_dir=None,
        session_id=None,
    ):
        self.topics = topics
        self.offline_timeout = offline_timeout
        self.last_seen = {}
        self.states = {}
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.record_file = None
        self.session_files = {}
        self.session_id = session_id
        if record is not None:
            record.parent.mkdir(parents=True, exist_ok=True)
            self.record_file = record.open("a", encoding="utf-8")
        if session_dir is not None:
            session_dir.mkdir(parents=True, exist_ok=True)
            for message_group, file_name in {
                "csi": "csi.jsonl",
                "ground_truth": "ground_truth.jsonl",
                "telemetry": "telemetry.jsonl",
            }.items():
                self.session_files[message_group] = (
                    session_dir / file_name
                ).open("a", encoding="utf-8")

    def session_file_for(self, message):
        message_type = message.get("message_type")
        if message_type == "csi":
            return self.session_files.get("csi")
        if message_type == "ground_truth":
            return self.session_files.get("ground_truth")
        return self.session_files.get("telemetry")

    def emit(self, message):
        if self.session_id is not None:
            message.setdefault("session_id", self.session_id)
        line = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        with self.lock:
            print(line, flush=True)
            if self.record_file is not None:
                self.record_file.write(line + "\n")
                self.record_file.flush()
            session_file = self.session_file_for(message)
            if session_file is not None:
                session_file.write(line + "\n")
                session_file.flush()

    def node_status(self, node_id, status, source):
        if self.states.get(node_id) == status:
            return
        self.states[node_id] = status
        collected_at_us = collector_timestamp_us()
        self.emit({
            "schema_version": 2,
            "message_type": "node_status",
            "node_id": node_id,
            "status": status,
            "source": source,
            "recorded_at": utc_from_timestamp_us(collected_at_us),
            "collector_ts_us": collected_at_us,
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
        if parts[1] == "gt":
            node_id, message_type = parts[2], "ground_truth"
        else:
            node_id, message_type = parts[1], parts[2]
        if message_type == "csi" and msg.payload.startswith(CSI_BINARY_MAGIC):
            try:
                payload = decode_csi_packet(msg.payload)
            except ValueError as exc:
                print(
                    f"Skipping invalid binary CSI on {msg.topic}: {exc}",
                    file=sys.stderr,
                )
                return
        else:
            try:
                payload = json.loads(msg.payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                print(
                    f"Skipping invalid payload on {msg.topic}: {exc}",
                    file=sys.stderr,
                )
                return
        if not isinstance(payload, dict):
            print(f"Skipping non-object payload on {msg.topic}", file=sys.stderr)
            return

        now = time.monotonic()
        self.last_seen[node_id] = now
        payload["node_id"] = node_id  # topic identity is authoritative
        if message_type == "ground_truth":
            payload["schema_version"] = 1
        else:
            payload.setdefault("schema_version", 2)
        payload["message_type"] = message_type
        payload["mqtt_topic"] = msg.topic
        collected_at_us = collector_timestamp_us()
        payload["recorded_at"] = utc_from_timestamp_us(collected_at_us)
        payload["collector_ts_us"] = collected_at_us

        if message_type == "status":
            status = payload.get("status")
            if status in {"online", "offline"}:
                self.node_status(node_id, status, "mqtt_status")
            return

        if message_type == "ground_truth":
            error = validate_ground_truth(payload)
            if error is not None:
                print(
                    f"Skipping invalid ground-truth payload on "
                    f"{msg.topic}: {error}",
                    file=sys.stderr,
                )
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
        for session_file in self.session_files.values():
            session_file.close()


def validate_ground_truth(payload):
    """Return an error string for an invalid LD2450 message, otherwise None."""
    for field in ("ts_us", "frame_seq", "targets"):
        if field not in payload:
            return f"missing required field: {field}"
    if not isinstance(payload["ts_us"], int):
        return "ts_us must be an integer"
    if not isinstance(payload["frame_seq"], int):
        return "frame_seq must be an integer"
    if not isinstance(payload["targets"], list):
        return "targets must be a list"

    required_target_fields = (
        "target_id",
        "x_mm",
        "y_mm",
        "speed_cm_s",
        "resolution_mm",
    )
    for index, target in enumerate(payload["targets"]):
        if not isinstance(target, dict):
            return f"targets[{index}] must be an object"
        for field in required_target_fields:
            if field not in target:
                return f"targets[{index}] missing required field: {field}"
            if not isinstance(target[field], int):
                return f"targets[{index}].{field} must be an integer"
        if "distance_mm" in target and not isinstance(target["distance_mm"], int):
            return f"targets[{index}].distance_mm must be an integer"
    return None


def parse_args():
    parser = argparse.ArgumentParser(description="Multi-node VSense MQTT collector")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument(
        "--password-env",
        help="Read the MQTT password from this environment variable",
    )
    parser.add_argument("--client-id", default="vsense-collector")
    parser.add_argument("--csi-topic", default="vsense/+/csi")
    parser.add_argument("--health-topic", default="vsense/+/health")
    parser.add_argument("--status-topic", default="vsense/+/status")
    parser.add_argument("--ground-truth-topic", default="vsense/gt/+")
    parser.add_argument("--offline-timeout", type=float, default=5.0)
    parser.add_argument("--keepalive", type=int, default=30)
    parser.add_argument("--record", type=Path, help="Append all normalized messages to JSONL")
    parser.add_argument(
        "--session-dir",
        type=Path,
        help="Write CSI, ground truth, and telemetry to separate JSONL files",
    )
    parser.add_argument("--session-id", help="Session identifier added to every row")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.offline_timeout <= 0:
        raise SystemExit("--offline-timeout must be positive")
    if not 15 <= args.keepalive <= 60:
        raise SystemExit("--keepalive must be between 15 and 60 seconds")
    collector = Collector(
        [
            args.csi_topic,
            args.health_topic,
            args.status_topic,
            args.ground_truth_topic,
        ],
        args.offline_timeout,
        args.record,
        args.session_dir,
        args.session_id,
    )
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=args.client_id,
        userdata=collector,
    )
    if args.password and args.password_env:
        raise SystemExit("use only one of --password or --password-env")
    password = args.password
    if args.password_env:
        password = os.environ.get(args.password_env)
        if password is None:
            raise SystemExit(
                f"MQTT password environment variable is not set: {args.password_env}"
            )
    if args.username:
        client.username_pw_set(args.username, password)
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
