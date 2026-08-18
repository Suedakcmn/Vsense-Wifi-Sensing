"""Train and honestly evaluate window-level kNN and SVM baselines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    accuracy_score,
    classification_report,
    f1_score,
)
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from ml.constants import CLASS_NAMES, META_COLUMNS, MODEL_SCHEMA_VERSION

def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--features",
        type=Path,
        default=Path("dataset-v1/processed/features.parquet"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dataset-v1/models/baseline_v1"),
    )
    return parser.parse_args()


def repeat_from_session_id(session_id: str) -> int:
    marker = session_id.rsplit("_r", 1)[-1]
    return int(marker)


def split_by_repeat(table: pd.DataFrame):
    repeats = table["session_id"].map(repeat_from_session_id)
    return table[repeats == 1], table[repeats == 2], table[repeats == 3]


def evaluate(model, x, y):
    prediction = model.predict(x)
    return {
        "accuracy": float(accuracy_score(y, prediction)),
        "macro_f1": float(f1_score(y, prediction, average="macro")),
        "classification_report": classification_report(
            y,
            prediction,
            labels=CLASS_NAMES,
            output_dict=True,
            zero_division=0,
        ),
    }, prediction


def save_confusion_matrix(y_true, y_pred, title, output_path):
    figure, axis = plt.subplots(figsize=(8, 7))
    ConfusionMatrixDisplay.from_predictions(
        y_true,
        y_pred,
        labels=CLASS_NAMES,
        normalize="true",
        values_format=".2f",
        cmap="Blues",
        ax=axis,
    )
    axis.set_title(title)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def main():
    args = parse_args()
    table = pd.read_parquet(args.features)
    manifest_path = args.features.with_suffix(".manifest.json")
    feature_manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.is_file()
        else {}
    )
    table = table[table["label"].isin(CLASS_NAMES)].copy()
    feature_columns = [column for column in table.columns if column not in META_COLUMNS]
    train, validation, test = split_by_repeat(table)
    for name, split in (("train", train), ("validation", validation), ("test", test)):
        missing = set(CLASS_NAMES) - set(split["label"])
        if missing:
            raise ValueError(f"{name} split is missing classes: {sorted(missing)}")

    models = {
        "knn": Pipeline(
            [
                ("scaler", StandardScaler()),
                ("classifier", KNeighborsClassifier(n_neighbors=7, weights="distance")),
            ]
        ),
        "svm": Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "classifier",
                    SVC(
                        kernel="rbf",
                        C=3.0,
                        gamma="scale",
                        class_weight="balanced",
                        probability=True,
                        random_state=42,
                    ),
                ),
            ]
        ),
    }
    x_train, y_train = train[feature_columns], train["label"]
    x_validation, y_validation = validation[feature_columns], validation["label"]
    x_test, y_test = test[feature_columns], test["label"]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    fitted = {}
    for model_name, model in models.items():
        print(f"Training {model_name} on {len(train)} windows...")
        model.fit(x_train, y_train)
        validation_metrics, validation_prediction = evaluate(
            model, x_validation, y_validation
        )
        test_metrics, test_prediction = evaluate(model, x_test, y_test)
        results[model_name] = {
            "validation": validation_metrics,
            "test": test_metrics,
        }
        fitted[model_name] = model
        save_confusion_matrix(
            y_test,
            test_prediction,
            f"{model_name.upper()} — session-held-out test",
            args.output_dir / f"confusion_matrix_{model_name}.png",
        )
        print(
            f"{model_name}: validation macro-F1={validation_metrics['macro_f1']:.3f}, "
            f"test macro-F1={test_metrics['macro_f1']:.3f}"
        )

    best_name = max(results, key=lambda name: results[name]["validation"]["macro_f1"])
    joblib.dump(fitted[best_name], args.output_dir / "model.joblib")
    selected_subcarriers = [
        int(column.split("_sc", 1)[1].split("_", 1)[0])
        for column in feature_columns
        if column.startswith("rx_01_sc") and column.endswith("_mean")
    ]
    (args.output_dir / "feature_config.json").write_text(
        json.dumps(
            {
                "schema_version": MODEL_SCHEMA_VERSION,
                "model_type": best_name,
                "window_seconds": 2.0,
                "stride_seconds": 1.0,
                "trim_seconds": 10.0,
                "max_gap_ms": 500.0,
                "min_rows_per_node": 20,
                "required_nodes": ["rx_01", "rx_02"],
                "selected_subcarriers": selected_subcarriers,
                "feature_columns": feature_columns,
                "class_names": CLASS_NAMES,
                "normalization": feature_manifest.get("normalization", "none"),
                "spectral_features": bool(feature_manifest.get("spectral_features", False)),
                "sample_rate_hz": feature_manifest.get("sample_rate_hz"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    split_summary = {
        name: {
            "windows": len(split),
            "sessions": sorted(split["session_id"].unique().tolist()),
            "subjects": sorted(split["subject"].unique().tolist()),
            "class_counts": split["label"].value_counts().to_dict(),
        }
        for name, split in (("train", train), ("validation", validation), ("test", test))
    }
    report = {
        "schema_version": MODEL_SCHEMA_VERSION,
        "selection_metric": "validation macro_f1",
        "selected_model": best_name,
        "split_policy": "repeat 1=train, repeat 2=validation, repeat 3=test",
        "honesty_note": (
            "Splits are session-independent but not fully person-independent; "
            "the campaign does not contain every class for every subject."
        ),
        "splits": split_summary,
        "models": results,
    }
    (args.output_dir / "metrics.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(f"Selected {best_name}; artifacts written to {args.output_dir}")


if __name__ == "__main__":
    main()
