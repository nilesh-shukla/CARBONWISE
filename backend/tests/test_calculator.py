"""Tests for CarbonCalculatorService and /api/v1/calculate endpoint."""

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.schemas.calculate import CalculationRequest
from app.services.calculator import CarbonCalculatorService
from app.services.registry import EmissionFactorRecord, EmissionFactorRegistry


@pytest.fixture
def mock_registry() -> EmissionFactorRegistry:
    """Fixture providing known static emission factors for hand-calculated tests."""
    factors = [
        EmissionFactorRecord(
            id="ef_elec_test",
            activity_type="electricity",
            fuel_energy_source="grid_electricity",
            value=0.716,
            original_unit="tCO2/MWh",
            unit_normalized="kgCO2/kWh",
            activity_unit="kWh",
            geography="India",
            reference_year="2024",
            source_title="Mock CEA Database",
            source_url="https://cea.nic.in/mock",
            gases_covered="CO2",
            boundary="indirect_scope_2",
            derivation="Direct 1:1 conversion from 0.716 tCO2/MWh to 0.716 kgCO2/kWh",
            status="verified",
        ),
        EmissionFactorRecord(
            id="ef_lpg_test",
            activity_type="cooking_heating",
            fuel_energy_source="lpg",
            value=2.98463,
            original_unit="kgCO2/kg",
            unit_normalized="kgCO2/kg",
            activity_unit="kg",
            geography="global_default",
            reference_year="2006",
            source_title="Mock IPCC 2006",
            source_url="https://ipcc.ch/mock",
            gases_covered="CO2",
            boundary="direct_scope_1",
            derivation="0.0000473 TJ/kg * 63100 kg/TJ = 2.98463 kgCO2/kg",
            status="verified",
        ),
        EmissionFactorRecord(
            id="petrol_road_ipcc_2006_volumetric",
            activity_type="transport",
            fuel_energy_source="petrol",
            value=None,
            original_unit="kgCO2/TJ",
            unit_normalized="kgCO2/litre",
            activity_unit="litres",
            geography="global_default",
            reference_year="2006",
            source_title="Mock IPCC 2006",
            source_url="https://ipcc.ch/mock",
            gases_covered="CO2",
            boundary="direct_scope_1",
            status="unresolved",
        ),
        EmissionFactorRecord(
            id="diesel_road_ipcc_2006_volumetric",
            activity_type="transport",
            fuel_energy_source="diesel",
            value=None,
            original_unit="kgCO2/TJ",
            unit_normalized="kgCO2/litre",
            activity_unit="litres",
            geography="global_default",
            reference_year="2006",
            source_title="Mock IPCC 2006",
            source_url="https://ipcc.ch/mock",
            gases_covered="CO2",
            boundary="direct_scope_1",
            status="unresolved",
        ),
    ]
    return EmissionFactorRegistry(factors=factors)


@pytest.fixture
def test_calculator(mock_registry: EmissionFactorRegistry) -> CarbonCalculatorService:
    """Fixture providing calculator service backed by mock registry."""
    return CarbonCalculatorService(registry=mock_registry)


def test_hand_calculated_emissions_complete(test_calculator: CarbonCalculatorService) -> None:
    """Verify hand-calculated emissions for complete calculation (electricity + LPG, transport omitted).

    Independent hand calculations:
    - Indirect (Electricity): 100 * 0.716 = 71.6000 kg CO2
    - Direct (LPG): 14.2 * 2.98463 = 42.381746 -> rounded to 42.3817 kg CO2
    - Total: 71.6000 + 42.381746 = 113.981746 -> rounded to 113.9817 kg CO2
    """
    request = CalculationRequest(
        electricity_kwh_per_month=100.0,
        lpg_kg_per_month=14.2,
    )
    response = test_calculator.calculate(request)

    assert response.reporting_period == "monthly"
    assert response.gas_scope == "CO2"
    assert response.unit == "kgCO2/month"
    assert response.calculation_status == "complete_for_provided_inputs"
    assert response.total_is_partial is False
    assert response.calculated_categories == ["electricity", "lpg"]
    assert response.excluded_categories == {}
    assert response.not_provided_categories == ["petrol", "diesel"]
    assert "not a full household footprint" in response.footprint_scope_note

    assert response.indirect_emissions_kg_co2 == 71.6000
    assert response.direct_emissions_kg_co2 == 42.3817
    assert response.total_emissions_kg_co2 == 113.9817

    assert response.categories["electricity"].status == "calculated"
    assert response.categories["electricity"].emissions_kg_co2 == 71.6000
    assert response.categories["electricity"].boundary == "indirect_scope_2"

    assert response.categories["lpg"].status == "calculated"
    assert response.categories["lpg"].emissions_kg_co2 == 42.3817
    assert response.categories["lpg"].boundary == "direct_scope_1"

    # Transport was omitted, so it must be marked not_provided
    assert response.categories["petrol"].status == "not_provided"
    assert response.categories["petrol"].activity_amount is None
    assert response.categories["diesel"].status == "not_provided"
    assert response.categories["diesel"].activity_amount is None


def test_hand_calculated_emissions_partial(test_calculator: CarbonCalculatorService) -> None:
    """Verify partial calculation semantics when unresolved petrol is provided."""
    request = CalculationRequest(
        electricity_kwh_per_month=100.0,
        lpg_kg_per_month=14.2,
        petrol_litres_per_month=25.0,
    )
    response = test_calculator.calculate(request)

    assert response.calculation_status == "partial"
    assert response.total_is_partial is True
    assert "electricity" in response.calculated_categories
    assert "lpg" in response.calculated_categories
    assert "petrol" in response.excluded_categories
    assert response.not_provided_categories == ["diesel"]
    assert "unresolved" in response.excluded_categories["petrol"].lower()

    # Petrol was provided (25.0 L) but uncalculated, and must not enter total
    assert response.categories["petrol"].status == "not_calculated"
    assert response.categories["petrol"].activity_amount == 25.0
    assert response.categories["petrol"].emissions_kg_co2 is None
    assert response.total_emissions_kg_co2 == 113.9817


def test_explicit_zero_for_unresolved_factor(test_calculator: CarbonCalculatorService) -> None:
    """Verify that an explicit 0.0 for an unresolved activity is marked excluded and partial."""
    request = CalculationRequest(
        electricity_kwh_per_month=100.0,
        petrol_litres_per_month=0.0,
    )
    response = test_calculator.calculate(request)

    assert response.calculation_status == "partial"
    assert response.total_is_partial is True
    assert "petrol" in response.excluded_categories
    assert response.categories["petrol"].status == "not_calculated"
    assert response.categories["petrol"].activity_amount == 0.0
    assert response.categories["petrol"].emissions_kg_co2 is None
    assert response.total_emissions_kg_co2 == 71.6000


def test_zero_consumption_vs_missing_input(test_calculator: CarbonCalculatorService) -> None:
    """Verify explicit 0.0 is calculated as zero, while omitted values are not_provided."""
    # Explicit zero electricity, omitted LPG
    req_zero_elec = CalculationRequest(electricity_kwh_per_month=0.0)
    res_zero_elec = test_calculator.calculate(req_zero_elec)

    assert res_zero_elec.calculation_status == "complete_for_provided_inputs"
    assert res_zero_elec.total_is_partial is False
    assert res_zero_elec.categories["electricity"].status == "calculated"
    assert res_zero_elec.categories["electricity"].activity_amount == 0.0
    assert res_zero_elec.categories["electricity"].emissions_kg_co2 == 0.0
    assert res_zero_elec.categories["lpg"].status == "not_provided"
    assert res_zero_elec.categories["lpg"].activity_amount is None
    assert "lpg" in res_zero_elec.not_provided_categories
    assert res_zero_elec.total_emissions_kg_co2 == 0.0

    # Explicit zero for both
    req_both_zero = CalculationRequest(electricity_kwh_per_month=0.0, lpg_kg_per_month=0.0)
    res_both_zero = test_calculator.calculate(req_both_zero)
    assert res_both_zero.calculation_status == "complete_for_provided_inputs"
    assert res_both_zero.total_is_partial is False
    assert res_both_zero.total_emissions_kg_co2 == 0.0
    assert res_both_zero.direct_emissions_kg_co2 == 0.0
    assert res_both_zero.indirect_emissions_kg_co2 == 0.0


@pytest.mark.parametrize(
    "kwh,lpg_kg",
    [
        (50.0, 10.0),
        (250.5, 28.4),
        (0.0, 15.0),
        (120.0, 0.0),
        (432.1, 8.5),
        (100.0, None),
        (None, 20.0),
    ],
)
def test_total_equals_sum_of_categories(
    test_calculator: CarbonCalculatorService, kwh: float | None, lpg_kg: float | None
) -> None:
    """Verify that total emissions equal direct plus indirect emissions."""
    request = CalculationRequest(
        electricity_kwh_per_month=kwh,
        lpg_kg_per_month=lpg_kg,
    )
    response = test_calculator.calculate(request)

    expected_sum = round(
        response.direct_emissions_kg_co2 + response.indirect_emissions_kg_co2, 4
    )
    assert abs(response.total_emissions_kg_co2 - expected_sum) <= 0.0001


def test_api_calculate_endpoint_complete(client: TestClient) -> None:
    """Test complete calculation via POST /api/v1/calculate."""
    payload = {
        "electricity_kwh_per_month": 150.0,
        "lpg_kg_per_month": 14.2,
    }
    response = client.post("/api/v1/calculate", json=payload)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["calculation_status"] == "complete_for_provided_inputs"
    assert data["total_is_partial"] is False
    assert data["calculated_categories"] == ["electricity", "lpg"]
    assert data["excluded_categories"] == {}
    assert data["not_provided_categories"] == ["petrol", "diesel"]
    assert data["total_emissions_kg_co2"] == round(150.0 * 0.716 + 14.2 * 2.98463, 4)


def test_api_calculate_endpoint_partial(client: TestClient) -> None:
    """Test partial calculation via POST /api/v1/calculate when petrol is provided."""
    payload = {
        "electricity_kwh_per_month": 150.0,
        "lpg_kg_per_month": 14.2,
        "petrol_litres_per_month": 30.0,
    }
    response = client.post("/api/v1/calculate", json=payload)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["calculation_status"] == "partial"
    assert data["total_is_partial"] is True
    assert "petrol" in data["excluded_categories"]
    assert data["not_provided_categories"] == ["diesel"]
    assert data["categories"]["petrol"]["status"] == "not_calculated"
    assert data["categories"]["petrol"]["activity_amount"] == 30.0
    assert data["categories"]["petrol"]["emissions_kg_co2"] is None


@pytest.mark.parametrize(
    "invalid_payload",
    [
        {"electricity_kwh_per_month": -10.0, "lpg_kg_per_month": 5.0},
        {"electricity_kwh_per_month": 10.0, "lpg_kg_per_month": -2.0},
        {"electricity_kwh_per_month": 10.0, "petrol_litres_per_month": -1.0},
        {"electricity_kwh_per_month": "NaN", "lpg_kg_per_month": 5.0},
        {"electricity_kwh_per_month": "Infinity", "lpg_kg_per_month": 5.0},
        {},  # Empty payload: no activity provided
        {"electricity_kwh_per_month": 10.0, "unsupported_activity": 123},  # Extra field
    ],
)
def test_api_calculate_invalid_inputs(client: TestClient, invalid_payload: dict) -> None:
    """Verify negative, non-finite, missing all activities, and extra keys return 422 VALIDATION_ERROR."""
    response = client.post("/api/v1/calculate", json=invalid_payload)
    assert response.status_code == 422

    error_data = response.json()
    assert "error" in error_data
    assert error_data["error"]["code"] == "VALIDATION_ERROR"


def test_api_calculate_unknown_region_fails(client: TestClient) -> None:
    """Verify that requesting an unsupported/missing region returns 404 FACTOR_NOT_FOUND."""
    payload = {
        "electricity_kwh_per_month": 100.0,
        "lpg_kg_per_month": 14.2,
        "region": "NonExistentRegion999",
    }
    response = client.post("/api/v1/calculate", json=payload)
    assert response.status_code == status.HTTP_404_NOT_FOUND

    error_data = response.json()
    assert "error" in error_data
    assert error_data["error"]["code"] == "FACTOR_NOT_FOUND"


def test_unresolved_factor_causes_calculation_failure() -> None:
    """Verify that an unresolved required factor halts calculation with UnresolvedFactorError."""
    from app.services.exceptions import UnresolvedFactorError

    factors = [
        EmissionFactorRecord(
            id="unresolved_elec",
            activity_type="electricity",
            fuel_energy_source="grid_electricity",
            value=None,
            original_unit="kgCO2/kWh",
            unit_normalized="kgCO2/kWh",
            geography="India",
            reference_year="2024",
            source_title="Test",
            source_url="https://example.com",
            gases_covered="CO2",
            boundary="indirect_scope_2",
            status="unresolved",
        )
    ]
    calc = CarbonCalculatorService(registry=EmissionFactorRegistry(factors=factors))
    req = CalculationRequest(electricity_kwh_per_month=100.0)

    with pytest.raises(UnresolvedFactorError) as exc_info:
        calc.calculate(req)
    assert "unresolved" in str(exc_info.value).lower()


def test_incompatible_unit_causes_calculation_failure() -> None:
    """Verify that an incompatible unit halts calculation with IncompatibleUnitError."""
    from app.services.exceptions import IncompatibleUnitError

    factors = [
        EmissionFactorRecord(
            id="mismatched_elec",
            activity_type="electricity",
            fuel_energy_source="grid_electricity",
            value=0.716,
            original_unit="kgCO2/MJ",
            unit_normalized="kgCO2/MJ",
            geography="India",
            reference_year="2024",
            source_title="Test",
            source_url="https://example.com",
            gases_covered="CO2",
            boundary="indirect_scope_2",
            status="verified",
        )
    ]
    calc = CarbonCalculatorService(registry=EmissionFactorRegistry(factors=factors))
    req = CalculationRequest(electricity_kwh_per_month=100.0)

    with pytest.raises(IncompatibleUnitError) as exc_info:
        calc.calculate(req)
    assert "unit" in str(exc_info.value).lower()


def test_model_rejects_non_finite_floats() -> None:
    """Verify that Python float('nan') and float('inf') are directly rejected by schema."""
    with pytest.raises(ValueError):
        CalculationRequest(electricity_kwh_per_month=float("nan"))
    with pytest.raises(ValueError):
        CalculationRequest(electricity_kwh_per_month=float("inf"))
