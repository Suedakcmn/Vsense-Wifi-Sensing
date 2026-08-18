"""Select and validate an activity-model adapter from an artifact directory."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from activity_model import ModelContractError
from models.base import ActivityModelAdapter, ModelMetadata
from models.sklearn_adapter import SklearnActivityModel


TORCH_MODEL_TYPES = frozenset({"torch_cnn", "cnn", "pytorch_cnn"})


@dataclass(frozen=True)
class LoadedArtifact:
    model: ActivityModelAdapter
    metadata: ModelMetadata
    config: dict


def _read_config(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ModelContractError(f"missing model config: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ModelContractError(f"invalid model config JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ModelContractError("model config must be a JSON object")
    return value


def load_activity_artifact(
    artifact_dir: Path | str,
    *,
    model_version: str | None = None,
) -> LoadedArtifact:
    directory = Path(artifact_dir)
    config = _read_config(directory / "feature_config.json")
    model_type = str(config.get("model_type", ""))
    if model_type in TORCH_MODEL_TYPES:
        from models.torch_adapter import TorchActivityModel

        model = TorchActivityModel(directory, config)
    elif model_type:
        model = SklearnActivityModel(directory)
    else:
        raise ModelContractError("model_type must not be empty")
    class_names = tuple(str(value) for value in config.get("class_names", ()))
    metadata = ModelMetadata(
        model_version=model_version or str(config.get("model_version") or directory.name),
        model_type=model_type,
        window_seconds=float(config["window_seconds"]),
        stride_seconds=float(config["stride_seconds"]),
        normalization=str(config.get("normalization", "none")),
        sample_rate_hz=(
            float(config["sample_rate_hz"])
            if config.get("sample_rate_hz") is not None
            else None
        ),
        class_names=class_names,
    )
    return LoadedArtifact(model=model, metadata=metadata, config=config)
