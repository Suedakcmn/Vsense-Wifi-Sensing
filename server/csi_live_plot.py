import argparse
import json
import queue
import sys
import threading
from pathlib import Path
from collections import deque

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import numpy as np

from csi_utils import (
    TemporalCSIFilter,
    csi_to_amplitude,
)


def message_to_amplitude(message):
    if "csi_amplitude" in message:
        amplitude = np.asarray(
            message["csi_amplitude"],
            dtype=np.float32,
        )
    elif "csi" in message:
        amplitude = np.asarray(
            csi_to_amplitude(message["csi"]),
            dtype=np.float32,
        )
    else:
        raise ValueError(
            "Message has neither 'csi' nor 'csi_amplitude'."
        )

    if amplitude.ndim != 1:
        raise ValueError("CSI amplitude must be one-dimensional.")

    return amplitude

def clean_amplitude(amplitude, edge_trim):
    amplitude = np.asarray(amplitude, dtype=np.float32)

    if edge_trim > 0:
        if len(amplitude) <= 2 * edge_trim:
            raise ValueError(
                "CSI amplitude is too short for the requested edge trim."
            )

        amplitude = amplitude[edge_trim:-edge_trim]

    median = float(np.median(amplitude))
    mad = float(
        np.median(np.abs(amplitude - median))
    )

    if mad > 1e-6:
        robust_z = np.abs(amplitude - median) / (1.4826 * mad)
        amplitude = np.where(
            robust_z > 5.0,
            median,
            amplitude,
        )

    return amplitude

def normalize_amplitude(amplitude):
    mean = float(np.mean(amplitude))
    std = float(np.std(amplitude))

    return (amplitude - mean) / (std + 1e-6)



def load_selected_indices(file_path):
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Selected subcarrier file does not exist: {path}"
        )

    content = path.read_text(encoding="utf-8").strip()

    if not content:
        raise ValueError(
            "Selected subcarrier file is empty."
        )

    indices = np.asarray(
        [
            int(value.strip())
            for value in content.split(",")
            if value.strip()
        ],
        dtype=np.int32,
    )

    if indices.size == 0:
        raise ValueError(
            "No selected subcarrier indices were loaded."
        )

    return indices


def stdin_reader(message_queue):
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
            print(
                f"Skipping invalid JSON line: {exc}",
                file=sys.stderr,
            )

        except Exception as exc:
            print(
                f"Skipping invalid CSI message: {exc}",
                file=sys.stderr,
            )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Live CSI motion score plotter."
    )

    parser.add_argument(
        "--edge-trim",
        type=int,
        default=4,
        help="Number of amplitude values removed from both edges.",
    )

    parser.add_argument(
        "--score-percentile",
        type=float,
        default=75.0,
        help="Percentile of frame differences used as motion score.",
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=0.75,
        help="Motion score threshold.",
    )

    parser.add_argument(
        "--window-size",
        type=int,
        default=20,
        help="Recent frame-difference scores used for smoothing.",
    )

    parser.add_argument(
        "--history",
        type=int,
        default=300,
        help="Number of score points shown on the graph.",
    )

    parser.add_argument(
        "--interval-ms",
        type=int,
        default=100,
        help="Graph refresh interval.",
    )

    parser.add_argument(
        "--start-count",
        type=int,
        default=3,
        help="Consecutive high scores required to start motion.",
    )

    parser.add_argument(
        "--stop-count",
        type=int,
        default=10,
        help="Consecutive low scores required to stop motion.",
    )


    parser.add_argument(
        "--selected-subcarriers",
        default="server/config/selected_subcarriers.txt",
        help=(
            "File containing comma-separated trimmed "
            "amplitude indices."
        ),
    )
    parser.add_argument(
        "--filter-history",
        type=int,
        default=15,
        help="Number of amplitude frames kept for temporal filtering.",
    )

    parser.add_argument(
        "--hampel-window",
        type=int,
        default=7,
        help="Recent frames used by the temporal Hampel filter.",
    )

    parser.add_argument(
        "--hampel-n-sigma",
        type=float,
        default=3.0,
        help="Hampel outlier threshold multiplier.",
    )

    parser.add_argument(
        "--savgol-window",
        type=int,
        default=7,
        help="Odd temporal window used by Savitzky-Golay filtering.",
    )

    parser.add_argument(
        "--savgol-polyorder",
        type=int,
        default=2,
        help="Polynomial order used by Savitzky-Golay filtering.",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    selected_indices = load_selected_indices(
        args.selected_subcarriers
    )
    temporal_filter = TemporalCSIFilter(
        history_size=args.filter_history,
        hampel_window=args.hampel_window,
        hampel_n_sigma=args.hampel_n_sigma,
        savgol_window=args.savgol_window,
        savgol_polyorder=args.savgol_polyorder,
    )

    print(
        f"Loaded {len(selected_indices)} selected CSI indices.",
        file=sys.stderr,
    )


    message_queue = queue.Queue(maxsize=500)

    score_buffer = deque(maxlen=args.window_size)
    frame_history = deque(maxlen=args.history)
    score_history = deque(maxlen=args.history)

    previous_normalized = None
    frame_count = 0

    is_moving = False
    high_count = 0
    low_count = 0

    print(
        "Reading CSI JSON lines from stdin. Press Ctrl+C to stop.",
        file=sys.stderr,
    )
    print(
        f"Motion threshold: {args.threshold:.3f}",
        file=sys.stderr,
    )
    print(
        f"Window size: {args.window_size}",
        file=sys.stderr,
    )

    reader_thread = threading.Thread(
        target=stdin_reader,
        args=(message_queue,),
        daemon=True,
    )
    reader_thread.start()

    fig, ax = plt.subplots()

    motion_line, = ax.plot(
        [],
        [],
        label="Motion score",
    )

    threshold_line = ax.axhline(
        args.threshold,
        linestyle="--",
        label="Threshold",
    )

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
        nonlocal previous_normalized
        nonlocal frame_count
        nonlocal is_moving
        nonlocal high_count
        nonlocal low_count

        latest_score = None
        latest_node_id = "unknown"
        latest_rssi = None

        while True:
            try:
                item = message_queue.get_nowait()
            except queue.Empty:
                break

            amplitude = item["amplitude"]

            cleaned = clean_amplitude(
                amplitude,
                args.edge_trim,
            )

            temporally_filtered = temporal_filter.process(
                cleaned
            )

            normalized = normalize_amplitude(
                temporally_filtered
            )

            latest_node_id = item["node_id"]
            latest_rssi = item["rssi"]
            latest_ts_us = item["ts_us"]

            if previous_normalized is None:
                previous_normalized = normalized
                continue

            if len(previous_normalized) != len(normalized):
                print(
                    "CSI vector length changed. Resetting score buffer.",
                    file=sys.stderr,
                )

                previous_normalized = normalized
                score_buffer.clear()
                temporal_filter.reset()
                high_count = 0
                low_count = 0
                is_moving = False
                continue

            frame_difference = np.abs(
                normalized - previous_normalized
            )

            if int(np.max(selected_indices)) >= len(frame_difference):
                raise ValueError(
                    "A selected CSI index is outside "
                    "the frame-difference vector."
                )

            selected_difference = frame_difference[
                selected_indices
            ]

            frame_score = float(
                np.mean(selected_difference)
            )
            score_buffer.append(frame_score)

            previous_normalized = normalized

            motion_score = float(np.mean(score_buffer))

            if motion_score > args.threshold:
                high_count += 1
                low_count = 0
            else:
                low_count += 1
                high_count = 0

            if not is_moving and high_count >= args.start_count:
                is_moving = True

                print(
                    f"EVENT=HAREKET "
                    f"ts_us={latest_ts_us} "
                    f"node_id={latest_node_id} "
                    f"motion_score={motion_score:.4f} "
                    f"threshold={args.threshold:.4f}",
                    file=sys.stderr,
                    flush=True,
                )

            elif is_moving and low_count >= args.stop_count:
                is_moving = False

                print(
                    f"EVENT=STILL "
                    f"ts_us={latest_ts_us} "
                    f"node_id={latest_node_id} "
                    f"motion_score={motion_score:.4f} "
                    f"threshold={args.threshold:.4f}",
                    file=sys.stderr,
                    flush=True,
                )

            frame_count += 1
            frame_history.append(frame_count)
            score_history.append(motion_score)

            latest_score = motion_score

        return latest_score, latest_node_id, latest_rssi

    def update(_frame):
        latest_score, latest_node_id, latest_rssi = (
            process_new_messages()
        )

        if not frame_history:
            status_text.set_text("Status: WAITING")
            return motion_line, threshold_line, status_text

        x = list(frame_history)
        y = list(score_history)

        motion_line.set_data(x, y)

        x_min = max(0, x[-1] - args.history)
        x_max = max(args.history, x[-1] + 1)
        ax.set_xlim(x_min, x_max)

        y_max = max(max(y), args.threshold, 0.1)
        ax.set_ylim(0, y_max * 1.2)

        if latest_score is not None:
            status = "HAREKET" if is_moving else "STILL"

            status_text.set_text(
                f"Status: {status}\n"
                f"Score: {latest_score:.4f}\n"
                f"Threshold: {args.threshold:.4f}\n"
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