import math
import unittest

from ld2450_simulator import (
    build_parser,
    ground_truth_message,
    simulated_target,
)


class Ld2450SimulatorTest(unittest.TestCase):
    def test_ground_truth_contract_and_empty_scene(self):
        message = ground_truth_message(
            "ld2450_test",
            ts_us=123456,
            frame_seq=42,
            count=0,
            elapsed_seconds=0.0,
        )

        self.assertEqual(message["schema_version"], 1)
        self.assertEqual(message["message_type"], "ground_truth")
        self.assertEqual(message["node_id"], "ld2450_test")
        self.assertEqual(message["ts_us"], 123456)
        self.assertEqual(message["frame_seq"], 42)
        self.assertEqual(message["targets"], [])

    def test_three_targets_have_expected_fields_and_distance(self):
        message = ground_truth_message(
            "ld2450_01",
            ts_us=0,
            frame_seq=0,
            count=3,
            elapsed_seconds=2.5,
        )

        self.assertEqual(len(message["targets"]), 3)
        self.assertEqual(
            [target["target_id"] for target in message["targets"]],
            [1, 2, 3],
        )

        for target in message["targets"]:
            self.assertEqual(
                target["distance_mm"],
                round(math.hypot(target["x_mm"], target["y_mm"])),
            )
            self.assertEqual(target["resolution_mm"], 320)

    def test_target_motion_is_deterministic(self):
        self.assertEqual(simulated_target(1, 1.25), simulated_target(1, 1.25))
        self.assertNotEqual(simulated_target(1, 1.25), simulated_target(1, 2.25))

    def test_cli_parameters_are_overridable(self):
        args = build_parser().parse_args([
            "--transport", "mqtt",
            "--broker-host", "192.0.2.10",
            "--broker-port", "1884",
            "--topic", "vsense/gt/test_radar",
            "--node-id", "test_radar",
            "--rate-hz", "5",
            "--duration-seconds", "2",
            "--target-count", "2",
        ])

        self.assertEqual(args.transport, "mqtt")
        self.assertEqual(args.broker_host, "192.0.2.10")
        self.assertEqual(args.broker_port, 1884)
        self.assertEqual(args.topic, "vsense/gt/test_radar")
        self.assertEqual(args.node_id, "test_radar")
        self.assertEqual(args.rate_hz, 5.0)
        self.assertEqual(args.duration_seconds, 2.0)
        self.assertEqual(args.target_count, 2)

    def test_cli_rejects_invalid_target_count(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["--target-count", "4"])


if __name__ == "__main__":
    unittest.main()
