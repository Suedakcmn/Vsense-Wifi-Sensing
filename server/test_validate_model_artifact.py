import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from activity_model import ModelContractError
from validate_model_artifact import FINAL_CLASSES, LEGACY_CLASSES, validate_artifact


def loaded_artifact(class_names):
    config = {
        "class_names": list(class_names),
        "required_nodes": ["rx_01", "rx_02"],
        "selected_subcarriers": list(range(20)),
        "model_file": "model.joblib",
    }
    metadata = SimpleNamespace(
        model_type="svm",
        window_seconds=2.0,
        stride_seconds=1.0,
        normalization="zscore",
        sample_rate_hz=40.0,
    )
    return SimpleNamespace(config=config, metadata=metadata)


class ValidateModelArtifactTest(unittest.TestCase):
    def validate(self, classes, **kwargs):
        with TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "model.joblib").write_bytes(b"model")
            (directory / "metrics.json").write_text("{}", encoding="utf-8")
            (directory / "README.md").write_text("# Model\n", encoding="utf-8")
            with patch(
                "validate_model_artifact.load_activity_artifact",
                return_value=loaded_artifact(classes),
            ):
                return validate_artifact(directory, require_report=True, **kwargs)

    def test_accepts_final_four_class_contract(self):
        result = self.validate(FINAL_CLASSES, require_final_classes=True)
        self.assertEqual(result["classes"], list(FINAL_CLASSES))
        self.assertEqual(result["warnings"], [])

    def test_marks_five_class_baseline_as_legacy(self):
        result = self.validate(LEGACY_CLASSES)
        self.assertIn("removed class: sitting", result["warnings"][0])

    def test_rejects_legacy_classes_for_final_package(self):
        with self.assertRaisesRegex(ModelContractError, "removed class: sitting"):
            self.validate(LEGACY_CLASSES, require_final_classes=True)

    def test_rejects_unexpected_class_order(self):
        with self.assertRaisesRegex(ModelContractError, "final project order"):
            self.validate(("walking", "empty_room", "standing", "desk_work"))


if __name__ == "__main__":
    unittest.main()
