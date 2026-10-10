"""Leakage-safe data preparation and baselines for the synthetic ML experiment."""

from __future__ import annotations

import csv
import math
import warnings
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pydantic import ValidationError
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.schemas.dataset import (
    MODEL_INPUT_FIELDS,
    SyntheticHouseholdRecord,
)

TARGET_FIELDS = ("electricity_kwh_per_month", "lpg_kg_per_month")
SPLIT_NAMES = ("train", "validation", "test")
SPLIT_PROPORTIONS = (0.70, 0.15, 0.15)
CATEGORICAL_FEATURES = (
    "dwelling_type",
    "settlement_type",
    "state",
    "monthly_household_income_band",
    "cooking_fuel_primary",
    "cooking_fuel_secondary",
    "climate_zone",
)
NUMERIC_FEATURES = (
    "household_size",
    "daytime_occupancy_hours",
    "num_working_members",
    "has_air_conditioner",
    "has_refrigerator",
    "has_washing_machine",
    "has_personal_vehicle",
)
DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "synthetic"
    / "household_records_v1.csv"
)
FEATURE_FIELDS = tuple(MODEL_INPUT_FIELDS)
NON_FEATURE_FIELDS = tuple(
    field
    for field in SyntheticHouseholdRecord.FIELD_ORDER
    if field not in FEATURE_FIELDS
)
if set(CATEGORICAL_FEATURES).union(NUMERIC_FEATURES) != set(FEATURE_FIELDS):
    raise RuntimeError("Preprocessing columns must exactly cover MODEL_INPUT_FIELDS")


class DatasetValidationError(ValueError):
    """Raised when the source CSV does not satisfy the v1 record contract."""


@dataclass(frozen=True)
class DataSplits:
    """Position-based, reproducible partitions of the validated source records."""

    train: np.ndarray
    validation: np.ndarray
    test: np.ndarray

    def as_dict(self) -> dict[str, np.ndarray]:
        return {name: getattr(self, name) for name in SPLIT_NAMES}


def load_dataset(path: Path | str = DEFAULT_DATASET_PATH) -> pd.DataFrame:
    """Read and validate every source record against the existing Pydantic schema."""
    source = Path(path)
    try:
        with source.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.reader(csv_file)
            try:
                header = next(reader)
            except StopIteration as exc:
                raise DatasetValidationError(f"Dataset is empty: {source}") from exc

            duplicates = sorted({name for name in header if header.count(name) > 1})
            if duplicates:
                raise DatasetValidationError(
                    f"Dataset has duplicate column names: {', '.join(duplicates)}"
                )

            required = set(SyntheticHouseholdRecord.FIELD_ORDER)
            missing = sorted(required.difference(header))
            unexpected = sorted(set(header).difference(required))
            if missing or unexpected:
                details = []
                if missing:
                    details.append(f"missing columns: {', '.join(missing)}")
                if unexpected:
                    details.append(f"unexpected columns: {', '.join(unexpected)}")
                raise DatasetValidationError(
                    "Invalid dataset header (" + "; ".join(details) + ")"
                )

            if "schema_version" not in header:
                raise DatasetValidationError(
                    "Dataset is missing required schema_version column"
                )

            dict_reader = csv.DictReader(csv_file, fieldnames=header)
            validated_rows: list[dict[str, Any]] = []
            for row_number, row in enumerate(dict_reader, start=2):
                if None in row or any(value is None for value in row.values()):
                    raise DatasetValidationError(
                        f"Malformed or incomplete CSV row {row_number} in {source}"
                    )
                if isinstance(row.get("is_synthetic"), str):
                    marker = row["is_synthetic"].strip().lower()
                    if marker in {"true", "false"}:
                        row["is_synthetic"] = marker == "true"
                try:
                    validated = SyntheticHouseholdRecord.model_validate(row)
                except ValidationError as exc:
                    raise DatasetValidationError(
                        f"Invalid record at CSV row {row_number}: {exc.errors(include_url=False)}"
                    ) from exc
                validated_rows.append(validated.model_dump(mode="python"))
    except DatasetValidationError:
        raise
    except OSError as exc:
        raise DatasetValidationError(
            f"Could not read dataset '{source}': {exc}"
        ) from exc

    if not validated_rows:
        raise DatasetValidationError(f"Dataset contains no records: {source}")
    return pd.DataFrame.from_records(
        validated_rows, columns=SyntheticHouseholdRecord.FIELD_ORDER
    )


def select_features(data: pd.DataFrame) -> pd.DataFrame:
    """Return only the authoritative descriptor allowlist, in schema-defined order."""
    missing = [name for name in FEATURE_FIELDS if name not in data.columns]
    if missing:
        raise DatasetValidationError(
            f"Cannot select model features; missing columns: {', '.join(missing)}"
        )
    return data.loc[:, list(FEATURE_FIELDS)].copy()


def select_target(data: pd.DataFrame, target: str) -> pd.Series:
    """Return one explicitly supported activity target."""
    if target not in TARGET_FIELDS:
        raise ValueError(
            f"Unsupported target '{target}'; expected one of {TARGET_FIELDS}"
        )
    if target not in data.columns:
        raise DatasetValidationError(f"Dataset is missing target column '{target}'")
    values = pd.to_numeric(data[target], errors="coerce")
    if values.isna().any() or not np.isfinite(values.to_numpy(dtype=float)).all():
        raise DatasetValidationError(
            f"Target '{target}' contains missing or non-finite values"
        )
    numeric = values.to_numpy(dtype=float)
    if target == "electricity_kwh_per_month" and (
        np.any(numeric < 10.0) or np.any(numeric > 2000.0)
    ):
        raise DatasetValidationError(
            "Target 'electricity_kwh_per_month' must be within [10, 2000] kWh/month"
        )
    if target == "lpg_kg_per_month" and (
        np.any(numeric < 0.0)
        or np.any(numeric > 60.0)
        or np.any((numeric > 0.0) & (numeric < 0.5))
    ):
        raise DatasetValidationError(
            "Target 'lpg_kg_per_month' must be 0 or within [0.5, 60] kg/month"
        )
    return values.astype(float)


def build_preprocessor(*, scale_numeric: bool) -> ColumnTransformer:
    """Build categorical encoding and numeric handling for one candidate pipeline."""
    return ColumnTransformer(
        transformers=[
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                list(CATEGORICAL_FEATURES),
            ),
            (
                "numeric",
                StandardScaler() if scale_numeric else "passthrough",
                list(NUMERIC_FEATURES),
            ),
        ],
        remainder="drop",
        sparse_threshold=0.0,
    )


def _pipeline(estimator: Any, *, scale_numeric: bool) -> Pipeline:
    return Pipeline(
        steps=[
            ("preprocess", build_preprocessor(scale_numeric=scale_numeric)),
            ("model", estimator),
        ]
    )


def _partition_sizes(n_rows: int) -> tuple[int, int, int]:
    if n_rows < len(SPLIT_NAMES):
        raise DatasetValidationError(
            "At least three records are required for non-empty train, validation, and test partitions"
        )
    quotas = np.asarray(SPLIT_PROPORTIONS) * n_rows
    sizes = np.floor(quotas).astype(int)
    for index in np.argsort(-(quotas - sizes), kind="stable")[
        : n_rows - int(sizes.sum())
    ]:
        sizes[index] += 1
    # Small datasets can round a partition to zero; borrow a row from the largest one.
    for empty_index in np.flatnonzero(sizes == 0):
        donor = int(np.argmax(sizes))
        sizes[donor] -= 1
        sizes[empty_index] = 1
    return tuple(int(size) for size in sizes)


def _allocate_positive_counts(
    positive_count: int,
    zero_count: int,
    capacities: tuple[int, int, int],
) -> tuple[int, int, int]:
    """Allocate LPG-use positives close to the split ratios while preserving classes."""
    lower = np.zeros(3, dtype=int)
    upper = np.asarray(capacities, dtype=int)
    if positive_count >= 3:
        lower = np.where(upper > 0, 1, 0)
    if zero_count >= 3:
        upper = np.maximum(upper - 1, 0)
    if lower.sum() > positive_count or upper.sum() < positive_count:
        lower = np.zeros(3, dtype=int)
        upper = np.asarray(capacities, dtype=int)

    allocated = lower.copy()
    ideal = positive_count * np.asarray(SPLIT_PROPORTIONS)
    while int(allocated.sum()) < positive_count:
        available = np.flatnonzero(allocated < upper)
        if available.size == 0:
            raise DatasetValidationError(
                "Could not allocate LPG-use classes across partitions"
            )
        deficits = ideal[available] - allocated[available]
        chosen = int(available[int(np.argmax(deficits))])
        allocated[chosen] += 1
    return tuple(int(count) for count in allocated)


def split_indices(data: pd.DataFrame, seed: int = 42) -> DataSplits:
    """Create deterministic 70/15/15 partitions stratified on LPG use when possible."""
    if seed < 0:
        raise ValueError("split seed must be non-negative")
    if data.empty:
        raise DatasetValidationError("Cannot split an empty dataset")
    lpg = select_target(data, "lpg_kg_per_month").to_numpy()
    capacities = _partition_sizes(len(data))
    positive = lpg > 0.0
    positive_count = int(positive.sum())
    positive_allocations = _allocate_positive_counts(
        positive_count, len(data) - positive_count, capacities
    )
    rng = np.random.default_rng(seed)
    assignments: dict[str, list[int]] = {name: [] for name in SPLIT_NAMES}

    for mask, counts in (
        (positive, positive_allocations),
        (
            ~positive,
            tuple(
                capacity - count
                for capacity, count in zip(
                    capacities, positive_allocations, strict=True
                )
            ),
        ),
    ):
        class_indices = rng.permutation(np.flatnonzero(mask))
        cursor = 0
        for name, count in zip(SPLIT_NAMES, counts, strict=True):
            assignments[name].extend(class_indices[cursor : cursor + count].tolist())
            cursor += count

    partitions = {
        name: rng.permutation(np.asarray(indices, dtype=int))
        for name, indices in assignments.items()
    }
    if any(
        len(partitions[name]) != capacities[index]
        for index, name in enumerate(SPLIT_NAMES)
    ):
        raise DatasetValidationError(
            "Internal split allocation did not match requested partition sizes"
        )
    return DataSplits(**partitions)


def _regression_metrics(
    actual: np.ndarray, prediction: float | np.ndarray, *, unit: str
) -> dict[str, float | int | str | None]:
    if actual.size == 0:
        return {
            "n": 0,
            "mae": None,
            "rmse": None,
            "unit": unit,
            "undefined_reason": "no_evaluation_records",
        }
    predicted = (
        np.full(actual.shape, prediction, dtype=float)
        if np.isscalar(prediction)
        else np.asarray(prediction, dtype=float)
    )
    if predicted.shape != actual.shape or not np.isfinite(predicted).all():
        raise ValueError("Regression predictions must be finite and match target shape")
    errors = actual.astype(float) - predicted
    return {
        "n": int(actual.size),
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(math.sqrt(np.mean(np.square(errors)))),
        "unit": unit,
        "undefined_reason": None,
    }


def _classification_metrics(
    actual_positive: np.ndarray, predicted_positive_class: bool | np.ndarray
) -> dict[str, float | int | bool | None | str]:
    actual = actual_positive.astype(bool)
    predicted = (
        np.full(actual.shape, predicted_positive_class, dtype=bool)
        if isinstance(predicted_positive_class, (bool, np.bool_))
        else np.asarray(predicted_positive_class, dtype=bool)
    )
    if predicted.shape != actual.shape:
        raise ValueError("Classification predictions must match target shape")
    tp = int(np.sum(actual & predicted))
    fp = int(np.sum(~actual & predicted))
    fn = int(np.sum(actual & ~predicted))
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1_denominator = 2 * tp + fp + fn
    f1 = 2 * tp / f1_denominator if f1_denominator else None
    undefined_metrics = []
    if precision is None:
        undefined_metrics.append("precision")
    if recall is None:
        undefined_metrics.append("recall")
    if f1 is None:
        undefined_metrics.append("f1")
    scalar_prediction = isinstance(predicted_positive_class, (bool, np.bool_))
    result = {
        "n": int(actual.size),
        "positive_count": int(actual.sum()),
        "zero_use_count": int((~actual).sum()),
        "prediction_type": "constant" if scalar_prediction else "model",
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "undefined_metrics": undefined_metrics,
        "undefined_reason": "; ".join(
            reason
            for metric, reason in (
                ("precision", "no_predicted_positive"),
                ("recall", "no_actual_positive"),
                ("f1", "no_positive_cases_or_predictions"),
            )
            if metric in undefined_metrics
        )
        or None,
        "confusion_matrix": {
            "labels": [0, 1],
            "rows_actual_columns_predicted": [
                [int(np.sum(~actual & ~predicted)), fp],
                [fn, tp],
            ],
        },
    }
    if scalar_prediction:
        result["predicted_positive_class"] = bool(predicted_positive_class)
    return result


def evaluate_partition_baselines(
    data: pd.DataFrame, partitions: DataSplits, *, partition_name: str
) -> dict[str, Any]:
    """Evaluate train-fitted constant baselines on one held-out partition."""
    if partition_name not in {"validation", "test"}:
        raise ValueError("baseline evaluation partition must be validation or test")
    select_features(
        data
    )  # Assert the authoritative feature contract before evaluation.
    electricity = select_target(data, "electricity_kwh_per_month").to_numpy()
    lpg = select_target(data, "lpg_kg_per_month").to_numpy()
    train = partitions.train
    evaluation_indices = getattr(partitions, partition_name)

    electricity_train = electricity[train]
    electricity_evaluation = electricity[evaluation_indices]
    electricity_baselines = {}
    for name, value in (
        ("mean", float(np.mean(electricity_train))),
        ("median", float(np.median(electricity_train))),
    ):
        electricity_baselines[name] = {
            "prediction_kwh_per_month": value,
            **_regression_metrics(electricity_evaluation, value, unit="kWh/month"),
        }

    lpg_train = lpg[train]
    lpg_evaluation = lpg[evaluation_indices]
    train_positive = lpg_train > 0.0
    evaluation_positive = lpg_evaluation > 0.0
    train_positive_count = int(train_positive.sum())
    train_zero_count = int((~train_positive).sum())
    majority_positive = train_positive_count > train_zero_count
    lpg_amount_baselines: dict[str, Any] = {}
    if train_positive_count:
        positive_train = lpg_train[train_positive]
        for name, value in (
            ("mean", float(np.mean(positive_train))),
            ("median", float(np.median(positive_train))),
        ):
            lpg_amount_baselines[name] = {
                "prediction_kg_per_month": value,
                **_regression_metrics(
                    lpg_evaluation[evaluation_positive],
                    value,
                    unit="kg/month",
                ),
            }
    else:
        for name in ("mean", "median"):
            lpg_amount_baselines[name] = {
                "prediction_kg_per_month": None,
                **_regression_metrics(
                    np.asarray([], dtype=float), 0.0, unit="kg/month"
                ),
                "undefined_reason": "no_positive_lpg_records_in_training_partition",
            }

    return {
        partition_name: {
            "electricity": {
                "target": "electricity_kwh_per_month",
                "unit": "kWh/month",
                "baselines": electricity_baselines,
            },
            "lpg_use": {
                "target": "lpg_kg_per_month > 0",
                "positive_class": 1,
                "majority_class_baseline": _classification_metrics(
                    evaluation_positive, majority_positive
                ),
                "training_counts": {
                    "positive_use": train_positive_count,
                    "zero_use": train_zero_count,
                },
            },
            "positive_lpg_amount": {
                "target": "lpg_kg_per_month",
                "unit": "kg/month",
                f"{partition_name}_positive_count": int(evaluation_positive.sum()),
                "baselines": lpg_amount_baselines,
            },
        }
    }


def evaluate_validation_baselines(
    data: pd.DataFrame, partitions: DataSplits
) -> dict[str, Any]:
    """Evaluate train-fitted constant baselines on validation rows only."""
    return evaluate_partition_baselines(data, partitions, partition_name="validation")


def _candidate_specs(seed: int) -> dict[str, dict[str, Any]]:
    forest_parameters = {
        "n_estimators": 100,
        "max_depth": 12,
        "min_samples_leaf": 5,
        "max_features": 1.0,
        "n_jobs": 1,
        "random_state": seed,
    }
    return {
        "electricity_ridge": {
            "task": "electricity",
            "estimator": Ridge(alpha=1.0),
            "estimator_name": "Ridge",
            "hyperparameters": {"alpha": 1.0},
            "scale_numeric": True,
        },
        "electricity_random_forest": {
            "task": "electricity",
            "estimator": RandomForestRegressor(**forest_parameters),
            "estimator_name": "RandomForestRegressor",
            "hyperparameters": forest_parameters.copy(),
            "scale_numeric": False,
        },
        "lpg_use_logistic_regression": {
            "task": "lpg_use",
            "estimator": LogisticRegression(
                C=1.0, max_iter=1_000, solver="lbfgs", random_state=seed
            ),
            "estimator_name": "LogisticRegression",
            "hyperparameters": {
                "C": 1.0,
                "max_iter": 1_000,
                "solver": "lbfgs",
                "random_state": seed,
            },
            "scale_numeric": True,
        },
        "lpg_use_random_forest": {
            "task": "lpg_use",
            "estimator": RandomForestClassifier(**forest_parameters),
            "estimator_name": "RandomForestClassifier",
            "hyperparameters": forest_parameters.copy(),
            "scale_numeric": False,
        },
        "positive_lpg_ridge": {
            "task": "positive_lpg_amount",
            "estimator": Ridge(alpha=1.0),
            "estimator_name": "Ridge",
            "hyperparameters": {"alpha": 1.0},
            "scale_numeric": True,
        },
        "positive_lpg_random_forest": {
            "task": "positive_lpg_amount",
            "estimator": RandomForestRegressor(**forest_parameters),
            "estimator_name": "RandomForestRegressor",
            "hyperparameters": forest_parameters.copy(),
            "scale_numeric": False,
        },
    }


def _comparison_to_baselines(
    candidate_metrics: dict[str, Any],
    baseline_metrics: dict[str, dict[str, Any]],
    metric_names: tuple[str, ...],
) -> dict[str, dict[str, float | None]]:
    comparisons = {}
    for baseline_name, baseline in baseline_metrics.items():
        comparisons[baseline_name] = {
            f"{metric}_delta_candidate_minus_baseline": (
                float(candidate_metrics[metric] - baseline[metric])
                if candidate_metrics.get(metric) is not None
                and baseline.get(metric) is not None
                else None
            )
            for metric in metric_names
        }
    return comparisons


def _package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for package in ("numpy", "pandas", "scikit-learn"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None
    return versions


def evaluate_candidate_models(
    data: pd.DataFrame,
    partitions: DataSplits,
    *,
    seed: int = 42,
    partition_name: str = "validation",
) -> dict[str, Any]:
    """Fit predeclared pipelines on train rows and score one held-out partition."""
    if partition_name not in {"validation", "test"}:
        raise ValueError("candidate evaluation partition must be validation or test")
    features = select_features(data)
    electricity = select_target(data, "electricity_kwh_per_month").to_numpy()
    lpg = select_target(data, "lpg_kg_per_month").to_numpy()
    train_indices = partitions.train
    evaluation_indices = getattr(partitions, partition_name)
    x_train = features.iloc[train_indices]
    x_evaluation = features.iloc[evaluation_indices]
    y_electricity_train = electricity[train_indices]
    y_electricity_evaluation = electricity[evaluation_indices]
    y_lpg_train = lpg[train_indices]
    y_lpg_evaluation = lpg[evaluation_indices]
    positive_train_mask = y_lpg_train > 0.0
    positive_evaluation_mask = y_lpg_evaluation > 0.0
    x_positive_train = x_train.iloc[np.flatnonzero(positive_train_mask)]
    y_positive_train = y_lpg_train[positive_train_mask]
    y_positive_evaluation = y_lpg_evaluation[positive_evaluation_mask]

    baseline_report = evaluate_partition_baselines(
        data, partitions, partition_name=partition_name
    )[partition_name]
    specs = _candidate_specs(seed)
    fitted: dict[str, Pipeline] = {}
    model_reports: dict[str, dict[str, Any]] = {}
    captured_warnings: dict[str, list[str]] = {}

    for name, spec in specs.items():
        task = spec["task"]
        if task == "electricity":
            fit_x, fit_y = x_train, y_electricity_train
        elif task == "lpg_use":
            fit_x, fit_y = x_train, (y_lpg_train > 0.0).astype(int)
        else:
            fit_x, fit_y = x_positive_train, y_positive_train

        if len(fit_y) == 0:
            model_reports[name] = {
                "model": spec["estimator_name"],
                "hyperparameters": spec["hyperparameters"],
                "status": "not_fit",
                "undefined_reason": "no_positive_lpg_records_in_training_partition",
                "fit_rows": 0,
                "warnings": [],
            }
            continue
        if (
            task == "lpg_use"
            and name.endswith("logistic_regression")
            and np.unique(fit_y).size < 2
        ):
            model_reports[name] = {
                "model": spec["estimator_name"],
                "hyperparameters": spec["hyperparameters"],
                "status": "not_fit",
                "undefined_reason": "logistic_regression_requires_both_training_classes",
                "fit_rows": len(fit_y),
                "warnings": [],
            }
            continue

        pipeline = _pipeline(spec["estimator"], scale_numeric=spec["scale_numeric"])
        with warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter("always")
            pipeline.fit(fit_x, fit_y)
        fitted[name] = pipeline
        captured_warnings[name] = [str(item.message) for item in observed]
        model_reports[name] = {
            "model": spec["estimator_name"],
            "hyperparameters": spec["hyperparameters"],
            "preprocessing": {
                "categorical_encoder": "OneHotEncoder(handle_unknown='ignore')",
                "numeric_features": list(NUMERIC_FEATURES),
                "categorical_features": list(CATEGORICAL_FEATURES),
                "numeric_scaling": "StandardScaler"
                if spec["scale_numeric"]
                else "none",
                "fit_scope": "training rows only",
            },
            "status": "fit",
            "fit_rows": len(fit_y),
            "warnings": captured_warnings[name],
        }

    electricity_models = {}
    for name in ("electricity_ridge", "electricity_random_forest"):
        report = model_reports[name]
        if name in fitted:
            prediction = fitted[name].predict(x_evaluation)
            metrics = _regression_metrics(
                y_electricity_evaluation, prediction, unit="kWh/month"
            )
            report["metrics"] = metrics
            report["baseline_comparison"] = _comparison_to_baselines(
                metrics,
                baseline_report["electricity"]["baselines"],
                ("mae", "rmse"),
            )
        electricity_models[name] = report

    lpg_use_models = {}
    for name in ("lpg_use_logistic_regression", "lpg_use_random_forest"):
        report = model_reports[name]
        if name in fitted:
            predictions = fitted[name].predict(x_evaluation).astype(bool)
            metrics = _classification_metrics(positive_evaluation_mask, predictions)
            report["metrics"] = metrics
            report["baseline_comparison"] = {
                metric: (
                    float(
                        metrics[metric]
                        - baseline_report["lpg_use"]["majority_class_baseline"][metric]
                    )
                    if metrics[metric] is not None
                    and baseline_report["lpg_use"]["majority_class_baseline"][metric]
                    is not None
                    else None
                )
                for metric in ("precision", "recall", "f1")
            }
        lpg_use_models[name] = report

    positive_amount_models = {}
    for name in ("positive_lpg_ridge", "positive_lpg_random_forest"):
        report = model_reports[name]
        if name in fitted:
            prediction = (
                fitted[name].predict(
                    x_evaluation.iloc[np.flatnonzero(positive_evaluation_mask)]
                )
                if y_positive_evaluation.size
                else np.asarray([], dtype=float)
            )
            metrics = _regression_metrics(
                y_positive_evaluation, prediction, unit="kg/month"
            )
            report["metrics"] = metrics
            report[f"eligible_{partition_name}_rows"] = int(y_positive_evaluation.size)
            report["baseline_comparison"] = _comparison_to_baselines(
                metrics,
                baseline_report["positive_lpg_amount"]["baselines"],
                ("mae", "rmse"),
            )
        positive_amount_models[name] = report

    two_stage = {}
    pairings = (
        ("logistic_plus_ridge", "lpg_use_logistic_regression", "positive_lpg_ridge"),
        (
            "random_forest_classifier_plus_regressor",
            "lpg_use_random_forest",
            "positive_lpg_random_forest",
        ),
    )
    unconditional_baselines = {}
    for baseline_name, value in (
        ("training_mean", float(np.mean(y_lpg_train))),
        ("training_median", float(np.median(y_lpg_train))),
    ):
        unconditional_baselines[baseline_name] = _regression_metrics(
            y_lpg_evaluation, value, unit="kg/month"
        )
    for pairing_name, classifier_name, amount_name in pairings:
        if classifier_name not in fitted or amount_name not in fitted:
            two_stage[pairing_name] = {
                "status": "not_evaluated",
                "undefined_reason": "required_stage_model_was_not_fit",
            }
            continue
        class_predictions = fitted[classifier_name].predict(x_evaluation).astype(bool)
        amount_predictions = fitted[amount_name].predict(x_evaluation)
        combined_predictions = np.where(class_predictions, amount_predictions, 0.0)
        end_to_end_metrics = _regression_metrics(
            y_lpg_evaluation, combined_predictions, unit="kg/month"
        )
        two_stage[pairing_name] = {
            "status": "evaluated",
            "use_classification_metrics": model_reports[classifier_name]["metrics"],
            "positive_amount_metrics_on_true_users": model_reports[amount_name].get(
                "metrics",
                {
                    "n": 0,
                    "mae": None,
                    "rmse": None,
                    "unit": "kg/month",
                    "undefined_reason": f"no_positive_{partition_name}_records",
                },
            ),
            "unconditional_amount_metrics": end_to_end_metrics,
            "unconditional_baselines": unconditional_baselines,
            "unconditional_baseline_comparison": _comparison_to_baselines(
                end_to_end_metrics, unconditional_baselines, ("mae", "rmse")
            ),
            "combination_rule": "predict the amount only when the use classifier predicts class 1; otherwise predict 0 kg/month",
        }

    return {
        f"{partition_name}_rows": len(evaluation_indices),
        "training_rows": len(train_indices),
        "training_positive_lpg_rows": int(positive_train_mask.sum()),
        "test_partition_scored": partition_name == "test",
        "electricity": {
            "target": "electricity_kwh_per_month",
            "unit": "kWh/month",
            "models": electricity_models,
        },
        "lpg_use": {
            "target": "lpg_kg_per_month > 0",
            "positive_class": 1,
            f"{partition_name}_positive_count": int(positive_evaluation_mask.sum()),
            f"{partition_name}_zero_use_count": int((~positive_evaluation_mask).sum()),
            "models": lpg_use_models,
        },
        "positive_lpg_amount": {
            "target": "lpg_kg_per_month",
            "unit": "kg/month",
            f"eligible_{partition_name}_rows": int(y_positive_evaluation.size),
            "models": positive_amount_models,
        },
        "two_stage_lpg": two_stage,
        "model_configurations": {
            name: {
                "model": spec["estimator_name"],
                "hyperparameters": spec["hyperparameters"],
            }
            for name, spec in specs.items()
        },
        "package_versions": _package_versions(),
        "warnings": {
            name: messages for name, messages in captured_warnings.items() if messages
        },
    }


def _experiment_context(
    data: pd.DataFrame, partitions: DataSplits, split_seed: int
) -> dict[str, Any]:
    lpg = select_target(data, "lpg_kg_per_month").to_numpy()
    partition_summary = {}
    for name, indices in partitions.as_dict().items():
        positive_count = int(np.sum(lpg[indices] > 0.0))
        partition_summary[name] = {
            "rows": int(indices.size),
            "positive_lpg_use": positive_count,
            "zero_lpg_use": int(indices.size - positive_count),
        }
    return {
        "schema_version": "v1",
        "split_seed": split_seed,
        "split_method": "seeded LPG-use stratification with fixed 70/15/15 partition sizes",
        "split_limitations": (
            "This random split evaluates held-out records from the same synthetic generation process; "
            "it does not test generalization to real households."
        ),
        "row_count": len(data),
        "features": list(FEATURE_FIELDS),
        "targets": list(TARGET_FIELDS),
        "excluded_fields": list(NON_FEATURE_FIELDS),
        "partitions": partition_summary,
    }


def run_baseline_experiment(
    data: pd.DataFrame, *, split_seed: int = 42
) -> dict[str, Any]:
    """Build reproducible splits and validation-only baseline results."""
    partitions = split_indices(data, seed=split_seed)
    return {
        **_experiment_context(data, partitions, split_seed),
        **evaluate_validation_baselines(data, partitions),
    }


def run_candidate_comparison(
    data: pd.DataFrame, *, split_seed: int = 42
) -> dict[str, Any]:
    """Compare predeclared ML candidates and baselines on the same validation split."""
    partitions = split_indices(data, seed=split_seed)
    return {
        **_experiment_context(data, partitions, split_seed),
        **evaluate_validation_baselines(data, partitions),
        "candidate_models": evaluate_candidate_models(
            data, partitions, seed=split_seed
        ),
    }


def run_final_test_evaluation(
    data: pd.DataFrame, *, split_seed: int = 42
) -> dict[str, Any]:
    """Evaluate the frozen candidate set and training-derived baselines on test only."""
    partitions = split_indices(data, seed=split_seed)
    return {
        **_experiment_context(data, partitions, split_seed),
        "synthetic_data_notice": (
            "All findings are synthetic-data results from the documented generator; "
            "they do not establish real-world accuracy or representativeness."
        ),
        "baseline_test_metrics": evaluate_partition_baselines(
            data, partitions, partition_name="test"
        )["test"],
        "final_test_evaluation": evaluate_candidate_models(
            data, partitions, seed=split_seed, partition_name="test"
        ),
        "model_selection_notice": (
            "The six predeclared C3.3.2 configurations are treated as a frozen finalist set. "
            "No configuration was tuned or selected using test results."
        ),
    }
