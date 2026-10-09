"""Deterministic carbon footprint calculation service."""

from typing import Dict, List

from app.core.config import Settings, get_settings
from app.schemas.calculate import (
    CalculationRequest,
    CalculationResponse,
    CategoryResult,
)
from app.services.registry import EmissionFactorRegistry, get_registry


class CarbonCalculatorService:
    """Service executing deterministic monthly carbon footprint calculations."""

    def __init__(
        self,
        registry: EmissionFactorRegistry | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.registry = registry or get_registry()

    def calculate(self, request: CalculationRequest) -> CalculationResponse:
        """Compute household carbon footprint deterministically from verified factors.

        Args:
            request: Validated consumption quantities for the month.

        Returns:
            CalculationResponse with itemized categories, partial status semantics, and sum totals.
        """
        region = request.region or self.settings.DEFAULT_REGION
        categories: Dict[str, CategoryResult] = {}
        calculated_categories: List[str] = []
        excluded_categories: Dict[str, str] = {}
        not_provided_categories: List[str] = []
        factor_ids: List[str] = []
        sources: List[str] = []

        raw_direct = 0.0
        raw_indirect = 0.0

        # 1. Electricity (Scope 2 - Indirect)
        if request.electricity_kwh_per_month is not None:
            elec_factor = self.registry.get_factor(
                activity_type="electricity",
                fuel_source="grid_electricity",
                geography=region,
                expected_unit="kgCO2/kWh",
                expected_activity_unit="kWh",
            )
            # Full precision calculation internally
            elec_emissions = request.electricity_kwh_per_month * elec_factor.value
            raw_indirect += elec_emissions
            categories["electricity"] = CategoryResult(
                status="calculated",
                activity_type="electricity",
                fuel_energy_source="grid_electricity",
                activity_amount=request.electricity_kwh_per_month,
                activity_unit="kWh",
                boundary=elec_factor.boundary,
                emissions_kg_co2=round(elec_emissions, 4),
                factor_id=elec_factor.id,
                factor_value=elec_factor.value,
                factor_unit=elec_factor.unit_normalized,
                source_title=elec_factor.source_title,
                source_url=elec_factor.source_url,
                reason=None,
            )
            calculated_categories.append("electricity")
            factor_ids.append(elec_factor.id)
            sources.append(f"{elec_factor.source_title} ({elec_factor.reference_year})")
        else:
            categories["electricity"] = CategoryResult(
                status="not_provided",
                activity_type="electricity",
                fuel_energy_source="grid_electricity",
                activity_amount=None,
                activity_unit="kWh",
                boundary=None,
                emissions_kg_co2=None,
                factor_id=None,
                factor_value=None,
                factor_unit="kgCO2/kWh",
                source_title=None,
                source_url=None,
                reason="Electricity consumption was not provided in request.",
            )
            not_provided_categories.append("electricity")

        # 2. LPG (Scope 1 - Direct)
        if request.lpg_kg_per_month is not None:
            lpg_factor = self.registry.get_factor(
                activity_type="cooking_heating",
                fuel_source="lpg",
                geography=region,
                expected_unit="kgCO2/kg",
                expected_activity_unit="kg",
            )
            lpg_emissions = request.lpg_kg_per_month * lpg_factor.value
            raw_direct += lpg_emissions
            categories["lpg"] = CategoryResult(
                status="calculated",
                activity_type="cooking_heating",
                fuel_energy_source="lpg",
                activity_amount=request.lpg_kg_per_month,
                activity_unit="kg",
                boundary=lpg_factor.boundary,
                emissions_kg_co2=round(lpg_emissions, 4),
                factor_id=lpg_factor.id,
                factor_value=lpg_factor.value,
                factor_unit=lpg_factor.unit_normalized,
                source_title=lpg_factor.source_title,
                source_url=lpg_factor.source_url,
                reason=None,
            )
            calculated_categories.append("lpg")
            factor_ids.append(lpg_factor.id)
            sources.append(f"{lpg_factor.source_title} ({lpg_factor.reference_year})")
        else:
            categories["lpg"] = CategoryResult(
                status="not_provided",
                activity_type="cooking_heating",
                fuel_energy_source="lpg",
                activity_amount=None,
                activity_unit="kg",
                boundary=None,
                emissions_kg_co2=None,
                factor_id=None,
                factor_value=None,
                factor_unit="kgCO2/kg",
                source_title=None,
                source_url=None,
                reason="LPG consumption was not provided in request.",
            )
            not_provided_categories.append("lpg")

        # 3. Petrol (Unresolved Volumetric Factor -> not_calculated if supplied, not_provided if omitted)
        petrol_unresolved = self.registry.get_by_id("petrol_road_ipcc_2006_volumetric")
        petrol_reason = "Volumetric emission factor is unresolved in IPCC 2006 (no default fuel density specified)."
        if request.petrol_litres_per_month is not None:
            categories["petrol"] = CategoryResult(
                status="not_calculated",
                activity_type="transport",
                fuel_energy_source="petrol",
                activity_amount=request.petrol_litres_per_month,
                activity_unit="litres",
                boundary=None,
                emissions_kg_co2=None,
                factor_id=petrol_unresolved.id if petrol_unresolved else None,
                factor_value=None,
                factor_unit="kgCO2/litre",
                source_title=petrol_unresolved.source_title if petrol_unresolved else None,
                source_url=petrol_unresolved.source_url if petrol_unresolved else None,
                reason=petrol_reason,
            )
            excluded_categories["petrol"] = petrol_reason
        else:
            categories["petrol"] = CategoryResult(
                status="not_provided",
                activity_type="transport",
                fuel_energy_source="petrol",
                activity_amount=None,
                activity_unit="litres",
                boundary=None,
                emissions_kg_co2=None,
                factor_id=None,
                factor_value=None,
                factor_unit="kgCO2/litre",
                source_title=None,
                source_url=None,
                reason="Petrol consumption was not provided in request.",
            )
            not_provided_categories.append("petrol")

        # 4. Diesel (Unresolved Volumetric Factor -> not_calculated if supplied, not_provided if omitted)
        diesel_unresolved = self.registry.get_by_id("diesel_road_ipcc_2006_volumetric")
        diesel_reason = "Volumetric emission factor is unresolved in IPCC 2006 (no default fuel density specified)."
        if request.diesel_litres_per_month is not None:
            categories["diesel"] = CategoryResult(
                status="not_calculated",
                activity_type="transport",
                fuel_energy_source="diesel",
                activity_amount=request.diesel_litres_per_month,
                activity_unit="litres",
                boundary=None,
                emissions_kg_co2=None,
                factor_id=diesel_unresolved.id if diesel_unresolved else None,
                factor_value=None,
                factor_unit="kgCO2/litre",
                source_title=diesel_unresolved.source_title if diesel_unresolved else None,
                source_url=diesel_unresolved.source_url if diesel_unresolved else None,
                reason=diesel_reason,
            )
            excluded_categories["diesel"] = diesel_reason
        else:
            categories["diesel"] = CategoryResult(
                status="not_provided",
                activity_type="transport",
                fuel_energy_source="diesel",
                activity_amount=None,
                activity_unit="litres",
                boundary=None,
                emissions_kg_co2=None,
                factor_id=None,
                factor_value=None,
                factor_unit="kgCO2/litre",
                source_title=None,
                source_url=None,
                reason="Diesel consumption was not provided in request.",
            )
            not_provided_categories.append("diesel")

        # Partial total evaluation:
        # complete_for_provided_inputs: every supplied activity was calculated.
        # partial: at least one supplied activity could not be calculated (e.g. unresolved factor).
        # Omitted activities do not make the result partial.
        total_is_partial = len(excluded_categories) > 0
        calculation_status = "partial" if total_is_partial else "complete_for_provided_inputs"

        # Sum of supported calculable categories only (uncalculated categories never enter total)
        raw_total = raw_direct + raw_indirect

        footprint_scope_note = (
            "The total covers only the supplied, calculable activities and is not a full household footprint."
        )

        assumptions = [
            "Reporting period is fixed to monthly.",
            "Missing input values represent 'not provided'; explicit 0.0 values represent an explicit zero supplied by the user (yielding zero emissions for calculable activities).",
            footprint_scope_note,
            "Results are reported strictly as CO2 emissions (not CO2e) per IPCC 2006 Tier 1 stationary and CEA grid baseline data.",
            "Grid electricity reflects CEA national grid generation busbar weighted average (including renewables), excluding technical T&D losses.",
            "LPG emissions assume complete 100% oxidation per IPCC Tier 1 stationary combustion defaults.",
            "Liquid transport fuels (petrol, diesel) are marked not_calculated because volumetric density is unresolved in IPCC 2006 Volume 2.",
        ]

        return CalculationResponse(
            reporting_period="monthly",
            gas_scope="CO2",
            unit="kgCO2/month",
            calculation_status=calculation_status,
            total_is_partial=total_is_partial,
            calculated_categories=calculated_categories,
            excluded_categories=excluded_categories,
            not_provided_categories=not_provided_categories,
            footprint_scope_note=footprint_scope_note,
            total_emissions_kg_co2=round(raw_total, 4),
            direct_emissions_kg_co2=round(raw_direct, 4),
            indirect_emissions_kg_co2=round(raw_indirect, 4),
            categories=categories,
            factor_ids=factor_ids,
            sources=list(dict.fromkeys(sources)),
            assumptions=assumptions,
        )


def get_calculator_service() -> CarbonCalculatorService:
    """Dependency provider for the carbon calculation service."""
    return CarbonCalculatorService()
