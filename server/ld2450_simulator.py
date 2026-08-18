import argparse
import json
import math
import sys
import time


SCHEMA_VERSION = 1
MESSAGE_TYPE = "ground_truth"
MAX_TARGETS = 3


def positive_float(value):
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return number


def target_count(value):
    count = int(value)
    if count < 0 or count > MAX_TARGETS:
        raise argparse.ArgumentTypeError(
            f"target count must be between 0 and {MAX_TARGETS}"
        )
    return count


def simulated_target(target_id, elapsed_seconds):
    phase = elapsed_seconds + ((target_id - 1) * 1.3)
    x_mm = round(1400 * math.sin(phase * 0.55))
    y_mm = round(2200 + 900 * math.cos(phase * 0.35))
    speed_cm_s = round(77 * math.cos(phase * 0.55))

    return {
        "target_id": target_id,
        "x_mm": x_mm,
        "y_mm": y_mm,
        "speed_cm_s": speed_cm_s,
        "distance_mm": round(math.hypot(x_mm, y_mm)),
        "resolution_mm": 320,
    }


def ground_truth_message(node_id, ts_us, frame_seq, count, elapsed_seconds):
    return {
        "schema_version": SCHEMA_VERSION,
        "message_type": MESSAGE_TYPE,
        "node_id": node_id,
        "ts_us": ts_us,
        "frame_seq": frame_seq,
        "targets": [
            simulated_target(target_id, elapsed_seconds)
            for target_id in range(1, count + 1)
        ],
    }


def build_parser():
    parser = argparse.ArgumentParser(
        description="Publish deterministic simulated LD2450 ground truth."
    )
    parser.add_argument(
        "--transport",
        choices=["stdout", "mqtt"],
        default="stdout",
        help="Print JSON locally or publish it to MQTT",
    )
    parser.add_argument(
        "--broker-host",
        default="127.0.0.1",
        help="MQTT broker hostname or IP",
    )
    parser.add_argument(
        "--broker-port",
        type=int,
        default=1883,
        help="MQTT broker port",
    )
    parser.add_argument(
        "--topic",
        default="vsense/gt/ld2450_01",
        help="Ground-truth MQTT topic",
    )
    parser.add_argument(
        "--node-id",
        default="ld2450_01",
        help="Node ID placed in each message",
    )
    parser.add_argument(
        "--rate-hz",
        type=positive_float,
        default=10.0,
        help="Messages per second",
    )
    parser.add_argument(
        "--duration-seconds",
        type=positive_float,
        default=10.0,
        help="Simulation duration",
    )
    parser.add_argument(
        "--target-count",
        type=target_count,
        default=1,
        help="Number of simulated targets (0-3)",
    )
    return parser


def connect_mqtt(host, port):
    try:
        import paho.mqtt.client as mqtt
    except ImportError as exc:
        raise SystemExit(
            "MQTT transport requires paho-mqtt. "
            "Install server/requirements.txt first."
        ) from exc

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(host, port, keepalive=30)
    client.loop_start()
    return client


def run(args):
    client = None
    if args.transport == "mqtt":
        client = connect_mqtt(args.broker_host, args.broker_port)

    interval_seconds = 1.0 / args.rate_hz
    total_frames = max(1, math.ceil(args.duration_seconds * args.rate_hz))
    started_at = time.monotonic()

    try:
        for frame_seq in range(total_frames):
            deadline = started_at + (frame_seq * interval_seconds)
            delay = deadline - time.monotonic()
            if delay > 0:
                time.sleep(delay)

            elapsed_seconds = frame_seq * interval_seconds
            message = ground_truth_message(
                args.node_id,
                round(elapsed_seconds * 1_000_000),
                frame_seq,
                args.target_count,
                elapsed_seconds,
            )
            payload = json.dumps(message, separators=(",", ":"))

            if client is None:
                print(payload, flush=True)
            else:
                result = client.publish(args.topic, payload, qos=0, retain=False)
                if result.rc != 0:
                    raise RuntimeError(
                        f"MQTT publish failed for frame {frame_seq}: rc={result.rc}"
                    )
    finally:
        if client is not None:
            client.loop_stop()
            client.disconnect()

    return total_frames


def main():
    args = build_parser().parse_args()
    frame_count = run(args)
    print(
        f"Simulated {frame_count} LD2450 frames via {args.transport}.",
        file=sys.stderr if args.transport == "stdout" else sys.stdout,
        flush=True,
    )


if __name__ == "__main__":
    main()
