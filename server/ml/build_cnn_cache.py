"""Build reusable fixed-size CNN tensors from clean CSI session windows."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import torch

from ml.cnn_data import CLASS_TO_INDEX, CNNTensorConfig, window_to_tensor
from ml.constants import CLASS_NAMES, MODEL_SCHEMA_VERSION
from ml.features import load_subcarrier_indices
from ml.windows import WindowConfig, discover_main_sessions, iter_session_windows


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=Path("dataset-v1"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dataset-v1/processed/cnn_2s_40hz_zscore"),
    )
    parser.add_argument("--repeats", type=int, nargs="+", default=[1, 2])
    parser.add_argument("--window-seconds", type=float, default=2.0)
    parser.add_argument("--stride-seconds", type=float, default=1.0)
    parser.add_argument("--sample-rate-hz", type=int, default=40)
    parser.add_argument("--normalization", default="zscore")
    parser.add_argument("--trim-seconds", type=float, default=10.0)
    parser.add_argument("--max-gap-ms", type=float, default=500.0)
    parser.add_argument("--min-rows-per-node", type=int, default=20)
    parser.add_argument(
        "--subcarriers",
        type=Path,
        default=Path("server/config/selected_subcarriers.txt"),
    )
    return parser.parse_args()


def session_repeat(session_dir: Path) -> int:
    metadata = json.loads(
        (session_dir / "metadata.json").read_text(encoding="utf-8")
    )
    return int(metadata["repeat"])


def build_session_cache(
    session_dir: Path,
    output_path: Path,
    window_config: WindowConfig,
    tensor_config: CNNTensorConfig,
    subcarrier_indices: list[int],
) -> dict:
    tensors = []
    targets = []
    starts = []
    label = None
    subject = None
    for window in iter_session_windows(session_dir, window_config):
        label = window.label
        subject = window.subject
        tensors.append(window_to_tensor(window, subcarrier_indices, tensor_config))
        targets.append(CLASS_TO_INDEX[window.label])
        starts.append(window.start_us)
    if not tensors:
        raise ValueError(f"session produced no valid CNN windows: {session_dir.name}")
    payload = {
        "inputs": torch.stack(tensors),
        "targets": torch.tensor(targets, dtype=torch.long),
        "window_start_us": torch.tensor(starts, dtype=torch.int64),
    }
    torch.save(payload, output_path)
    return {
        "session_id": session_dir.name,
        "repeat": session_repeat(session_dir),
        "label": label,
        "subject": subject,
        "windows": len(targets),
        "file": output_path.name,
    }


def main():
    args = parse_args()
    repeats = sorted(set(args.repeats))
    if not repeats or any(repeat not in {1, 2, 3} for repeat in repeats):
        raise ValueError("repeats must contain only 1, 2, or 3")
    window_config = WindowConfig(
        duration_us=int(args.window_seconds * 1_000_000),
        stride_us=int(args.stride_seconds * 1_000_000),
        trim_us=int(args.trim_seconds * 1_000_000),
        max_gap_us=int(args.max_gap_ms * 1000),
        min_rows_per_node=args.min_rows_per_node,
    )
    tensor_config = CNNTensorConfig(
        sample_rate_hz=args.sample_rate_hz,
        normalization=args.normalization,
        node_ids=window_config.required_nodes,
    )
    subcarrier_indices = load_subcarrier_indices(args.subcarriers)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    sessions = []
    for session_dir in discover_main_sessions(args.dataset_dir):
        repeat = session_repeat(session_dir)
        if repeat not in repeats:
            continue
        output_path = args.output_dir / f"{session_dir.name}.pt"
        summary = build_session_cache(
            session_dir,
            output_path,
            window_config,
            tensor_config,
            subcarrier_indices,
        )
        sessions.append(summary)
        print(
            f"{summary['session_id']}: {summary['windows']} windows "
            f"shape=[2,{int(args.window_seconds * args.sample_rate_hz)},"
            f"{len(subcarrier_indices)}]"
        )
    manifest = {
        "schema_version": MODEL_SCHEMA_VERSION,
        "class_names": CLASS_NAMES,
        "window_config": asdict(window_config),
        "tensor_config": asdict(tensor_config),
        "subcarrier_indices": subcarrier_indices,
        "tensor_shape": [
            len(tensor_config.node_ids),
            int(round(args.window_seconds * args.sample_rate_hz)),
            len(subcarrier_indices),
        ],
        "cached_repeats": repeats,
        "sessions": sessions,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"Cached {sum(item['windows'] for item in sessions)} windows")
    print(f"Manifest: {args.output_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()
