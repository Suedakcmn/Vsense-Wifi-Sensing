"""Train and evaluate the small CSI CNN on one development session fold."""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import matplotlib
import numpy as np
import torch
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    accuracy_score,
    classification_report,
    f1_score,
)
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from ml.cnn_model import CNNModelConfig, SmallCSIConvNet
from ml.constants import CLASS_NAMES, MODEL_SCHEMA_VERSION


matplotlib.use("Agg")
import matplotlib.pyplot as plt


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("dataset-v1/processed/cnn_2s_40hz_zscore"),
    )
    parser.add_argument("--train-repeat", type=int, required=True, choices=(1, 2))
    parser.add_argument("--validation-repeat", type=int, required=True, choices=(1, 2))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-train-samples", type=int)
    parser.add_argument("--max-validation-samples", type=int)
    parser.add_argument("--device", choices=("auto", "cpu", "mps"), default="auto")
    return parser.parse_args()


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def select_device(requested: str) -> torch.device:
    if requested == "mps":
        if not torch.backends.mps.is_available():
            raise RuntimeError("MPS was requested but is not available")
        return torch.device("mps")
    if requested == "cpu":
        return torch.device("cpu")
    return torch.device("mps" if torch.backends.mps.is_available() else "cpu")


def load_repeat(cache_dir: Path, repeat: int, max_samples: int | None = None):
    manifest = json.loads((cache_dir / "manifest.json").read_text(encoding="utf-8"))
    selected = [item for item in manifest["sessions"] if item["repeat"] == repeat]
    if len(selected) != len(CLASS_NAMES):
        raise ValueError(
            f"repeat {repeat} must contain {len(CLASS_NAMES)} sessions, got {len(selected)}"
        )
    inputs = []
    targets = []
    if max_samples is not None and max_samples < len(CLASS_NAMES):
        raise ValueError(f"max_samples must be at least {len(CLASS_NAMES)}")
    per_session_limit = (
        None if max_samples is None else max_samples // len(selected)
    )
    remainder = 0 if max_samples is None else max_samples % len(selected)
    for index, item in enumerate(selected):
        payload = torch.load(cache_dir / item["file"], map_location="cpu", weights_only=True)
        limit = None
        if per_session_limit is not None:
            limit = per_session_limit + (1 if index < remainder else 0)
        inputs.append(payload["inputs"][:limit])
        targets.append(payload["targets"][:limit])
    all_inputs = torch.cat(inputs)
    all_targets = torch.cat(targets)
    return TensorDataset(all_inputs, all_targets), manifest


def balanced_class_weights(targets: torch.Tensor) -> torch.Tensor:
    counts = torch.bincount(targets, minlength=len(CLASS_NAMES)).float()
    if torch.any(counts == 0):
        raise ValueError(f"training split is missing classes: counts={counts.tolist()}")
    return targets.numel() / (len(CLASS_NAMES) * counts)


def run_epoch(model, loader, criterion, device, optimizer=None):
    training = optimizer is not None
    model.train(training)
    total_loss = 0.0
    total_examples = 0
    truth = []
    prediction = []
    context = torch.enable_grad() if training else torch.inference_mode()
    with context:
        for inputs, targets in loader:
            inputs = inputs.to(device)
            targets = targets.to(device)
            if training:
                optimizer.zero_grad(set_to_none=True)
            logits = model(inputs)
            loss = criterion(logits, targets)
            if not torch.isfinite(loss):
                raise RuntimeError("CNN loss became NaN or Inf")
            if training:
                loss.backward()
                for parameter in model.parameters():
                    if parameter.grad is not None and not torch.isfinite(parameter.grad).all():
                        raise RuntimeError("CNN gradient became NaN or Inf")
                optimizer.step()
            batch_size = targets.shape[0]
            total_loss += float(loss.detach()) * batch_size
            total_examples += batch_size
            truth.extend(targets.detach().cpu().tolist())
            prediction.extend(logits.argmax(dim=1).detach().cpu().tolist())
    return {
        "loss": total_loss / total_examples,
        "accuracy": float(accuracy_score(truth, prediction)),
        "macro_f1": float(
            f1_score(
                truth,
                prediction,
                labels=list(range(len(CLASS_NAMES))),
                average="macro",
                zero_division=0,
            )
        ),
        "truth": truth,
        "prediction": prediction,
    }


def save_training_curves(history: list[dict], output_path: Path) -> None:
    epochs = [item["epoch"] for item in history]
    figure, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].plot(epochs, [item["train"]["loss"] for item in history], label="train")
    axes[0].plot(epochs, [item["validation"]["loss"] for item in history], label="validation")
    axes[0].set_title("Loss")
    axes[0].legend()
    axes[1].plot(
        epochs,
        [item["train"]["macro_f1"] for item in history],
        label="train",
    )
    axes[1].plot(
        epochs,
        [item["validation"]["macro_f1"] for item in history],
        label="validation",
    )
    axes[1].set_title("Macro-F1")
    axes[1].legend()
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def save_confusion_matrix(truth, prediction, output_path: Path) -> None:
    figure, axis = plt.subplots(figsize=(8, 7))
    ConfusionMatrixDisplay.from_predictions(
        truth,
        prediction,
        labels=list(range(len(CLASS_NAMES))),
        display_labels=CLASS_NAMES,
        normalize="true",
        values_format=".2f",
        cmap="Blues",
        ax=axis,
    )
    axis.set_title("CNN validation")
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def measure_inference_ms(model, sample: torch.Tensor, device: torch.device) -> float:
    model.eval()
    sample = sample[:1].to(device)
    with torch.inference_mode():
        for _ in range(10):
            model(sample)
        start = time.perf_counter()
        for _ in range(100):
            model(sample)
        elapsed = time.perf_counter() - start
    return elapsed * 1000 / 100


def main():
    args = parse_args()
    if args.train_repeat == args.validation_repeat:
        raise ValueError("training and validation repeats must be different")
    if args.epochs <= 0 or args.batch_size <= 0 or args.patience <= 0:
        raise ValueError("epochs, batch size, and patience must be positive")
    set_seed(args.seed)
    device = select_device(args.device)
    train_dataset, manifest = load_repeat(
        args.cache_dir, args.train_repeat, args.max_train_samples
    )
    validation_dataset, validation_manifest = load_repeat(
        args.cache_dir, args.validation_repeat, args.max_validation_samples
    )
    if manifest != validation_manifest:
        raise ValueError("training and validation cache manifests differ")
    generator = torch.Generator().manual_seed(args.seed)
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        generator=generator,
    )
    validation_loader = DataLoader(
        validation_dataset,
        batch_size=args.batch_size,
        shuffle=False,
    )
    model_config = CNNModelConfig(
        input_receivers=manifest["tensor_shape"][0],
        input_subcarriers=manifest["tensor_shape"][2],
        class_count=len(CLASS_NAMES),
    )
    model = SmallCSIConvNet(model_config).to(device)
    class_weights = balanced_class_weights(train_dataset.tensors[1]).to(device)
    criterion = nn.CrossEntropyLoss(weight=class_weights)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.learning_rate,
        weight_decay=args.weight_decay,
    )
    args.output_dir.mkdir(parents=True, exist_ok=False)
    history = []
    best_f1 = -1.0
    best_epoch = 0
    epochs_without_improvement = 0
    started = time.perf_counter()
    checkpoint_path = args.output_dir / "best_model.pt"
    for epoch in range(1, args.epochs + 1):
        train_metrics = run_epoch(model, train_loader, criterion, device, optimizer)
        validation_metrics = run_epoch(
            model, validation_loader, criterion, device, optimizer=None
        )
        history.append(
            {
                "epoch": epoch,
                "train": {key: train_metrics[key] for key in ("loss", "accuracy", "macro_f1")},
                "validation": {
                    key: validation_metrics[key]
                    for key in ("loss", "accuracy", "macro_f1")
                },
            }
        )
        print(
            f"epoch={epoch:02d} train_loss={train_metrics['loss']:.4f} "
            f"train_f1={train_metrics['macro_f1']:.3f} "
            f"val_loss={validation_metrics['loss']:.4f} "
            f"val_f1={validation_metrics['macro_f1']:.3f}"
        )
        if validation_metrics["macro_f1"] > best_f1 + 1e-6:
            best_f1 = validation_metrics["macro_f1"]
            best_epoch = epoch
            epochs_without_improvement = 0
            torch.save(
                {
                    "state_dict": model.state_dict(),
                    "model_config": model_config.to_dict(),
                    "class_names": CLASS_NAMES,
                    "preprocessing": {
                        "window_config": manifest["window_config"],
                        "tensor_config": manifest["tensor_config"],
                        "subcarrier_indices": manifest["subcarrier_indices"],
                        "tensor_shape": manifest["tensor_shape"],
                    },
                },
                checkpoint_path,
            )
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= args.patience:
                print(f"early stopping at epoch {epoch}")
                break
    training_seconds = time.perf_counter() - started
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=True)
    model.load_state_dict(checkpoint["state_dict"])
    final_validation = run_epoch(
        model, validation_loader, criterion, device, optimizer=None
    )
    inference_ms = measure_inference_ms(model, validation_dataset.tensors[0], device)
    report = {
        "schema_version": MODEL_SCHEMA_VERSION,
        "model_type": "small_2d_cnn",
        "model_config": model_config.to_dict(),
        "class_names": CLASS_NAMES,
        "train_repeat": args.train_repeat,
        "validation_repeat": args.validation_repeat,
        "test_repeat_evaluated": False,
        "seed": args.seed,
        "epochs_requested": args.epochs,
        "epochs_completed": len(history),
        "best_epoch": best_epoch,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "weight_decay": args.weight_decay,
        "patience": args.patience,
        "device": str(device),
        "training_seconds": training_seconds,
        "inference_ms_per_window": inference_ms,
        "class_weights": class_weights.detach().cpu().tolist(),
        "training_samples": len(train_dataset),
        "validation_samples": len(validation_dataset),
        "validation": {
            "loss": final_validation["loss"],
            "accuracy": final_validation["accuracy"],
            "macro_f1": final_validation["macro_f1"],
            "classification_report": classification_report(
                final_validation["truth"],
                final_validation["prediction"],
                labels=list(range(len(CLASS_NAMES))),
                target_names=CLASS_NAMES,
                output_dict=True,
                zero_division=0,
            ),
        },
        "history": history,
    }
    (args.output_dir / "metrics.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    save_training_curves(history, args.output_dir / "training_curves.png")
    save_confusion_matrix(
        final_validation["truth"],
        final_validation["prediction"],
        args.output_dir / "confusion_matrix.png",
    )
    print(
        f"best_epoch={best_epoch} validation_macro_f1={final_validation['macro_f1']:.3f} "
        f"inference_ms={inference_ms:.3f} training_seconds={training_seconds:.1f}"
    )
    print(f"Results: {args.output_dir}")


if __name__ == "__main__":
    main()
