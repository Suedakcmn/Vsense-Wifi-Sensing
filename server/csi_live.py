import argparse
import json
import sys
from collections import deque

import numpy as np

from csi_utils import csi_to_amplitude


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


def main():
    args = parse_args()

    score_buffer = deque(maxlen=args.window_size)
    previous_normalized = None

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

    for line in sys.stdin:
        line = line.strip()

        if not line:
            continue

        try:
            message = json.loads(line)
            amplitude = message_to_amplitude(message)
            cleaned = clean_amplitude(
                amplitude,
                args.edge_trim,
            )
            normalized = normalize_amplitude(cleaned)

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

        if previous_normalized is None:
            previous_normalized = normalized
            continue

        if len(previous_normalized) != len(normalized):
            print(
                "Skipping frame because CSI vector length changed.",
                file=sys.stderr,
            )

            previous_normalized = normalized
            score_buffer.clear()
            high_count = 0
            low_count = 0
            is_moving = False
            continue

        frame_difference = np.abs(
            normalized - previous_normalized
        )

        frame_score = float(
            np.percentile(
                frame_difference,
                args.score_percentile,
            )
        )
        score_buffer.append(frame_score)

        previous_normalized = normalized

        motion_score = float(np.mean(score_buffer))

        above_threshold = motion_score > args.threshold

        if above_threshold:
            high_count += 1
            low_count = 0
        else:
            low_count += 1
            high_count = 0

        if not is_moving and high_count >= args.start_count:
            is_moving = True

            print(
                f"EVENT=HAREKET "
                f"ts_us={message.get('ts_us', '')} "
                f"node_id={message.get('node_id', '')} "
                f"motion_score={motion_score:.4f} "
                f"threshold={args.threshold:.4f}",
                file=sys.stderr,
                flush=True,
            )

        elif is_moving and low_count >= args.stop_count:
            is_moving = False

            print(
                f"EVENT=STILL "
                f"ts_us={message.get('ts_us', '')} "
                f"node_id={message.get('node_id', '')} "
                f"motion_score={motion_score:.4f} "
                f"threshold={args.threshold:.4f}",
                file=sys.stderr,
                flush=True,
            )

        status = "HAREKET" if is_moving else "STILL"

        print(
            f"ts_us={message.get('ts_us', '')} "
            f"node_id={message.get('node_id', '')} "
            f"rssi={message.get('rssi', '')} "
            f"motion_score={motion_score:.4f} "
            f"threshold={args.threshold:.4f} "
            f"status={status}",
            flush=True,
        )


if __name__ == "__main__":
    main()