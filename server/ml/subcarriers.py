"""Subcarrier masks and training-only multi-class ranking helpers."""

from __future__ import annotations

import numpy as np


OFDM_BLOCK_SIZE = 64
PILOT_INDICES_64 = frozenset({6, 20, 34, 48})
DC_NULL_INDICES_64 = frozenset({27, 28})
EDGE_GUARD_INDICES_64 = frozenset({0, 1, 2, 3, 60, 61, 62, 63})


def get_ignore_indices(num_subcarriers: int = 64) -> set[int]:
    """Return pilot, DC/null, and edge bins for repeated 64-bin OFDM blocks.

    The index layout follows the project-provided 64-bin mapping. A 128-value
    amplitude vector is treated as two consecutive 64-bin blocks, so the same
    relative mask is applied at offsets 0 and 64.
    """
    if num_subcarriers <= 0 or num_subcarriers % OFDM_BLOCK_SIZE != 0:
        raise ValueError(
            f"num_subcarriers must be a positive multiple of {OFDM_BLOCK_SIZE}"
        )
    ignored_in_block = (
        PILOT_INDICES_64 | DC_NULL_INDICES_64 | EDGE_GUARD_INDICES_64
    )
    return {
        offset + index
        for offset in range(0, num_subcarriers, OFDM_BLOCK_SIZE)
        for index in ignored_in_block
    }


def multiclass_fisher_scores(features: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """Score columns by between-class variance divided by within-class variance."""
    values = np.asarray(features, dtype=np.float64)
    targets = np.asarray(labels)
    if values.ndim != 2:
        raise ValueError("features must have shape [samples, subcarriers]")
    if targets.ndim != 1 or len(targets) != len(values):
        raise ValueError("labels must be one-dimensional and match feature rows")
    classes = np.unique(targets)
    if len(classes) < 2:
        raise ValueError("at least two classes are required")
    overall_mean = np.mean(values, axis=0)
    between = np.zeros(values.shape[1], dtype=np.float64)
    within = np.zeros(values.shape[1], dtype=np.float64)
    for class_name in classes:
        group = values[targets == class_name]
        class_mean = np.mean(group, axis=0)
        between += len(group) * np.square(class_mean - overall_mean)
        within += np.sum(np.square(group - class_mean), axis=0)
    scores = between / (within + 1e-12)
    return np.nan_to_num(scores, nan=0.0, posinf=0.0, neginf=0.0)


def combine_receiver_scores(scores_by_node: dict[str, np.ndarray]) -> np.ndarray:
    """Normalize receiver rankings independently, then average them fairly."""
    if not scores_by_node:
        raise ValueError("at least one receiver score vector is required")
    normalized = []
    expected_length = None
    for node_id, scores in scores_by_node.items():
        values = np.asarray(scores, dtype=np.float64)
        if values.ndim != 1:
            raise ValueError(f"scores for {node_id} must be one-dimensional")
        if expected_length is None:
            expected_length = len(values)
        elif len(values) != expected_length:
            raise ValueError("receiver score vectors must have equal length")
        maximum = float(np.max(values))
        normalized.append(values / maximum if maximum > 0 else np.zeros_like(values))
    return np.mean(np.stack(normalized), axis=0)


def select_ranked_subcarriers(
    combined_scores: np.ndarray,
    top_n: int,
    ignored_indices: set[int],
) -> tuple[list[int], list[int]]:
    """Return score-ranked indices and the same selection in frequency order."""
    scores = np.asarray(combined_scores, dtype=np.float64)
    valid = [index for index in range(len(scores)) if index not in ignored_indices]
    if top_n <= 0 or top_n > len(valid):
        raise ValueError(f"top_n must be between 1 and {len(valid)}")
    ranked = sorted(valid, key=lambda index: (-scores[index], index))[:top_n]
    return ranked, sorted(ranked)
