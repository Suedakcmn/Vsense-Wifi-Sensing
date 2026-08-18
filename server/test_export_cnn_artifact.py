import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import torch

from ml.cnn_model import CNNModelConfig, SmallCSIConvNet
from ml.constants import CLASS_NAMES
from ml.export_cnn_artifact import export_cnn_artifact
from ml.windows import CSIWindow
from models import load_activity_artifact
from validate_model_artifact import validate_artifact


class ExportCNNArtifactTest(unittest.TestCase):
    def test_exports_loadable_final_four_class_artifact(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            checkpoint_path = root / "best_model.pt"
            metrics_path = root / "metrics.json"
            output_dir = root / "final_v1"
            model = SmallCSIConvNet(CNNModelConfig(dropout=0.0))
            torch.save(
                {
                    "state_dict": model.state_dict(),
                    "model_config": model.config.to_dict(),
                    "class_names": CLASS_NAMES,
                    "preprocessing": {
                        "window_config": {
                            "duration_us": 2_000_000,
                            "stride_us": 1_000_000,
                            "max_gap_us": 500_000,
                            "min_rows_per_node": 20,
                            "required_nodes": ["rx_01", "rx_02"],
                        },
                        "tensor_config": {
                            "sample_rate_hz": 40,
                            "normalization": "zscore",
                            "node_ids": ["rx_01", "rx_02"],
                        },
                        "subcarrier_indices": list(range(20)),
                        "tensor_shape": [2, 80, 20],
                    },
                },
                checkpoint_path,
            )
            metrics_path.write_text(json.dumps({"macro_f1": 0.9}))
            export_cnn_artifact(checkpoint_path, metrics_path, output_dir)
            result = validate_artifact(
                output_dir,
                require_report=True,
                require_final_classes=True,
            )
            loaded = load_activity_artifact(output_dir)
            self.assertEqual(result["model_type"], "torch_cnn")
            self.assertEqual(result["classes"], CLASS_NAMES)
            self.assertEqual(loaded.config["tensor_shape"], [2, 80, 20])
            rows = [
                {
                    "collector_ts_us": index * 25_000,
                    "csi": [value for carrier in range(128) for value in (carrier + index, 1)],
                }
                for index in range(80)
            ]
            prediction = loaded.model.predict_window(
                CSIWindow(
                    session_id="live-smoke",
                    label="walking",
                    subject="tester",
                    start_us=0,
                    end_us=2_000_000,
                    rows_by_node={"rx_01": rows, "rx_02": rows},
                )
            )
            self.assertIn(prediction.activity, CLASS_NAMES)
            self.assertEqual(list(prediction.probabilities), CLASS_NAMES)
            self.assertAlmostEqual(sum(prediction.probabilities.values()), 1.0)


if __name__ == "__main__":
    unittest.main()
