"""Health check response schema."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Schema representing application health check output."""

    status: str = Field(default="healthy", description="Current operating status of the service")
    app_name: str = Field(..., description="Name of the application")
    version: str = Field(..., description="Current version of the application")
    environment: str = Field(..., description="Runtime environment (e.g., development, production)")
