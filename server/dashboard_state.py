"""Framework-independent live state consumed by the VSense web dashboard."""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass


@dataclass(frozen=True)
class DashboardStateConfig:
    max_events: int = 100

    def validate(self):
        if self.max_events <= 0:
            raise ValueError("max_events must be positive")


class DashboardState:
    """Reduce normalized pipeline records into a serializable dashboard snapshot."""

    def __init__(self, config: DashboardStateConfig = DashboardStateConfig()):
        config.validate()
        self.config = config
        self.latest_prediction: dict | None = None
        self.active_alarm: dict | None = None
        self.latest_zone: dict | None = None
        self.latest_ground_truth: dict | None = None
        self.motion_scores: deque[dict] = deque(maxlen=config.max_events)
        self.nodes: dict[str, dict] = {}
        self.events: deque[dict] = deque(maxlen=config.max_events)
        self.revision = 0

    def apply(self, record: dict) -> bool:
        if not isinstance(record, dict):
            return False
        message_type = record.get("message_type")
        changed = False

        if message_type == "activity_prediction":
            changed = self._apply_prediction(record)
        elif message_type == "inactivity_alarm":
            changed = self._apply_alarm(record)
        elif message_type == "node_status":
            changed = self._apply_node_status(record)
        elif message_type == "health":
            changed = self._apply_health(record)
        elif message_type == "zone_prediction":
            changed = self._apply_zone(record)
        elif message_type == "motion_score":
            changed = self._apply_motion_score(record)
        elif message_type == "ground_truth":
            changed = self._apply_ground_truth(record)

        if changed:
            self.revision += 1
        return changed

    def _apply_prediction(self, record: dict) -> bool:
        activity = record.get("activity")
        timestamp = record.get("window_end_us")
        if not isinstance(activity, str) or not isinstance(timestamp, int):
            return False
        self.latest_prediction = deepcopy(record)
        self.events.append(deepcopy(record))
        return True

    def _apply_alarm(self, record: dict) -> bool:
        status = record.get("status")
        timestamp = record.get("timestamp_us")
        if status not in {"raised", "cleared"} or not isinstance(timestamp, int):
            return False
        if status == "raised":
            self.active_alarm = deepcopy(record)
        else:
            self.active_alarm = None
        self.events.append(deepcopy(record))
        return True

    def _apply_node_status(self, record: dict) -> bool:
        node_id = record.get("node_id")
        status = record.get("status")
        if not isinstance(node_id, str) or not node_id or status not in {
            "online",
            "offline",
        }:
            return False
        node = self.nodes.setdefault(node_id, {"node_id": node_id})
        node.update({
            "status": status,
            "status_source": record.get("source"),
            "last_status": deepcopy(record),
        })
        self.events.append(deepcopy(record))
        return True

    def _apply_health(self, record: dict) -> bool:
        node_id = record.get("node_id")
        if not isinstance(node_id, str) or not node_id:
            return False
        node = self.nodes.setdefault(node_id, {"node_id": node_id})
        node["health"] = deepcopy(record)
        return True

    def _apply_zone(self, record: dict) -> bool:
        zone = record.get("zone")
        timestamp = record.get("timestamp_us")
        if not isinstance(zone, str) or not zone or not isinstance(timestamp, int):
            return False
        self.latest_zone = deepcopy(record)
        self.events.append(deepcopy(record))
        return True

    def _apply_motion_score(self, record: dict) -> bool:
        timestamp = record.get("window_end_us")
        scores = record.get("scores")
        if not isinstance(timestamp, int) or not isinstance(scores, dict) or not scores:
            return False
        if not all(
            isinstance(node_id, str)
            and node_id
            and isinstance(score, (int, float))
            and not isinstance(score, bool)
            for node_id, score in scores.items()
        ):
            return False
        self.motion_scores.append(deepcopy(record))
        return True

    def _apply_ground_truth(self, record: dict) -> bool:
        timestamp = record.get("collector_ts_us")
        targets = record.get("targets")
        if not isinstance(timestamp, int) or not isinstance(targets, list):
            return False
        if not all(
            isinstance(target, dict)
            and all(isinstance(target.get(field), int) for field in (
                "target_id", "x_mm", "y_mm", "speed_cm_s", "resolution_mm"
            ))
            for target in targets
        ):
            return False
        self.latest_ground_truth = deepcopy(record)
        return True

    def snapshot(self) -> dict:
        return {
            "schema_version": 1,
            "message_type": "dashboard_state",
            "revision": self.revision,
            "latest_prediction": deepcopy(self.latest_prediction),
            "active_alarm": deepcopy(self.active_alarm),
            "latest_zone": deepcopy(self.latest_zone),
            "latest_ground_truth": deepcopy(self.latest_ground_truth),
            "motion_scores": [deepcopy(value) for value in self.motion_scores],
            "nodes": {
                node_id: deepcopy(value)
                for node_id, value in sorted(self.nodes.items())
            },
            "events": [deepcopy(event) for event in self.events],
        }
