"""Estimate a coarse indoor zone from receiver motion and RSSI signals."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import deque
from dataclasses import dataclass
from io import TextIOBase
from pathlib import Path


class ZoneConfigError(ValueError):
    """Raised when the zone configuration is incomplete or inconsistent."""


@dataclass(frozen=True)
class ZoneNodeConfig:
    zone: str
    motion_scale: float = 1.0
    rssi_reference: float = -55.0
    rssi_range: float = 25.0


@dataclass(frozen=True)
class ZonePredictorConfig:
    nodes: dict[str, ZoneNodeConfig]
    zones: dict[str, dict[str, float]] | None = None
    smoothing_windows: int = 5
    switch_margin: float = 0.15
    minimum_confidence: float = 0.55
    stale_after_us: int = 10_000_000
    motion_weight: float = 0.8
    rssi_weight: float = 0.2

    @classmethod
    def from_path(cls, path: Path | str) -> "ZonePredictorConfig":
        config_path = Path(path)
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ZoneConfigError(f"zone config not found: {config_path}") from exc
        except json.JSONDecodeError as exc:
            raise ZoneConfigError(f"invalid zone config JSON: {config_path}: {exc}") from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise ZoneConfigError("zone config must use schema_version 1")
        raw_nodes = raw.get("nodes")
        if not isinstance(raw_nodes, dict) or not raw_nodes:
            raise ZoneConfigError("zone config nodes must be a non-empty object")
        nodes = {}
        for node_id, value in raw_nodes.items():
            if not isinstance(node_id, str) or not node_id or not isinstance(value, dict):
                raise ZoneConfigError("zone config node entries must be named objects")
            try:
                nodes[node_id] = ZoneNodeConfig(
                    zone=str(value["zone"]),
                    motion_scale=float(value.get("motion_scale", 1.0)),
                    rssi_reference=float(value.get("rssi_reference", -55.0)),
                    rssi_range=float(value.get("rssi_range", 25.0)),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ZoneConfigError(f"invalid zone config for node {node_id}") from exc
        raw_zones = raw.get("zones")
        zones = None
        if raw_zones is not None:
            if not isinstance(raw_zones, dict) or not raw_zones:
                raise ZoneConfigError("zones must be a non-empty object when provided")
            zones = {}
            for zone_name, weights in raw_zones.items():
                if not isinstance(zone_name, str) or not zone_name or not isinstance(weights, dict):
                    raise ZoneConfigError("zone signatures must be named objects")
                try:
                    zones[zone_name] = {
                        str(node_id): float(weight)
                        for node_id, weight in weights.items()
                    }
                except (TypeError, ValueError) as exc:
                    raise ZoneConfigError(f"invalid signature for zone {zone_name}") from exc
        config = cls(
            nodes=nodes,
            zones=zones,
            smoothing_windows=int(raw.get("smoothing_windows", 5)),
            switch_margin=float(raw.get("switch_margin", 0.15)),
            minimum_confidence=float(raw.get("minimum_confidence", 0.55)),
            stale_after_us=int(float(raw.get("stale_after_seconds", 10.0)) * 1_000_000),
            motion_weight=float(raw.get("motion_weight", 0.8)),
            rssi_weight=float(raw.get("rssi_weight", 0.2)),
        )
        config.validate()
        return config

    def validate(self):
        if self.smoothing_windows <= 0:
            raise ZoneConfigError("smoothing_windows must be positive")
        if not 0 <= self.switch_margin <= 1:
            raise ZoneConfigError("switch_margin must be between 0 and 1")
        if not 0 <= self.minimum_confidence <= 1:
            raise ZoneConfigError("minimum_confidence must be between 0 and 1")
        if self.stale_after_us <= 0:
            raise ZoneConfigError("stale_after_seconds must be positive")
        if self.motion_weight < 0 or self.rssi_weight < 0:
            raise ZoneConfigError("zone signal weights must not be negative")
        if self.motion_weight + self.rssi_weight <= 0:
            raise ZoneConfigError("at least one zone signal weight must be positive")
        node_zones = []
        for node_id, node in self.nodes.items():
            if not node.zone:
                raise ZoneConfigError(f"zone must not be empty for {node_id}")
            if node.motion_scale <= 0 or node.rssi_range <= 0:
                raise ZoneConfigError(f"node scales must be positive for {node_id}")
            node_zones.append(node.zone)
        if self.zones is None and len(node_zones) != len(set(node_zones)):
            raise ZoneConfigError("each receiver must map to a distinct coarse zone")
        if self.zones is not None:
            if len(self.zones) < 2:
                raise ZoneConfigError("at least two calibrated zone signatures are required")
            for zone_name, weights in self.zones.items():
                if set(weights) != set(self.nodes):
                    raise ZoneConfigError(
                        f"zone {zone_name} must define every configured receiver"
                    )
                if any(weight < 0 for weight in weights.values()) or sum(weights.values()) <= 0:
                    raise ZoneConfigError(f"zone {zone_name} weights must be non-negative")


class ZonePredictor:
    """Smooth receiver evidence and emit stable, coarse zone predictions."""

    EMPTY_ACTIVITIES = frozenset({"empty_room"})

    def __init__(self, config: ZonePredictorConfig):
        config.validate()
        self.config = config
        self.history = {
            node_id: deque(maxlen=config.smoothing_windows)
            for node_id in config.nodes
        }
        self.node_online: dict[str, bool] = {}
        self.latest_rssi: dict[str, tuple[float, int | None]] = {}
        self.latest_activity: str | None = None
        self.current_node: str | None = None
        self.current_zone: str | None = None
        self.last_motion_timestamp_us: int | None = None

    def process(self, record: dict) -> list[dict]:
        if not isinstance(record, dict):
            return []
        message_type = record.get("message_type")
        if message_type == "node_status":
            self._update_node_status(record)
            return []
        if message_type == "health":
            self._update_health(record)
            return []
        if message_type == "activity_prediction":
            activity = record.get("activity")
            if isinstance(activity, str):
                self.latest_activity = activity
            if activity in self.EMPTY_ACTIVITIES:
                timestamp = record.get("window_end_us")
                if isinstance(timestamp, int):
                    self.current_node = None
                    self.current_zone = None
                    return [self._unoccupied(timestamp)]
            return []
        if message_type != "motion_score":
            return []
        return self._process_motion(record)

    def _update_node_status(self, record: dict):
        node_id = record.get("node_id")
        status = record.get("status")
        if node_id in self.config.nodes and status in {"online", "offline"}:
            self.node_online[node_id] = status == "online"
            if status == "offline":
                self.history[node_id].clear()

    def _update_health(self, record: dict):
        node_id = record.get("node_id")
        if node_id not in self.config.nodes:
            return
        value = record.get("last_rssi", record.get("rssi"))
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            timestamp = record.get("collector_ts_us")
            self.latest_rssi[node_id] = (
                float(value),
                timestamp if isinstance(timestamp, int) else None,
            )

    def _process_motion(self, record: dict) -> list[dict]:
        timestamp = record.get("window_end_us")
        raw_scores = record.get("scores")
        if not isinstance(timestamp, int) or not isinstance(raw_scores, dict):
            return []
        if self.last_motion_timestamp_us is not None and timestamp <= self.last_motion_timestamp_us:
            return []
        self.last_motion_timestamp_us = timestamp

        for node_id, node in self.config.nodes.items():
            raw_score = raw_scores.get(node_id)
            if (
                self.node_online.get(node_id, True)
                and isinstance(raw_score, (int, float))
                and not isinstance(raw_score, bool)
                and math.isfinite(raw_score)
                and raw_score >= 0
            ):
                motion = math.log1p(float(raw_score) / node.motion_scale)
                rssi_entry = self.latest_rssi.get(node_id)
                rssi = None
                if rssi_entry is not None:
                    value, rssi_timestamp = rssi_entry
                    if (
                        rssi_timestamp is None
                        or abs(timestamp - rssi_timestamp) <= self.config.stale_after_us
                    ):
                        rssi = value
                rssi_score = (
                    max(0.0, 1.0 - abs(rssi - node.rssi_reference) / node.rssi_range)
                    if rssi is not None
                    else 0.0
                )
                combined = (
                    self.config.motion_weight * motion
                    + self.config.rssi_weight * rssi_score
                )
                self.history[node_id].append(combined)

        if self.latest_activity in self.EMPTY_ACTIVITIES:
            self.current_node = None
            self.current_zone = None
            return [self._unoccupied(timestamp)]

        smoothed = {
            node_id: sum(values) / len(values)
            for node_id, values in self.history.items()
            if values and self.node_online.get(node_id, True)
        }
        if not smoothed:
            self.current_node = None
            return [self._unknown(timestamp, "no_receiver_evidence", {})]

        ordered = sorted(smoothed, key=smoothed.get, reverse=True)
        candidate = ordered[0]
        total = sum(max(0.0, value) for value in smoothed.values())
        confidence = smoothed[candidate] / total if total > 0 else 0.0

        if self.current_node in smoothed and candidate != self.current_node:
            current_score = smoothed[self.current_node]
            required = current_score * (1.0 + self.config.switch_margin)
            if smoothed[candidate] < required:
                candidate = self.current_node
                confidence = smoothed[candidate] / total if total > 0 else 0.0

        normalized_scores = {
            node_id: round(value / total, 6) if total > 0 else 0.0
            for node_id, value in smoothed.items()
        }
        if self.config.zones is not None:
            return [self._profile_prediction(timestamp, smoothed, normalized_scores)]
        if confidence < self.config.minimum_confidence:
            return [self._unknown(timestamp, "low_confidence", normalized_scores)]

        self.current_node = candidate
        self.current_zone = self.config.nodes[candidate].zone
        return [{
            "schema_version": 1,
            "message_type": "zone_prediction",
            "timestamp_us": timestamp,
            "zone": self.config.nodes[candidate].zone,
            "confidence": round(confidence, 6),
            "source_node": candidate,
            "node_scores": normalized_scores,
            "method": "smoothed_receiver_evidence",
            "coarse_location_only": True,
        }]

    def _profile_prediction(
        self,
        timestamp: int,
        smoothed: dict[str, float],
        normalized_scores: dict[str, float],
    ) -> dict:
        available_nodes = set(normalized_scores)
        similarities = {}
        for zone_name, weights in self.config.zones.items():
            available_weights = {
                node_id: weight
                for node_id, weight in weights.items()
                if node_id in available_nodes
            }
            weight_total = sum(available_weights.values())
            if weight_total <= 0:
                continue
            profile = {
                node_id: weight / weight_total
                for node_id, weight in available_weights.items()
            }
            distance = sum(
                abs(normalized_scores[node_id] - profile[node_id])
                for node_id in available_nodes
            ) / 2
            similarities[zone_name] = max(0.0, 1.0 - distance)
        if not similarities:
            return self._unknown(timestamp, "no_zone_signature", normalized_scores)
        candidate = max(similarities, key=similarities.get)
        if self.current_zone in similarities and candidate != self.current_zone:
            if similarities[candidate] - similarities[self.current_zone] < self.config.switch_margin:
                candidate = self.current_zone
        confidence = similarities[candidate]
        if confidence < self.config.minimum_confidence:
            return self._unknown(timestamp, "low_confidence", normalized_scores)
        self.current_zone = candidate
        self.current_node = max(smoothed, key=smoothed.get)
        return {
            "schema_version": 1,
            "message_type": "zone_prediction",
            "timestamp_us": timestamp,
            "zone": candidate,
            "confidence": round(confidence, 6),
            "source_node": self.current_node,
            "node_scores": normalized_scores,
            "zone_scores": {
                zone_name: round(score, 6)
                for zone_name, score in similarities.items()
            },
            "method": "calibrated_receiver_signature",
            "coarse_location_only": True,
        }

    @staticmethod
    def _unknown(timestamp: int, reason: str, scores: dict[str, float]) -> dict:
        return {
            "schema_version": 1,
            "message_type": "zone_prediction",
            "timestamp_us": timestamp,
            "zone": "unknown",
            "confidence": 0.0,
            "source_node": None,
            "node_scores": scores,
            "reason": reason,
            "method": "smoothed_receiver_evidence",
            "coarse_location_only": True,
        }

    @staticmethod
    def _unoccupied(timestamp: int) -> dict:
        return {
            "schema_version": 1,
            "message_type": "zone_prediction",
            "timestamp_us": timestamp,
            "zone": "unoccupied",
            "confidence": 1.0,
            "source_node": None,
            "node_scores": {},
            "reason": "empty_room_activity",
            "method": "activity_gate",
            "coarse_location_only": True,
        }


def run_stream(
    predictor: ZonePredictor,
    input_stream: TextIOBase,
    output_stream: TextIOBase,
    error_stream: TextIOBase,
) -> int:
    invalid_lines = 0
    for line_number, line in enumerate(input_stream, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            invalid_lines += 1
            print(f"Skipping invalid JSON on input line {line_number}: {exc}", file=error_stream)
            continue
        if not isinstance(record, dict):
            invalid_lines += 1
            print(f"Skipping non-object JSON on input line {line_number}", file=error_stream)
            continue
        print(json.dumps(record, ensure_ascii=False, separators=(",", ":")), file=output_stream, flush=True)
        for prediction in predictor.process(record):
            print(json.dumps(prediction, ensure_ascii=False, separators=(",", ":")), file=output_stream, flush=True)
    return invalid_lines


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("server/config/zones.json"),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    predictor = ZonePredictor(ZonePredictorConfig.from_path(args.config))
    try:
        run_stream(predictor, sys.stdin, sys.stdout, sys.stderr)
    except KeyboardInterrupt:
        print("Stopping zone predictor.", file=sys.stderr)


if __name__ == "__main__":
    main()
