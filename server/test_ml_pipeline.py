import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import torch
from torch.utils.data import DataLoader

from ml.cnn_data import CNNTensorConfig, CSITensorIterableDataset, window_to_tensor
from ml.cnn_model import CNNModelConfig, SmallCSIConvNet
from ml.features import extract_window_features, feature_names, normalize_amplitude
from ml.windows import CSIWindow, WindowConfig, iter_session_windows
from ml.train_baselines import repeat_from_session_id, split_by_repeat
from ml.run_experiments import development_folds, validate_table
from ml.subcarriers import (
    combine_receiver_scores,
    get_ignore_indices,
    multiclass_fisher_scores,
    select_ranked_subcarriers,
)
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
    def test_subcarrier_ignore_indices_repeat_for_128_bins(self):
        ignored_64 = get_ignore_indices(64)
        self.assertEqual(
            ignored_64,
            {0, 1, 2, 3, 6, 20, 27, 28, 34, 48, 60, 61, 62, 63},
        )
        ignored_128 = get_ignore_indices(128)
        self.assertEqual(ignored_128, ignored_64 | {index + 64 for index in ignored_64})

    def test_subcarrier_selection_ignores_bins_and_returns_frequency_order(self):
        scores = np.asarray([0.1, 9.0, 0.8, 0.7, 0.2])
        ranked, ordered = select_ranked_subcarriers(scores, 2, {1})
        self.assertEqual(ranked, [2, 3])
        self.assertEqual(ordered, [2, 3])

    def test_multiclass_fisher_and_receiver_combination(self):
        features = np.asarray(
            [[0.0, 1.0], [0.1, 1.1], [5.0, 1.0], [5.1, 1.1]],
            dtype=np.float32,
        )
        labels = np.asarray(["a", "a", "b", "b"])
        scores = multiclass_fisher_scores(features, labels)
        self.assertGreater(scores[0], scores[1])
        combined = combine_receiver_scores({"rx_01": scores, "rx_02": scores * 2})
        self.assertEqual(int(np.argmax(combined)), 0)

    def test_cnn_forward_produces_four_finite_logits(self):
        model = SmallCSIConvNet()
        inputs = torch.randn(4, 2, 80, 20)
        logits = model(inputs)
        self.assertEqual(tuple(logits.shape), (4, 4))
        self.assertTrue(torch.isfinite(logits).all())

    def test_cnn_rejects_wrong_receiver_or_subcarrier_shape(self):
        model = SmallCSIConvNet()
        with self.assertRaises(ValueError):
            model(torch.randn(4, 1, 80, 20))
        with self.assertRaises(ValueError):
            model(torch.randn(4, 2, 80, 19))

    def test_cnn_backward_has_finite_gradients_and_updates_weights(self):
        torch.manual_seed(42)
        model = SmallCSIConvNet(CNNModelConfig(dropout=0.0))
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
        criterion = torch.nn.CrossEntropyLoss()
        inputs = torch.randn(8, 2, 80, 20)
        targets = torch.tensor([0, 1, 2, 3, 0, 1, 2, 3])
        before = model.classifier[-1].weight.detach().clone()
        optimizer.zero_grad(set_to_none=True)
        loss = criterion(model(inputs), targets)
        self.assertTrue(torch.isfinite(loss))
        loss.backward()
        gradients = [
            parameter.grad
            for parameter in model.parameters()
            if parameter.grad is not None
        ]
        self.assertTrue(gradients)
        self.assertTrue(all(torch.isfinite(gradient).all() for gradient in gradients))
        optimizer.step()
        after = model.classifier[-1].weight.detach()
        self.assertFalse(torch.equal(before, after))

    def test_cnn_window_tensor_has_fixed_shape_and_normalization(self):
        timestamps = [0, 17_000, 51_000, 88_000, 131_000, 177_000]
        rows = [
            csi_row(timestamp, "rx_01", value=3 + index)
            for index, timestamp in enumerate(timestamps)
        ]
        window = CSIWindow(
            "s",
            "walking",
            "person",
            0,
            200_000,
            {
                "rx_01": rows,
                "rx_02": [dict(row, node_id="rx_02") for row in rows],
            },
        )
        tensor = window_to_tensor(
            window,
            [0, 1, 2],
            CNNTensorConfig(sample_rate_hz=40, normalization="zscore"),
        )
        self.assertEqual(tuple(tensor.shape), (2, 8, 3))
        self.assertEqual(tensor.dtype, torch.float32)
        self.assertTrue(torch.isfinite(tensor).all())
        self.assertTrue(
            torch.allclose(tensor.mean(dim=1), torch.zeros((2, 3)), atol=1e-5)
        )

    def test_cnn_iterable_dataset_batches_tensors(self):
        with TemporaryDirectory() as temporary_directory:
            session_dir = Path(temporary_directory)
            metadata = {
                "session_id": "walking_r01",
                "status": "completed",
                "subject": "person",
                "started_collector_ts_us": 0,
                "ended_collector_ts_us": 2_000_000,
            }
            labels = {
                "segments": [
                    {
                        "label": "walking",
                        "start_collector_ts_us": 0,
                        "end_collector_ts_us": 2_000_000,
                    }
                ]
            }
            (session_dir / "metadata.json").write_text(json.dumps(metadata))
            (session_dir / "labels.json").write_text(json.dumps(labels))
            rows = []
            for timestamp in range(0, 2_000_000, 20_000):
                for node_id in ("rx_01", "rx_02"):
                    rows.append(csi_row(timestamp, node_id, value=3 + timestamp // 20_000))
            rows.sort(key=lambda row: row["collector_ts_us"])
            (session_dir / "csi.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows)
            )
            dataset = CSITensorIterableDataset(
                [session_dir],
                WindowConfig(
                    duration_us=1_000_000,
                    stride_us=1_000_000,
                    trim_us=0,
                    min_rows_per_node=20,
                ),
                [0, 1],
                CNNTensorConfig(sample_rate_hz=40),
            )
            batch = next(iter(DataLoader(dataset, batch_size=2)))
            self.assertEqual(tuple(batch["inputs"].shape), (2, 2, 40, 2))
            self.assertEqual(batch["target"].tolist(), [1, 1])

    def test_window_normalization_is_per_subcarrier(self):
        amplitude = np.asarray(
            [[1.0, 100.0], [2.0, 110.0], [3.0, 120.0]], dtype=np.float32
        )
        zscore = normalize_amplitude(amplitude, "zscore")
        self.assertTrue(np.allclose(np.mean(zscore, axis=0), 0.0, atol=1e-6))
        self.assertTrue(np.allclose(np.std(zscore, axis=0), 1.0, atol=1e-6))
        robust = normalize_amplitude(amplitude, "robust")
        self.assertTrue(np.allclose(np.median(robust, axis=0), 0.0, atol=1e-6))

    def test_unknown_window_normalization_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_amplitude(np.ones((3, 2)), "invalid")

    def test_development_cv_keeps_repeat_three_locked(self):
        rows = []
        for repeat in (1, 2, 3):
            for label in ("empty_room", "walking", "standing", "desk_work"):
                rows.append(
                    {
                        "session_id": f"{label}_r{repeat:02d}",
                        "subject": "person",
                        "label": label,
                        "window_start_us": 0,
                        "window_end_us": 1,
                        "feature": repeat,
                    }
                )
        table = pd.DataFrame(rows)
        validate_table(table)
        folds = list(development_folds(table))
        self.assertEqual(len(folds), 2)
        for _, train, validation in folds:
            used_sessions = set(train["session_id"]) | set(validation["session_id"])
            self.assertFalse(any(session.endswith("_r03") for session in used_sessions))

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
