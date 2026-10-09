"""Traceable Emission Factor Registry for CARBONWISE."""

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.services.exceptions import (
    FactorNotFoundError,
    IncompatibleUnitError,
    UnresolvedFactorError,
)


class EmissionFactorRecord(BaseModel):
    """Pydantic model representing an emission factor entry with full provenance."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="Stable unique identifier for the factor")
    activity_type: str = Field(..., description="Activity category (e.g., electricity, cooking_heating, transport)")
    fuel_energy_source: str = Field(..., description="Specific fuel or energy source")
    value: Optional[float] = Field(default=None, description="Numeric factor value per normalized unit")
    original_unit: str = Field(..., description="Unit as published in authoritative source")
    unit_normalized: str = Field(..., description="Normalized calculation unit")
    activity_unit: Optional[str] = Field(default=None, description="Expected activity measurement unit")
    geography: str = Field(..., description="Jurisdiction / geography or global_default")
    reference_year: str = Field(..., description="Publication year or baseline period")
    source_title: str = Field(..., description="Authoritative publication title")
    source_url: str = Field(..., description="Direct citation reference or URL")
    gases_covered: str = Field(default="CO2", description="Greenhouse gases covered (e.g. CO2, CO2e)")
    boundary: str = Field(..., description="Emissions boundary: direct_scope_1 or indirect_scope_2")
    derivation: Optional[str] = Field(default=None, description="Documented mathematical derivation")
    assumptions: Optional[str] = Field(default=None, description="Documented factor assumptions")
    verification_notes: Optional[str] = Field(default=None, description="Audit verification statement")
    status: Literal["verified", "unresolved"] = Field(..., description="Verification status")


class EmissionFactorRegistry:
    """Registry maintaining traceable emission factors loaded from external YAML."""

    def __init__(self, factors: Optional[List[EmissionFactorRecord]] = None) -> None:
        self._factors: List[EmissionFactorRecord] = factors or []
        self._by_id: Dict[str, EmissionFactorRecord] = {f.id: f for f in self._factors}

    @classmethod
    def from_yaml(cls, path: Path | str) -> "EmissionFactorRegistry":
        """Load and validate factors from a YAML file."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Emission factor file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data: Any = yaml.safe_load(f)

        if not isinstance(data, dict) or "factors" not in data:
            raise ValueError(f"Invalid factors YAML format: missing top-level 'factors' list in {file_path}")

        records: List[EmissionFactorRecord] = [
            EmissionFactorRecord.model_validate(item) for item in data["factors"]
        ]
        return cls(factors=records)

    def get_factor(
        self,
        activity_type: str,
        fuel_source: str,
        geography: str = "India",
        expected_unit: Optional[str] = None,
        expected_activity_unit: Optional[str] = None,
    ) -> EmissionFactorRecord:
        """Resolve a verified emission factor.

        Args:
            activity_type: Activity category (e.g. electricity, cooking_heating).
            fuel_source: Fuel or energy stream (e.g. grid_electricity, lpg).
            geography: Target jurisdiction (e.g. India, fallback to global_default).
            expected_unit: Expected normalized calculation unit (e.g. kgCO2/kWh).
            expected_activity_unit: Expected activity input unit (e.g. kWh, kg).

        Returns:
            Validated EmissionFactorRecord.

        Raises:
            FactorNotFoundError: If no factor exists.
            UnresolvedFactorError: If factor is marked unresolved or missing numeric value.
            IncompatibleUnitError: If normalized unit or activity unit does not match expected.
        """
        candidates = [
            f for f in self._factors
            if f.activity_type == activity_type and f.fuel_energy_source == fuel_source
        ]

        if not candidates:
            raise FactorNotFoundError(
                f"No emission factor found for activity '{activity_type}' and fuel '{fuel_source}'."
            )

        # Match target geography first; fallback to global_default
        matched = next((f for f in candidates if f.geography.lower() == geography.lower()), None)
        if not matched:
            matched = next((f for f in candidates if f.geography.lower() == "global_default"), None)

        if not matched:
            raise FactorNotFoundError(
                f"No emission factor found for activity '{activity_type}', fuel '{fuel_source}' in geography '{geography}'."
            )

        if matched.status == "unresolved" or matched.value is None:
            raise UnresolvedFactorError(
                f"Emission factor '{matched.id}' is unresolved: {matched.assumptions or matched.derivation or 'Unresolved factor'}"
            )

        if expected_unit and matched.unit_normalized.lower() != expected_unit.lower():
            raise IncompatibleUnitError(
                f"Emission factor '{matched.id}' unit '{matched.unit_normalized}' does not match expected '{expected_unit}'."
            )

        if expected_activity_unit and matched.activity_unit and matched.activity_unit.lower() != expected_activity_unit.lower():
            raise IncompatibleUnitError(
                f"Emission factor '{matched.id}' activity unit '{matched.activity_unit}' does not match expected '{expected_activity_unit}'."
            )

        return matched

    def get_by_id(self, factor_id: str) -> Optional[EmissionFactorRecord]:
        """Retrieve a factor by ID if present."""
        return self._by_id.get(factor_id)

    @property
    def all_factors(self) -> List[EmissionFactorRecord]:
        """Return list of all factors in registry."""
        return list(self._factors)


@lru_cache
def get_registry() -> EmissionFactorRegistry:
    """Return a cached singleton instance of the factor registry."""
    settings = get_settings()
    return EmissionFactorRegistry.from_yaml(settings.factors_path)
