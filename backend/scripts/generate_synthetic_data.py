"""Generate reproducible synthetic household records for CARBONWISE schema v1.

The seeded NumPy generator makes sampled descriptors, intermediates, and calculator
targets repeatable. UUID v4 values are intentionally generated independently, so
record IDs and the per-run ID differ between invocations and CSV bytes are not
identical even when the seed and configuration match.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import numpy as np

# Support both `python backend/scripts/...` from the repository root and
# `python scripts/...` from the backend directory without requiring installation.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.schemas.calculate import CalculationRequest
from app.schemas.dataset import (
    CLIMATE_ZONES,
    DWELLING_TYPES,
    INCOME_BANDS,
    PRIMARY_FUELS,
    SECONDARY_FUELS,
    SETTLEMENT_TYPES,
    STATE_CODES,
    SyntheticHouseholdRecord,
)
from app.services.calculator import CarbonCalculatorService

DEFAULT_OUTPUT_PATH = BACKEND_ROOT / "data" / "synthetic" / "household_records_v1.csv"


@dataclass(frozen=True)
class GenerationConfig:
    """Configurable v1 generation settings, including documented defaults."""

    n_records: int = 10_000
    random_seed: int = 42
    output_path: Path = DEFAULT_OUTPUT_PATH
    schema_version: str = "v1"

    electricity_mu: float = 5.0
    electricity_sigma: float = 0.6
    electricity_low: float = 10.0
    electricity_high: float = 2000.0
    electricity_ac_multiplier: float = 1.8
    electricity_refrigerator_multiplier: float = 1.15
    electricity_washing_machine_multiplier: float = 1.10
    electricity_household_size_increment: float = 0.05
    electricity_occupancy_hour_increment: float = 0.02
    electricity_climate_multipliers: tuple[tuple[str, float], ...] = (
        ("hot_dry", 1.3),
        ("warm_humid", 1.2),
        ("composite", 1.0),
        ("temperate", 0.9),
        ("cold", 0.85),
    )
    electricity_settlement_scalars: tuple[tuple[str, float], ...] = (
        ("urban", 1.0),
        ("peri_urban", 0.85),
        ("rural", 0.70),
    )
    lpg_mu_primary: float = 2.7
    lpg_mu_secondary: float = 1.6
    lpg_sigma: float = 0.5
    lpg_low: float = 0.5
    lpg_high: float = 60.0
    lpg_household_size_increment: float = 0.08
    secondary_none_probability: float = 0.70
    state_codes: tuple[str, ...] = field(default_factory=lambda: STATE_CODES)
    max_rejection_draws: int = 100_000

    def __post_init__(self) -> None:
        if self.n_records < 1:
            raise ValueError("n_records must be at least 1")
        if self.random_seed < 0:
            raise ValueError("random_seed must be non-negative")
        if self.schema_version != "v1":
            raise ValueError("only schema_version 'v1' is supported")
        numeric_values = (
            self.electricity_mu,
            self.electricity_sigma,
            self.electricity_low,
            self.electricity_high,
            self.electricity_ac_multiplier,
            self.electricity_refrigerator_multiplier,
            self.electricity_washing_machine_multiplier,
            self.electricity_household_size_increment,
            self.electricity_occupancy_hour_increment,
            self.lpg_mu_primary,
            self.lpg_mu_secondary,
            self.lpg_sigma,
            self.lpg_low,
            self.lpg_high,
            self.lpg_household_size_increment,
            self.secondary_none_probability,
            *(value for _, value in self.electricity_climate_multipliers),
            *(value for _, value in self.electricity_settlement_scalars),
        )
        if not all(math.isfinite(value) for value in numeric_values):
            raise ValueError("generation configuration values must be finite")
        if self.electricity_sigma <= 0 or self.lpg_sigma <= 0:
            raise ValueError("lognormal sigma values must be positive")
        if not 0 < self.electricity_low < self.electricity_high:
            raise ValueError("electricity bounds must satisfy 0 < low < high")
        if not 0 < self.lpg_low < self.lpg_high:
            raise ValueError("LPG bounds must satisfy 0 < low < high")
        if any(
            value <= 0
            for _, value in (
                *self.electricity_climate_multipliers,
                *self.electricity_settlement_scalars,
            )
        ):
            raise ValueError(
                "electricity multipliers and settlement scalars must be positive"
            )
        if {name for name, _ in self.electricity_climate_multipliers} != set(
            CLIMATE_ZONES
        ):
            raise ValueError(
                "electricity_climate_multipliers must define every climate zone"
            )
        if {name for name, _ in self.electricity_settlement_scalars} != set(
            SETTLEMENT_TYPES
        ):
            raise ValueError(
                "electricity_settlement_scalars must define every settlement type"
            )
        if not 0.0 <= self.secondary_none_probability <= 1.0:
            raise ValueError("secondary_none_probability must be between 0 and 1")
        if not self.state_codes or any(
            code not in STATE_CODES for code in self.state_codes
        ):
            raise ValueError("state_codes must contain valid ISO 3166-2:IN codes")
        if self.max_rejection_draws < 1:
            raise ValueError("max_rejection_draws must be at least 1")


class DatasetGenerationError(RuntimeError):
    """Raised when a complete, validated dataset cannot be written."""


def _truncated_lognormal(
    rng: np.random.Generator,
    *,
    mu: float,
    sigma: float,
    low: float,
    high: float,
    max_draws: int,
) -> float:
    """Sample a lognormal by rejection, preserving the true conditional distribution."""
    for _ in range(max_draws):
        value = float(rng.lognormal(mean=mu, sigma=sigma))
        if low <= value <= high:
            return value
    raise DatasetGenerationError(
        f"Truncated LogNormal rejection sampling accepted no value in {max_draws} draws; "
        "check the configured mean, sigma, and bounds."
    )


def _sample_descriptors(
    rng: np.random.Generator, config: GenerationConfig
) -> dict[str, object]:
    household_size = int(rng.integers(1, 11))
    primary = str(rng.choice(PRIMARY_FUELS))

    # The schema has no calibrated fuel weights. This explicit 70% default keeps
    # secondary='none' as the majority case described by U4; the other valid
    # secondary fuels share the remaining probability uniformly.
    if rng.random() < config.secondary_none_probability:
        secondary = "none"
    else:
        alternatives = tuple(
            fuel for fuel in SECONDARY_FUELS if fuel != primary and fuel != "none"
        )
        if primary == "none":
            alternatives = tuple(fuel for fuel in SECONDARY_FUELS if fuel != "none")
        secondary = str(rng.choice(alternatives))

    return {
        "household_size": household_size,
        "dwelling_type": str(rng.choice(DWELLING_TYPES)),
        "settlement_type": str(rng.choice(SETTLEMENT_TYPES)),
        "state": str(rng.choice(config.state_codes)),
        "monthly_household_income_band": str(rng.choice(INCOME_BANDS)),
        "daytime_occupancy_hours": float(rng.uniform(0.0, 24.0)),
        "cooking_fuel_primary": primary,
        "cooking_fuel_secondary": secondary,
        "num_working_members": int(rng.integers(0, min(household_size, 6) + 1)),
        "climate_zone": str(rng.choice(CLIMATE_ZONES)),
        "has_air_conditioner": bool(rng.integers(0, 2)),
        "has_refrigerator": bool(rng.integers(0, 2)),
        "has_washing_machine": bool(rng.integers(0, 2)),
        "has_personal_vehicle": bool(rng.integers(0, 2)),
    }


def _sample_electricity(
    rng: np.random.Generator, descriptors: dict[str, object], config: GenerationConfig
) -> float:
    climate_multipliers = dict(config.electricity_climate_multipliers)
    settlement_scalars = dict(config.electricity_settlement_scalars)
    household_size = int(descriptors["household_size"])
    occupancy = float(descriptors["daytime_occupancy_hours"])
    multipliers = (
        config.electricity_ac_multiplier if descriptors["has_air_conditioner"] else 1.0,
        config.electricity_refrigerator_multiplier
        if descriptors["has_refrigerator"]
        else 1.0,
        config.electricity_washing_machine_multiplier
        if descriptors["has_washing_machine"]
        else 1.0,
        1.0 + config.electricity_household_size_increment * (household_size - 1),
        climate_multipliers[str(descriptors["climate_zone"])],
        1.0 + config.electricity_occupancy_hour_increment * occupancy,
        settlement_scalars[str(descriptors["settlement_type"])],
    )
    adjusted_mu = config.electricity_mu + sum(
        float(np.log(item)) for item in multipliers
    )
    return _truncated_lognormal(
        rng,
        mu=adjusted_mu,
        sigma=config.electricity_sigma,
        low=config.electricity_low,
        high=config.electricity_high,
        max_draws=config.max_rejection_draws,
    )


def _sample_lpg(
    rng: np.random.Generator, descriptors: dict[str, object], config: GenerationConfig
) -> float:
    primary = descriptors["cooking_fuel_primary"]
    secondary = descriptors["cooking_fuel_secondary"]
    if primary == "lpg":
        log_mean = config.lpg_mu_primary
    elif secondary == "lpg":
        log_mean = config.lpg_mu_secondary
    else:
        return 0.0

    household_size = int(descriptors["household_size"])
    adjusted_mu = log_mean + float(
        np.log(1.0 + config.lpg_household_size_increment * (household_size - 1))
    )
    return _truncated_lognormal(
        rng,
        mu=adjusted_mu,
        sigma=config.lpg_sigma,
        low=config.lpg_low,
        high=config.lpg_high,
        max_draws=config.max_rejection_draws,
    )


def iter_records(
    config: GenerationConfig,
    calculator: CarbonCalculatorService | None = None,
) -> Iterable[SyntheticHouseholdRecord]:
    """Yield fully validated rows using one locally seeded random stream."""
    rng = np.random.default_rng(config.random_seed)
    service = calculator or CarbonCalculatorService()
    run_id = str(uuid4())

    for _ in range(config.n_records):
        descriptors = _sample_descriptors(rng, config)
        electricity = _sample_electricity(rng, descriptors, config)
        lpg = _sample_lpg(rng, descriptors, config)
        response = service.calculate(
            CalculationRequest(
                electricity_kwh_per_month=electricity,
                lpg_kg_per_month=lpg,
            )
        )
        values: dict[str, object] = {
            "record_id": str(uuid4()),
            "schema_version": config.schema_version,
            "generation_run_id": run_id,
            "random_seed": config.random_seed,
            "is_synthetic": True,
            **descriptors,
            "electricity_kwh_per_month": electricity,
            "lpg_kg_per_month": lpg,
            "total_emissions_kg_co2": response.total_emissions_kg_co2,
            "direct_emissions_kg_co2": response.direct_emissions_kg_co2,
            "indirect_emissions_kg_co2": response.indirect_emissions_kg_co2,
        }
        try:
            yield SyntheticHouseholdRecord.model_validate(values)
        except Exception as exc:
            raise DatasetGenerationError(
                f"Generated record failed schema validation: {exc}"
            ) from exc


def generate_dataset(
    config: GenerationConfig,
    calculator: CarbonCalculatorService | None = None,
) -> Path:
    """Write a complete dataset atomically, preserving the old file on failure."""
    destination = Path(config.output_path).expanduser()
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                prefix=f".{destination.name}.",
                suffix=".tmp",
                dir=destination.parent,
                delete=False,
            ) as temp_file:
                temporary_path = Path(temp_file.name)
                writer = csv.DictWriter(
                    temp_file,
                    fieldnames=SyntheticHouseholdRecord.FIELD_ORDER,
                    extrasaction="raise",
                    lineterminator="\n",
                )
                writer.writeheader()
                count = 0
                for record in iter_records(config, calculator):
                    writer.writerow(record.model_dump(mode="python"))
                    count += 1
                if count != config.n_records:
                    raise DatasetGenerationError(
                        f"Expected {config.n_records} records, generated {count}."
                    )
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temporary_path, destination)
            return destination
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
    except DatasetGenerationError:
        raise
    except Exception as exc:
        raise DatasetGenerationError(
            f"Could not complete dataset at '{destination}': {exc}"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--records", type=int, default=10_000, help="number of rows (default: 10000)"
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="sampling seed (default: 42)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"CSV destination (default: {DEFAULT_OUTPUT_PATH})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = GenerationConfig(
            n_records=args.records,
            random_seed=args.seed,
            output_path=args.output,
        )
        path = generate_dataset(config)
    except (DatasetGenerationError, ValueError) as exc:
        print(f"Dataset generation failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"Generated {config.n_records} validated synthetic records at {path}. "
        "Sampled values are seed-reproducible; UUID metadata makes CSV bytes differ by run."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
