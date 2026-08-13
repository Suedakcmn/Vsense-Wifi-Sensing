"""Build inference-ready CSI windows from the normalized live stream."""

from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from dataclasses import dataclass
from io import TextIOBase
from pathlib import Path

from activity_model import ActivityModel
from csi_utils import csi_to_amplitude, compute_motion_score
from ml.windows import CSIWindow


PASSTHROUGH_MESSAGE_TYPES = frozenset({"health", "node_status", "zone_prediction"})


@dataclass(frozen=True)
class LiveWindowConfig:
    duration_us: int
    stride_us: int
    max_gap_us: int
    min_rows_per_node: int
    expected_csi_length: int
    required_nodes: tuple[str, ...]

    @classmethod
    def from_model_config(cls, config: dict) -> "LiveWindowConfig":
        return cls(
            duration_us=int(float(config["window_seconds"]) * 1_000_000),
            stride_us=int(float(config["stride_seconds"]) * 1_000_000),
            max_gap_us=int(float(config["max_gap_ms"]) * 1000),
            min_rows_per_node=int(config["min_rows_per_node"]),
            expected_csi_length=int(config.get("expected_csi_length", 256)),
            required_nodes=tuple(config["required_nodes"]),
        )

    def validate(self):
        if self.duration_us <= 0:
            raise ValueError("window duration must be positive")
        if self.stride_us <= 0:
            raise ValueError("window stride must be positive")
        if self.stride_us > self.duration_us:
            raise ValueError("window stride must not exceed duration")
        if self.max_gap_us <= 0:
            raise ValueError("maximum CSI gap must be positive")
        if self.min_rows_per_node <= 0:
            raise ValueError("minimum rows per node must be positive")
        if self.expected_csi_length <= 0:
            raise ValueError("expected CSI length must be positive")
        if not self.required_nodes or len(self.required_nodes) != len(
            set(self.required_nodes)
        ):
            raise ValueError("required nodes must be non-empty and unique")


class LiveCSIWindowBuffer:
    """Collect ordered CSI rows and emit clean, overlapping live windows."""

    def __init__(self, config: LiveWindowConfig):
        config.validate()
        self.config = config
        self.rows = {node_id: deque() for node_id in config.required_nodes}
        self.next_window_start_us: int | None = None
        self.latest_timestamp_by_node: dict[str, int] = {}

    def add(self, row: dict) -> list[CSIWindow]:
        if row.get("message_type") != "csi":
            return []
        node_id = row.get("node_id")
        if node_id not in self.rows:
            return []
        timestamp = row.get("collector_ts_us")
        if not isinstance(timestamp, int):
            return []
        previous_timestamp = self.latest_timestamp_by_node.get(node_id)
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            return []
        if not self._row_has_valid_csi(row):
            return []

        self.rows[node_id].append(row)
        self.latest_timestamp_by_node[node_id] = timestamp
        if self.next_window_start_us is None:
            self.next_window_start_us = timestamp
        return self._emit_ready_windows()

    def _row_has_valid_csi(self, row: dict) -> bool:
        csi = row.get("csi")
        return (
            row.get("len") == self.config.expected_csi_length
            and isinstance(csi, list)
            and len(csi) == self.config.expected_csi_length
        )

    def _emit_ready_windows(self) -> list[CSIWindow]:
        if self.next_window_start_us is None:
            return []
        if set(self.latest_timestamp_by_node) != set(self.config.required_nodes):
            return []

        watermark_us = min(self.latest_timestamp_by_node.values())
        windows = []
        while self.next_window_start_us + self.config.duration_us <= watermark_us:
            start_us = self.next_window_start_us
            end_us = start_us + self.config.duration_us
            rows_by_node = {
                node_id: [
                    row
                    for row in node_rows
                    if start_us <= row["collector_ts_us"] < end_us
                ]
                for node_id, node_rows in self.rows.items()
            }
            if self._window_is_valid(rows_by_node):
                windows.append(CSIWindow(
                    session_id="live",
                    label="unknown",
                    subject="unknown",
                    start_us=start_us,
                    end_us=end_us,
                    rows_by_node=rows_by_node,
                ))
            self.next_window_start_us += self.config.stride_us
            self._discard_before(self.next_window_start_us)
        return windows

    def _window_is_valid(self, rows_by_node: dict[str, list[dict]]) -> bool:
        for node_id in self.config.required_nodes:
            rows = rows_by_node[node_id]
            if len(rows) < self.config.min_rows_per_node:
                return False
            timestamps = [row["collector_ts_us"] for row in rows]
            if any(
                current - previous > self.config.max_gap_us
                for previous, current in zip(timestamps, timestamps[1:])
            ):
                return False
        return True

    def _discard_before(self, timestamp_us: int):
        for node_rows in self.rows.values():
            while node_rows and node_rows[0]["collector_ts_us"] < timestamp_us:
                node_rows.popleft()


class LiveActivityPredictor:
    """Convert normalized live CSI rows into JSON-compatible predictions."""

    def __init__(
        self,
        artifact_dir: Path | str,
        *,
        model_version: str | None = None,
    ):
        self.model = ActivityModel(artifact_dir)
        self.model_version = model_version or Path(artifact_dir).name
        self.window_buffer = LiveCSIWindowBuffer(
            LiveWindowConfig.from_model_config(self.model.config)
        )

    def process(self, row: dict) -> list[dict]:
        records = []
        for window in self.window_buffer.add(row):
            motion_scores = {}
            for node_id, rows in window.rows_by_node.items():
                amplitude_matrix = [csi_to_amplitude(value["csi"]) for value in rows]
                scores = compute_motion_score(amplitude_matrix)
                motion_scores[node_id] = round(float(scores.iloc[-1]), 6)
            records.append({
                "schema_version": 1,
                "message_type": "motion_score",
                "window_start_us": window.start_us,
                "window_end_us": window.end_us,
                "scores": motion_scores,
            })
            prediction = self.model.predict_window(window)
            records.append({
                "schema_version": 1,
                "message_type": "activity_prediction",
                "model_version": self.model_version,
                "window_start_us": window.start_us,
                "window_end_us": window.end_us,
                "activity": prediction.activity,
                "confidence": prediction.confidence,
                "probabilities": prediction.probabilities,
            })
        return records


def run_stream(
    predictor: LiveActivityPredictor,
    input_stream: TextIOBase,
    output_stream: TextIOBase,
    error_stream: TextIOBase,
) -> int:
    invalid_lines = 0
    for line_number, line in enumerate(input_stream, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            invalid_lines += 1
            print(
                f"Skipping invalid JSON on input line {line_number}: {exc}",
                file=error_stream,
            )
            continue
        if not isinstance(row, dict):
            invalid_lines += 1
            print(
                f"Skipping non-object JSON on input line {line_number}",
                file=error_stream,
            )
            continue
        if row.get("message_type") in PASSTHROUGH_MESSAGE_TYPES:
            print(
                json.dumps(row, ensure_ascii=False, separators=(",", ":")),
                file=output_stream,
                flush=True,
            )
        for record in predictor.process(row):
            print(
                json.dumps(record, ensure_ascii=False, separators=(",", ":")),
                file=output_stream,
                flush=True,
            )
    return invalid_lines


def parse_args():
    parser = argparse.ArgumentParser(
        description="Predict activities from normalized CSI JSONL on stdin",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path("dataset-v1/models/baseline_v1"),
    )
    parser.add_argument("--model-version")
    return parser.parse_args()


def main():
    args = parse_args()
    predictor = LiveActivityPredictor(
        args.artifact_dir,
        model_version=args.model_version,
    )
    try:
        run_stream(predictor, sys.stdin, sys.stdout, sys.stderr)
    except KeyboardInterrupt:
        print("Stopping activity predictor.", file=sys.stderr)


if __name__ == "__main__":
    main()
