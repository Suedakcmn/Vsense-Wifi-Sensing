import argparse
import json
import sys
from pathlib import Path
from collections import deque

import numpy as np

from csi_utils import (
    TemporalCSIFilter,
    csi_to_amplitude,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Read CSI JSON lines from stdin and detect motion."
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
        help="Number of recent frame differences used for smoothing.",
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
        help="File containing comma-separated trimmed amplitude indices.",
    )

    parser.add_argument(
        "--filter-history",
        type=int,
        default=15,
    )

    parser.add_argument(
        "--hampel-window",
        type=int,
        default=7,
    )

    parser.add_argument(
        "--hampel-n-sigma",
        type=float,
        default=3.0,
    )

    parser.add_argument(
        "--savgol-window",
        type=int,
        default=7,
    )

    parser.add_argument(
        "--savgol-polyorder",
        type=int,
        default=2,
    )

    return parser.parse_args()


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

    content = path.read_text(
        encoding="utf-8"
    ).strip()

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
        "previous_normalized": None,
        "is_moving": False,
        "high_count": 0,
        "low_count": 0,
    }

def main():
    args = parse_args()

    selected_indices = load_selected_indices(
        args.selected_subcarriers
    )

    # Her node kendi state'ine sahip olacak.
    node_states = {}

    print(
        f"Loaded {len(selected_indices)} selected CSI indices.",
        file=sys.stderr,
    )

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

    for line in sys.stdin:
        line = line.strip()

        if not line:
            continue

        try:
            message = json.loads(line)

            # Mesajın hangi RX node'dan geldiğini bul.
            node_id = message.get(
                "node_id",
                "unknown",
            )

            # Bu node'u ilk defa görüyorsak
            # ona özel state oluştur.
            if node_id not in node_states:
                node_states[node_id] = create_node_state(
                    args
                )

                print(
                    f"New CSI node detected: {node_id}",
                    file=sys.stderr,
                )

            # Sadece bu node'un state'ini kullan.
            state = node_states[node_id]

            amplitude = message_to_amplitude(
                message
            )

            cleaned = clean_amplitude(
                amplitude,
                args.edge_trim,
            )

            # Her node'un kendi temporal filter'ı var.
            temporally_filtered = state[
                "temporal_filter"
            ].process(
                cleaned
            )

            normalized = normalize_amplitude(
                temporally_filtered
            )

        except json.JSONDecodeError as exc:
            print(
                f"Skipping invalid JSON line: {exc}",
                file=sys.stderr,
            )
            continue

        except Exception as exc:
            print(
                f"Skipping invalid CSI message: {exc}",
                file=sys.stderr,
            )
            continue

        previous_normalized = state[
            "previous_normalized"
        ]

        if previous_normalized is None:
            state["previous_normalized"] = normalized
            continue

        if len(previous_normalized) != len(normalized):
            print(
                f"Skipping frame for node {node_id} "
                "because CSI vector length changed.",
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
            normalized - previous_normalized
        )

        if int(np.max(selected_indices)) >= len(
            frame_difference
        ):
            print(
                f"Skipping frame for node {node_id}: "
                "selected CSI index is outside "
                "the frame-difference vector.",
                file=sys.stderr,
            )
            continue

        selected_difference = frame_difference[
            selected_indices
        ]

        frame_score = float(
            np.mean(selected_difference)
        )

        # Sadece bu node'un score buffer'ına ekle.
        state["score_buffer"].append(
            frame_score
        )

        state["previous_normalized"] = normalized

        motion_score = float(
            np.mean(
                state["score_buffer"]
            )
        )

        above_threshold = (
            motion_score > args.threshold
        )

        if above_threshold:
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
                f"ts_us={message.get('ts_us', '')} "
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
                f"ts_us={message.get('ts_us', '')} "
                f"node_id={node_id} "
                f"motion_score={motion_score:.4f} "
                f"threshold={args.threshold:.4f}",
                file=sys.stderr,
                flush=True,
            )

        status = (
            "HAREKET"
            if state["is_moving"]
            else "STILL"
        )

        print(
            f"ts_us={message.get('ts_us', '')} "
            f"node_id={node_id} "
            f"rssi={message.get('rssi', '')} "
            f"motion_score={motion_score:.4f} "
            f"threshold={args.threshold:.4f} "
            f"status={status}",
            flush=True,
        )


if __name__ == "__main__":
    main()