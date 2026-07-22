import argparse
import json
import time
from pathlib import Path

import pandas as pd
import paho.mqtt.client as mqtt


def to_jsonable(value):
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def get_rssi(row):
    if "rssi" in row and pd.notna(row["rssi"]):
        return int(row["rssi"])

    candidates = []

    for col in ["rssi_a", "rssi_b", "rssi_c"]:
        if col in row and pd.notna(row[col]):
            candidates.append(int(row[col]))

    if candidates:
        return max(candidates)

    return 0


def parquet_messages(path, node_id):
    df = pd.read_parquet(path)

    for index, row in df.iterrows():
        message = {
            "ts_us": (
                int(row["ts_us"])
                if "ts_us" in row and pd.notna(row["ts_us"])
                else int(index)
            ),
            "node_id": (
                str(row["node_id"])
                if "node_id" in row and pd.notna(row["node_id"])
                else node_id
            ),
            "rssi": get_rssi(row),
            "label": (
                str(row["label"])
                if "label" in row and pd.notna(row["label"])
                else ""
            ),
        }

        if "csi" in row and row["csi"] is not None:
            message["csi"] = to_jsonable(row["csi"])

        elif "csi_amplitude" in row and row["csi_amplitude"] is not None:
            message["csi_amplitude"] = to_jsonable(
                row["csi_amplitude"]
            )

        else:
            continue

        yield message


def jsonl_messages(path, node_id, override_node_id=False):
    with open(path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                print(
                    f"Skipping invalid JSON on line "
                    f"{line_number}: {exc}"
                )
                continue

            if override_node_id or "node_id" not in message:
                message["node_id"] = node_id

            yield message


def load_messages(path, node_id, override_node_id=False):
    suffix = Path(path).suffix.lower()

    if suffix == ".parquet":
        return parquet_messages(path, node_id)

    if suffix == ".jsonl":
        return jsonl_messages(
    path,
    node_id,
    override_node_id,
)

    raise ValueError(
        f"Unsupported input format: {suffix}. "
        "Use .jsonl or .parquet."
    )


def main():
    parser = argparse.ArgumentParser(
        description="Replay recorded CSI data."
    )

    parser.add_argument(
        "input",
        help="Path to CSI .jsonl or .parquet file",
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=0.05,
        help="Delay between frames in seconds",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of frames to replay",
    )

    parser.add_argument(
        "--node-id",
        default="replay_rx_01",
        help="Default node ID",
    )

    parser.add_argument(
        "--transport",
        choices=["stdout", "mqtt"],
        default="stdout",
        help="Where replayed CSI messages are sent",
    )

    parser.add_argument(
        "--mqtt-host",
        default="127.0.0.1",
        help="MQTT broker hostname or IP",
    )

    parser.add_argument(
        "--mqtt-port",
        type=int,
        default=1883,
        help="MQTT broker port",
    )
    parser.add_argument(
    "--override-node-id",
    action="store_true",
    help="Replace node_id in recorded messages with --node-id",
)
    args = parser.parse_args()

    client = None

    if args.transport == "mqtt":
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2
        )

        client.connect(
            args.mqtt_host,
            args.mqtt_port,
            keepalive=60,
        )

        client.loop_start()

        print(
            f"Connected to MQTT broker at "
            f"{args.mqtt_host}:{args.mqtt_port}"
        )

    messages = load_messages(
    args.input,
    args.node_id,
    args.override_node_id,
)

    count = 0

    try:
        for message in messages:
            if args.limit is not None and count >= args.limit:
                break

            if args.transport == "stdout":
                print(
                    json.dumps(message),
                    flush=True,
                )

            else:
                node_id = message.get(
                    "node_id",
                    args.node_id,
                )

                topic = f"vsense/{node_id}/csi"

                client.publish(
                    topic,
                    json.dumps(message),
                    qos=0,
                )

            count += 1

            time.sleep(args.delay)

    except KeyboardInterrupt:
        print("\nReplay stopped.")

    finally:
        if client is not None:
            time.sleep(0.2)
            client.loop_stop()
            client.disconnect()

    print(f"Replayed {count} CSI frames.")


if __name__ == "__main__":
    main()