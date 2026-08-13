import io
import json
import unittest
from unittest.mock import patch

import inactivity_alarm
from inactivity_alarm import InactivityAlarmConfig, InactivityAlarmEngine, run_stream


def prediction(activity: str, seconds: float, zone: str | None = None) -> dict:
    value = {
        "message_type": "activity_prediction",
        "activity": activity,
        "window_end_us": int(seconds * 1_000_000),
    }
    if zone is not None:
        value["zone"] = zone
    return value


class InactivityAlarmEngineTest(unittest.TestCase):
    def setUp(self):
        self.engine = InactivityAlarmEngine(
            InactivityAlarmConfig(threshold_seconds=300),
        )

    def test_raises_once_when_threshold_is_reached(self):
        self.assertEqual(self.engine.process(prediction("sitting", 10)), [])
        self.assertEqual(self.engine.process(prediction("sitting", 309)), [])
        events = self.engine.process(prediction("sitting", 310, zone="office"))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "raised")
        self.assertEqual(events[0]["inactive_seconds"], 300.0)
        self.assertEqual(events[0]["zone"], "office")
        self.assertEqual(self.engine.process(prediction("standing", 400)), [])

    def test_movement_clears_active_alarm_and_resets_timer(self):
        self.engine.process(prediction("standing", 10, zone="bedroom"))
        self.engine.process(prediction("standing", 310))
        events = self.engine.process(prediction("walking", 311))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "cleared")
        self.assertEqual(events[0]["reason"], "movement_detected")
        self.assertEqual(events[0]["zone"], "bedroom")
        self.assertEqual(self.engine.process(prediction("sitting", 312)), [])

    def test_empty_room_does_not_raise_person_inactivity_alarm(self):
        self.assertEqual(self.engine.process(prediction("empty_room", 10)), [])
        self.assertEqual(self.engine.process(prediction("empty_room", 1000)), [])
        self.assertIsNone(self.engine.inactive_since_us)
        self.assertFalse(self.engine.alarm_active)

    def test_empty_room_clears_existing_alarm(self):
        self.engine.process(prediction("desk_work", 10))
        self.engine.process(prediction("desk_work", 310))
        events = self.engine.process(prediction("empty_room", 311))
        self.assertEqual(events[0]["status"], "cleared")
        self.assertEqual(events[0]["reason"], "room_empty")

    def test_inactive_classes_share_one_continuous_timer(self):
        self.engine.process(prediction("sitting", 10))
        self.engine.process(prediction("standing", 150))
        events = self.engine.process(prediction("desk_work", 310))
        self.assertEqual(events[0]["status"], "raised")
        self.assertEqual(events[0]["inactive_seconds"], 300.0)

    def test_ignores_unknown_activity_without_resetting_state(self):
        self.engine.process(prediction("sitting", 10))
        self.assertEqual(self.engine.process(prediction("unknown", 100)), [])
        events = self.engine.process(prediction("sitting", 310))
        self.assertEqual(events[0]["status"], "raised")

    def test_ignores_duplicate_out_of_order_and_unrelated_messages(self):
        self.engine.process(prediction("sitting", 10))
        self.assertEqual(self.engine.process(prediction("sitting", 10)), [])
        self.assertEqual(self.engine.process(prediction("sitting", 9)), [])
        self.assertEqual(self.engine.process({"message_type": "health"}), [])
        self.assertEqual(self.engine.last_timestamp_us, 10_000_000)

    def test_rejects_invalid_config(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            InactivityAlarmEngine(InactivityAlarmConfig(threshold_seconds=0))
        with self.assertRaisesRegex(ValueError, "overlap"):
            InactivityAlarmEngine(InactivityAlarmConfig(
                threshold_seconds=10,
                moving_activities=frozenset({"walking", "sitting"}),
            ))


class InactivityAlarmStreamTest(unittest.TestCase):
    def test_passes_predictions_through_and_appends_alarm_transitions(self):
        engine = InactivityAlarmEngine(
            InactivityAlarmConfig(threshold_seconds=10),
        )
        inputs = [
            prediction("sitting", 1, zone="office"),
            prediction("standing", 11),
            prediction("walking", 12),
        ]
        output = io.StringIO()
        invalid_lines = run_stream(
            engine,
            io.StringIO("".join(json.dumps(value) + "\n" for value in inputs)),
            output,
            io.StringIO(),
        )
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(invalid_lines, 0)
        self.assertEqual(
            [record["message_type"] for record in records],
            [
                "activity_prediction",
                "activity_prediction",
                "inactivity_alarm",
                "activity_prediction",
                "inactivity_alarm",
            ],
        )
        self.assertEqual(records[2]["status"], "raised")
        self.assertEqual(records[4]["status"], "cleared")

    def test_reports_invalid_input_without_forwarding_it(self):
        engine = InactivityAlarmEngine(
            InactivityAlarmConfig(threshold_seconds=10),
        )
        output = io.StringIO()
        errors = io.StringIO()
        invalid_lines = run_stream(
            engine,
            io.StringIO("not-json\n[]\n"),
            output,
            errors,
        )
        self.assertEqual(invalid_lines, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("invalid JSON", errors.getvalue())
        self.assertIn("non-object JSON", errors.getvalue())

    def test_main_stops_cleanly_on_keyboard_interrupt(self):
        with (
            patch.object(inactivity_alarm, "parse_args") as parse_args,
            patch.object(
                inactivity_alarm,
                "run_stream",
                side_effect=KeyboardInterrupt,
            ),
            patch.object(inactivity_alarm.sys, "stderr", io.StringIO()) as errors,
        ):
            parse_args.return_value.threshold_seconds = 30
            inactivity_alarm.main()
            self.assertEqual(errors.getvalue(), "Stopping inactivity alarm.\n")


if __name__ == "__main__":
    unittest.main()
