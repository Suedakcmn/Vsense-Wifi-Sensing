import argparse
import json
import sys
from collections import deque

import numpy as np

from csi_utils import csi_to_amplitude

def parse_args():
    parser = argparse.ArgumentParser(
        description="Read CSI JSON lines from stdin and compute a simple motion score."
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=0.15,
        help="Motion score threshold. If motion_score is above this value, motion is detected.",
    )

    return parser.parse_args()


def message_to_amplitude(message):
    if "csi_amplitude" in message:
        return np.array(message["csi_amplitude"], dtype=np.float32)

    if "csi" in message:
        return csi_to_amplitude(message["csi"])

    raise ValueError("Message has neither 'csi' nor 'csi_amplitude'.")


def main():
    args = parse_args()
    threshold = args.threshold
    buffer = deque(maxlen=100)
    was_moving = False

    print("Reading CSI JSON lines from stdin. Press Ctrl+C to stop.", file=sys.stderr)
    print(f"Motion threshold: {threshold:.3f}", file=sys.stderr)

    for line in sys.stdin:
        line = line.strip()

        if not line:
            continue

        try:
            message = json.loads(line)
            amplitude = message_to_amplitude(message)
        except json.JSONDecodeError as exc:
            print(f"Skipping invalid JSON line: {exc}", file=sys.stderr)
            continue
        except Exception as exc:
            print(f"Skipping invalid CSI message: {exc}", file=sys.stderr)
            continue

        buffer.append(amplitude)

        try:
            matrix = np.stack(buffer)
            motion_score = matrix.var() if len(buffer) > 1 else 0.0
        except ValueError:
            print("Skipping frame because CSI vector length changed.", file=sys.stderr)
            buffer.clear()
            was_moving = False
            continue

        is_moving = motion_score > threshold
        status = "HAREKET" if is_moving else "STILL"

        print(
            f"ts_us={message.get('ts_us', '')} "
            f"node_id={message.get('node_id', '')} "
            f"rssi={message.get('rssi', '')} "
            f"motion_score={motion_score:.2f}",
            f"threshold={threshold:.2f} "
            f"status={status}",
            flush=True,
        )

        if is_moving and not was_moving:
            print(
                f"EVENT=HAREKET "
                f"ts_us={message.get('ts_us', '')} "
                f"node_id={message.get('node_id', '')} "
                f"motion_score={motion_score:.2f} "
                f"threshold={threshold:.2f}",
                file=sys.stderr,
                flush=True,
            )

        was_moving = is_moving


if __name__ == "__main__":
    main()
