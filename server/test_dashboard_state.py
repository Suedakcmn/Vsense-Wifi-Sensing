import unittest

from dashboard_state import DashboardState, DashboardStateConfig


class DashboardStateTest(unittest.TestCase):
    def test_reduces_prediction_alarm_and_clear_events(self):
        state = DashboardState()
        prediction = {
            "message_type": "activity_prediction",
            "window_end_us": 10,
            "activity": "sitting",
            "confidence": 0.8,
        }
        raised = {
            "message_type": "inactivity_alarm",
            "timestamp_us": 20,
            "status": "raised",
            "zone": "office",
        }
        cleared = {
            "message_type": "inactivity_alarm",
            "timestamp_us": 30,
            "status": "cleared",
            "zone": "office",
        }
        self.assertTrue(state.apply(prediction))
        self.assertTrue(state.apply(raised))
        self.assertEqual(state.snapshot()["active_alarm"]["zone"], "office")
        self.assertTrue(state.apply(cleared))
        snapshot = state.snapshot()
        self.assertEqual(snapshot["latest_prediction"]["activity"], "sitting")
        self.assertIsNone(snapshot["active_alarm"])
        self.assertEqual(snapshot["revision"], 3)
        self.assertEqual(len(snapshot["events"]), 3)

    def test_combines_node_status_and_health(self):
        state = DashboardState()
        state.apply({
            "message_type": "node_status",
            "node_id": "rx_02",
            "status": "online",
            "source": "mqtt_status",
        })
        state.apply({
            "message_type": "health",
            "node_id": "rx_02",
            "csi_pps": 83,
        })
        node = state.snapshot()["nodes"]["rx_02"]
        self.assertEqual(node["status"], "online")
        self.assertEqual(node["health"]["csi_pps"], 83)

    def test_accepts_future_zone_prediction_without_model_dependency(self):
        state = DashboardState()
        self.assertTrue(state.apply({
            "message_type": "zone_prediction",
            "timestamp_us": 50,
            "zone": "kitchen",
            "confidence": 0.7,
        }))
        self.assertEqual(state.snapshot()["latest_zone"]["zone"], "kitchen")

    def test_ignores_invalid_and_unknown_records(self):
        state = DashboardState()
        self.assertFalse(state.apply([]))
        self.assertFalse(state.apply({"message_type": "unknown"}))
        self.assertFalse(state.apply({
            "message_type": "activity_prediction",
            "activity": "walking",
        }))
        self.assertFalse(state.apply({
            "message_type": "node_status",
            "node_id": "rx_01",
            "status": "starting",
        }))
        self.assertEqual(state.snapshot()["revision"], 0)

    def test_event_history_is_bounded(self):
        state = DashboardState(DashboardStateConfig(max_events=2))
        for timestamp in (1, 2, 3):
            state.apply({
                "message_type": "activity_prediction",
                "window_end_us": timestamp,
                "activity": "walking",
            })
        snapshot = state.snapshot()
        self.assertEqual(
            [event["window_end_us"] for event in snapshot["events"]],
            [2, 3],
        )

    def test_snapshot_isolated_from_external_mutation(self):
        state = DashboardState()
        record = {
            "message_type": "activity_prediction",
            "window_end_us": 10,
            "activity": "walking",
            "probabilities": {"walking": 1.0},
        }
        state.apply(record)
        record["probabilities"]["walking"] = 0.0
        snapshot = state.snapshot()
        snapshot["latest_prediction"]["activity"] = "changed"
        self.assertEqual(
            state.snapshot()["latest_prediction"]["probabilities"]["walking"],
            1.0,
        )
        self.assertEqual(state.snapshot()["latest_prediction"]["activity"], "walking")

    def test_rejects_invalid_config(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            DashboardState(DashboardStateConfig(max_events=0))


if __name__ == "__main__":
    unittest.main()
