"""Run reproducible development experiments without touching repeat-3 test data."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import ConfusionMatrixDisplay, accuracy_score, f1_score
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from ml.constants import CLASS_NAMES, META_COLUMNS, MODEL_SCHEMA_VERSION
from ml.train_baselines import repeat_from_session_id


matplotlib.use("Agg")
import matplotlib.pyplot as plt


DEVELOPMENT_REPEATS = (1, 2)
LOCKED_TEST_REPEAT = 3


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--features",
        type=Path,
        default=Path("dataset-v1/processed/features.parquet"),
    )
    parser.add_argument("--experiment-name", required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("dataset-v1/experiments"),
    )
    return parser.parse_args()


def build_models() -> dict[str, Pipeline]:
    """Return fresh, explicitly configured models used in every experiment."""
    return {
        "knn": Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "classifier",
                    KNeighborsClassifier(n_neighbors=7, weights="distance"),
                ),
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


def development_folds(table: pd.DataFrame):
    """Swap repeats 1 and 2; repeat 3 is never yielded or inspected."""
    repeats = table["session_id"].map(repeat_from_session_id)
    for validation_repeat in DEVELOPMENT_REPEATS:
        training_repeat = next(
            repeat for repeat in DEVELOPMENT_REPEATS if repeat != validation_repeat
        )
        yield (
            f"train_r{training_repeat:02d}_validate_r{validation_repeat:02d}",
            table[repeats == training_repeat],
            table[repeats == validation_repeat],
        )


def validate_table(table: pd.DataFrame) -> None:
    required = META_COLUMNS | {"label"}
    missing_columns = required - set(table.columns)
    if missing_columns:
        raise ValueError(f"feature table is missing columns: {sorted(missing_columns)}")
    repeats = set(table["session_id"].map(repeat_from_session_id))
    expected_repeats = set(DEVELOPMENT_REPEATS) | {LOCKED_TEST_REPEAT}
    if repeats != expected_repeats:
        raise ValueError(
            f"expected repeats {sorted(expected_repeats)}, found {sorted(repeats)}"
        )
    for repeat in expected_repeats:
        labels = set(
            table[
                table["session_id"].map(repeat_from_session_id) == repeat
            ]["label"]
        )
        missing_classes = set(CLASS_NAMES) - labels
        if missing_classes:
            raise ValueError(
                f"repeat {repeat} is missing classes: {sorted(missing_classes)}"
            )


def filter_model_classes(table: pd.DataFrame) -> pd.DataFrame:
    """Keep only labels in the current model contract."""
    return table[table["label"].isin(CLASS_NAMES)].copy()


def model_parameters(model: Pipeline) -> dict:
    """Keep only stable parameters that explain the actual experiment."""
    classifier = model.named_steps["classifier"]
    return {
        "scaler": type(model.named_steps["scaler"]).__name__,
        "classifier": type(classifier).__name__,
        "classifier_parameters": {
            key: value
            for key, value in classifier.get_params().items()
            if key
            in {
                "n_neighbors",
                "weights",
                "kernel",
                "C",
                "gamma",
                "class_weight",
                "probability",
                "random_state",
            }
        },
    }


def save_confusion_matrix(y_true, y_pred, title: str, output_path: Path) -> None:
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


def run_development_cv(table: pd.DataFrame, models: dict[str, Pipeline]):
    feature_columns = [column for column in table.columns if column not in META_COLUMNS]
    results = {}
    predictions = {}
    for model_name, template in models.items():
        folds = []
        fold_predictions = {}
        true_parts = []
        predicted_parts = []
        for fold_name, train, validation in development_folds(table):
            model = clone(template)
            model.fit(train[feature_columns], train["label"])
            predicted = model.predict(validation[feature_columns])
            folds.append(
                {
                    "fold": fold_name,
                    "training_sessions": sorted(train["session_id"].unique()),
                    "validation_sessions": sorted(validation["session_id"].unique()),
                    "training_windows": len(train),
                    "validation_windows": len(validation),
                    "accuracy": float(accuracy_score(validation["label"], predicted)),
                    "macro_f1": float(
                        f1_score(
                            validation["label"],
                            predicted,
                            labels=CLASS_NAMES,
                            average="macro",
                            zero_division=0,
                        )
                    ),
                }
            )
            true_parts.extend(validation["label"].tolist())
            predicted_parts.extend(predicted.tolist())
            fold_predictions[fold_name] = (
                validation["label"].tolist(),
                predicted.tolist(),
            )
        macro_f1_values = [fold["macro_f1"] for fold in folds]
        accuracy_values = [fold["accuracy"] for fold in folds]
        results[model_name] = {
            "parameters": model_parameters(template),
            "folds": folds,
            "mean_macro_f1": float(np.mean(macro_f1_values)),
            "std_macro_f1": float(np.std(macro_f1_values)),
            "mean_accuracy": float(np.mean(accuracy_values)),
            "std_accuracy": float(np.std(accuracy_values)),
        }
        predictions[model_name] = {
            "combined": (true_parts, predicted_parts),
            "folds": fold_predictions,
        }
    return feature_columns, results, predictions


def main():
    args = parse_args()
    table = filter_model_classes(pd.read_parquet(args.features))
    validate_table(table)
    manifest_path = args.features.with_suffix(".manifest.json")
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else None
    )
    feature_columns, results, predictions = run_development_cv(table, build_models())
    output_dir = args.output_root / args.experiment_name
    output_dir.mkdir(parents=True, exist_ok=False)
    for model_name, model_predictions in predictions.items():
        truth, prediction = model_predictions["combined"]
        save_confusion_matrix(
            truth,
            prediction,
            f"{model_name.upper()} — development session CV",
            output_dir / f"confusion_matrix_{model_name}.png",
        )
        for fold_name, (fold_truth, fold_prediction) in model_predictions["folds"].items():
            save_confusion_matrix(
                fold_truth,
                fold_prediction,
                f"{model_name.upper()} — {fold_name}",
                output_dir / f"confusion_matrix_{model_name}_{fold_name}.png",
            )
    selected_model = max(results, key=lambda name: results[name]["mean_macro_f1"])
    report = {
        "schema_version": MODEL_SCHEMA_VERSION,
        "experiment_name": args.experiment_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selection_metric": "mean development session-CV macro-F1",
        "selected_model": selected_model,
        "split_policy": {
            "development_repeats": list(DEVELOPMENT_REPEATS),
            "folds": "swap repeat 1 and repeat 2",
            "locked_test_repeat": LOCKED_TEST_REPEAT,
            "test_was_evaluated": False,
        },
        "feature_source": str(args.features),
        "feature_manifest": manifest,
        "feature_columns": feature_columns,
        "class_names": CLASS_NAMES,
        "class_counts": table["label"].value_counts().to_dict(),
        "session_ids": sorted(table["session_id"].unique()),
        "results": results,
    }
    (output_dir / "experiment.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(f"Experiment: {args.experiment_name}")
    for model_name, result in results.items():
        print(
            f"{model_name}: macro-F1={result['mean_macro_f1']:.3f} "
            f"+/- {result['std_macro_f1']:.3f}"
        )
    print(f"Development winner: {selected_model}")
    print("Repeat 3 remains locked and was not evaluated.")
    print(f"Results: {output_dir}")


if __name__ == "__main__":
    main()
