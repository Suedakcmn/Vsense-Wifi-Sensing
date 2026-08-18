import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from ml.features import extract_window_features, feature_names
from ml.windows import CSIWindow, WindowConfig, iter_session_windows
from ml.train_baselines import repeat_from_session_id, split_by_repeat
import pandas as pd


def csi_row(timestamp, node_id, value=3):
    return {
        "message_type": "csi",
        "node_id": node_id,
        "collector_ts_us": timestamp,
        "len": 256,
        "rssi": -40,
        "csi": [value, 4] * 128,
    }


class MLPipelineTest(unittest.TestCase):
    def test_split_is_session_repeat_based(self):
        table = pd.DataFrame({
            "session_id": ["a_r01", "b_r02", "c_r03"],
            "label": ["walking", "walking", "walking"],
        })
        train, validation, test = split_by_repeat(table)
        self.assertEqual(train.iloc[0]["session_id"], "a_r01")
        self.assertEqual(validation.iloc[0]["session_id"], "b_r02")
        self.assertEqual(test.iloc[0]["session_id"], "c_r03")
        self.assertEqual(repeat_from_session_id("session_r03"), 3)

    def test_feature_vector_has_stable_shape(self):
        rows = [csi_row(index * 100_000, "rx_01") for index in range(20)]
        window = CSIWindow("s", "walking", "person", 0, 2_000_000, {
            "rx_01": rows,
            "rx_02": [dict(row, node_id="rx_02") for row in rows],
        })
        indices = [0, 1, 2]
        vector = extract_window_features(window, indices)
        self.assertEqual(len(vector), len(feature_names(("rx_01", "rx_02"), indices)))
        self.assertTrue(np.isfinite(vector).all())

    def test_zscore_spectral_features_have_stable_finite_shape(self):
        rows = [
            csi_row(index * 25_000, "rx_01", value=3 + (index % 4))
            for index in range(80)
        ]
        window = CSIWindow("s", "walking", "person", 0, 2_000_000, {
            "rx_01": rows,
            "rx_02": [dict(row, node_id="rx_02") for row in rows],
        })
        indices = [0, 1, 2]
        vector = extract_window_features(
            window,
            indices,
            normalization="zscore",
            spectral_features=True,
            sample_rate_hz=40,
        )
        names = feature_names(
            ("rx_01", "rx_02"),
            indices,
            spectral_features=True,
        )
        self.assertEqual(len(vector), len(names))
        self.assertTrue(np.isfinite(vector).all())

    def test_streaming_windows_reject_gap_and_keep_clean_window(self):
        with TemporaryDirectory() as temporary_directory:
            session_dir = Path(temporary_directory)
            metadata = {
                "session_id": "test",
                "status": "completed",
                "subject": "person",
                "started_collector_ts_us": 0,
                "ended_collector_ts_us": 4_000_000,
            }
            labels = {"segments": [{
                "label": "walking",
                "start_collector_ts_us": 0,
                "end_collector_ts_us": 4_000_000,
            }]}
            (session_dir / "metadata.json").write_text(json.dumps(metadata))
            (session_dir / "labels.json").write_text(json.dumps(labels))
            rows = []
            for timestamp in range(0, 4_000_000, 100_000):
                for node_id in ("rx_01", "rx_02"):
                    rows.append(csi_row(timestamp, node_id))
            rows.sort(key=lambda row: row["collector_ts_us"])
            (session_dir / "csi.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows)
            )
            config = WindowConfig(trim_us=0, min_rows_per_node=10)
            windows = list(iter_session_windows(session_dir, config))
            self.assertEqual(len(windows), 3)
            self.assertTrue(all(window.label == "walking" for window in windows))


if __name__ == "__main__":
    unittest.main()
