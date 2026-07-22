import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def load_csi_file(path: Path) -> np.ndarray:
    frames = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                print(f"Skipping invalid JSON at line {line_number}: {path}")
                continue

            csi = payload.get("csi")

            if not isinstance(csi, list):
                continue

            if len(csi) != 256:
                continue

            frames.append(csi)

    if not frames:
        raise ValueError(f"No valid len=256 CSI frames found in {path}")

    return np.asarray(frames, dtype=np.float32)


def csi_to_amplitude(csi_frames: np.ndarray) -> np.ndarray:
    real = csi_frames[:, 0::2]
    imag = csi_frames[:, 1::2]

    return np.sqrt(real**2 + imag**2)


def calculate_motion_score(
    amplitudes: np.ndarray,
    window_size: int = 20,
) -> np.ndarray:
    # Her frame'i kendi ortalamasına göre normalize et.
    frame_mean = np.mean(amplitudes, axis=1, keepdims=True)
    frame_std = np.std(amplitudes, axis=1, keepdims=True) + 1e-6
    normalized = (amplitudes - frame_mean) / frame_std

    # Ardışık frameler arasındaki değişimi ölç.
    frame_difference = np.abs(np.diff(normalized, axis=0))

    # Her frame için tüm subcarrier değişimlerinin ortalaması.
    per_frame_score = np.mean(frame_difference, axis=1)

    # Gürültüyü azaltmak için hareketli ortalama.
    kernel = np.ones(window_size, dtype=np.float32) / window_size
    scores = np.convolve(per_frame_score, kernel, mode="valid")

    return scores.astype(np.float32)


def analyze_file(path: Path, window_size: int) -> np.ndarray:
    csi_frames = load_csi_file(path)
    amplitudes = csi_to_amplitude(csi_frames)
    scores = calculate_motion_score(amplitudes, window_size)

    print(f"\nFile: {path}")
    print(f"Valid CSI frames: {len(csi_frames)}")
    print(f"Motion score count: {len(scores)}")
    print(f"Mean: {np.mean(scores):.4f}")
    print(f"Std:  {np.std(scores):.4f}")
    print(f"Min:  {np.min(scores):.4f}")
    print(f"Max:  {np.max(scores):.4f}")

    return scores


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare motion scores from recorded CSI sessions."
    )

    parser.add_argument(
        "files",
        nargs="+",
        type=Path,
        help="JSONL CSI recording files.",
    )

    parser.add_argument(
        "--window-size",
        type=int,
        default=20,
        help="Number of CSI frames used for each motion score.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/motion_session_comparison.png"),
        help="Output graph path.",
    )

    args = parser.parse_args()

    if args.window_size < 2:
        raise SystemExit("--window-size must be at least 2")

    args.output.parent.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(12, 6))

    for path in args.files:
        scores = analyze_file(path, args.window_size)
        plt.plot(scores, label=path.stem)

    plt.title("CSI Motion Score Comparison")
    plt.xlabel("Window index")
    plt.ylabel("Motion score")
    plt.legend()
    plt.tight_layout()
    plt.savefig(args.output, dpi=150)

    print(f"\nGraph saved to: {args.output}")


if __name__ == "__main__":
    main()