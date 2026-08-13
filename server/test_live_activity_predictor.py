import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from test_activity_model import write_window_artifact
from live_activity_predictor import (
    LiveActivityPredictor,
    LiveCSIWindowBuffer,
    LiveWindowConfig,
    run_stream,
)
import live_activity_predictor


def csi_row(timestamp: int, node_id: str, csi_length: int = 256) -> dict:
    return {
        "message_type": "csi",
        "node_id": node_id,
        "collector_ts_us": timestamp,
        "len": csi_length,
        "rssi": -40,
        "csi": [1] * csi_length,
    }


def config(**overrides) -> LiveWindowConfig:
    values = {
        "duration_us": 2_000_000,
        "stride_us": 1_000_000,
        "max_gap_us": 500_000,
        "min_rows_per_node": 4,
        "expected_csi_length": 256,
        "required_nodes": ("rx_01", "rx_02"),
    }
    values.update(overrides)
    return LiveWindowConfig(**values)


class LiveCSIWindowBufferTest(unittest.TestCase):
    def test_emits_overlapping_windows_after_both_nodes_reach_watermark(self):
        buffer = LiveCSIWindowBuffer(config())
        windows = []
        for timestamp in range(0, 3_500_001, 250_000):
            windows.extend(buffer.add(csi_row(timestamp, "rx_01")))
            windows.extend(buffer.add(csi_row(timestamp, "rx_02")))
        self.assertEqual(
            [(window.start_us, window.end_us) for window in windows],
            [(0, 2_000_000), (1_000_000, 3_000_000)],
        )
        self.assertTrue(all(
            set(window.rows_by_node) == {"rx_01", "rx_02"}
            for window in windows
        ))

    def test_waits_when_one_required_node_is_behind(self):
        buffer = LiveCSIWindowBuffer(config(min_rows_per_node=2))
        for timestamp in (0, 500_000, 1_000_000, 1_500_000, 2_000_000):
            self.assertEqual(buffer.add(csi_row(timestamp, "rx_01")), [])
        self.assertEqual(buffer.add(csi_row(0, "rx_02")), [])
        self.assertEqual(buffer.add(csi_row(500_000, "rx_02")), [])
        self.assertEqual(buffer.add(csi_row(1_000_000, "rx_02")), [])
        self.assertEqual(buffer.add(csi_row(1_500_000, "rx_02")), [])
        windows = buffer.add(csi_row(2_000_000, "rx_02"))
        self.assertEqual(len(windows), 1)

    def test_rejects_window_with_large_internal_gap(self):
        buffer = LiveCSIWindowBuffer(config(min_rows_per_node=2))
        windows = []
        for timestamp in (0, 100_000, 1_500_000, 2_000_000):
            windows.extend(buffer.add(csi_row(timestamp, "rx_01")))
            windows.extend(buffer.add(csi_row(timestamp, "rx_02")))
        self.assertEqual(windows, [])

    def test_ignores_wrong_length_unknown_node_and_non_csi_rows(self):
        buffer = LiveCSIWindowBuffer(config())
        self.assertEqual(buffer.add(csi_row(0, "rx_01", csi_length=128)), [])
        self.assertEqual(buffer.add(csi_row(0, "rx_99")), [])
        self.assertEqual(buffer.add({"message_type": "health"}), [])
        self.assertEqual(buffer.latest_timestamp_by_node, {})

    def test_ignores_duplicate_and_out_of_order_rows_per_node(self):
        buffer = LiveCSIWindowBuffer(config())
        buffer.add(csi_row(100, "rx_01"))
        buffer.add(csi_row(100, "rx_01"))
        buffer.add(csi_row(99, "rx_01"))
        self.assertEqual(len(buffer.rows["rx_01"]), 1)
        self.assertEqual(buffer.latest_timestamp_by_node["rx_01"], 100)

    def test_builds_config_from_model_contract(self):
        value = LiveWindowConfig.from_model_config({
            "window_seconds": 4.0,
            "stride_seconds": 2.0,
            "max_gap_ms": 250.0,
            "min_rows_per_node": 30,
            "expected_csi_length": 256,
            "required_nodes": ["rx_01", "rx_02"],
        })
        self.assertEqual(value.duration_us, 4_000_000)
        self.assertEqual(value.stride_us, 2_000_000)
        self.assertEqual(value.max_gap_us, 250_000)

    def test_rejects_invalid_window_config(self):
        with self.assertRaisesRegex(ValueError, "stride"):
            LiveCSIWindowBuffer(config(stride_us=3_000_000))


class LiveActivityPredictorTest(unittest.TestCase):
    def test_emits_json_compatible_prediction_for_clean_window(self):
        with TemporaryDirectory() as temporary_directory:
            artifact_dir = Path(temporary_directory)
            write_window_artifact(artifact_dir)
            predictor = LiveActivityPredictor(
                artifact_dir,
                model_version="test_v1",
            )
            records = []
            for timestamp in range(0, 2_000_001, 100_000):
                records.extend(predictor.process(csi_row(timestamp, "rx_01")))
                records.extend(predictor.process(csi_row(timestamp, "rx_02")))

            self.assertEqual(len(records), 1)
            record = records[0]
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["message_type"], "activity_prediction")
            self.assertEqual(record["model_version"], "test_v1")
            self.assertEqual(record["window_start_us"], 0)
            self.assertEqual(record["window_end_us"], 2_000_000)
            self.assertIn(record["activity"], {"empty_room", "walking"})
            self.assertAlmostEqual(sum(record["probabilities"].values()), 1.0)
            self.assertEqual(
                record["confidence"],
                record["probabilities"][record["activity"]],
            )

    def test_does_not_emit_for_non_csi_or_incomplete_window(self):
        with TemporaryDirectory() as temporary_directory:
            artifact_dir = Path(temporary_directory)
            write_window_artifact(artifact_dir)
            predictor = LiveActivityPredictor(artifact_dir)
            self.assertEqual(
                predictor.process({"message_type": "health"}),
                [],
            )
            for timestamp in range(0, 2_000_001, 100_000):
                self.assertEqual(
                    predictor.process(csi_row(timestamp, "rx_01")),
                    [],
                )

    def test_stream_emits_jsonl_and_reports_invalid_input(self):
        with TemporaryDirectory() as temporary_directory:
            artifact_dir = Path(temporary_directory)
            write_window_artifact(artifact_dir)
            predictor = LiveActivityPredictor(artifact_dir)
            lines = ["not-json\n", "[]\n"]
            for timestamp in range(0, 2_000_001, 100_000):
                lines.append(json.dumps(csi_row(timestamp, "rx_01")) + "\n")
                lines.append(json.dumps(csi_row(timestamp, "rx_02")) + "\n")
            output = io.StringIO()
            errors = io.StringIO()

            invalid_lines = run_stream(
                predictor,
                io.StringIO("".join(lines)),
                output,
                errors,
            )

            records = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(invalid_lines, 2)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["message_type"], "activity_prediction")
            self.assertIn("invalid JSON", errors.getvalue())
            self.assertIn("non-object JSON", errors.getvalue())

    def test_main_stops_cleanly_on_keyboard_interrupt(self):
        with (
            patch.object(live_activity_predictor, "parse_args") as parse_args,
            patch.object(live_activity_predictor, "LiveActivityPredictor"),
            patch.object(
                live_activity_predictor,
                "run_stream",
                side_effect=KeyboardInterrupt,
            ),
            patch.object(live_activity_predictor.sys, "stderr", io.StringIO()) as errors,
        ):
            parse_args.return_value.artifact_dir = Path("artifact")
            parse_args.return_value.model_version = None
            live_activity_predictor.main()
            self.assertEqual(errors.getvalue(), "Stopping activity predictor.\n")


if __name__ == "__main__":
    unittest.main()
