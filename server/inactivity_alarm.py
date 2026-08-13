"""Stateful inactivity alarms driven by activity prediction events."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from io import TextIOBase


@dataclass(frozen=True)
class InactivityAlarmConfig:
    threshold_seconds: float
    moving_activities: frozenset[str] = frozenset({"walking"})
    inactive_activities: frozenset[str] = frozenset({
        "sitting",
        "standing",
        "desk_work",
    })
    empty_activities: frozenset[str] = frozenset({"empty_room"})
    default_zone: str = "unknown"

    def validate(self):
        if self.threshold_seconds <= 0:
            raise ValueError("inactivity threshold must be positive")
        groups = (
            self.moving_activities,
            self.inactive_activities,
            self.empty_activities,
        )
        if any(not group for group in groups):
            raise ValueError("activity groups must not be empty")
        if (
            self.moving_activities & self.inactive_activities
            or self.moving_activities & self.empty_activities
            or self.inactive_activities & self.empty_activities
        ):
            raise ValueError("activity groups must not overlap")


class InactivityAlarmEngine:
    """Track inactivity and emit raised/cleared alarm events once per transition."""

    def __init__(self, config: InactivityAlarmConfig):
        config.validate()
        self.config = config
        self.inactive_since_us: int | None = None
        self.last_timestamp_us: int | None = None
        self.last_zone = config.default_zone
        self.alarm_active = False

    def process(self, prediction: dict) -> list[dict]:
        if prediction.get("message_type") != "activity_prediction":
            return []
        activity = prediction.get("activity")
        timestamp_us = prediction.get("window_end_us")
        if not isinstance(activity, str) or not isinstance(timestamp_us, int):
            return []
        if self.last_timestamp_us is not None and timestamp_us <= self.last_timestamp_us:
            return []
        self.last_timestamp_us = timestamp_us
        zone = prediction.get("zone")
        if isinstance(zone, str) and zone:
            self.last_zone = zone

        if activity in self.config.empty_activities:
            return self._reset(timestamp_us, activity, reason="room_empty")
        if activity in self.config.moving_activities:
            return self._reset(timestamp_us, activity, reason="movement_detected")
        if activity not in self.config.inactive_activities:
            return []

        if self.inactive_since_us is None:
            self.inactive_since_us = timestamp_us
            return []
        inactive_seconds = (timestamp_us - self.inactive_since_us) / 1_000_000
        if inactive_seconds < self.config.threshold_seconds or self.alarm_active:
            return []

        self.alarm_active = True
        return [self._event(
            status="raised",
            timestamp_us=timestamp_us,
            activity=activity,
            inactive_seconds=inactive_seconds,
            reason="inactivity_threshold_reached",
        )]

    def _reset(self, timestamp_us: int, activity: str, reason: str) -> list[dict]:
        inactive_seconds = (
            (timestamp_us - self.inactive_since_us) / 1_000_000
            if self.inactive_since_us is not None
            else 0.0
        )
        was_active = self.alarm_active
        self.inactive_since_us = None
        self.alarm_active = False
        if not was_active:
            return []
        return [self._event(
            status="cleared",
            timestamp_us=timestamp_us,
            activity=activity,
            inactive_seconds=max(0.0, inactive_seconds),
            reason=reason,
        )]

    def _event(
        self,
        *,
        status: str,
        timestamp_us: int,
        activity: str,
        inactive_seconds: float,
        reason: str,
    ) -> dict:
        return {
            "schema_version": 1,
            "message_type": "inactivity_alarm",
            "status": status,
            "timestamp_us": timestamp_us,
            "zone": self.last_zone,
            "activity": activity,
            "inactive_seconds": round(inactive_seconds, 3),
            "threshold_seconds": self.config.threshold_seconds,
            "reason": reason,
        }


def run_stream(
    engine: InactivityAlarmEngine,
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
            print(
                f"Skipping invalid JSON on input line {line_number}: {exc}",
                file=error_stream,
            )
            continue
        if not isinstance(record, dict):
            invalid_lines += 1
            print(
                f"Skipping non-object JSON on input line {line_number}",
                file=error_stream,
            )
            continue

        print(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")),
            file=output_stream,
            flush=True,
        )
        for event in engine.process(record):
            print(
                json.dumps(event, ensure_ascii=False, separators=(",", ":")),
                file=output_stream,
                flush=True,
            )
    return invalid_lines


def parse_args():
    parser = argparse.ArgumentParser(
        description="Add inactivity alarm events to activity-prediction JSONL",
    )
    parser.add_argument("--threshold-seconds", type=float, default=300.0)
    return parser.parse_args()


def main():
    args = parse_args()
    engine = InactivityAlarmEngine(
        InactivityAlarmConfig(threshold_seconds=args.threshold_seconds),
    )
    try:
        run_stream(engine, sys.stdin, sys.stdout, sys.stderr)
    except KeyboardInterrupt:
        print("Stopping inactivity alarm.", file=sys.stderr)


if __name__ == "__main__":
    main()
