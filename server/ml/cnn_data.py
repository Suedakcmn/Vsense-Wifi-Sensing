"""Convert clean CSI windows into fixed-size tensors for CNN training."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

import numpy as np
import torch
from torch.utils.data import IterableDataset, get_worker_info

from csi_utils import csi_to_amplitude
from ml.constants import CLASS_NAMES
from ml.features import NORMALIZATION_MODES, normalize_amplitude
from ml.windows import CSIWindow, WindowConfig, iter_session_windows


CLASS_TO_INDEX = {name: index for index, name in enumerate(CLASS_NAMES)}


@dataclass(frozen=True)
class CNNTensorConfig:
    sample_rate_hz: int = 40
    normalization: str = "zscore"
    node_ids: tuple[str, ...] = ("rx_01", "rx_02")

    def __post_init__(self):
        if self.sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        if self.normalization not in NORMALIZATION_MODES:
            raise ValueError(
                f"normalization must be one of {NORMALIZATION_MODES}, "
                f"got {self.normalization!r}"
            )
        if not self.node_ids:
            raise ValueError("node_ids cannot be empty")


def _unique_sorted_samples(rows: list[dict], indices: list[int]):
    """Return sorted, duplicate-free timestamps and selected CSI amplitudes."""
    latest_by_timestamp = {}
    for row in rows:
        timestamp = row.get("collector_ts_us")
        if not isinstance(timestamp, int):
            continue
        amplitude = csi_to_amplitude(row["csi"])
        latest_by_timestamp[timestamp] = amplitude[indices]
    if len(latest_by_timestamp) < 2:
        raise ValueError("at least two distinct CSI timestamps are required")
    timestamps = np.asarray(sorted(latest_by_timestamp), dtype=np.float64)
    amplitude = np.stack(
        [latest_by_timestamp[int(timestamp)] for timestamp in timestamps]
    ).astype(np.float32)
    return timestamps, amplitude


def _resample_node(
    rows: list[dict],
    indices: list[int],
    target_timestamps_us: np.ndarray,
    normalization: str,
) -> np.ndarray:
    source_timestamps, source_amplitude = _unique_sorted_samples(rows, indices)
    resampled = np.empty(
        (len(target_timestamps_us), len(indices)), dtype=np.float32
    )
    for subcarrier in range(len(indices)):
        resampled[:, subcarrier] = np.interp(
            target_timestamps_us,
            source_timestamps,
            source_amplitude[:, subcarrier],
        )
    return normalize_amplitude(resampled, normalization)


def window_to_tensor(
    window: CSIWindow,
    subcarrier_indices: list[int],
    config: CNNTensorConfig = CNNTensorConfig(),
) -> torch.Tensor:
    """Create a [receiver, time, subcarrier] float32 tensor from one window."""
    duration_seconds = (window.end_us - window.start_us) / 1_000_000
    time_steps = int(round(duration_seconds * config.sample_rate_hz))
    if time_steps < 2:
        raise ValueError("window is too short for the configured sample rate")
    target_timestamps = window.start_us + (
        np.arange(time_steps, dtype=np.float64) * 1_000_000 / config.sample_rate_hz
    )
    receiver_matrices = []
    for node_id in config.node_ids:
        if node_id not in window.rows_by_node:
            raise ValueError(f"window is missing required node {node_id}")
        receiver_matrices.append(
            _resample_node(
                window.rows_by_node[node_id],
                subcarrier_indices,
                target_timestamps,
                config.normalization,
            )
        )
    values = np.stack(receiver_matrices).astype(np.float32)
    if not np.isfinite(values).all():
        raise ValueError("CNN tensor contains non-finite values")
    return torch.from_numpy(values)


class CSITensorIterableDataset(IterableDataset):
    """Stream session windows as CNN tensors without loading raw sessions at once."""

    def __init__(
        self,
        session_dirs: Iterable[Path],
        window_config: WindowConfig,
        subcarrier_indices: list[int],
        tensor_config: CNNTensorConfig = CNNTensorConfig(),
    ):
        super().__init__()
        self.session_dirs = tuple(Path(path) for path in session_dirs)
        self.window_config = window_config
        self.subcarrier_indices = list(subcarrier_indices)
        self.tensor_config = tensor_config

    def _worker_session_dirs(self) -> tuple[Path, ...]:
        worker = get_worker_info()
        if worker is None:
            return self.session_dirs
        return self.session_dirs[worker.id :: worker.num_workers]

    def __iter__(self) -> Iterator[dict]:
        for session_dir in self._worker_session_dirs():
            for window in iter_session_windows(session_dir, self.window_config):
                if window.label not in CLASS_TO_INDEX:
                    raise ValueError(f"unknown class label {window.label!r}")
                yield {
                    "inputs": window_to_tensor(
                        window,
                        self.subcarrier_indices,
                        self.tensor_config,
                    ),
                    "target": torch.tensor(
                        CLASS_TO_INDEX[window.label], dtype=torch.long
                    ),
                    "session_id": window.session_id,
                    "window_start_us": window.start_us,
                }
