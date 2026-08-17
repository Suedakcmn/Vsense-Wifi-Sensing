import argparse
import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from run_dashboard import (
    build_commands,
    monitor_pipeline,
    stop_pipeline,
    validate_paths,
)


def arguments(root: Path):
    return argparse.Namespace(
        mqtt_host="broker.local",
        mqtt_port=1883,
        mqtt_username=None,
        mqtt_password_env="VSENSE_MQTT_PASSWORD",
        client_id="test-dashboard",
        offline_timeout=5.0,
        artifact_dir=root / "model",
        model_version="test_v1",
        zone_config=root / "zones.json",
        inactivity_seconds=30.0,
        zone_max_age_seconds=15.0,
        web_host="127.0.0.1",
        web_port=8000,
        max_events=50,
        static_dir=root / "web",
    )


class RunDashboardTest(unittest.TestCase):
    def test_builds_five_stage_pipeline_without_password_on_command_line(self):
        with TemporaryDirectory() as temporary_directory:
            args = arguments(Path(temporary_directory))
            commands = build_commands(args, "/python")
            self.assertEqual(len(commands), 5)
            self.assertIn("server/mqtt_collector.py", commands[0])
            self.assertIn("server/live_activity_predictor.py", commands[1])
            self.assertIn("server/zone_predictor.py", commands[2])
            self.assertIn("server/inactivity_alarm.py", commands[3])
            self.assertIn("server/dashboard_api.py", commands[4])
            self.assertNotIn("--password", commands[0])

    def test_reads_optional_password_from_named_environment_variable(self):
        with TemporaryDirectory() as temporary_directory:
            args = arguments(Path(temporary_directory))
            args.mqtt_username = "sensor"
            with patch.dict(os.environ, {"VSENSE_MQTT_PASSWORD": "secret"}):
                command = build_commands(args, "/python")[0]
            self.assertNotIn("secret", command)
            self.assertNotIn("--password", command)
            self.assertEqual(
                command[command.index("--password-env") + 1],
                "VSENSE_MQTT_PASSWORD",
            )

    def test_validates_model_and_dashboard_build(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            args = arguments(root)
            args.static_dir.mkdir()
            (args.static_dir / "index.html").write_text("dashboard")
            with (
                patch("run_dashboard.validate_artifact"),
                patch("run_dashboard.ZonePredictorConfig.from_path"),
            ):
                validate_paths(args)
            (args.static_dir / "index.html").unlink()
            with (
                patch("run_dashboard.validate_artifact"),
                patch("run_dashboard.ZonePredictorConfig.from_path"),
                self.assertRaisesRegex(SystemExit, "dashboard build not found"),
            ):
                validate_paths(args)

    def test_monitor_reports_failed_stage(self):
        first = Mock()
        second = Mock()
        first.poll.return_value = None
        second.poll.return_value = 2
        with self.assertRaisesRegex(RuntimeError, "stage 2 exited with code 2"):
            monitor_pipeline([first, second], poll_interval=0)

    def test_stop_terminates_running_processes_in_reverse_order(self):
        order = []

        def process(name):
            value = Mock()
            value.poll.return_value = None
            value.terminate.side_effect = lambda: order.append(f"terminate:{name}")
            value.wait.side_effect = lambda timeout=None: order.append(f"wait:{name}")
            return value

        first = process("first")
        second = process("second")
        stop_pipeline([first, second])
        self.assertEqual(order[:2], ["terminate:second", "terminate:first"])


if __name__ == "__main__":
    unittest.main()
