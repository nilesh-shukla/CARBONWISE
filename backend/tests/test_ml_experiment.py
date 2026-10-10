"""Tests for leakage-safe synthetic experiment preparation and baselines."""

import csv
import json
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from app.ml.experiment import (
    CATEGORICAL_FEATURES,
    FEATURE_FIELDS,
    NON_FEATURE_FIELDS,
    DatasetValidationError,
    DataSplits,
    _classification_metrics,
    evaluate_candidate_models,
    evaluate_validation_baselines,
    load_dataset,
    run_baseline_experiment,
    run_candidate_comparison,
    run_final_test_evaluation,
    select_features,
    split_indices,
)
from app.schemas.dataset import MODEL_INPUT_FIELDS, SyntheticHouseholdRecord
from scripts.run_ml_baselines import main as run_cli


def _record(index: int, lpg: float) -> dict[str, object]:
    values: dict[str, object] = {
        "record_id": str(uuid4()),
        "schema_version": "v1",
        "generation_run_id": str(uuid4()),
        "random_seed": 42,
        "is_synthetic": True,
        "household_size": 4,
        "dwelling_type": "apartment",
        "settlement_type": "urban",
        "state": "IN-MH",
        "monthly_household_income_band": "25k-50k",
        "daytime_occupancy_hours": 8.0,
        "cooking_fuel_primary": "lpg" if lpg > 0 else "electricity",
        "cooking_fuel_secondary": "none",
        "num_working_members": 2,
        "climate_zone": "composite",
        "has_air_conditioner": False,
        "has_refrigerator": True,
        "has_washing_machine": False,
        "has_personal_vehicle": False,
        "electricity_kwh_per_month": 100.0 + index % 1_000,
        "lpg_kg_per_month": lpg,
        "total_emissions_kg_co2": (100.0 + index % 1_000) * 0.716 + lpg * 2.98463,
        "direct_emissions_kg_co2": lpg * 2.98463,
        "indirect_emissions_kg_co2": (100.0 + index % 1_000) * 0.716,
    }
    return SyntheticHouseholdRecord.model_validate(values).model_dump(mode="python")


def _data(zero_count: int = 20, positive_count: int = 20) -> pd.DataFrame:
    rows = [_record(index, 0.0) for index in range(zero_count)]
    rows.extend(
        _record(zero_count + index, 5.0 + index) for index in range(positive_count)
    )
    return pd.DataFrame.from_records(rows, columns=SyntheticHouseholdRecord.FIELD_ORDER)


def _write_csv(path, rows: list[dict[str, object]], header=None) -> None:
    columns = header or list(SyntheticHouseholdRecord.FIELD_ORDER)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def test_feature_allowlist_excludes_targets_and_metadata() -> None:
    data = _data()
    features = select_features(data)
    assert list(FEATURE_FIELDS) == MODEL_INPUT_FIELDS
    assert list(features.columns) == MODEL_INPUT_FIELDS
    assert not set(features.columns).intersection(NON_FEATURE_FIELDS)
    assert "electricity_kwh_per_month" not in features
    assert "lpg_kg_per_month" not in features
    assert "total_emissions_kg_co2" not in features
    assert "record_id" not in features


def test_load_dataset_validates_complete_rows(tmp_path) -> None:
    path = tmp_path / "valid.csv"
    _write_csv(path, [_record(0, 0.0), _record(1, 5.0)])
    loaded = load_dataset(path)
    assert len(loaded) == 2
    assert set(loaded["schema_version"]) == {"v1"}


def test_load_dataset_rejects_missing_and_duplicate_columns(tmp_path) -> None:
    row = _record(0, 0.0)
    missing_path = tmp_path / "missing.csv"
    missing_columns = [
        name for name in SyntheticHouseholdRecord.FIELD_ORDER if name != "state"
    ]
    _write_csv(
        missing_path,
        [{key: value for key, value in row.items() if key != "state"}],
        missing_columns,
    )
    with pytest.raises(DatasetValidationError, match="missing columns: state"):
        load_dataset(missing_path)

    duplicate_path = tmp_path / "duplicate.csv"
    duplicate_columns = [*SyntheticHouseholdRecord.FIELD_ORDER, "state"]
    duplicate_row = {**row, "state": row["state"]}
    _write_csv(duplicate_path, [duplicate_row], duplicate_columns)
    with pytest.raises(DatasetValidationError, match="duplicate column names: state"):
        load_dataset(duplicate_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "v2"),
        ("electricity_kwh_per_month", "nan"),
        ("electricity_kwh_per_month", "0"),
        ("lpg_kg_per_month", "-1"),
        ("lpg_kg_per_month", "inf"),
    ],
)
def test_load_dataset_rejects_invalid_schema_or_targets(tmp_path, field, value) -> None:
    row = _record(0, 0.0)
    row[field] = value
    path = tmp_path / "invalid.csv"
    _write_csv(path, [row])
    with pytest.raises(DatasetValidationError, match="Invalid record at CSV row 2"):
        load_dataset(path)


def test_split_is_reproducible_exact_and_non_overlapping() -> None:
    data = _data()
    first = split_indices(data, seed=73)
    second = split_indices(data, seed=73)
    for name in ("train", "validation", "test"):
        np.testing.assert_array_equal(getattr(first, name), getattr(second, name))
    assert (len(first.train), len(first.validation), len(first.test)) == (28, 6, 6)
    sets = [set(first.train), set(first.validation), set(first.test)]
    assert not (sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])
    assert set.union(*sets) == set(range(len(data)))


def test_split_preserves_both_lpg_classes_when_possible() -> None:
    data = _data(zero_count=12, positive_count=12)
    partitions = split_indices(data, seed=7)
    lpg = data["lpg_kg_per_month"].to_numpy()
    for indices in partitions.as_dict().values():
        assert np.any(lpg[indices] == 0.0)
        assert np.any(lpg[indices] > 0.0)


def test_small_split_reports_class_absence_when_unavoidable() -> None:
    data = _data(zero_count=8, positive_count=1)
    partitions = split_indices(data, seed=2)
    lpg = data["lpg_kg_per_month"].to_numpy()
    assert sum(np.any(lpg[index] > 0.0) for index in partitions.as_dict().values()) == 1


def test_baselines_use_training_values_and_report_units() -> None:
    data = _data(zero_count=20, positive_count=20)
    partitions = split_indices(data, seed=13)
    report = evaluate_validation_baselines(data, partitions)["validation"]

    electricity_train = data.iloc[partitions.train]["electricity_kwh_per_month"]
    electricity_validation = data.iloc[partitions.validation][
        "electricity_kwh_per_month"
    ]
    mean = float(electricity_train.mean())
    expected_mae = float(np.mean(np.abs(electricity_validation.to_numpy() - mean)))
    expected_rmse = float(
        np.sqrt(np.mean(np.square(electricity_validation.to_numpy() - mean)))
    )
    assert (
        report["electricity"]["baselines"]["mean"]["prediction_kwh_per_month"] == mean
    )
    assert report["electricity"]["baselines"]["mean"]["mae"] == pytest.approx(
        expected_mae
    )
    assert report["electricity"]["baselines"]["mean"]["rmse"] == pytest.approx(
        expected_rmse
    )
    assert report["electricity"]["baselines"]["mean"]["unit"] == "kWh/month"

    lpg_train = data.iloc[partitions.train]["lpg_kg_per_month"]
    positive_train = lpg_train[lpg_train > 0]
    assert report["positive_lpg_amount"]["baselines"]["median"][
        "prediction_kg_per_month"
    ] == float(positive_train.median())
    assert report["positive_lpg_amount"]["baselines"]["median"]["unit"] == "kg/month"


def test_empty_positive_lpg_validation_is_explicitly_undefined() -> None:
    data = _data(zero_count=20, positive_count=10)
    partitions = DataSplits(
        train=np.asarray([20, 21, 22, 23, 24, 25]),
        validation=np.asarray([0, 1, 2, 3]),
        test=np.asarray(
            [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 26, 27, 28, 29]
        ),
    )
    report = evaluate_validation_baselines(data, partitions)["validation"]
    amount = report["positive_lpg_amount"]
    assert amount["validation_positive_count"] == 0
    assert amount["baselines"]["mean"]["n"] == 0
    assert amount["baselines"]["mean"]["mae"] is None
    assert amount["baselines"]["mean"]["undefined_reason"] == "no_evaluation_records"


def test_majority_class_baseline_and_explicit_undefined_metrics() -> None:
    data = _data(zero_count=30, positive_count=0)
    partitions = DataSplits(
        train=np.arange(0, 20),
        validation=np.arange(20, 25),
        test=np.arange(25, 30),
    )
    result = evaluate_validation_baselines(data, partitions)["validation"]["lpg_use"]
    baseline = result["majority_class_baseline"]
    assert baseline["predicted_positive_class"] is False
    assert baseline["precision"] is None
    assert baseline["recall"] is None
    assert baseline["f1"] is None
    assert baseline["undefined_metrics"] == ["precision", "recall", "f1"]


def test_classification_metrics_for_majority_positive_baseline() -> None:
    data = _data(zero_count=30, positive_count=40)
    partitions = DataSplits(
        train=np.asarray([*range(10), *range(30, 60)]),
        validation=np.asarray([*range(10, 20), *range(60, 70)]),
        test=np.asarray([*range(20, 30)]),
    )
    baseline = evaluate_validation_baselines(data, partitions)["validation"]["lpg_use"][
        "majority_class_baseline"
    ]
    assert baseline["predicted_positive_class"] is True
    assert baseline["precision"] == pytest.approx(0.5)
    assert baseline["recall"] == pytest.approx(1.0)
    assert baseline["f1"] == pytest.approx(2 / 3)
    assert baseline["undefined_metrics"] == []


def test_experiment_reports_exact_default_partition_sizes() -> None:
    report = run_baseline_experiment(
        _data(zero_count=50, positive_count=50), split_seed=42
    )
    assert report["partitions"]["train"]["rows"] == 70
    assert report["partitions"]["validation"]["rows"] == 15
    assert report["partitions"]["test"]["rows"] == 15


def test_candidate_models_fit_preprocessing_on_training_rows_only(monkeypatch) -> None:
    from sklearn.pipeline import Pipeline

    data = _data(zero_count=20, positive_count=20)
    data.loc[14:19, "state"] = "IN-AP"
    data.loc[36:39, "state"] = "IN-BR"
    partitions = DataSplits(
        train=np.asarray([*range(14), *range(20, 30)]),
        validation=np.asarray([*range(14, 20), *range(30, 36)]),
        test=np.asarray([*range(36, 40)]),
    )
    original_fit = Pipeline.fit
    fit_calls = []
    learned_state_categories = []

    def spy_fit(self, X, y=None, **params):
        fit_calls.append((X.index.tolist(), np.asarray(y).tolist()))
        result = original_fit(self, X, y, **params)
        categorical = self.named_steps["preprocess"].named_transformers_["categorical"]
        state_position = CATEGORICAL_FEATURES.index("state")
        learned_state_categories.append(
            categorical.categories_[state_position].tolist()
        )
        return result

    monkeypatch.setattr(Pipeline, "fit", spy_fit)
    result = evaluate_candidate_models(data, partitions, seed=19)

    train_positions = set(partitions.train.tolist())
    assert len(fit_calls) == 6
    assert all(
        set(row_positions).issubset(train_positions) for row_positions, _ in fit_calls
    )
    assert [len(row_positions) for row_positions, _ in fit_calls] == [
        24,
        24,
        24,
        24,
        10,
        10,
    ]
    assert all(categories == ["IN-MH"] for categories in learned_state_categories)
    assert result["training_rows"] == 24
    assert result["training_positive_lpg_rows"] == 10
    assert result["test_partition_scored"] is False
    assert (
        result["positive_lpg_amount"]["models"]["positive_lpg_ridge"]["fit_rows"] == 10
    )


def test_candidate_classification_metrics_labels_and_confusion_matrix() -> None:
    metrics = _classification_metrics(
        np.asarray([True, True, False, False]),
        np.asarray([True, False, True, False]),
    )
    assert metrics["positive_count"] == 2
    assert metrics["zero_use_count"] == 2
    assert metrics["precision"] == pytest.approx(0.5)
    assert metrics["recall"] == pytest.approx(0.5)
    assert metrics["f1"] == pytest.approx(0.5)
    assert metrics["confusion_matrix"]["labels"] == [0, 1]
    assert metrics["confusion_matrix"]["rows_actual_columns_predicted"] == [
        [1, 1],
        [1, 1],
    ]


def test_candidate_comparison_is_reproducible_and_does_not_score_test() -> None:
    data = _data(zero_count=30, positive_count=30)
    first = run_candidate_comparison(data, split_seed=23)
    second = run_candidate_comparison(data, split_seed=23)
    assert first["partitions"] == second["partitions"]
    assert (
        first["candidate_models"]["model_configurations"]
        == second["candidate_models"]["model_configurations"]
    )
    assert (
        first["candidate_models"]["electricity"]
        == second["candidate_models"]["electricity"]
    )
    assert first["candidate_models"]["test_partition_scored"] is False
    assert "test_metrics" not in first["candidate_models"]


def test_candidate_cli_emits_json_and_safe_output_behavior(tmp_path, capsys) -> None:
    dataset_path = tmp_path / "records.csv"
    _write_csv(
        dataset_path,
        [_record(index, 0.0 if index < 20 else 5.0 + index) for index in range(40)],
    )
    exit_code = run_cli(
        ["--dataset", str(dataset_path), "--split-seed", "31", "--compare-models"]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["dataset"]["rows"] == 40
    assert payload["split_seed"] == 31
    assert "candidate_models" in payload

    result_path = tmp_path / "results.json"
    assert (
        run_cli(
            [
                "--dataset",
                str(dataset_path),
                "--compare-models",
                "--output",
                str(result_path),
            ]
        )
        == 0
    )
    saved = json.loads(result_path.read_text(encoding="utf-8"))
    assert saved["dataset"]["path"] == str(dataset_path.resolve())

    previous = result_path.read_text(encoding="utf-8")
    assert (
        run_cli(
            [
                "--dataset",
                str(dataset_path),
                "--compare-models",
                "--output",
                str(result_path),
            ]
        )
        == 1
    )
    assert result_path.read_text(encoding="utf-8") == previous

    source_before = dataset_path.read_bytes()
    assert run_cli(["--dataset", str(dataset_path), "--output", str(dataset_path)]) == 1
    assert dataset_path.read_bytes() == source_before


def test_final_test_evaluation_scores_only_test_and_keeps_frozen_configs(
    monkeypatch,
) -> None:
    from sklearn.pipeline import Pipeline

    data = _data(zero_count=30, positive_count=30)
    partitions = split_indices(data, seed=47)
    test_states = set(partitions.test.tolist())
    data.loc[list(test_states), "state"] = "TEST-ONLY-STATE"
    original_fit = Pipeline.fit
    original_predict = Pipeline.predict
    fit_indices = []
    prediction_indices = []
    fitted_state_categories = []

    def spy_fit(self, X, y=None, **params):
        fit_indices.append(X.index.tolist())
        result = original_fit(self, X, y, **params)
        categorical = self.named_steps["preprocess"].named_transformers_["categorical"]
        state_position = CATEGORICAL_FEATURES.index("state")
        fitted_state_categories.append(categorical.categories_[state_position].tolist())
        return result

    def spy_predict(self, X, **params):
        prediction_indices.append(X.index.tolist())
        return original_predict(self, X, **params)

    monkeypatch.setattr(Pipeline, "fit", spy_fit)
    monkeypatch.setattr(Pipeline, "predict", spy_predict)
    validation_comparison = run_candidate_comparison(data, split_seed=47)
    fit_indices.clear()
    prediction_indices.clear()
    report = run_final_test_evaluation(data, split_seed=47)

    final = report["final_test_evaluation"]
    assert report["split_seed"] == 47
    assert final["test_partition_scored"] is True
    assert final["test_rows"] == len(partitions.test)
    assert final["training_rows"] == len(partitions.train)
    assert (
        final["model_configurations"]
        == validation_comparison["candidate_models"]["model_configurations"]
    )
    assert len(fit_indices) == 6
    assert all(
        set(indices) == set(partitions.train.tolist()) for indices in fit_indices[:4]
    )
    assert all(
        set(indices)
        == set(partitions.train.tolist())
        & set(np.flatnonzero(data["lpg_kg_per_month"].to_numpy() > 0))
        for indices in fit_indices[4:]
    )
    assert prediction_indices
    assert all(set(indices).issubset(test_states) for indices in prediction_indices)
    assert all("TEST-ONLY-STATE" not in values for values in fitted_state_categories)
    assert final["electricity"]["models"]["electricity_ridge"]["metrics"]["n"] == len(
        partitions.test
    )
    assert final["lpg_use"]["models"]["lpg_use_logistic_regression"]["metrics"][
        "confusion_matrix"
    ]["labels"] == [0, 1]
    assert final["positive_lpg_amount"]["eligible_test_rows"] == int(
        (data.iloc[partitions.test]["lpg_kg_per_month"] > 0).sum()
    )
    assert final["two_stage_lpg"]["logistic_plus_ridge"][
        "unconditional_amount_metrics"
    ]["n"] == len(partitions.test)
    assert report["baseline_test_metrics"]["electricity"]["baselines"]["mean"][
        "n"
    ] == len(partitions.test)
    assert "real-world accuracy" in report["synthetic_data_notice"]


def test_final_test_cli_emits_test_report(tmp_path, capsys) -> None:
    dataset_path = tmp_path / "records.csv"
    _write_csv(
        dataset_path,
        [
            _record(index, 0.0 if index < 30 else 5.0 + index % 40)
            for index in range(60)
        ],
    )
    assert (
        run_cli(["--dataset", str(dataset_path), "--split-seed", "37", "--final-test"])
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["split_seed"] == 37
    assert payload["final_test_evaluation"]["test_partition_scored"] is True
    assert (
        payload["baseline_test_metrics"]["lpg_use"]["majority_class_baseline"]["n"]
        == payload["partitions"]["test"]["rows"]
    )
