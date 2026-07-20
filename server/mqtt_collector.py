import argparse
import json
import sys

import paho.mqtt.client as mqtt


def on_connect(client, userdata, flags, reason_code, properties):
    """Called when connection to MQTT broker succeeds or fails."""
    if reason_code == 0:
        topic = userdata["topic"]

        print(
            f"Connected to MQTT broker. Subscribing to: {topic}",
            file=sys.stderr,
        )

        client.subscribe(topic)

    else:
        print(
            f"MQTT connection failed. Reason code: {reason_code}",
            file=sys.stderr,
        )


def on_message(client, userdata, msg):
    """Receive MQTT message and forward valid JSON to stdout."""
    try:
        payload = msg.payload.decode("utf-8")
        message = json.loads(payload)

    except UnicodeDecodeError as exc:
        print(
            f"Skipping non-UTF8 MQTT message: {exc}",
            file=sys.stderr,
        )
        return

    except json.JSONDecodeError as exc:
        print(
            f"Skipping invalid JSON message: {exc}",
            file=sys.stderr,
        )
        return

    # Topic format:
    # vsense/{node_id}/csi
    topic_parts = msg.topic.split("/")

    if "node_id" not in message and len(topic_parts) >= 3:
        message["node_id"] = topic_parts[1]

    # IMPORTANT:
    # Only JSON goes to stdout.
    # This allows:
    #
    # mqtt_collector.py | csi_live.py
    #
    print(
        json.dumps(message),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(
        description="VSense MQTT CSI collector."
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
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

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        userdata=userdata,
    )

    client.on_connect = on_connect
    client.on_message = on_message

    print(
        f"Connecting to MQTT broker at "
        f"{args.host}:{args.port}",
        file=sys.stderr,
    )

    try:
        client.connect(
            args.host,
            args.port,
            keepalive=60,
        )

        client.loop_forever()

    except KeyboardInterrupt:
        print(
            "\nStopping MQTT collector.",
            file=sys.stderr,
        )

    except Exception as exc:
        print(
            f"MQTT collector error: {exc}",
            file=sys.stderr,
        )
        raise


if __name__ == "__main__":
    main()