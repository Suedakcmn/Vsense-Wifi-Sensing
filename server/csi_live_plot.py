import argparse
import json
import queue
import sys
import threading
from collections import deque

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import numpy as np

from csi_utils import csi_to_amplitude


def message_to_amplitude(message):
    """
    Convert one CSI JSON message into amplitude.

    Accepted formats:

    1) Raw CSI format:
       {
         "ts_us": 1,
         "node_id": "rx_01",
         "rssi": -55,
         "csi": [imag0, real0, imag1, real1, ...]
       }

    2) Precomputed amplitude format:
       {
         "ts_us": 1,
         "node_id": "rx_01",
         "rssi": -55,
         "csi_amplitude": [5.0, 5.38, ...]
       }
    """
    if "csi_amplitude" in message:
        return np.array(message["csi_amplitude"], dtype=np.float32)

    if "csi" in message:
        return csi_to_amplitude(message["csi"])

    raise ValueError("Message has neither 'csi' nor 'csi_amplitude'.")


def stdin_reader(message_queue):
    """
    Read JSON lines from stdin in a background thread.

    Why background thread?
    - matplotlib must keep updating the graph.
    - sys.stdin.readline() can block.
    - So we read input separately and send parsed messages to the graph loop.
    """
    for line in sys.stdin:
        line = line.strip()

        if not line:
            continue

        try:
            message = json.loads(line)
            amplitude = message_to_amplitude(message)

            message_queue.put(
                {
                    "ts_us": message.get("ts_us"),
                    "node_id": message.get("node_id", "unknown"),
                    "rssi": message.get("rssi"),
                    "amplitude": amplitude,
                }
            )

        except json.JSONDecodeError as exc:
            print(f"Skipping invalid JSON line: {exc}", file=sys.stderr)

        except Exception as exc:
            print(f"Skipping invalid CSI message: {exc}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Live CSI motion score plotter from JSON lines."
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=50.0,
        help="Motion threshold. If motion_score > threshold, status becomes HAREKET.",
    )

    parser.add_argument(
        "--window",
        type=int,
        default=100,
        help="Number of recent CSI frames used to compute motion score.",
    )

    parser.add_argument(
        "--history",
        type=int,
        default=300,
        help="Number of motion score points shown on the graph.",
    )

    parser.add_argument(
        "--interval-ms",
        type=int,
        default=100,
        help="Graph refresh interval in milliseconds.",
    )

    args = parser.parse_args()

    message_queue = queue.Queue()

    # Recent amplitude frames for motion score calculation.
    amplitude_buffer = deque(maxlen=args.window)

    # Data shown on graph.
    frame_history = deque(maxlen=args.history)
    score_history = deque(maxlen=args.history)

    frame_count = 0
    last_amplitude_len = None
    last_status = "STILL"

    print("Reading CSI JSON lines from stdin. Press Ctrl+C to stop.", file=sys.stderr)
    print(f"Motion threshold: {args.threshold:.3f}", file=sys.stderr)

    reader_thread = threading.Thread(
        target=stdin_reader,
        args=(message_queue,),
        daemon=True,
    )
    reader_thread.start()

    fig, ax = plt.subplots()

    motion_line, = ax.plot([], [], label="Motion score")
    threshold_line = ax.axhline(args.threshold, linestyle="--", label="Threshold")

    ax.set_title("Live CSI Motion Score")
    ax.set_xlabel("Frame")
    ax.set_ylabel("Motion score")
    ax.legend()

    status_text = ax.text(
        0.02,
        0.95,
        "Status: WAITING",
        transform=ax.transAxes,
        verticalalignment="top",
    )

    def process_new_messages():
        nonlocal frame_count
        nonlocal last_amplitude_len
        nonlocal last_status

        latest_status = last_status
        latest_score = None
        latest_node_id = "unknown"
        latest_rssi = None
        latest_ts_us = None

        while True:
            try:
                item = message_queue.get_nowait()
            except queue.Empty:
                break

            amplitude = item["amplitude"]
            latest_node_id = item["node_id"]
            latest_rssi = item["rssi"]
            latest_ts_us = item["ts_us"]

            # If CSI length changes, np.stack will fail.
            # Example: sometimes len=256, sometimes len=128.
            # For v0, reset the buffer when length changes.
            if last_amplitude_len is None:
                last_amplitude_len = len(amplitude)

            if len(amplitude) != last_amplitude_len:
                print(
                    f"CSI amplitude length changed from {last_amplitude_len} "
                    f"to {len(amplitude)}. Resetting buffer.",
                    file=sys.stderr,
                )
                amplitude_buffer.clear()
                last_amplitude_len = len(amplitude)

            amplitude_buffer.append(amplitude)
            frame_count += 1

            if len(amplitude_buffer) < 2:
                motion_score = 0.0
            else:
                matrix = np.stack(amplitude_buffer)

                # Variance over time for each subcarrier.
                subcarrier_variance = np.var(matrix, axis=0)

                # Collapse all subcarrier variances into one motion score.
                motion_score = float(np.mean(subcarrier_variance))

            status = "HAREKET" if motion_score > args.threshold else "STILL"

            frame_history.append(frame_count)
            score_history.append(motion_score)

            latest_score = motion_score
            latest_status = status

            print(
                f"ts_us={latest_ts_us} "
                f"node_id={latest_node_id} "
                f"rssi={latest_rssi} "
                f"motion_score={motion_score:.2f} "
                f"threshold={args.threshold:.2f} "
                f"status={status}"
            )

            # Event log: only print when status changes.
            if status == "HAREKET" and last_status != "HAREKET":
                print(
                    f"EVENT=HAREKET "
                    f"ts_us={latest_ts_us} "
                    f"node_id={latest_node_id} "
                    f"motion_score={motion_score:.2f} "
                    f"threshold={args.threshold:.2f}"
                )

            if status == "STILL" and last_status == "HAREKET":
                print(
                    f"EVENT=STILL "
                    f"ts_us={latest_ts_us} "
                    f"node_id={latest_node_id} "
                    f"motion_score={motion_score:.2f} "
                    f"threshold={args.threshold:.2f}"
                )

            last_status = status

        return latest_score, latest_status, latest_node_id, latest_rssi

    def update(_frame):
        latest_score, latest_status, latest_node_id, latest_rssi = process_new_messages()

        if not frame_history:
            status_text.set_text("Status: WAITING")
            return motion_line, threshold_line, status_text

        x = list(frame_history)
        y = list(score_history)

        motion_line.set_data(x, y)

        x_min = max(0, x[-1] - args.history)
        x_max = max(args.history, x[-1] + 1)
        ax.set_xlim(x_min, x_max)

        y_max = max(max(y), args.threshold, 1.0)
        ax.set_ylim(0, y_max * 1.2)

        if latest_score is not None:
            status_text.set_text(
                f"Status: {latest_status}\n"
                f"Score: {latest_score:.2f}\n"
                f"Threshold: {args.threshold:.2f}\n"
                f"Node: {latest_node_id}\n"
                f"RSSI: {latest_rssi}"
            )

        return motion_line, threshold_line, status_text

    animation = FuncAnimation(
        fig,
        update,
        interval=args.interval_ms,
        cache_frame_data=False,
    )

    plt.show()


if __name__ == "__main__":
    main()