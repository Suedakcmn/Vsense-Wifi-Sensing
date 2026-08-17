"""Build a window-level feature table from dataset-v1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from ml.features import (
    NORMALIZATION_MODES,
    extract_window_features,
    feature_names,
    load_subcarrier_indices,
)
from ml.windows import WindowConfig, discover_main_sessions, iter_session_windows


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=Path("dataset-v1"))
    parser.add_argument("--output", type=Path, default=Path("dataset-v1/processed/features.parquet"))
    parser.add_argument("--window-seconds", type=float, default=2.0)
    parser.add_argument("--stride-seconds", type=float, default=1.0)
    parser.add_argument("--trim-seconds", type=float, default=10.0)
    parser.add_argument("--max-gap-ms", type=float, default=500.0)
    parser.add_argument("--min-rows-per-node", type=int, default=20)
    parser.add_argument(
        "--normalization",
        choices=NORMALIZATION_MODES,
        default="none",
        help="per-window, per-subcarrier signal normalization",
    )
    parser.add_argument("--spectral-features", action="store_true")
    parser.add_argument("--sample-rate-hz", type=float, default=40.0)
    parser.add_argument(
        "--subcarriers",
        type=Path,
        default=Path("server/config/selected_subcarriers.txt"),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    config = WindowConfig(
        duration_us=int(args.window_seconds * 1_000_000),
        stride_us=int(args.stride_seconds * 1_000_000),
        trim_us=int(args.trim_seconds * 1_000_000),
        max_gap_us=int(args.max_gap_ms * 1000),
        min_rows_per_node=args.min_rows_per_node,
    )
    indices = load_subcarrier_indices(args.subcarriers)
    names = feature_names(
        config.required_nodes,
        indices,
        spectral_features=args.spectral_features,
    )
    records = []
    summaries = []
    for session_dir in discover_main_sessions(args.dataset_dir):
        accepted = 0
        for window in iter_session_windows(session_dir, config):
            values = extract_window_features(
                window,
                indices,
                config.required_nodes,
                normalization=args.normalization,
                spectral_features=args.spectral_features,
                sample_rate_hz=args.sample_rate_hz,
            )
            record = dict(zip(names, values.tolist()))
            record.update(
                {
                    "session_id": window.session_id,
                    "subject": window.subject,
                    "label": window.label,
                    "window_start_us": window.start_us,
                    "window_end_us": window.end_us,
                }
            )
            records.append(record)
            accepted += 1
        summaries.append({"session_id": session_dir.name, "accepted_windows": accepted})
        print(f"{session_dir.name}: {accepted} clean windows")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    table = pd.DataFrame.from_records(records)
    table.to_parquet(args.output, index=False)
    manifest = {
        "schema_version": 1,
        "feature_table": args.output.name,
        "feature_extractor": "ml.features.extract_window_features",
        "signal_normalization": args.normalization,
        "window_seconds": args.window_seconds,
        "stride_seconds": args.stride_seconds,
        "trim_seconds": args.trim_seconds,
        "max_gap_ms": args.max_gap_ms,
        "min_rows_per_node": args.min_rows_per_node,
        "required_nodes": list(config.required_nodes),
        "selected_subcarriers": indices,
        "normalization": args.normalization,
        "spectral_features": args.spectral_features,
        "sample_rate_hz": args.sample_rate_hz,
        "feature_count": len(names),
        "feature_columns": names,
        "window_count": len(table),
        "sessions": summaries,
    }
    args.output.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"Wrote {len(table)} windows to {args.output}")


if __name__ == "__main__":
    main()
