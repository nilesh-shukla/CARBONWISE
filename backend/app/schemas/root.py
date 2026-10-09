"""Root endpoint response schema."""

from pydantic import BaseModel, Field


class RootResponse(BaseModel):
    """Schema representing root endpoint summary output."""

    name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    description: str = Field(..., description="Short summary of the API purpose")
    docs_url: str = Field(..., description="Relative link to interactive API documentation")
