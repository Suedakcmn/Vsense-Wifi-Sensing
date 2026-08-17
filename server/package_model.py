"""Create a reproducible, checksummed final VSense model artifact directory."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from validate_model_artifact import sha256_file, validate_artifact


def package_model(
    *,
    model_path: Path,
    config_path: Path,
    metrics_path: Path,
    output_dir: Path,
    readme_path: Path | None = None,
    confusion_dir: Path | None = None,
    training_curves_dir: Path | None = None,
) -> dict:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output directory must be empty: {output_dir}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("feature config must be a JSON object")
    configured_name = str(config.get("model_file") or model_path.name)
    config["model_file"] = configured_name
    config.setdefault("model_version", output_dir.name)
    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(model_path, output_dir / configured_name)
    (output_dir / "feature_config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copy2(metrics_path, output_dir / "metrics.json")
    if readme_path:
        shutil.copy2(readme_path, output_dir / "README.md")
    else:
        (output_dir / "README.md").write_text(
            f"# {config['model_version']}\n\nPackaged VSense activity model.\n",
            encoding="utf-8",
        )
    for source, name in (
        (confusion_dir, "confusion_matrix"),
        (training_curves_dir, "training_curves"),
    ):
        if source:
            shutil.copytree(source, output_dir / name)

    try:
        git_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        git_commit = "unknown"
    packages = {}
    for name in ("numpy", "scikit-learn", "joblib", "torch"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
    manifest = {
        "schema_version": 1,
        "model_version": config["model_version"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit,
        "python_version": sys.version.split()[0],
        "packages": packages,
        "files": {
            path.name: sha256_file(path)
            for path in sorted(output_dir.iterdir())
            if path.is_file()
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    validate_artifact(
        output_dir,
        require_report=True,
        require_final_classes=True,
    )
    return manifest


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--readme", type=Path)
    parser.add_argument("--confusion-dir", type=Path)
    parser.add_argument("--training-curves-dir", type=Path)
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        manifest = package_model(
            model_path=args.model,
            config_path=args.config,
            metrics_path=args.metrics,
            output_dir=args.output,
            readme_path=args.readme,
            confusion_dir=args.confusion_dir,
            training_curves_dir=args.training_curves_dir,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Could not package model: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"Packaged {manifest['model_version']} at {args.output}")


if __name__ == "__main__":
    main()
