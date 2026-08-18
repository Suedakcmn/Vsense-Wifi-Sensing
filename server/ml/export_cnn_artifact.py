"""Export a trained CSI CNN checkpoint as a validated live model artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import torch

from ml.cnn_model import CNNModelConfig, SmallCSIConvNet
from ml.constants import CLASS_NAMES, MODEL_SCHEMA_VERSION
from package_model import package_model


def _positive_number(value, name: str) -> float:
    number = float(value)
    if number <= 0:
        raise ValueError(f"{name} must be positive")
    return number


def build_feature_config(checkpoint: dict, model_version: str) -> dict:
    class_names = list(checkpoint.get("class_names", ()))
    if class_names != CLASS_NAMES:
        raise ValueError(
            f"checkpoint class order must be {CLASS_NAMES}, got {class_names}"
        )
    preprocessing = checkpoint.get("preprocessing")
    if not isinstance(preprocessing, dict):
        raise ValueError("checkpoint is missing preprocessing metadata")
    window = preprocessing.get("window_config")
    tensor = preprocessing.get("tensor_config")
    subcarriers = preprocessing.get("subcarrier_indices")
    tensor_shape = preprocessing.get("tensor_shape")
    if not isinstance(window, dict) or not isinstance(tensor, dict):
        raise ValueError("checkpoint preprocessing metadata is incomplete")
    required_nodes = list(tensor.get("node_ids", ()))
    if required_nodes != ["rx_01", "rx_02"]:
        raise ValueError("checkpoint nodes must be ordered as rx_01, rx_02")
    if not isinstance(subcarriers, list) or len(subcarriers) != 20:
        raise ValueError("checkpoint must contain exactly 20 subcarrier indices")
    if len(set(subcarriers)) != len(subcarriers):
        raise ValueError("checkpoint subcarrier indices must be unique")
    duration_us = _positive_number(window.get("duration_us"), "duration_us")
    stride_us = _positive_number(window.get("stride_us"), "stride_us")
    max_gap_us = _positive_number(window.get("max_gap_us"), "max_gap_us")
    sample_rate_hz = _positive_number(
        tensor.get("sample_rate_hz"), "sample_rate_hz"
    )
    expected_shape = [
        len(required_nodes),
        round(duration_us / 1_000_000 * sample_rate_hz),
        len(subcarriers),
    ]
    if tensor_shape != expected_shape:
        raise ValueError(
            f"checkpoint tensor shape must be {expected_shape}, got {tensor_shape}"
        )
    normalization = str(tensor.get("normalization", ""))
    if normalization not in {"zscore", "none"}:
        raise ValueError("checkpoint normalization must be zscore or none")
    min_rows = int(window.get("min_rows_per_node", 0))
    if min_rows <= 0:
        raise ValueError("min_rows_per_node must be positive")
    return {
        "schema_version": MODEL_SCHEMA_VERSION,
        "model_version": model_version,
        "model_type": "torch_cnn",
        "model_file": "model.pt",
        "window_seconds": duration_us / 1_000_000,
        "stride_seconds": stride_us / 1_000_000,
        "max_gap_ms": max_gap_us / 1_000,
        "min_rows_per_node": min_rows,
        "required_nodes": required_nodes,
        "selected_subcarriers": subcarriers,
        "class_names": class_names,
        "sample_rate_hz": sample_rate_hz,
        "normalization": normalization,
        "tensor_shape": tensor_shape,
    }


def export_cnn_artifact(
    checkpoint_path: Path,
    metrics_path: Path,
    output_dir: Path,
    readme_path: Path | None = None,
) -> dict:
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    if not isinstance(checkpoint, dict):
        raise ValueError("CNN checkpoint must contain a dictionary")
    raw_model_config = checkpoint.get("model_config")
    if not isinstance(raw_model_config, dict):
        raise ValueError("checkpoint is missing model_config")
    model_config = CNNModelConfig(**raw_model_config)
    if model_config.class_count != len(CLASS_NAMES):
        raise ValueError("checkpoint model output count does not match final classes")
    state_dict = checkpoint.get("state_dict")
    if not isinstance(state_dict, dict):
        raise ValueError("checkpoint is missing state_dict")
    model = SmallCSIConvNet(model_config)
    model.load_state_dict(state_dict, strict=True)
    model.eval()
    config = build_feature_config(checkpoint, output_dir.name)
    with TemporaryDirectory(prefix="vsense-cnn-export-") as temporary_directory:
        temporary_path = Path(temporary_directory)
        scripted_path = temporary_path / "model.pt"
        config_path = temporary_path / "feature_config.json"
        example = torch.zeros((1, *config["tensor_shape"]), dtype=torch.float32)
        torch.jit.trace(model, example, strict=True).save(str(scripted_path))
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        return package_model(
            model_path=scripted_path,
            config_path=config_path,
            metrics_path=metrics_path,
            output_dir=output_dir,
            readme_path=readme_path,
        )


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--readme", type=Path)
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        manifest = export_cnn_artifact(
            checkpoint_path=args.checkpoint,
            metrics_path=args.metrics,
            output_dir=args.output,
            readme_path=args.readme,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise SystemExit(f"Could not export CNN artifact: {exc}") from exc
    print(f"Exported {manifest['model_version']} at {args.output}")


if __name__ == "__main__":
    main()
