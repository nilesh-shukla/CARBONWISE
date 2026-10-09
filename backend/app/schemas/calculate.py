"""Pydantic schemas for the deterministic carbon calculation endpoint."""

import math
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CalculationRequest(BaseModel):
    """Monthly household activity data input contract."""

    model_config = ConfigDict(extra="forbid")

    electricity_kwh_per_month: Optional[float] = Field(
        default=None,
        description="Monthly household grid electricity consumption in kilowatt-hours (kWh). Must be non-negative and finite. Explicit 0.0 is an explicit zero supplied by the user.",
    )
    lpg_kg_per_month: Optional[float] = Field(
        default=None,
        description="Monthly household liquefied petroleum gas (LPG) consumption in kilograms (kg). Must be non-negative and finite. Explicit 0.0 is an explicit zero supplied by the user.",
    )
    petrol_litres_per_month: Optional[float] = Field(
        default=None,
        description="Optional monthly motor gasoline (petrol) consumption in litres. Must be non-negative and finite. Explicit 0.0 is an explicit zero supplied by the user.",
    )
    diesel_litres_per_month: Optional[float] = Field(
        default=None,
        description="Optional monthly gas/diesel oil consumption in litres. Must be non-negative and finite. Explicit 0.0 is an explicit zero supplied by the user.",
    )
    region: Optional[str] = Field(
        default=None,
        description="Target geographic boundary for factor resolution (defaults to system default 'India').",
    )

    @field_validator(
        "electricity_kwh_per_month",
        "lpg_kg_per_month",
        "petrol_litres_per_month",
        "diesel_litres_per_month",
        mode="before",
    )
    @classmethod
    def validate_finite_non_negative_number(cls, v: Any) -> Optional[float]:
        """Ensure inputs are finite, non-NaN, and non-negative numbers."""
        if v is None:
            return None
        try:
            val = float(v)
        except (TypeError, ValueError):
            raise ValueError("Input must be a valid number.")
        if not math.isfinite(val):
            raise ValueError("Input must be a finite number (NaN and infinity are rejected).")
        if val < 0.0:
            raise ValueError("Input must be greater than or equal to 0.")
        return val

    @model_validator(mode="after")
    def validate_at_least_one_activity_provided(self) -> "CalculationRequest":
        """Ensure the user provides at least one consumption stream."""
        activities = [
            self.electricity_kwh_per_month,
            self.lpg_kg_per_month,
            self.petrol_litres_per_month,
            self.diesel_litres_per_month,
        ]
        if all(a is None for a in activities):
            raise ValueError("At least one consumption activity must be provided.")
        return self


class CategoryResult(BaseModel):
    """Detailed calculation outcome for an individual consumption category."""

    status: Literal["calculated", "not_calculated", "not_provided"] = Field(
        ...,
        description="Calculation outcome: 'calculated', 'not_calculated' (unresolved factor), or 'not_provided' (omitted)",
    )
    activity_type: str = Field(..., description="High-level activity category")
    fuel_energy_source: str = Field(..., description="Specific energy or fuel source")
    activity_amount: Optional[float] = Field(
        default=None, description="Reported monthly consumption quantity (null if not provided, 0.0 if explicit zero supplied by the user)"
    )
    activity_unit: str = Field(..., description="Consumption measurement unit")
    boundary: Optional[str] = Field(
        default=None, description="Emissions scope boundary: direct_scope_1 or indirect_scope_2"
    )
    emissions_kg_co2: Optional[float] = Field(
        default=None, description="Computed emissions in kg CO2 (rounded to 4 decimals, null if uncalculated/omitted)"
    )
    factor_id: Optional[str] = Field(
        default=None, description="Stable identifier of the emission factor used"
    )
    factor_value: Optional[float] = Field(
        default=None, description="Numerical emission factor applied"
    )
    factor_unit: Optional[str] = Field(
        default=None, description="Unit of the emission factor"
    )
    source_title: Optional[str] = Field(
        default=None, description="Citation title for the emission factor"
    )
    source_url: Optional[str] = Field(
        default=None, description="URL reference for the emission factor"
    )
    reason: Optional[str] = Field(
        default=None, description="Explanation when category is not_calculated or not_provided"
    )


class CalculationResponse(BaseModel):
    """Deterministic household carbon footprint output response with partial-total semantics."""

    reporting_period: Literal["monthly"] = Field(
        default="monthly", description="Fixed reporting time window"
    )
    gas_scope: Literal["CO2"] = Field(
        default="CO2", description="Specific greenhouse gas evaluated (CO2 only)"
    )
    unit: str = Field(
        default="kgCO2/month", description="Output unit for all calculated emissions values"
    )
    calculation_status: Literal["complete_for_provided_inputs", "partial"] = Field(
        ...,
        description=(
            "Calculation status: 'complete_for_provided_inputs' if every supplied activity was calculated; "
            "'partial' if at least one supplied activity could not be calculated (e.g., unresolved factor). "
            "Omitted activities do not make the result partial."
        ),
    )
    total_is_partial: bool = Field(
        ...,
        description="Explicit flag indicating whether any supplied activities were excluded from the total emissions sum",
    )
    calculated_categories: List[str] = Field(
        ...,
        description="Names of categories successfully computed and included in total emissions",
    )
    excluded_categories: Dict[str, str] = Field(
        ...,
        description="Mapping of supplied but uncalculated categories to their exclusion reason",
    )
    not_provided_categories: List[str] = Field(
        ...,
        description="Names of consumption categories that were omitted (not provided) by the user in this request",
    )
    footprint_scope_note: str = Field(
        default="The total covers only the supplied, calculable activities and is not a full household footprint.",
        description="Explicit note clarifying that the total covers only supplied, calculable activities and is not a full household footprint.",
    )
    total_emissions_kg_co2: float = Field(
        ..., description="Sum of all supported calculated categories in kg CO2/month (rounded to 4 decimals)"
    )
    direct_emissions_kg_co2: float = Field(
        ..., description="Sum of direct combustion emissions (Scope 1) in kg CO2/month (rounded to 4 decimals)"
    )
    indirect_emissions_kg_co2: float = Field(
        ..., description="Sum of indirect electricity emissions (Scope 2) in kg CO2/month (rounded to 4 decimals)"
    )
    categories: Dict[str, CategoryResult] = Field(
        ..., description="Itemized breakdown per activity stream"
    )
    factor_ids: List[str] = Field(
        ..., description="List of factor IDs used in the calculations"
    )
    sources: List[str] = Field(
        ..., description="Authoritative citations for verified factors used"
    )
    assumptions: List[str] = Field(
        ..., description="Explicit methodological assumptions applied in this calculation"
    )
