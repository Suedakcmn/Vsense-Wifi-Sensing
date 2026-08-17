"""Validate a VSense model artifact before it enters the live pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from activity_model import ModelContractError
from models import load_activity_artifact


EXPECTED_CLASSES = (
    "empty_room",
    "walking",
    "sitting",
    "standing",
    "desk_work",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_artifact(artifact_dir: Path | str, *, require_report: bool = False) -> dict:
    directory = Path(artifact_dir)
    loaded = load_activity_artifact(directory)
    config = loaded.config
    classes = tuple(config.get("class_names", ()))
    if classes != EXPECTED_CLASSES:
        raise ModelContractError(
            f"class_names must use the project order: {list(EXPECTED_CLASSES)}"
        )
    required_nodes = config.get("required_nodes")
    if required_nodes != ["rx_01", "rx_02"]:
        raise ModelContractError("required_nodes must be ordered as rx_01, rx_02")
    subcarriers = config.get("selected_subcarriers")
    if not isinstance(subcarriers, list) or len(subcarriers) != 20:
        raise ModelContractError("selected_subcarriers must contain exactly 20 indices")
    if len(set(subcarriers)) != len(subcarriers):
        raise ModelContractError("selected_subcarriers must be unique")

    model_type = loaded.metadata.model_type
    model_name = str(config.get("model_file") or (
        "model.pt" if model_type in {"torch_cnn", "cnn", "pytorch_cnn"}
        else "model.joblib"
    ))
    model_path = directory / model_name
    if not model_path.is_file():
        raise ModelContractError(f"missing configured model file: {model_path}")
    warnings = []
    for name in ("metrics.json", "README.md"):
        if not (directory / name).is_file():
            message = f"recommended artifact report is missing: {name}"
            if require_report:
                raise ModelContractError(message)
            warnings.append(message)
    return {
        "status": "VALID",
        "artifact": directory.name,
        "model_type": model_type,
        "model_file": model_name,
        "model_sha256": sha256_file(model_path),
        "classes": list(classes),
        "required_nodes": required_nodes,
        "window_seconds": loaded.metadata.window_seconds,
        "stride_seconds": loaded.metadata.stride_seconds,
        "normalization": loaded.metadata.normalization,
        "sample_rate_hz": loaded.metadata.sample_rate_hz,
        "warnings": warnings,
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("--require-report", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        result = validate_artifact(args.artifact_dir, require_report=args.require_report)
    except (ModelContractError, OSError, ValueError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    if args.json:
        print(json.dumps(result, indent=2))
        return
    print(f"Artifact: {result['artifact']}")
    print(f"Model type: {result['model_type']}")
    print(f"Classes: {len(result['classes'])}")
    print(f"RX nodes: {', '.join(result['required_nodes'])}")
    print(f"Window: {result['window_seconds']} s")
    print(f"Status: {result['status']}")
    for warning in result["warnings"]:
        print(f"Warning: {warning}")


if __name__ == "__main__":
    main()
