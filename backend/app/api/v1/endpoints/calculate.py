"""Calculation endpoint for deterministic monthly household carbon footprint."""

from fastapi import APIRouter, Depends, status

from app.schemas.calculate import CalculationRequest, CalculationResponse
from app.services.calculator import CarbonCalculatorService, get_calculator_service

router = APIRouter()


@router.post(
    "/calculate",
    response_model=CalculationResponse,
    status_code=status.HTTP_200_OK,
    summary="Calculate Household Monthly Carbon Footprint",
    description=(
        "Computes deterministic monthly carbon footprint for supported consumption activities "
        "(grid electricity and LPG) using cited emission factors. Unsupported or unresolved activities "
        "(petrol and diesel) are itemized as not_calculated."
    ),
)
async def calculate_footprint(
    request: CalculationRequest,
    calculator: CarbonCalculatorService = Depends(get_calculator_service),
) -> CalculationResponse:
    """Execute deterministic calculation from validated monthly activity data."""
    return calculator.calculate(request)
