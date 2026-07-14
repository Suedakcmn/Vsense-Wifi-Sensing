from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from csi_utils import (
    build_amplitude_matrix,
    compute_dynamic_threshold,
    compute_motion_score,
    debounce_motion_decision,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze recorded/provided CSI Parquet data."
    )

    parser.add_argument(
        "input",
        help="Path to recorded/provided CSI Parquet file.",
    )

    parser.add_argument(
        "--file-name",
        default=None,
        help="Optional file_name value to filter if the dataset contains multiple recordings.",
    )

    parser.add_argument(
        "--max-frames",
        type=int,
        default=1000,
        help="Maximum number of frames to use for the heatmap.",
    )

    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="Directory where output figures will be saved.",
    )

    parser.add_argument(
        "--prefix",
        default="csi_analysis",
        help="Prefix for output figure names.",
    )

    return parser.parse_args()


def save_heatmap(amplitude_matrix: np.ndarray, output_path: Path, max_frames: int) -> None:
    frames = amplitude_matrix[:max_frames]

    plt.figure(figsize=(12, 6))
    plt.imshow(frames.T, aspect="auto")
    plt.colorbar(label="Amplitude")
    plt.title(f"CSI Amplitude Heatmap - first {len(frames)} frames")
    plt.xlabel("Time / packet index")
    plt.ylabel("Subcarrier index")
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


def save_motion_plot(
    motion_score: pd.Series,
    threshold: float,
    decision: pd.Series,
    output_path: Path,
) -> None:
    x = np.arange(len(motion_score))

    plt.figure(figsize=(12, 5))
    plt.plot(x, motion_score.values, linewidth=1.5, label="Motion score")
    plt.axhline(y=threshold, linestyle="--", linewidth=2, label=f"Threshold ({threshold:.2f})")
    plt.fill_between(
        x,
        0,
        motion_score.values,
        where=decision.values,
        alpha=0.25,
        label="Motion decision",
    )
    plt.title("CSI Motion Score with Dynamic Threshold")
    plt.xlabel("Time / packet index")
    plt.ylabel("Motion score")
    plt.legend()
    plt.grid(True)
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


def main() -> None:
    args = parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading data: {input_path}")
    df = pd.read_parquet(input_path)

    print("\n--- Data summary ---")
    print(f"Rows: {len(df)}")
    print(f"Columns: {list(df.columns)}")

    if args.file_name is not None:
        if "file_name" not in df.columns:
            raise ValueError("--file-name was provided, but dataset has no 'file_name' column.")

        before = len(df)
        df = df[df["file_name"] == args.file_name].copy()
        print(f"Filtered file_name={args.file_name}: {before} -> {len(df)} rows")

        if len(df) == 0:
            raise ValueError(f"No rows found for file_name={args.file_name}")

    amplitude_matrix, source_column = build_amplitude_matrix(df)

    print("\n--- CSI summary ---")
    print(f"CSI source column: {source_column}")
    print(f"Amplitude matrix shape: {amplitude_matrix.shape}")

    heatmap_path = output_dir / f"{args.prefix}_heatmap.png"
    motion_path = output_dir / f"{args.prefix}_motion_score.png"

    save_heatmap(amplitude_matrix, heatmap_path, args.max_frames)

    motion_score = compute_motion_score(amplitude_matrix)
    threshold = compute_dynamic_threshold(motion_score)
    decision = debounce_motion_decision(motion_score, threshold)

    save_motion_plot(motion_score, threshold, decision, motion_path)

    print("\n--- Outputs ---")
    print(f"Heatmap saved to: {heatmap_path}")
    print(f"Motion score plot saved to: {motion_path}")
    print(f"Threshold: {threshold:.4f}")
    print(f"Motion frames: {int(decision.sum())} / {len(decision)}")


if __name__ == "__main__":
    main()
