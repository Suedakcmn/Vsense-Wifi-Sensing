"""Statistical CSI features shared by training and live inference."""

from __future__ import annotations

import numpy as np

from csi_utils import csi_to_amplitude
from ml.windows import CSIWindow


STAT_NAMES = ("mean", "std", "median", "iqr", "min", "max", "energy", "diff_mean")
SPECTRAL_NAMES = (
    "dominant_frequency",
    "spectral_energy",
    "low_frequency_energy",
    "high_frequency_energy",
    "low_high_energy_ratio",
    "spectral_entropy",
    "spectral_centroid",
    "spectral_bandwidth",
)


def load_subcarrier_indices(path) -> list[int]:
    values = [int(value) for value in path.read_text(encoding="utf-8").strip().split(",")]
    if len(values) != len(set(values)):
        raise ValueError("selected subcarrier indices must be unique")
    return values


def feature_names(
    node_ids: tuple[str, ...],
    subcarrier_indices: list[int],
    *,
    spectral_features: bool = False,
) -> list[str]:
    names = []
    for node_id in node_ids:
        for index in subcarrier_indices:
            names.extend(f"{node_id}_sc{index}_{stat}" for stat in STAT_NAMES)
            if spectral_features:
                names.extend(
                    f"{node_id}_sc{index}_{stat}"
                    for stat in SPECTRAL_NAMES
                )
        names.extend(
            [
                f"{node_id}_rssi_mean",
                f"{node_id}_rssi_std",
                f"{node_id}_frame_rate_hz",
            ]
        )
    return names


def _normalize(selected: np.ndarray, method: str) -> np.ndarray:
    if method == "none":
        return selected
    if method == "zscore":
        center = np.mean(selected, axis=0, keepdims=True)
        scale = np.std(selected, axis=0, keepdims=True)
    elif method == "robust":
        center = np.median(selected, axis=0, keepdims=True)
        q25, q75 = np.percentile(selected, [25, 75], axis=0)
        scale = (q75 - q25)[None, :]
    else:
        raise ValueError(f"unsupported window normalization: {method}")
    return (selected - center) / np.maximum(scale, 1e-6)


def _resample(
    rows: list[dict],
    selected: np.ndarray,
    start_us: int,
    end_us: int,
    sample_rate_hz: float,
) -> np.ndarray:
    time_points = int(round((end_us - start_us) / 1_000_000 * sample_rate_hz))
    if time_points < 2:
        raise ValueError("resampled window must contain at least two time points")
    timestamps = np.asarray([row["collector_ts_us"] for row in rows], dtype=np.float64)
    target = np.linspace(start_us, end_us, num=time_points, endpoint=False)
    return np.stack(
        [np.interp(target, timestamps, selected[:, index]) for index in range(selected.shape[1])],
        axis=1,
    )


def _spectral_statistics(selected: np.ndarray, sample_rate_hz: float) -> np.ndarray:
    centered = selected - np.mean(selected, axis=0, keepdims=True)
    spectrum = np.fft.rfft(centered, axis=0)
    power = np.square(np.abs(spectrum))
    frequencies = np.fft.rfftfreq(len(centered), d=1.0 / sample_rate_hz)
    if len(frequencies) > 1:
        non_dc_power = power[1:, :]
        non_dc_frequencies = frequencies[1:]
    else:
        non_dc_power = power
        non_dc_frequencies = frequencies
    epsilon = 1e-12
    totals = np.sum(non_dc_power, axis=0) + epsilon
    dominant = non_dc_frequencies[np.argmax(non_dc_power, axis=0)]
    low = np.sum(
        non_dc_power[(non_dc_frequencies >= 0.1) & (non_dc_frequencies < 1.0), :],
        axis=0,
    )
    high = np.sum(
        non_dc_power[(non_dc_frequencies >= 1.0) & (non_dc_frequencies <= 8.0), :],
        axis=0,
    )
    distribution = non_dc_power / totals[None, :]
    entropy = -np.sum(distribution * np.log2(distribution + epsilon), axis=0)
    entropy /= np.log2(max(2, len(non_dc_frequencies)))
    centroid = np.sum(non_dc_frequencies[:, None] * non_dc_power, axis=0) / totals
    bandwidth = np.sqrt(
        np.sum(
            np.square(non_dc_frequencies[:, None] - centroid[None, :]) * non_dc_power,
            axis=0,
        ) / totals
    )
    return np.stack(
        [dominant, totals, low, high, low / (high + epsilon), entropy, centroid, bandwidth],
        axis=1,
    )


def _node_features(
    rows: list[dict],
    indices: list[int],
    start_us: int,
    end_us: int,
    *,
    normalization: str,
    spectral_features: bool,
    sample_rate_hz: float,
) -> np.ndarray:
    duration_seconds = (end_us - start_us) / 1_000_000
    amplitude = np.stack([csi_to_amplitude(row["csi"]) for row in rows])
    selected = amplitude[:, indices]
    if spectral_features:
        selected = _resample(rows, selected, start_us, end_us, sample_rate_hz)
    selected = _normalize(selected, normalization)
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
    )
    if spectral_features:
        statistics = np.concatenate(
            [statistics, _spectral_statistics(selected, sample_rate_hz)],
            axis=1,
        )
    statistics = statistics.reshape(-1)
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
    *,
    normalization: str = "none",
    spectral_features: bool = False,
    sample_rate_hz: float = 40.0,
) -> np.ndarray:
    return np.concatenate(
        [
            _node_features(
                window.rows_by_node[node_id],
                subcarrier_indices,
                window.start_us,
                window.end_us,
                normalization=normalization,
                spectral_features=spectral_features,
                sample_rate_hz=sample_rate_hz,
            )
            for node_id in node_ids
        ]
    )
