"""Statistical CSI features shared by training and live inference."""

from __future__ import annotations

import numpy as np

from csi_utils import csi_to_amplitude
from ml.windows import CSIWindow


STAT_NAMES = ("mean", "std", "median", "iqr", "min", "max", "energy", "diff_mean")


def load_subcarrier_indices(path) -> list[int]:
    values = [int(value) for value in path.read_text(encoding="utf-8").strip().split(",")]
    if len(values) != len(set(values)):
        raise ValueError("selected subcarrier indices must be unique")
    return values


def feature_names(node_ids: tuple[str, ...], subcarrier_indices: list[int]) -> list[str]:
    names = []
    for node_id in node_ids:
        for index in subcarrier_indices:
            names.extend(f"{node_id}_sc{index}_{stat}" for stat in STAT_NAMES)
        names.extend(
            [
                f"{node_id}_rssi_mean",
                f"{node_id}_rssi_std",
                f"{node_id}_frame_rate_hz",
            ]
        )
    return names


def _node_features(rows: list[dict], indices: list[int], duration_seconds: float) -> np.ndarray:
    amplitude = np.stack([csi_to_amplitude(row["csi"]) for row in rows])
    selected = amplitude[:, indices]
    temporal_diff = np.abs(np.diff(selected, axis=0))
    q25, q75 = np.percentile(selected, [25, 75], axis=0)
    statistics = np.stack(
        [
            np.mean(selected, axis=0),
            np.std(selected, axis=0),
            np.median(selected, axis=0),
            q75 - q25,
            np.min(selected, axis=0),
            np.max(selected, axis=0),
            np.mean(np.square(selected), axis=0),
            np.mean(temporal_diff, axis=0),
        ],
        axis=1,
    ).reshape(-1)
    rssi = np.asarray([row.get("rssi", 0) for row in rows], dtype=np.float32)
    extras = np.asarray(
        [np.mean(rssi), np.std(rssi), len(rows) / duration_seconds],
        dtype=np.float32,
    )
    return np.concatenate([statistics, extras]).astype(np.float32)


def extract_window_features(
    window: CSIWindow,
    subcarrier_indices: list[int],
    node_ids: tuple[str, ...] = ("rx_01", "rx_02"),
) -> np.ndarray:
    duration_seconds = (window.end_us - window.start_us) / 1_000_000
    return np.concatenate(
        [
            _node_features(window.rows_by_node[node_id], subcarrier_indices, duration_seconds)
            for node_id in node_ids
        ]
    )

