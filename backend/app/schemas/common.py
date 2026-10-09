"""Common schemas including standardized error response contracts."""

from typing import Any, List, Optional
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Detailed validation or processing error item."""

    location: Optional[List[str]] = Field(default=None, description="Location of the error in the request")
    message: str = Field(..., description="Error message explaining the issue")
    type: Optional[str] = Field(default=None, description="Machine-readable error type identifier")


class ErrorBody(BaseModel):
    """Structured body for error responses."""

    code: str = Field(..., description="High-level machine-readable error code")
    message: str = Field(..., description="Human-readable description of the error")
    details: Optional[List[Any]] = Field(default=None, description="Specific error details or validation findings")


class ErrorResponse(BaseModel):
    """Standardized top-level wrapper for all non-2xx responses."""

    error: ErrorBody
