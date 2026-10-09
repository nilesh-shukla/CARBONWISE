"""FastAPI application entry point and application factory."""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.endpoints import health, root
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.schemas.common import ErrorBody, ErrorResponse
from app.services.exceptions import EmissionFactorException

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure an instance of the FastAPI application.

    Args:
        settings: Optional Settings override for testing or environment customizations.

    Returns:
        Configured FastAPI application instance.
    """
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="A Data-Driven Estimation Model for Personalized Household Carbon Footprints Using Synthetic Lifestyle and Consumption Data.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        debug=settings.DEBUG,
    )

    # Global Exception Handlers
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle request schema validation errors with consistent JSON formatting."""
        details = [
            {
                "location": [str(loc) for loc in err.get("loc", [])],
                "message": err.get("msg"),
                "type": err.get("type"),
            }
            for err in exc.errors()
        ]
        error_payload = ErrorResponse(
            error=ErrorBody(
                code="VALIDATION_ERROR",
                message="Request validation failed.",
                details=details,
            )
        )
        return JSONResponse(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            content=error_payload.model_dump(),
        )

    @app.exception_handler(EmissionFactorException)
    async def emission_factor_exception_handler(
        request: Request, exc: EmissionFactorException
    ) -> JSONResponse:
        """Handle domain errors with consistent JSON formatting."""
        error_payload = ErrorResponse(
            error=ErrorBody(
                code=exc.code,
                message=exc.message,
                details=None,
            )
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload.model_dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """Handle HTTP exceptions with consistent JSON formatting."""
        code_map = {
            status.HTTP_404_NOT_FOUND: "NOT_FOUND",
            status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
            status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
            status.HTTP_403_FORBIDDEN: "FORBIDDEN",
            status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
        }
        code = code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
        message = str(exc.detail) if exc.detail else "An HTTP error occurred."
        error_payload = ErrorResponse(
            error=ErrorBody(
                code=code,
                message=message,
                details=None,
            )
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload.model_dump(),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle unexpected unhandled server exceptions."""
        logger.exception("Unhandled server exception: %s", exc)
        error_payload = ErrorResponse(
            error=ErrorBody(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected server error occurred.",
                details=None,
            )
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_payload.model_dump(),
        )

    # Base and API routes
    app.include_router(root.router)
    app.include_router(health.router)
    app.include_router(api_router, prefix=settings.API_V1_STR)

    return app


app = create_app()
