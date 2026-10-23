"""Tests for EmissionFactorRegistry."""

from pathlib import Path
import pytest

from app.services.exceptions import (
    FactorNotFoundError,
    IncompatibleUnitError,
    UnresolvedFactorError,
)
from app.services.registry import EmissionFactorRecord, EmissionFactorRegistry


@pytest.fixture
def sample_registry() -> EmissionFactorRegistry:
    """Fixture providing an isolated registry with verified and unresolved factors."""
    factors = [
        EmissionFactorRecord(
            id="test_elec_in",
            activity_type="electricity",
            fuel_energy_source="grid_electricity",
            value=0.716,
            original_unit="tCO2/MWh",
            unit_normalized="kgCO2/kWh",
            geography="India",
            reference_year="2024",
            source_title="CEA Test Source",
            source_url="https://example.com/cea",
            gases_covered="CO2",
            boundary="indirect_scope_2",
            methodology_notes="Test electricity notes",
            status="verified",
        ),
        EmissionFactorRecord(
            id="test_lpg_global",
            activity_type="cooking_heating",
            fuel_energy_source="lpg",
            value=2.98463,
            original_unit="kgCO2/kg",
            unit_normalized="kgCO2/kg",
            geography="global_default",
            reference_year="2006",
            source_title="IPCC Test Source",
            source_url="https://example.com/ipcc",
            gases_covered="CO2",
            boundary="direct_scope_1",
            methodology_notes="Test LPG notes",
            status="verified",
        ),
        EmissionFactorRecord(
            id="test_petrol_unresolved",
            activity_type="transport",
            fuel_energy_source="petrol",
            value=None,
            original_unit="kgCO2/TJ",
            unit_normalized="kgCO2/litre",
            geography="global_default",
            reference_year="2006",
            source_title="IPCC Test Source",
            source_url="https://example.com/ipcc",
            gases_covered="CO2",
            boundary="direct_scope_1",
            methodology_notes="Unresolved density",
            status="unresolved",
        ),
    ]
    return EmissionFactorRegistry(factors=factors)


def test_registry_get_verified_factors(sample_registry: EmissionFactorRegistry) -> None:
    """Verify retrieval of verified factors for India and global_default."""
    elec = sample_registry.get_factor("electricity", "grid_electricity", "India", "kgCO2/kWh")
    assert elec.id == "test_elec_in"
    assert elec.value == 0.716

    lpg = sample_registry.get_factor("cooking_heating", "lpg", "India", "kgCO2/kg")
    assert lpg.id == "test_lpg_global"
    assert lpg.value == 2.98463


def test_registry_unresolved_factor_raises(sample_registry: EmissionFactorRegistry) -> None:
    """Verify that attempting to get an unresolved factor raises UnresolvedFactorError."""
    with pytest.raises(UnresolvedFactorError) as exc_info:
        sample_registry.get_factor("transport", "petrol")
    assert "unresolved" in str(exc_info.value).lower()


def test_registry_missing_factor_raises(sample_registry: EmissionFactorRegistry) -> None:
    """Verify that looking for an unknown activity/fuel raises FactorNotFoundError."""
    with pytest.raises(FactorNotFoundError):
        sample_registry.get_factor("aviation", "jet_fuel")


def test_registry_incompatible_unit_raises(sample_registry: EmissionFactorRegistry) -> None:
    """Verify that mismatch between requested and normalized unit raises IncompatibleUnitError."""
    with pytest.raises(IncompatibleUnitError):
        sample_registry.get_factor(
            "electricity", "grid_electricity", "India", expected_unit="kgCO2/MJ"
        )


def test_real_factors_yaml_loading() -> None:
    """Test loading factors from actual factors.yaml file."""
    yaml_path = Path("data/emission_factors/factors.yaml")
    registry = EmissionFactorRegistry.from_yaml(yaml_path)
    assert len(registry.all_factors) >= 4

    elec = registry.get_factor("electricity", "grid_electricity", "India")
    assert elec.status == "verified"
    assert elec.value == 0.716

    lpg = registry.get_factor("cooking_heating", "lpg")
    assert lpg.status == "verified"
    assert elec.boundary == "indirect_scope_2"
    assert lpg.boundary == "direct_scope_1"


def test_region_matching_is_case_insensitive() -> None:
    """India casing resolves the same configured electricity factor."""
    registry = EmissionFactorRegistry.from_yaml(Path("data/emission_factors/factors.yaml"))

    title_case = registry.get_factor("electricity", "grid_electricity", "India")
    lower_case = registry.get_factor("electricity", "grid_electricity", "india")

    assert title_case.id == lower_case.id
    assert title_case.value == lower_case.value


def test_registry_activity_unit_mismatch_raises() -> None:
    """Verify that mismatch between expected and configured activity unit raises IncompatibleUnitError."""
    yaml_path = Path("data/emission_factors/factors.yaml")
    registry = EmissionFactorRegistry.from_yaml(yaml_path)
    with pytest.raises(IncompatibleUnitError):
        registry.get_factor(
            "electricity",
            "grid_electricity",
            "India",
            expected_activity_unit="MWh",  # Configured is kWh
        )
