import io
import json
import unittest

from zone_predictor import (
    ZoneNodeConfig,
    ZonePredictor,
    ZonePredictorConfig,
    run_stream,
)


def config(**overrides):
    values = {
        "nodes": {
            "rx_01": ZoneNodeConfig(zone="desk", motion_scale=1),
            "rx_02": ZoneNodeConfig(zone="door", motion_scale=1),
        },
        "smoothing_windows": 1,
        "switch_margin": 0.15,
        "minimum_confidence": 0.55,
        "motion_weight": 1,
        "rssi_weight": 0,
    }
    values.update(overrides)
    return ZonePredictorConfig(**values)


def motion(timestamp, rx_01, rx_02):
    return {
        "message_type": "motion_score",
        "window_end_us": timestamp,
        "scores": {"rx_01": rx_01, "rx_02": rx_02},
    }


class ZonePredictorTest(unittest.TestCase):
    def test_selects_stronger_receiver_zone(self):
        predictor = ZonePredictor(config())
        record = predictor.process(motion(1, 20, 1))[0]
        self.assertEqual(record["zone"], "desk")
        self.assertEqual(record["source_node"], "rx_01")
        self.assertGreater(record["confidence"], 0.55)
        self.assertTrue(record["coarse_location_only"])

    def test_reports_unknown_when_receivers_are_ambiguous(self):
        predictor = ZonePredictor(config())
        record = predictor.process(motion(1, 5, 5))[0]
        self.assertEqual(record["zone"], "unknown")
        self.assertEqual(record["reason"], "low_confidence")

    def test_hysteresis_prevents_small_zone_switch(self):
        predictor = ZonePredictor(config(minimum_confidence=0.4, switch_margin=0.3))
        self.assertEqual(predictor.process(motion(1, 10, 1))[0]["zone"], "desk")
        record = predictor.process(motion(2, 10, 11))[0]
        self.assertEqual(record["zone"], "desk")

    def test_offline_receiver_is_removed_from_evidence(self):
        predictor = ZonePredictor(config())
        predictor.process({
            "message_type": "node_status",
            "node_id": "rx_01",
            "status": "offline",
        })
        record = predictor.process(motion(1, 100, 1))[0]
        self.assertEqual(record["zone"], "door")
        self.assertEqual(record["source_node"], "rx_02")

    def test_empty_room_gates_zone_as_unoccupied(self):
        predictor = ZonePredictor(config())
        records = predictor.process({
            "message_type": "activity_prediction",
            "window_end_us": 10,
            "activity": "empty_room",
        })
        self.assertEqual(records[0]["zone"], "unoccupied")
        self.assertEqual(records[0]["confidence"], 1.0)

    def test_calibrated_signatures_support_third_zone_with_two_receivers(self):
        predictor = ZonePredictor(config(
            zones={
                "desk": {"rx_01": 0.85, "rx_02": 0.15},
                "door": {"rx_01": 0.15, "rx_02": 0.85},
                "window": {"rx_01": 0.5, "rx_02": 0.5},
            },
        ))
        record = predictor.process(motion(1, 5, 5))[0]
        self.assertEqual(record["zone"], "window")
        self.assertEqual(record["method"], "calibrated_receiver_signature")
        self.assertEqual(set(record["zone_scores"]), {"desk", "door", "window"})

    def test_stream_preserves_input_and_appends_zone(self):
        predictor = ZonePredictor(config())
        input_record = motion(1, 20, 1)
        output = io.StringIO()
        self.assertEqual(
            run_stream(
                predictor,
                io.StringIO(json.dumps(input_record) + "\n"),
                output,
                io.StringIO(),
            ),
            0,
        )
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(
            [record["message_type"] for record in records],
            ["motion_score", "zone_prediction"],
        )


if __name__ == "__main__":
    unittest.main()
