import json
import sys
from collections import deque

import numpy as np

from csi_utils import csi_to_amplitude


def message_to_amplitude(message):
    if "csi_amplitude" in message:
        return np.array(message["csi_amplitude"], dtype=np.float32)

    if "csi" in message:
        return csi_to_amplitude(message["csi"])

    raise ValueError("Message has neither 'csi' nor 'csi_amplitude'.")


def main():
    buffer = deque(maxlen=100)

    print("Reading CSI JSON lines from stdin. Press Ctrl+C to stop.", file=sys.stderr)

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
            continue

        print(
            f"ts_us={message.get('ts_us', '')} "
            f"node_id={message.get('node_id', '')} "
            f"rssi={message.get('rssi', '')} "
            f"motion_score={motion_score:.2f}",
            flush=True,
        )


if __name__ == "__main__":
    main()
