import json
import sys
from collections import deque

import numpy as np

from csi_utils import csi_to_amplitude


def main():
    buffer = deque(maxlen=100)

    print("Reading CSI JSON lines from stdin. Press Ctrl+C to stop.")

    for line in sys.stdin:
        message = json.loads(line)
        amplitude = csi_to_amplitude(message["csi"])

        buffer.append(amplitude)
        matrix = np.array(buffer)

        motion_score = matrix.var() if len(buffer) > 1 else 0.0

        print(
            f"ts_us={message['ts_us']} "
            f"node_id={message['node_id']} "
            f"rssi={message['rssi']} "
            f"motion_score={motion_score:.2f}"
        )


if __name__ == "__main__":
    main()