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

            if message.get("message_type") == "node_status":
                message_queue.put(
                    {
                        "message_type": "node_status",
                        "node_id": message.get("node_id", "unknown"),
                        "status": message.get("status", "unknown"),
                    }
                )
                continue

            if message.get("message_type", "csi") != "csi":
                continue

            amplitude = message_to_amplitude(message)

            message_queue.put(
                {
                    "message_type": "csi",
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


def create_node_state(args):
    return {
        "temporal_filter": TemporalCSIFilter(
            history_size=args.filter_history,
            hampel_window=args.hampel_window,
            hampel_n_sigma=args.hampel_n_sigma,
            savgol_window=args.savgol_window,
            savgol_polyorder=args.savgol_polyorder,
        ),
        "score_buffer": deque(maxlen=args.window_size),
        "frame_history": deque(maxlen=args.history),
        "score_history": deque(maxlen=args.history),
        "previous_normalized": None,
        "frame_count": 0,
        "is_moving": False,
        "high_count": 0,
        "low_count": 0,
        "connection_status": "online",
        "latest_score": None,
        "latest_rssi": None,
    }


def main():
    args = parse_args()

    selected_indices = load_selected_indices(
        args.selected_subcarriers
    )
    print(
        f"Loaded {len(selected_indices)} selected CSI indices.",
        file=sys.stderr,
    )


    message_queue = queue.Queue(maxsize=500)

    node_states = {}
    node_lines = {}

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

    threshold_line = ax.axhline(
        args.threshold,
        linestyle="--",
        label="Threshold",
    )

    ax.set_title("Live CSI Motion Score by Receiver")
    ax.set_xlabel("Frame")
    ax.set_ylabel("Motion score")
    ax.legend()

    status_text = ax.text(
        0.02,
        0.95,
        "Waiting for receiver nodes...",
        transform=ax.transAxes,
        verticalalignment="top",
    )

    def get_node_state(node_id):
        if node_id not in node_states:
            node_states[node_id] = create_node_state(args)
            node_lines[node_id], = ax.plot([], [], label=node_id)
            ax.legend()
            print(f"New CSI node detected: {node_id}", file=sys.stderr)
        return node_states[node_id]

    def process_new_messages():
        while True:
            try:
                item = message_queue.get_nowait()
            except queue.Empty:
                break

            node_id = item["node_id"]
            state = get_node_state(node_id)

            if item["message_type"] == "node_status":
                state["connection_status"] = item["status"]
                continue

            state["connection_status"] = "online"
            amplitude = item["amplitude"]

            cleaned = clean_amplitude(
                amplitude,
                args.edge_trim,
            )

            temporally_filtered = state["temporal_filter"].process(
                cleaned
            )

            normalized = normalize_amplitude(
                temporally_filtered
            )

            state["latest_rssi"] = item["rssi"]
            latest_ts_us = item["ts_us"]

            if state["previous_normalized"] is None:
                state["previous_normalized"] = normalized
                continue

            if len(state["previous_normalized"]) != len(normalized):
                print(
                    f"CSI vector length changed for {node_id}. "
                    "Resetting its score buffer.",
                    file=sys.stderr,
                )

                state["previous_normalized"] = normalized
                state["score_buffer"].clear()
                state["temporal_filter"].reset()
                state["high_count"] = 0
                state["low_count"] = 0
                state["is_moving"] = False
                continue

            frame_difference = np.abs(
                normalized - state["previous_normalized"]
            )

            if int(np.max(selected_indices)) >= len(frame_difference):
                print(
                    f"Skipping frame for {node_id}: selected CSI index "
                    "is outside the frame-difference vector.",
                    file=sys.stderr,
                )
                continue

            selected_difference = frame_difference[
                selected_indices
            ]

            frame_score = float(
                np.mean(selected_difference)
            )
            state["score_buffer"].append(frame_score)

            state["previous_normalized"] = normalized

            motion_score = float(np.mean(state["score_buffer"]))

            if motion_score > args.threshold:
                state["high_count"] += 1
                state["low_count"] = 0
            else:
                state["low_count"] += 1
                state["high_count"] = 0

            if (
                not state["is_moving"]
                and state["high_count"] >= args.start_count
            ):
                state["is_moving"] = True

                print(
                    f"EVENT=HAREKET "
                    f"ts_us={latest_ts_us} "
                    f"node_id={node_id} "
                    f"motion_score={motion_score:.4f} "
                    f"threshold={args.threshold:.4f}",
                    file=sys.stderr,
                    flush=True,
                )

            elif (
                state["is_moving"]
                and state["low_count"] >= args.stop_count
            ):
                state["is_moving"] = False

                print(
                    f"EVENT=STILL "
                    f"ts_us={latest_ts_us} "
                    f"node_id={node_id} "
                    f"motion_score={motion_score:.4f} "
                    f"threshold={args.threshold:.4f}",
                    file=sys.stderr,
                    flush=True,
                )

            state["frame_count"] += 1
            state["frame_history"].append(state["frame_count"])
            state["score_history"].append(motion_score)
            state["latest_score"] = motion_score

    def update(_frame):
        process_new_messages()

        latest_frames = []
        all_scores = []
        status_rows = []

        for node_id, state in sorted(node_states.items()):
            x = list(state["frame_history"])
            y = list(state["score_history"])
            node_lines[node_id].set_data(x, y)
            node_lines[node_id].set_alpha(
                1.0 if state["connection_status"] == "online" else 0.3
            )
            if x:
                latest_frames.append(x[-1])
                all_scores.extend(y)

            motion = "HAREKET" if state["is_moving"] else "STILL"
            score = (
                f"{state['latest_score']:.4f}"
                if state["latest_score"] is not None
                else "-"
            )
            status_rows.append(
                f"{node_id}: {state['connection_status'].upper()} | "
                f"{motion} | score={score} | RSSI={state['latest_rssi']}"
            )

        if latest_frames:
            newest_frame = max(latest_frames)
            ax.set_xlim(
                max(0, newest_frame - args.history),
                max(args.history, newest_frame + 1),
            )
            ax.set_ylim(
                0,
                max(max(all_scores), args.threshold, 0.1) * 1.2,
            )

        status_text.set_text(
            "\n".join(status_rows) if status_rows
            else "Waiting for receiver nodes..."
        )

        return [*node_lines.values(), threshold_line, status_text]

    animation = FuncAnimation(
        fig,
        update,
        interval=args.interval_ms,
        cache_frame_data=False,
    )

    plt.show()


if __name__ == "__main__":
    main()
