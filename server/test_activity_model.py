import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import joblib
import numpy as np
from sklearn.dummy import DummyClassifier

from activity_model import ActivityModel, ModelContractError
from ml.features import feature_names
from ml.windows import CSIWindow


def write_artifact(
    directory: Path,
    *,
    feature_count: int = 3,
    config_classes=("empty_room", "walking"),
    schema_version: int = 1,
):
    features = np.asarray([
        [0.0] * feature_count,
        [1.0] * feature_count,
        [0.1] * feature_count,
        [0.9] * feature_count,
    ])
    labels = np.asarray(["empty_room", "walking", "empty_room", "walking"])
    model = DummyClassifier(strategy="prior").fit(features, labels)
    joblib.dump(model, directory / "model.joblib")
    (directory / "feature_config.json").write_text(
        json.dumps({
            "schema_version": schema_version,
            "model_type": "dummy",
            "window_seconds": 2.0,
            "stride_seconds": 1.0,
            "max_gap_ms": 500.0,
            "min_rows_per_node": 20,
            "required_nodes": ["rx_01", "rx_02"],
            "selected_subcarriers": [1, 2],
            "feature_columns": [f"feature_{index}" for index in range(feature_count)],
            "class_names": list(config_classes),
        }),
        encoding="utf-8",
    )


def csi_rows(node_id: str, count: int = 20) -> list[dict]:
    return [
        {
            "message_type": "csi",
            "node_id": node_id,
            "collector_ts_us": index * 100_000,
            "len": 256,
            "rssi": -40,
            "csi": [3, 4] * 128,
        }
        for index in range(count)
    ]


def write_window_artifact(directory: Path):
    node_ids = ("rx_01", "rx_02")
    subcarriers = [0, 1]
    columns = feature_names(node_ids, subcarriers)
    features = np.vstack([
        np.zeros(len(columns), dtype=np.float32),
        np.ones(len(columns), dtype=np.float32),
    ])
    labels = np.asarray(["empty_room", "walking"])
    model = DummyClassifier(strategy="prior").fit(features, labels)
    joblib.dump(model, directory / "model.joblib")
    (directory / "feature_config.json").write_text(
        json.dumps({
            "schema_version": 1,
            "model_type": "dummy",
            "window_seconds": 2.0,
            "stride_seconds": 1.0,
            "max_gap_ms": 500.0,
            "min_rows_per_node": 4,
            "required_nodes": list(node_ids),
            "selected_subcarriers": subcarriers,
            "feature_columns": columns,
            "class_names": ["empty_room", "walking"],
        }),
        encoding="utf-8",
    )


class ActivityModelTest(unittest.TestCase):
    def test_loads_contract_and_predicts_in_configured_class_order(self):
        with TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            write_artifact(directory)
            model = ActivityModel(directory)
            prediction = model.predict([0.0, 0.0, 0.0])
            self.assertIn(prediction.activity, model.class_names)
            self.assertEqual(
                list(prediction.probabilities),
                ["empty_room", "walking"],
            )
            self.assertAlmostEqual(sum(prediction.probabilities.values()), 1.0)
            self.assertEqual(
                prediction.confidence,
                prediction.probabilities[prediction.activity],
            )

    def test_rejects_wrong_feature_vector_length(self):
        with TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            write_artifact(directory)
            model = ActivityModel(directory)
            with self.assertRaisesRegex(ModelContractError, "vector length"):
                model.predict([0.0, 0.0])

    def test_rejects_non_finite_features(self):
        with TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            write_artifact(directory)
            model = ActivityModel(directory)
            with self.assertRaisesRegex(ModelContractError, "NaN or infinity"):
                model.predict([0.0, np.nan, 0.0])

    def test_rejects_model_and_config_class_mismatch(self):
        with TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            write_artifact(directory, config_classes=("empty_room", "standing"))
            with self.assertRaisesRegex(ModelContractError, "classes do not match"):
                ActivityModel(directory)

    def test_rejects_unsupported_schema(self):
        with TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            write_artifact(directory, schema_version=99)
            with self.assertRaisesRegex(ModelContractError, "unsupported"):
                ActivityModel(directory)

    def test_rejects_missing_artifact(self):
        with TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(ModelContractError, "missing model config"):
                ActivityModel(temporary_directory)

    def test_rejects_config_with_missing_required_field(self):
        with TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            write_artifact(directory)
            config_path = directory / "feature_config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            del config["feature_columns"]
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(
                ModelContractError,
                "missing fields:.*feature_columns",
            ):
                ActivityModel(directory)

    def test_predicts_from_shared_window_features(self):
        with TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            write_window_artifact(directory)
            model = ActivityModel(directory)
            window = CSIWindow(
                session_id="live",
                label="unknown",
                subject="unknown",
                start_us=0,
                end_us=2_000_000,
                rows_by_node={
                    "rx_01": csi_rows("rx_01"),
                    "rx_02": csi_rows("rx_02"),
                },
            )
            prediction = model.predict_window(window)
            self.assertIn(prediction.activity, model.class_names)
            self.assertAlmostEqual(sum(prediction.probabilities.values()), 1.0)

    def test_window_rejects_missing_required_node(self):
        with TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            write_window_artifact(directory)
            model = ActivityModel(directory)
            window = CSIWindow(
                session_id="live",
                label="unknown",
                subject="unknown",
                start_us=0,
                end_us=2_000_000,
                rows_by_node={"rx_01": csi_rows("rx_01")},
            )
            with self.assertRaisesRegex(ModelContractError, "missing required nodes"):
                model.predict_window(window)

    def test_window_rejects_runtime_feature_contract_drift(self):
        with TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            write_window_artifact(directory)
            config_path = directory / "feature_config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["feature_columns"] = list(reversed(config["feature_columns"]))
            config_path.write_text(json.dumps(config), encoding="utf-8")
            model = ActivityModel(directory)
            window = CSIWindow(
                session_id="live",
                label="unknown",
                subject="unknown",
                start_us=0,
                end_us=2_000_000,
                rows_by_node={
                    "rx_01": csi_rows("rx_01"),
                    "rx_02": csi_rows("rx_02"),
                },
            )
            with self.assertRaisesRegex(ModelContractError, "feature names"):
                model.predict_window(window)


if __name__ == "__main__":
    unittest.main()
