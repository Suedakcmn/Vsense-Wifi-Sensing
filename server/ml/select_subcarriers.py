"""Select ordered CNN subcarriers using only one training repeat."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from csi_utils import csi_to_amplitude
from ml.constants import CLASS_NAMES, DEVELOPMENT_REPEATS, MODEL_SCHEMA_VERSION
from ml.features import normalize_amplitude
from ml.subcarriers import (
    combine_receiver_scores,
    get_ignore_indices,
    multiclass_fisher_scores,
    select_ranked_subcarriers,
)
from ml.windows import WindowConfig, discover_main_sessions, iter_session_windows


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=Path("dataset-v1"))
    parser.add_argument(
        "--train-repeats",
        type=int,
        nargs="+",
        required=True,
        choices=DEVELOPMENT_REPEATS,
    )
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--window-seconds", type=float, default=2.0)
    parser.add_argument("--stride-seconds", type=float, default=1.0)
    parser.add_argument("--trim-seconds", type=float, default=10.0)
    parser.add_argument("--max-gap-ms", type=float, default=500.0)
    parser.add_argument("--min-rows-per-node", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def session_repeat(session_dir: Path) -> int:
    metadata = json.loads(
        (session_dir / "metadata.json").read_text(encoding="utf-8")
    )
    return int(metadata["repeat"])


def dynamic_subcarrier_features(rows: list[dict]) -> np.ndarray:
    """Describe temporal change per subcarrier, independent of absolute level."""
    amplitude = np.stack([csi_to_amplitude(row["csi"]) for row in rows])
    normalized = normalize_amplitude(amplitude, "zscore")
    temporal_difference = np.abs(np.diff(normalized, axis=0))
    return np.mean(temporal_difference, axis=0).astype(np.float32)


def main():
    args = parse_args()
    train_repeats = sorted(set(args.train_repeats))
    window_config = WindowConfig(
        duration_us=int(args.window_seconds * 1_000_000),
        stride_us=int(args.stride_seconds * 1_000_000),
        trim_us=int(args.trim_seconds * 1_000_000),
        max_gap_us=int(args.max_gap_ms * 1000),
        min_rows_per_node=args.min_rows_per_node,
    )
    features_by_node = {node_id: [] for node_id in window_config.required_nodes}
    labels = []
    sessions = []
    expected_subcarriers = None
    for session_dir in discover_main_sessions(args.dataset_dir):
        repeat = session_repeat(session_dir)
        if repeat not in train_repeats:
            continue
        accepted = 0
        for window in iter_session_windows(session_dir, window_config):
            per_node = {
                node_id: dynamic_subcarrier_features(window.rows_by_node[node_id])
                for node_id in window_config.required_nodes
            }
            lengths = {len(values) for values in per_node.values()}
            if len(lengths) != 1:
                raise ValueError("receiver subcarrier lengths do not match")
            current_length = lengths.pop()
            if expected_subcarriers is None:
                expected_subcarriers = current_length
            elif current_length != expected_subcarriers:
                raise ValueError("window subcarrier lengths do not match")
            for node_id, values in per_node.items():
                features_by_node[node_id].append(values)
            labels.append(window.label)
            accepted += 1
        sessions.append(
            {
                "session_id": session_dir.name,
                "repeat": repeat,
                "label": window.label if accepted else None,
                "windows": accepted,
            }
        )
        print(f"{session_dir.name}: {accepted} training windows")
    if expected_subcarriers is None:
        raise ValueError("no training windows were found")
    for repeat in train_repeats:
        repeat_labels = {
            item["label"] for item in sessions if item["repeat"] == repeat
        }
        if repeat_labels != set(CLASS_NAMES):
            raise ValueError(
                f"training repeat {repeat} is missing classes: "
                f"{set(CLASS_NAMES) - repeat_labels}"
            )
    label_array = np.asarray(labels)
    scores_by_node = {
        node_id: multiclass_fisher_scores(np.stack(values), label_array)
        for node_id, values in features_by_node.items()
    }
    combined_scores = combine_receiver_scores(scores_by_node)
    ignored = get_ignore_indices(expected_subcarriers)
    ranked, frequency_ordered = select_ranked_subcarriers(
        combined_scores, args.top_n, ignored
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        ",".join(str(index) for index in frequency_ordered) + "\n",
        encoding="utf-8",
    )
    report = {
        "schema_version": MODEL_SCHEMA_VERSION,
        "selection_scope": "training repeats only",
        "train_repeats": train_repeats,
        "validation_or_test_used": False,
        "method": "per-window zscore temporal-difference multi-class Fisher score",
        "receiver_combination": "normalize each RX score by its max, then mean",
        "num_subcarriers": expected_subcarriers,
        "ignored_indices": sorted(ignored),
        "ignored_layout": {
            "pilots_per_64": [6, 20, 34, 48],
            "dc_nulls_per_64": [27, 28],
            "edges_per_64": [0, 1, 2, 3, 60, 61, 62, 63],
        },
        "top_n": args.top_n,
        "ranked_indices": ranked,
        "frequency_ordered_indices": frequency_ordered,
        "scores": {
            str(index): {
                "combined": float(combined_scores[index]),
                **{
                    node_id: float(scores[index])
                    for node_id, scores in scores_by_node.items()
                },
            }
            for index in ranked
        },
        "sessions": sessions,
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(f"Ignored {len(ignored)} pilot/DC/edge indices")
    print(f"Ranked selection: {ranked}")
    print(f"CNN frequency order: {frequency_ordered}")
    print(f"Wrote: {args.output}")


if __name__ == "__main__":
    main()
