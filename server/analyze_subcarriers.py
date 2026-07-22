import argparse
import csv
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

from csi_utils import csi_to_amplitude


SESSION_FILES = {
    "empty_room": Path("data/sessions/empty_room.jsonl"),
    "hand_movement": Path("data/sessions/hand_movement.jsonl"),
    "walking": Path("data/sessions/walking.jsonl"),
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Compare frame-to-frame CSI changes for each subcarrier."
        )
    )

    parser.add_argument(
        "--edge-trim",
        type=int,
        default=4,
        help="Amplitude values removed from both ends.",
    )

    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="Number of informative subcarriers to select.",
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
        raise ValueError("Amplitude must be one-dimensional.")

    return amplitude


def clean_amplitude(amplitude, edge_trim):
    amplitude = np.asarray(amplitude, dtype=np.float32)

    if edge_trim > 0:
        if len(amplitude) <= 2 * edge_trim:
            raise ValueError(
                "CSI amplitude is too short for edge trimming."
            )

        amplitude = amplitude[edge_trim:-edge_trim]

    median = float(np.median(amplitude))
    mad = float(
        np.median(
            np.abs(amplitude - median)
        )
    )

    if mad > 1e-6:
        robust_z = (
            np.abs(amplitude - median)
            / (1.4826 * mad)
        )

        amplitude = np.where(
            robust_z > 5.0,
            median,
            amplitude,
        )

    return amplitude


def normalize_frame(amplitude):
    mean = float(np.mean(amplitude))
    std = float(np.std(amplitude))

    return (amplitude - mean) / (std + 1e-6)


def load_session(path, edge_trim):
    frames = []
    skipped = 0
    expected_length = None

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if not line:
                continue

            try:
                message = json.loads(line)
                amplitude = message_to_amplitude(message)

                cleaned = clean_amplitude(
                    amplitude,
                    edge_trim,
                )

                normalized = normalize_frame(cleaned)

                if expected_length is None:
                    expected_length = len(normalized)

                if len(normalized) != expected_length:
                    skipped += 1
                    continue

                frames.append(normalized)

            except Exception:
                skipped += 1

    if len(frames) < 2:
        raise RuntimeError(
            f"Not enough valid frames in {path}."
        )

    frame_matrix = np.stack(frames)

    frame_differences = np.abs(
        np.diff(frame_matrix, axis=0)
    )

    return frame_differences, len(frames), skipped


def effect_size(
    movement_mean,
    movement_std,
    empty_mean,
    empty_std,
):
    pooled_std = np.sqrt(
        (
            np.square(movement_std)
            + np.square(empty_std)
        )
        / 2.0
    )

    return (
        movement_mean - empty_mean
    ) / (pooled_std + 1e-6)


def print_selected_score_summary(
    name,
    differences,
    selected_indices,
):
    scores = np.mean(
        differences[:, selected_indices],
        axis=1,
    )

    print(f"\n{name} — selected-subcarrier score")
    print("-" * (len(name) + 30))
    print(f"Mean       : {np.mean(scores):.4f}")
    print(f"Median     : {np.median(scores):.4f}")
    print(f"Std        : {np.std(scores):.4f}")
    print(
        f"90th pct.  : "
        f"{np.percentile(scores, 90):.4f}"
    )
    print(f"Minimum    : {np.min(scores):.4f}")
    print(f"Maximum    : {np.max(scores):.4f}")


def main():
    args = parse_args()

    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    session_differences = {}

    for name, path in SESSION_FILES.items():
        if not path.exists():
            raise FileNotFoundError(
                f"Missing session file: {path}"
            )

        differences, frame_count, skipped = (
            load_session(
                path,
                args.edge_trim,
            )
        )

        session_differences[name] = differences

        print(
            f"{name}: "
            f"frames={frame_count} "
            f"differences={len(differences)} "
            f"subcarriers={differences.shape[1]} "
            f"skipped={skipped}"
        )

    subcarrier_counts = {
        values.shape[1]
        for values in session_differences.values()
    }

    if len(subcarrier_counts) != 1:
        raise RuntimeError(
            "Session subcarrier counts do not match."
        )

    empty = session_differences["empty_room"]
    hand = session_differences["hand_movement"]
    walking = session_differences["walking"]

    empty_mean = np.mean(empty, axis=0)
    empty_std = np.std(empty, axis=0)

    hand_mean = np.mean(hand, axis=0)
    hand_std = np.std(hand, axis=0)

    walking_mean = np.mean(walking, axis=0)
    walking_std = np.std(walking, axis=0)

    walking_gain = walking_mean - empty_mean
    hand_gain = hand_mean - empty_mean

    walking_ratio = walking_mean / (
        empty_mean + 1e-6
    )

    hand_ratio = hand_mean / (
        empty_mean + 1e-6
    )

    walking_effect = effect_size(
        walking_mean,
        walking_std,
        empty_mean,
        empty_std,
    )

    hand_effect = effect_size(
        hand_mean,
        hand_std,
        empty_mean,
        empty_std,
    )

    positive_indices = np.where(
        walking_gain > 0
    )[0]

    sorted_indices = positive_indices[
        np.argsort(
            walking_effect[positive_indices]
        )[::-1]
    ]

    selected_indices = sorted_indices[
        :args.top_n
    ]

    print("\nTop informative subcarriers")
    print("---------------------------")
    print(
        "Rank  Trimmed  Original  "
        "Empty   Hand    Walking  "
        "WalkRatio  Effect"
    )

    for rank, index in enumerate(
        selected_indices,
        start=1,
    ):
        original_index = index + args.edge_trim

        print(
            f"{rank:>4}  "
            f"{index:>7}  "
            f"{original_index:>8}  "
            f"{empty_mean[index]:>6.3f}  "
            f"{hand_mean[index]:>6.3f}  "
            f"{walking_mean[index]:>7.3f}  "
            f"{walking_ratio[index]:>9.3f}  "
            f"{walking_effect[index]:>6.3f}"
        )

    csv_path = (
        output_dir
        / "subcarrier_analysis.csv"
    )

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as csv_file:
        writer = csv.writer(csv_file)

        writer.writerow(
            [
                "trimmed_index",
                "original_amplitude_index",
                "empty_mean_difference",
                "hand_mean_difference",
                "walking_mean_difference",
                "hand_gain",
                "walking_gain",
                "hand_ratio",
                "walking_ratio",
                "hand_effect_size",
                "walking_effect_size",
                "selected",
            ]
        )

        for index in range(len(empty_mean)):
            writer.writerow(
                [
                    index,
                    index + args.edge_trim,
                    float(empty_mean[index]),
                    float(hand_mean[index]),
                    float(walking_mean[index]),
                    float(hand_gain[index]),
                    float(walking_gain[index]),
                    float(hand_ratio[index]),
                    float(walking_ratio[index]),
                    float(hand_effect[index]),
                    float(walking_effect[index]),
                    index in selected_indices,
                ]
            )

    selected_path = (
        output_dir
        / "selected_subcarriers.txt"
    )

    selected_path.write_text(
        ",".join(
            str(int(index))
            for index in selected_indices
        )
        + "\n",
        encoding="utf-8",
    )

    x = np.arange(len(empty_mean))

    plt.figure(figsize=(12, 6))
    plt.plot(
        x,
        empty_mean,
        label="Empty room",
    )
    plt.plot(
        x,
        hand_mean,
        label="Hand movement",
    )
    plt.plot(
        x,
        walking_mean,
        label="Walking",
    )
    plt.xlabel("Trimmed amplitude index")
    plt.ylabel("Mean frame-to-frame difference")
    plt.title(
        "CSI Difference by Subcarrier"
    )
    plt.legend()
    plt.tight_layout()

    difference_plot_path = (
        output_dir
        / "subcarrier_mean_differences.png"
    )

    plt.savefig(
        difference_plot_path,
        dpi=160,
    )
    plt.close()

    selected_effects = walking_effect[
        selected_indices
    ]

    selected_labels = [
        str(int(index))
        for index in selected_indices
    ]

    plt.figure(figsize=(12, 6))
    plt.bar(
        selected_labels,
        selected_effects,
    )
    plt.xlabel("Selected trimmed amplitude index")
    plt.ylabel("Walking effect size")
    plt.title(
        "Top Motion-Sensitive Subcarriers"
    )
    plt.tight_layout()

    top_plot_path = (
        output_dir
        / "top_subcarrier_effects.png"
    )

    plt.savefig(
        top_plot_path,
        dpi=160,
    )
    plt.close()

    print_selected_score_summary(
        "empty_room",
        empty,
        selected_indices,
    )

    print_selected_score_summary(
        "hand_movement",
        hand,
        selected_indices,
    )

    print_selected_score_summary(
        "walking",
        walking,
        selected_indices,
    )

    print("\nSaved outputs")
    print("-------------")
    print(csv_path)
    print(selected_path)
    print(difference_plot_path)
    print(top_plot_path)


if __name__ == "__main__":
    main()
