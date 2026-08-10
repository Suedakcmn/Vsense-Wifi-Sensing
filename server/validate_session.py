"""Validate a VSense CSI + LD2450 recording session."""

import argparse
import bisect
import json
import sys
from collections import Counter
from pathlib import Path


def read_jsonl(path):
    records = []
    errors = []
    if not path.exists():
        return records, [f"missing file: {path.name}"]
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{path.name}:{line_number}: invalid JSON: {exc}")
                continue
            if not isinstance(value, dict):
                errors.append(f"{path.name}:{line_number}: row is not an object")
                continue
            records.append(value)
    return records, errors


def percentile(values, percentile_value):
    if not values:
        return None
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * percentile_value / 100))
    return ordered[index]


def nearest_delta_us(sorted_timestamps, timestamp):
    position = bisect.bisect_left(sorted_timestamps, timestamp)
    candidates = []
    if position < len(sorted_timestamps):
        candidates.append(abs(sorted_timestamps[position] - timestamp))
    if position > 0:
        candidates.append(abs(sorted_timestamps[position - 1] - timestamp))
    return min(candidates) if candidates else None


def maximum_gap_us(timestamps, start_timestamp=None, end_timestamp=None):
    points = list(sorted(timestamps))
    if start_timestamp is not None:
        points.insert(0, start_timestamp)
    if end_timestamp is not None:
        points.append(end_timestamp)
    return max(
        (current - previous for previous, current in zip(points, points[1:])),
        default=0,
    )


def validate_session(
    session_dir,
    required_nodes,
    max_delta_us,
    min_duration_seconds,
    max_radar_gap_us=1_000_000,
    max_csi_gap_us=1_000_000,
    min_ground_truth_rate_hz=5.0,
    max_radar_frame_loss_ratio=0.05,
):
    errors = []
    warnings = []
    metadata_path = session_dir / "metadata.json"
    if not metadata_path.exists():
        errors.append("missing file: metadata.json")
        metadata = {}
    else:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"metadata.json is invalid: {exc}")
            metadata = {}

    csi, csi_errors = read_jsonl(session_dir / "csi.jsonl")
    radar, radar_errors = read_jsonl(session_dir / "ground_truth.jsonl")
    errors.extend(csi_errors)
    errors.extend(radar_errors)

    for file_name, records, expected_type in (
        ("csi.jsonl", csi, "csi"),
        ("ground_truth.jsonl", radar, "ground_truth"),
    ):
        for index, record in enumerate(records, start=1):
            if record.get("message_type") != expected_type:
                errors.append(
                    f"{file_name}:{index}: expected message_type={expected_type}"
                )
            if not isinstance(record.get("collector_ts_us"), int):
                errors.append(f"{file_name}:{index}: missing integer collector_ts_us")

    csi_by_node = Counter(record.get("node_id") for record in csi)
    for node_id in required_nodes:
        if csi_by_node[node_id] == 0:
            errors.append(f"no CSI rows found for required node: {node_id}")
    if not radar:
        errors.append("no ground-truth rows found")

    all_timestamps = [
        record["collector_ts_us"]
        for record in csi + radar
        if isinstance(record.get("collector_ts_us"), int)
    ]
    data_duration_seconds = (
        (max(all_timestamps) - min(all_timestamps)) / 1_000_000
        if len(all_timestamps) >= 2
        else 0.0
    )

    frame_sequences = [
        record["frame_seq"]
        for record in radar
        if isinstance(record.get("frame_seq"), int)
    ]
    frame_gap_count = sum(
        max(0, current - previous - 1)
        for previous, current in zip(frame_sequences, frame_sequences[1:])
        if current > previous
    )
    expected_radar_frames = len(frame_sequences) + frame_gap_count
    radar_frame_loss_ratio = (
        frame_gap_count / expected_radar_frames
        if expected_radar_frames
        else 0.0
    )
    if frame_gap_count:
        warnings.append(f"LD2450 frame sequence contains {frame_gap_count} missing frames")
    if radar_frame_loss_ratio > max_radar_frame_loss_ratio:
        errors.append(
            f"LD2450 frame loss {radar_frame_loss_ratio * 100:.2f}% exceeds "
            f"allowed {max_radar_frame_loss_ratio * 100:.2f}%"
        )

    deltas_by_node = {}
    reverse_deltas_by_node = {}
    maximum_csi_gap_by_node = {}
    radar_timestamps = sorted(
        record["collector_ts_us"]
        for record in radar
        if isinstance(record.get("collector_ts_us"), int)
    )
    session_start_us = metadata.get("started_collector_ts_us")
    session_end_us = metadata.get("ended_collector_ts_us")
    session_start_us = session_start_us if isinstance(session_start_us, int) else None
    session_end_us = session_end_us if isinstance(session_end_us, int) else None
    for node_id in required_nodes:
        node_timestamps = sorted(
            record["collector_ts_us"]
            for record in csi
            if record.get("node_id") == node_id
            and isinstance(record.get("collector_ts_us"), int)
        )
        deltas_by_node[node_id] = [
            nearest_delta_us(node_timestamps, timestamp)
            for timestamp in radar_timestamps
        ]
        deltas_by_node[node_id] = [
            delta for delta in deltas_by_node[node_id] if delta is not None
        ]
        reverse_deltas_by_node[node_id] = [
            nearest_delta_us(radar_timestamps, timestamp)
            for timestamp in node_timestamps
        ]
        reverse_deltas_by_node[node_id] = [
            delta
            for delta in reverse_deltas_by_node[node_id]
            if delta is not None
        ]
        maximum_csi_gap_by_node[node_id] = maximum_gap_us(
            node_timestamps,
            session_start_us,
            session_end_us,
        )
        if (
            node_timestamps
            and maximum_csi_gap_by_node[node_id] > max_csi_gap_us
        ):
            errors.append(
                f"{node_id} maximum CSI stream gap "
                f"{maximum_csi_gap_by_node[node_id] / 1000:.1f} ms exceeds "
                f"allowed {max_csi_gap_us / 1000:.1f} ms"
            )
        if deltas_by_node[node_id] and max(deltas_by_node[node_id]) > max_delta_us:
            errors.append(
                f"{node_id} maximum CSI-radar delta exceeds "
                f"{max_delta_us / 1000:.1f} ms"
            )
        if (
            reverse_deltas_by_node[node_id]
            and max(reverse_deltas_by_node[node_id]) > max_delta_us
        ):
            errors.append(
                f"{node_id} maximum radar coverage gap exceeds "
                f"{max_delta_us / 1000:.1f} ms"
            )

    maximum_radar_gap_us = maximum_gap_us(
        radar_timestamps,
        session_start_us,
        session_end_us,
    )
    if radar_timestamps and maximum_radar_gap_us > max_radar_gap_us:
        errors.append(
            f"maximum ground-truth gap {maximum_radar_gap_us / 1000:.1f} ms "
            f"exceeds allowed {max_radar_gap_us / 1000:.1f} ms"
        )

    ground_truth_rate_hz = (
        len(radar_timestamps) / data_duration_seconds
        if data_duration_seconds > 0
        else 0.0
    )
    if radar_timestamps and ground_truth_rate_hz < min_ground_truth_rate_hz:
        errors.append(
            f"ground-truth rate {ground_truth_rate_hz:.2f} Hz is below "
            f"required {min_ground_truth_rate_hz:.2f} Hz"
        )

    if data_duration_seconds < min_duration_seconds:
        errors.append(
            f"recorded data duration {data_duration_seconds:.1f}s is below "
            f"required {min_duration_seconds:.1f}s"
        )
    if metadata.get("status") != "completed":
        errors.append("metadata status is not completed")

    return {
        "session_id": metadata.get("session_id", session_dir.name),
        "status": "PASS" if not errors else "FAIL",
        "csi_rows": len(csi),
        "ground_truth_rows": len(radar),
        "csi_rows_by_node": dict(csi_by_node),
        "data_duration_seconds": round(data_duration_seconds, 3),
        "radar_frame_gaps": frame_gap_count,
        "radar_frame_loss_percent": round(radar_frame_loss_ratio * 100, 3),
        "ground_truth_rate_hz": round(ground_truth_rate_hz, 3),
        "max_radar_gap_ms": round(maximum_radar_gap_us / 1000, 3),
        "max_allowed_radar_gap_ms": max_radar_gap_us / 1000,
        "max_allowed_delta_ms": max_delta_us / 1000,
        "synchronization": {
            node_id: {
                "matched_radar_rows": len(deltas),
                "median_delta_ms": (
                    round(percentile(deltas, 50) / 1000, 3) if deltas else None
                ),
                "p95_delta_ms": (
                    round(percentile(deltas, 95) / 1000, 3) if deltas else None
                ),
                "max_delta_ms": round(max(deltas) / 1000, 3) if deltas else None,
                "matched_csi_rows": len(reverse_deltas_by_node[node_id]),
                "max_csi_to_radar_delta_ms": (
                    round(max(reverse_deltas_by_node[node_id]) / 1000, 3)
                    if reverse_deltas_by_node[node_id]
                    else None
                ),
                "max_csi_stream_gap_ms": round(
                    maximum_csi_gap_by_node[node_id] / 1000,
                    3,
                ),
            }
            for node_id, deltas in deltas_by_node.items()
        },
        "warnings": warnings,
        "errors": errors,
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Validate a VSense recording session")
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("--required-node", action="append", dest="required_nodes")
    parser.add_argument("--max-delta-ms", type=float, default=200.0)
    parser.add_argument("--min-duration-seconds", type=float, default=600.0)
    parser.add_argument("--max-radar-gap-ms", type=float, default=1000.0)
    parser.add_argument("--max-csi-gap-ms", type=float, default=1000.0)
    parser.add_argument("--min-ground-truth-rate-hz", type=float, default=5.0)
    parser.add_argument(
        "--max-radar-frame-loss-percent",
        type=float,
        default=5.0,
    )
    return parser.parse_args()


def main():
    args = parse_args()
    result = validate_session(
        args.session_dir,
        args.required_nodes or ["rx_01", "rx_02"],
        int(args.max_delta_ms * 1000),
        args.min_duration_seconds,
        int(args.max_radar_gap_ms * 1000),
        int(args.max_csi_gap_ms * 1000),
        args.min_ground_truth_rate_hz,
        args.max_radar_frame_loss_percent / 100,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
