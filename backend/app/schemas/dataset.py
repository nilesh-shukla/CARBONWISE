"""Pydantic schema and field policy for synthetic household records v1."""

import math
from typing import ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

STATE_CODES: tuple[str, ...] = (
    "IN-AN",
    "IN-AP",
    "IN-AR",
    "IN-AS",
    "IN-BR",
    "IN-CH",
    "IN-CT",
    "IN-DH",
    "IN-DL",
    "IN-GA",
    "IN-GJ",
    "IN-HP",
    "IN-HR",
    "IN-JH",
    "IN-JK",
    "IN-KA",
    "IN-KL",
    "IN-LA",
    "IN-LD",
    "IN-MH",
    "IN-ML",
    "IN-MN",
    "IN-MP",
    "IN-MZ",
    "IN-NL",
    "IN-OD",
    "IN-PB",
    "IN-PY",
    "IN-RJ",
    "IN-SK",
    "IN-TG",
    "IN-TN",
    "IN-TR",
    "IN-UT",
    "IN-UP",
    "IN-WB",
)

DWELLING_TYPES = ("apartment", "independent_house", "chawl_shared")
SETTLEMENT_TYPES = ("urban", "peri_urban", "rural")
INCOME_BANDS = ("<10k", "10k-25k", "25k-50k", "50k-100k", ">100k")
PRIMARY_FUELS = ("lpg", "electricity", "biomass", "piped_gas", "none")
SECONDARY_FUELS = ("lpg", "electricity", "biomass", "none")
CLIMATE_ZONES = ("hot_dry", "warm_humid", "composite", "temperate", "cold")


class SyntheticHouseholdRecord(BaseModel):
    """One validated row in the v1 synthetic household dataset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    FIELD_ORDER: ClassVar[tuple[str, ...]]

    record_id: str
    schema_version: Literal["v1"]
    generation_run_id: str
    random_seed: int
    is_synthetic: Literal[True]

    household_size: int = Field(ge=1, le=10)
    dwelling_type: Literal["apartment", "independent_house", "chawl_shared"]
    settlement_type: Literal["urban", "peri_urban", "rural"]
    state: str
    monthly_household_income_band: Literal[
        "<10k", "10k-25k", "25k-50k", "50k-100k", ">100k"
    ]

    daytime_occupancy_hours: float = Field(ge=0.0, le=24.0)
    cooking_fuel_primary: Literal["lpg", "electricity", "biomass", "piped_gas", "none"]
    cooking_fuel_secondary: Literal["lpg", "electricity", "biomass", "none"]
    num_working_members: int = Field(ge=0)
    climate_zone: Literal["hot_dry", "warm_humid", "composite", "temperate", "cold"]

    has_air_conditioner: bool
    has_refrigerator: bool
    has_washing_machine: bool
    has_personal_vehicle: bool

    electricity_kwh_per_month: float = Field(ge=10.0, le=2000.0)
    lpg_kg_per_month: float = Field(ge=0.0, le=60.0)

    total_emissions_kg_co2: float = Field(ge=0.0)
    direct_emissions_kg_co2: float = Field(ge=0.0)
    indirect_emissions_kg_co2: float = Field(ge=0.0)

    @field_validator("record_id", "generation_run_id")
    @classmethod
    def validate_uuid_v4(cls, value: str) -> str:
        try:
            parsed = UUID(value)
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("must be a valid UUID v4") from exc
        if parsed.version != 4:
            raise ValueError("must be a valid UUID v4")
        return value

    @field_validator("state")
    @classmethod
    def validate_state_code(cls, value: str) -> str:
        if value not in STATE_CODES:
            raise ValueError("must be a current ISO 3166-2:IN subdivision code")
        return value

    @field_validator(
        "daytime_occupancy_hours",
        "electricity_kwh_per_month",
        "lpg_kg_per_month",
        "total_emissions_kg_co2",
        "direct_emissions_kg_co2",
        "indirect_emissions_kg_co2",
    )
    @classmethod
    def validate_finite_numbers(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("must be finite")
        return value

    @model_validator(mode="after")
    def validate_record_consistency(self) -> "SyntheticHouseholdRecord":
        if self.num_working_members > min(self.household_size, 6):
            raise ValueError(
                "num_working_members must not exceed min(household_size, 6)"
            )
        if (
            self.cooking_fuel_primary != "none"
            and self.cooking_fuel_secondary == self.cooking_fuel_primary
        ):
            raise ValueError("secondary cooking fuel must differ from primary fuel")
        if self.lpg_kg_per_month != 0.0 and self.lpg_kg_per_month < 0.5:
            raise ValueError(
                "LPG use must be 0.0 or within the generated-user range [0.5, 60]"
            )
        return self


SyntheticHouseholdRecord.FIELD_ORDER = tuple(SyntheticHouseholdRecord.model_fields)

MODEL_INPUT_FIELDS: list[str] = [
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
