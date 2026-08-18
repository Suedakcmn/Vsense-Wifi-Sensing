"""Common model adapter contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from activity_model import ActivityPrediction
from ml.windows import CSIWindow


class ActivityModelAdapter(Protocol):
    config: dict

    def predict_window(self, window: CSIWindow) -> ActivityPrediction:
        """Predict one already validated CSI window."""


@dataclass(frozen=True)
class ModelMetadata:
    model_version: str
    model_type: str
    window_seconds: float
    stride_seconds: float
    normalization: str
    sample_rate_hz: float | None
    class_names: tuple[str, ...]

    def as_status(self) -> dict:
        return {
            "schema_version": 1,
            "message_type": "model_status",
            "status": "ready",
            "model_version": self.model_version,
            "model_type": self.model_type,
            "window_seconds": self.window_seconds,
            "stride_seconds": self.stride_seconds,
            "normalization": self.normalization,
            "sample_rate_hz": self.sample_rate_hz,
            "class_names": list(self.class_names),
        }
