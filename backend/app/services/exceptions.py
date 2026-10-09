"""Domain exceptions for emission factors and calculation services."""


class EmissionFactorException(Exception):
    """Base exception for emission factor and calculation errors."""

    def __init__(
        self,
        message: str,
        code: str = "FACTOR_ERROR",
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class FactorNotFoundError(EmissionFactorException):
    """Raised when an emission factor cannot be found in the registry."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="FACTOR_NOT_FOUND", status_code=404)


class UnresolvedFactorError(EmissionFactorException):
    """Raised when attempting to use a factor whose status is unresolved."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="UNRESOLVED_FACTOR", status_code=422)


class IncompatibleUnitError(EmissionFactorException):
    """Raised when activity units are incompatible with the emission factor."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="INCOMPATIBLE_UNIT", status_code=422)


class CalculationError(EmissionFactorException):
    """Raised when a calculation cannot be performed due to business rules."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="CALCULATION_ERROR", status_code=400)
