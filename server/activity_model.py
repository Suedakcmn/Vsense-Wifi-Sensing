"""Load and run a versioned VSense activity-classification artifact."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ml.features import extract_window_features, feature_names
from ml.windows import CSIWindow


class ModelContractError(ValueError):
    """Raised when model.joblib and feature_config.json are incompatible."""


@dataclass(frozen=True)
class ActivityPrediction:
    activity: str
    confidence: float
    probabilities: dict[str, float]


class ActivityModel:
    """Validated inference wrapper around a scikit-learn model artifact."""

    SUPPORTED_SCHEMA_VERSIONS = {1}

    def __init__(self, artifact_dir: Path | str):
        self.artifact_dir = Path(artifact_dir)
        self.config = self._load_config(self.artifact_dir / "feature_config.json")
        self._validate_required_config_fields()
        self.model = self._load_model(self.artifact_dir / "model.joblib")
        self.feature_columns = tuple(self.config["feature_columns"])
        self.class_names = tuple(self.config["class_names"])
        self.model_classes = tuple(
            str(value)
            for value in getattr(self.model, "classes_", ())
        )
        self._validate_contract()

    @staticmethod
    def _load_config(path: Path) -> dict:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ModelContractError(f"missing model config: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ModelContractError(f"invalid model config JSON: {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise ModelContractError("model config must be a JSON object")
        return value

    @staticmethod
    def _load_model(path: Path):
        try:
            return joblib.load(path)
        except FileNotFoundError as exc:
            raise ModelContractError(f"missing model artifact: {path}") from exc

    def _validate_required_config_fields(self):
        required_fields = {
            "schema_version",
            "model_type",
            "window_seconds",
            "stride_seconds",
            "max_gap_ms",
            "min_rows_per_node",
            "required_nodes",
            "selected_subcarriers",
            "feature_columns",
            "class_names",
        }
        missing = sorted(required_fields - self.config.keys())
        if missing:
            raise ModelContractError(f"model config is missing fields: {missing}")

    def _validate_contract(self):
        if self.config["schema_version"] not in self.SUPPORTED_SCHEMA_VERSIONS:
            raise ModelContractError(
                f"unsupported model config schema: {self.config['schema_version']}"
            )
        if not self.feature_columns:
            raise ModelContractError("feature_columns must not be empty")
        if len(self.feature_columns) != len(set(self.feature_columns)):
            raise ModelContractError("feature_columns must be unique")
        if not self.class_names:
            raise ModelContractError("class_names must not be empty")
        if len(self.class_names) != len(set(self.class_names)):
            raise ModelContractError("class_names must be unique")
        if not hasattr(self.model, "predict") or not hasattr(self.model, "predict_proba"):
            raise ModelContractError("model must implement predict and predict_proba")
        if not hasattr(self.model, "classes_"):
            raise ModelContractError("model does not expose fitted classes_")
        if set(self.model_classes) != set(self.class_names):
            raise ModelContractError(
                "model classes do not match configured classes: "
                f"model={list(self.model_classes)} config={list(self.class_names)}"
            )
        model_feature_count = getattr(self.model, "n_features_in_", None)
        if model_feature_count != len(self.feature_columns):
            raise ModelContractError(
                "model feature count does not match feature_columns: "
                f"model={model_feature_count} config={len(self.feature_columns)}"
            )
        if not isinstance(self.config["required_nodes"], list) or not all(
            isinstance(value, str) and value
            for value in self.config["required_nodes"]
        ):
            raise ModelContractError("required_nodes must be a non-empty string list")
        if not self.config["required_nodes"]:
            raise ModelContractError("required_nodes must not be empty")
        if not isinstance(self.config["selected_subcarriers"], list) or not all(
            isinstance(value, int)
            for value in self.config["selected_subcarriers"]
        ):
            raise ModelContractError("selected_subcarriers must be an integer list")

    @property
    def window_seconds(self) -> float:
        return float(self.config["window_seconds"])

    @property
    def stride_seconds(self) -> float:
        return float(self.config["stride_seconds"])

    @property
    def required_nodes(self) -> tuple[str, ...]:
        return tuple(self.config["required_nodes"])

    @property
    def selected_subcarriers(self) -> list[int]:
        return list(self.config["selected_subcarriers"])

    def predict_window(self, window: CSIWindow) -> ActivityPrediction:
        generated_columns = tuple(
            feature_names(
                self.required_nodes,
                self.selected_subcarriers,
                spectral_features=bool(self.config.get("spectral_features", False)),
            )
        )
        if generated_columns != self.feature_columns:
            raise ModelContractError(
                "runtime feature names do not match the model contract"
            )
        missing_nodes = [
            node_id
            for node_id in self.required_nodes
            if node_id not in window.rows_by_node
        ]
        if missing_nodes:
            raise ModelContractError(
                f"CSI window is missing required nodes: {missing_nodes}"
            )
        features = extract_window_features(
            window,
            self.selected_subcarriers,
            self.required_nodes,
            normalization=str(self.config.get("normalization", "none")),
            spectral_features=bool(self.config.get("spectral_features", False)),
            sample_rate_hz=float(self.config.get("sample_rate_hz") or 40.0),
        )
        return self.predict(features)

    def predict(self, features) -> ActivityPrediction:
        vector = np.asarray(features, dtype=np.float32)
        if vector.ndim != 1:
            raise ModelContractError(
                f"features must be one-dimensional, received shape={vector.shape}"
            )
        if len(vector) != len(self.feature_columns):
            raise ModelContractError(
                "feature vector length does not match model contract: "
                f"received={len(vector)} expected={len(self.feature_columns)}"
            )
        if not np.isfinite(vector).all():
            raise ModelContractError("feature vector contains NaN or infinity")

        matrix = pd.DataFrame(
            [vector],
            columns=self.feature_columns,
        )
        activity = str(self.model.predict(matrix)[0])
        raw_probabilities = self.model.predict_proba(matrix)[0]
        probabilities_by_model_class = {
            class_name: float(probability)
            for class_name, probability in zip(
                self.model_classes,
                raw_probabilities,
                strict=True,
            )
        }
        probabilities = {
            class_name: probabilities_by_model_class[class_name]
            for class_name in self.class_names
        }
        confidence = probabilities[activity]
        return ActivityPrediction(
            activity=activity,
            confidence=confidence,
            probabilities=probabilities,
        )
