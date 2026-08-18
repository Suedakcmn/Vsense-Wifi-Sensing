"""Lazy TorchScript adapter for a two-receiver CSI tensor model."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from activity_model import ActivityPrediction, ModelContractError
from csi_utils import csi_to_amplitude
from ml.windows import CSIWindow


class TorchActivityModel:
    """Run a scripted CNN with preprocessing fully defined by its artifact config."""

    def __init__(self, artifact_dir: Path | str, config: dict):
        self.artifact_dir = Path(artifact_dir)
        self.config = config
        self._validate_config()
        try:
            import torch
        except ImportError as exc:
            raise ModelContractError(
                "PyTorch is required to load a torch_cnn artifact"
            ) from exc
        self.torch = torch
        model_path = self.artifact_dir / str(config.get("model_file", "model.pt"))
        try:
            self.model = torch.jit.load(str(model_path), map_location="cpu")
        except (OSError, RuntimeError) as exc:
            raise ModelContractError(f"could not load TorchScript model: {model_path}") from exc
        self.model.eval()

    def _validate_config(self):
        required = {
            "window_seconds",
            "stride_seconds",
            "max_gap_ms",
            "min_rows_per_node",
            "required_nodes",
            "selected_subcarriers",
            "class_names",
            "sample_rate_hz",
            "normalization",
            "tensor_shape",
        }
        missing = sorted(required - self.config.keys())
        if missing:
            raise ModelContractError(f"torch model config is missing fields: {missing}")
        nodes = self.config["required_nodes"]
        subcarriers = self.config["selected_subcarriers"]
        sample_rate = float(self.config["sample_rate_hz"])
        expected_time = round(float(self.config["window_seconds"]) * sample_rate)
        expected_shape = [len(nodes), expected_time, len(subcarriers)]
        if self.config["tensor_shape"] != expected_shape:
            raise ModelContractError(
                f"tensor_shape must match preprocessing contract: {expected_shape}"
            )
        if self.config["normalization"] not in {"zscore", "none"}:
            raise ModelContractError("torch normalization must be zscore or none")
        if sample_rate <= 0 or not nodes or not subcarriers or not self.config["class_names"]:
            raise ModelContractError("torch tensor contract must not be empty")

    def predict_window(self, window: CSIWindow) -> ActivityPrediction:
        array = self._window_tensor(window)
        tensor = self.torch.from_numpy(array[None, ...]).to(dtype=self.torch.float32)
        with self.torch.inference_mode():
            logits = self.model(tensor)
            if isinstance(logits, (tuple, list)):
                logits = logits[0]
            if tuple(logits.shape) != (1, len(self.config["class_names"])):
                raise ModelContractError(
                    "torch model output shape does not match configured classes"
                )
            probabilities_tensor = self.torch.softmax(logits, dim=1)[0].cpu()
        probabilities_values = probabilities_tensor.numpy().astype(float)
        if not np.isfinite(probabilities_values).all():
            raise ModelContractError("torch model produced NaN or infinity")
        class_names = tuple(self.config["class_names"])
        probabilities = {
            name: float(value)
            for name, value in zip(class_names, probabilities_values, strict=True)
        }
        best_index = int(np.argmax(probabilities_values))
        activity = class_names[best_index]
        return ActivityPrediction(
            activity=activity,
            confidence=probabilities[activity],
            probabilities=probabilities,
        )

    def _window_tensor(self, window: CSIWindow) -> np.ndarray:
        nodes = tuple(self.config["required_nodes"])
        subcarriers = list(self.config["selected_subcarriers"])
        sample_rate = float(self.config["sample_rate_hz"])
        time_points = int(round(float(self.config["window_seconds"]) * sample_rate))
        target_times = np.linspace(
            window.start_us,
            window.end_us,
            num=time_points,
            endpoint=False,
            dtype=np.float64,
        )
        receiver_tensors = []
        for node_id in nodes:
            rows = window.rows_by_node.get(node_id)
            if not rows:
                raise ModelContractError(f"CSI window is missing required node: {node_id}")
            timestamps = np.asarray(
                [row["collector_ts_us"] for row in rows], dtype=np.float64
            )
            amplitudes = np.stack([csi_to_amplitude(row["csi"]) for row in rows])
            if max(subcarriers) >= amplitudes.shape[1] or min(subcarriers) < 0:
                raise ModelContractError("selected subcarrier is outside CSI amplitude range")
            selected = amplitudes[:, subcarriers]
            resampled = np.stack(
                [
                    np.interp(target_times, timestamps, selected[:, index])
                    for index in range(selected.shape[1])
                ],
                axis=1,
            ).astype(np.float32)
            if self.config["normalization"] == "zscore":
                mean = np.mean(resampled, axis=0, keepdims=True)
                standard_deviation = np.std(resampled, axis=0, keepdims=True)
                resampled = (resampled - mean) / np.maximum(standard_deviation, 1e-6)
            receiver_tensors.append(resampled)
        result = np.stack(receiver_tensors).astype(np.float32)
        if not np.isfinite(result).all() or not math.prod(result.shape):
            raise ModelContractError("preprocessed tensor contains invalid values")
        return result
