"""Stream CSI JSONL sessions into fixed-duration, overlapping windows."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from ml.constants import CLASS_NAMES


@dataclass(frozen=True)
class WindowConfig:
    duration_us: int = 2_000_000
    stride_us: int = 1_000_000
    trim_us: int = 10_000_000
    max_gap_us: int = 500_000
    min_rows_per_node: int = 20
    expected_csi_length: int = 256
    required_nodes: tuple[str, ...] = ("rx_01", "rx_02")


@dataclass
class CSIWindow:
    session_id: str
    label: str
    subject: str
    start_us: int
    end_us: int
    rows_by_node: dict[str, list[dict]]


def load_session_context(session_dir: Path) -> tuple[dict, dict]:
    metadata = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
    labels = json.loads((session_dir / "labels.json").read_text(encoding="utf-8"))
    if metadata.get("status") != "completed":
        raise ValueError(f"session is not completed: {session_dir.name}")
    if not labels.get("segments"):
        raise ValueError(f"session has no label segments: {session_dir.name}")
    return metadata, labels


def _window_is_valid(rows_by_node: dict[str, list[dict]], config: WindowConfig) -> bool:
    for node_id in config.required_nodes:
        rows = rows_by_node[node_id]
        if len(rows) < config.min_rows_per_node:
            return False
        timestamps = [row["collector_ts_us"] for row in rows]
        if any(
            current - previous > config.max_gap_us
            for previous, current in zip(timestamps, timestamps[1:])
        ):
            return False
        if any(
            row.get("len") != config.expected_csi_length
            or len(row.get("csi", [])) != config.expected_csi_length
            for row in rows
        ):
            return False
    return True


def iter_session_windows(
    session_dir: Path,
    config: WindowConfig = WindowConfig(),
) -> Iterator[CSIWindow]:
    """Yield clean windows without loading a whole CSI session into memory."""
    metadata, labels = load_session_context(session_dir)
    segment = labels["segments"][0]
    usable_start = max(
        int(metadata["started_collector_ts_us"]),
        int(segment["start_collector_ts_us"]),
    ) + config.trim_us
    usable_end = min(
        int(metadata["ended_collector_ts_us"]),
        int(segment["end_collector_ts_us"]),
    ) - config.trim_us
    if usable_end - usable_start < config.duration_us:
        return

    buffers = {node_id: deque() for node_id in config.required_nodes}
    next_start = usable_start

    def emit_ready_windows(until_us):
        nonlocal next_start
        while next_start + config.duration_us <= min(until_us, usable_end):
            end_us = next_start + config.duration_us
            rows_by_node = {
                key: [
                    item
                    for item in values
                    if next_start <= item["collector_ts_us"] < end_us
                ]
                for key, values in buffers.items()
            }
            if _window_is_valid(rows_by_node, config):
                yield CSIWindow(
                    session_id=metadata["session_id"],
                    label=segment["label"],
                    subject=metadata.get("subject", "unknown"),
                    start_us=next_start,
                    end_us=end_us,
                    rows_by_node=rows_by_node,
                )
            next_start += config.stride_us
            for values in buffers.values():
                while values and values[0]["collector_ts_us"] < next_start:
                    values.popleft()

    with (session_dir / "csi.jsonl").open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            node_id = row.get("node_id")
            timestamp = row.get("collector_ts_us")
            if node_id not in buffers or not isinstance(timestamp, int):
                continue
            if timestamp < usable_start:
                continue

            yield from emit_ready_windows(timestamp)

            if timestamp >= usable_end:
                break
            buffers[node_id].append(row)
    yield from emit_ready_windows(usable_end)


def discover_main_sessions(dataset_dir: Path) -> list[Path]:
    """Select the canonical three repeats for each modelled scenario."""
    candidates: dict[tuple[str, int], list[Path]] = {}
    for session_dir in (dataset_dir / "sessions").iterdir():
        metadata_path = session_dir / "metadata.json"
        if not metadata_path.exists():
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        scenario = metadata.get("scenario")
        repeat = metadata.get("repeat")
        if scenario not in set(CLASS_NAMES):
            continue
        if repeat not in {1, 2, 3} or metadata.get("status") != "completed":
            continue
        candidates.setdefault((scenario, repeat), []).append(session_dir)

    selected = []
    for scenario in CLASS_NAMES:
        for repeat in (1, 2, 3):
            matches = candidates.get((scenario, repeat), [])
            if len(matches) != 1:
                raise ValueError(
                    f"expected exactly one main session for {scenario} repeat {repeat}, "
                    f"found {[path.name for path in matches]}"
                )
            selected.append(matches[0])
    return selected
