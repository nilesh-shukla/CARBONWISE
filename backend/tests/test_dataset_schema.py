"""Focused schema and synthetic dataset generator tests."""

import csv
import math
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from pydantic import ValidationError

from app.schemas.calculate import CalculationRequest
from app.schemas.dataset import MODEL_INPUT_FIELDS, SyntheticHouseholdRecord
from app.services.calculator import CarbonCalculatorService
from scripts.generate_synthetic_data import (
    DatasetGenerationError,
    GenerationConfig,
    _sample_electricity,
    _sample_lpg,
    _truncated_lognormal,
    generate_dataset,
    iter_records,
)


def valid_record_values(**overrides: object) -> dict[str, object]:
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
        "cooking_fuel_primary": "lpg",
        "cooking_fuel_secondary": "none",
        "num_working_members": 2,
        "climate_zone": "composite",
        "has_air_conditioner": False,
        "has_refrigerator": True,
        "has_washing_machine": False,
        "has_personal_vehicle": False,
        "electricity_kwh_per_month": 100.0,
        "lpg_kg_per_month": 10.0,
        "total_emissions_kg_co2": 101.0,
        "direct_emissions_kg_co2": 29.8463,
        "indirect_emissions_kg_co2": 71.6,
    }
    values.update(overrides)
    return values


def test_schema_has_24_fields_and_14_model_inputs() -> None:
    assert len(SyntheticHouseholdRecord.FIELD_ORDER) == 24
    assert MODEL_INPUT_FIELDS == [
        "household_size",
        "dwelling_type",
        "settlement_type",
        "state",
        "monthly_household_income_band",
        "daytime_occupancy_hours",
        "cooking_fuel_primary",
        "cooking_fuel_secondary",
        "num_working_members",
        "climate_zone",
        "has_air_conditioner",
        "has_refrigerator",
        "has_washing_machine",
        "has_personal_vehicle",
    ]
    assert len(MODEL_INPUT_FIELDS) == 14
    assert set(MODEL_INPUT_FIELDS).issubset(SyntheticHouseholdRecord.model_fields)
    assert not set(MODEL_INPUT_FIELDS).intersection(
        {
            "record_id",
            "generation_run_id",
            "random_seed",
            "electricity_kwh_per_month",
            "lpg_kg_per_month",
            "total_emissions_kg_co2",
            "direct_emissions_kg_co2",
            "indirect_emissions_kg_co2",
        }
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"household_size": 0},
        {"household_size": 11},
        {"num_working_members": 5},
        {"cooking_fuel_secondary": "lpg"},
        {"state": "IN-DN"},
        {"electricity_kwh_per_month": float("nan")},
        {"lpg_kg_per_month": 0.25},
    ],
)
def test_schema_rejects_invalid_record_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SyntheticHouseholdRecord.model_validate(valid_record_values(**overrides))


def test_none_primary_with_secondary_lpg_is_valid() -> None:
    record = SyntheticHouseholdRecord.model_validate(
        valid_record_values(cooking_fuel_primary="none", cooking_fuel_secondary="lpg")
    )
    assert record.cooking_fuel_primary == "none"
    assert record.cooking_fuel_secondary == "lpg"


def test_truncated_lognormal_is_seeded_and_within_bounds() -> None:
    first_rng = np.random.default_rng(91)
    second_rng = np.random.default_rng(91)
    first = [
        _truncated_lognormal(
            first_rng, mu=5.0, sigma=0.6, low=10.0, high=2000.0, max_draws=100_000
        )
        for _ in range(100)
    ]
    second = [
        _truncated_lognormal(
            second_rng, mu=5.0, sigma=0.6, low=10.0, high=2000.0, max_draws=100_000
        )
        for _ in range(100)
    ]
    assert first == second
    assert all(10.0 <= value <= 2000.0 for value in first)
    assert all(value not in (10.0, 2000.0) for value in first)


def test_electricity_and_lpg_generation_follow_documented_cases() -> None:
    config = GenerationConfig(n_records=1)
    base = {
        "household_size": 2,
        "daytime_occupancy_hours": 10.0,
        "climate_zone": "composite",
        "settlement_type": "urban",
        "has_air_conditioner": False,
        "has_refrigerator": True,
        "has_washing_machine": False,
    }
    elec_a = _sample_electricity(np.random.default_rng(7), base, config)
    elec_b = _sample_electricity(np.random.default_rng(7), base, config)
    assert elec_a == elec_b
    assert 10.0 <= elec_a <= 2000.0

    primary = {**base, "cooking_fuel_primary": "lpg", "cooking_fuel_secondary": "none"}
    secondary = {
        **base,
        "cooking_fuel_primary": "none",
        "cooking_fuel_secondary": "lpg",
    }
    no_lpg = {
        **base,
        "cooking_fuel_primary": "biomass",
        "cooking_fuel_secondary": "none",
    }
    primary_value = _sample_lpg(np.random.default_rng(1), primary, config)
    secondary_value = _sample_lpg(np.random.default_rng(1), secondary, config)
    assert 0.5 <= primary_value <= 60.0
    assert 0.5 <= secondary_value <= 60.0
    assert primary_value > secondary_value
    assert _sample_lpg(np.random.default_rng(1), no_lpg, config) == 0.0


def test_generator_csv_schema_targets_and_seeded_values(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "sample.csv"
    config = GenerationConfig(n_records=12, random_seed=42, output_path=output)
    first_records = list(iter_records(config))
    second_records = list(iter_records(config))
    assert len(first_records) == len(second_records) == 12
    assert first_records[0].record_id != second_records[0].record_id
    assert first_records[0].generation_run_id != second_records[0].generation_run_id

    for first, second in zip(first_records, second_records, strict=True):
        first_values = first.model_dump()
        second_values = second.model_dump()
        first_values.pop("record_id")
        first_values.pop("generation_run_id")
        second_values.pop("record_id")
        second_values.pop("generation_run_id")
        assert first_values == second_values

    assert len({row.generation_run_id for row in first_records}) == 1
    assert len({row.record_id for row in first_records}) == 12
    assert {row.random_seed for row in first_records} == {42}

    service = CarbonCalculatorService()
    for row in first_records:
        response = service.calculate(
            CalculationRequest(
                electricity_kwh_per_month=row.electricity_kwh_per_month,
                lpg_kg_per_month=row.lpg_kg_per_month,
            )
        )
        assert row.total_emissions_kg_co2 == response.total_emissions_kg_co2
        assert row.direct_emissions_kg_co2 == response.direct_emissions_kg_co2
        assert row.indirect_emissions_kg_co2 == response.indirect_emissions_kg_co2
        assert all(
            math.isfinite(value)
            for value in (
                row.electricity_kwh_per_month,
                row.lpg_kg_per_month,
                row.total_emissions_kg_co2,
                row.direct_emissions_kg_co2,
                row.indirect_emissions_kg_co2,
            )
        )

    assert generate_dataset(config) == output
    with output.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == SyntheticHouseholdRecord.FIELD_ORDER
        rows = list(reader)
    assert len(rows) == 12
    assert len({row["generation_run_id"] for row in rows}) == 1


def test_failed_generation_preserves_existing_file_and_cleans_temp(
    tmp_path: Path,
) -> None:
    output = tmp_path / "existing.csv"
    output.write_text("previous complete data\n", encoding="utf-8")

    class FailingCalculator:
        def calculate(self, request: CalculationRequest) -> object:
            raise RuntimeError("test calculation failure")

    config = GenerationConfig(n_records=2, output_path=output)
    with pytest.raises(DatasetGenerationError, match="Could not complete dataset"):
        generate_dataset(config, calculator=FailingCalculator())  # type: ignore[arg-type]

    assert output.read_text(encoding="utf-8") == "previous complete data\n"
    assert list(tmp_path.glob(".existing.csv.*.tmp")) == []
