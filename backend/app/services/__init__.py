"""Services package for emission factor registry and deterministic carbon calculations."""

from app.services.calculator import CarbonCalculatorService, get_calculator_service
from app.services.exceptions import (
    CalculationError,
    EmissionFactorException,
    FactorNotFoundError,
    IncompatibleUnitError,
    UnresolvedFactorError,
)
from app.services.registry import (
    EmissionFactorRecord,
    EmissionFactorRegistry,
    get_registry,
)

__all__ = [
    "CalculationError",
    "CarbonCalculatorService",
    "EmissionFactorException",
    "EmissionFactorRecord",
    "EmissionFactorRegistry",
    "FactorNotFoundError",
    "IncompatibleUnitError",
    "UnresolvedFactorError",
    "get_calculator_service",
    "get_registry",
]
