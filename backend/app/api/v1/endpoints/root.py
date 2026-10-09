"""Root information endpoint."""

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.root import RootResponse

router = APIRouter()


@router.get(
    "/",
    response_model=RootResponse,
    summary="API Root Information",
    description="Returns a short description of the service and interactive documentation link.",
)
async def root_info(settings: Settings = Depends(get_settings)) -> RootResponse:
    """Return introductory metadata and link to documentation."""
    return RootResponse(
        name=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="A Data-Driven Estimation Model for Personalized Household Carbon Footprints Using Synthetic Lifestyle and Consumption Data.",
        docs_url="/docs",
    )
