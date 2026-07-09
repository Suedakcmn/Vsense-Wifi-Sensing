from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pandas as pd


def _to_numpy_1d(values) -> np.ndarray:
    """
    Convert list / numpy array / pandas object to a 1D float32 numpy array.
    """
    if hasattr(values, "tolist"):
        values = values.tolist()

    arr = np.asarray(values, dtype=np.float32).reshape(-1)
    return arr


def csi_to_amplitude(csi_values) -> np.ndarray:
    """
    Convert raw CSI int8 values in [imag0, real0, imag1, real1, ...] format
    into amplitude values.

    amplitude = sqrt(real^2 + imag^2)

    Example:
    [3, 4, -2, 5] -> [5.0, sqrt(29)]
    """
    arr = _to_numpy_1d(csi_values)

    if len(arr) % 2 != 0:
        raise ValueError(
            "Raw CSI array length must be even because the expected format is "
            "[imag0, real0, imag1, real1, ...]."
        )

    imag = arr[0::2]
    real = arr[1::2]

    return np.sqrt(real**2 + imag**2)


def build_amplitude_matrix(
    df: pd.DataFrame,
    csi_column: Optional[str] = None,
    amplitude_column: str = "csi_amplitude",
) -> Tuple[np.ndarray, str]:
    """
    Build a 2D amplitude matrix from a CSI dataframe.

    Priority:
    1. If csi_amplitude exists, use it directly.
    2. Else, use csi column and convert raw [imag, real] values to amplitude.

    Returns:
    - amplitude_matrix: shape = [frames, subcarriers]
    - source_column: which column was used
    """
    if amplitude_column in df.columns:
        rows = [_to_numpy_1d(row) for row in df[amplitude_column].values]
        return np.stack(rows), amplitude_column

    if csi_column is None:
        if "csi" in df.columns:
            csi_column = "csi"
        else:
            raise ValueError(
                "No CSI column found. Expected either 'csi_amplitude' or 'csi'."
            )

    rows = [csi_to_amplitude(row) for row in df[csi_column].values]
    return np.stack(rows), csi_column


def compute_motion_score(
    amplitude_matrix: np.ndarray,
    smooth_window: int = 10,
    variance_window: int = 50,
    score_window: int = 30,
) -> pd.Series:
    """
    Compute a simple motion score from CSI amplitude.

    Logic:
    1. Smooth amplitude values with rolling mean.
    2. Compute rolling variance.
    3. Average variance across subcarriers.
    4. Smooth final score again.

    This is a simple Week-1 baseline, not a final ML model.
    """
    df_csi = pd.DataFrame(amplitude_matrix)

    smoothed = df_csi.rolling(window=smooth_window, min_periods=1).mean()
    rolling_var = smoothed.rolling(window=variance_window, min_periods=1).var()
    raw_motion_score = rolling_var.mean(axis=1)

    final_motion_score = raw_motion_score.rolling(
        window=score_window,
        min_periods=1,
    ).mean()

    return final_motion_score.fillna(0.0)


def compute_dynamic_threshold(
    motion_score: pd.Series,
    calibration_start: int = 50,
    calibration_packets: int = 500,
    multiplier: float = 1.5,
) -> float:
    """
    Compute a simple dynamic threshold using an initial calibration region.

    The first frames are assumed to be relatively stable / baseline.
    """
    if len(motion_score) == 0:
        return 0.0

    start = min(calibration_start, len(motion_score) - 1)
    end = min(calibration_packets, len(motion_score))

    baseline = motion_score.iloc[start:end]

    if len(baseline) == 0:
        baseline = motion_score

    baseline_max = float(baseline.max())

    return baseline_max * multiplier


def debounce_motion_decision(
    motion_score: pd.Series,
    threshold: float,
    window: int = 10,
    min_ratio: float = 0.8,
) -> pd.Series:
    """
    Convert motion score to a stable motion/no-motion decision.

    A frame is accepted as motion only if enough recent frames are above threshold.
    This reduces short noise spikes.
    """
    raw_decision = motion_score > threshold

    debounced = raw_decision.rolling(window=window, min_periods=1).mean() >= min_ratio

    return debounced
