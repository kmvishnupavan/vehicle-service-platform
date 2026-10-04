"""
Common API Schemas.

Standard response formats for health checks, pagination, and unified error structures.
"""

from typing import Any
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Standard health check response schema."""
    status: str = Field(default="ok", description="Server health status")


class DatabaseHealthResponse(BaseModel):
    """Database connectivity health check response schema."""
    status: str = Field(..., description="Connection status: connected or disconnected")
    healthy: bool = Field(..., description="Boolean flag indicating database responsiveness")
    error: str | None = Field(default=None, description="Error description if unhealthy")


class LivenessResponse(BaseModel):
    """Liveness probe response schema."""
    status: str = Field(default="ok", description="Process liveness state")
    timestamp: str = Field(..., description="ISO UTC timestamp of probe")


class ReadinessResponse(BaseModel):
    """Readiness probe response schema."""
    status: str = Field(..., description="Service readiness state: ready or not_ready")
    environment: str = Field(..., description="Active environment mode")
    checks: dict[str, str] = Field(..., description="Subsystem health status breakdown")
    timestamp: str = Field(..., description="ISO UTC timestamp of probe")


class ErrorResponse(BaseModel):
    """Standardized API error response schema."""
    detail: str = Field(..., description="Human-readable error explanation")
    error_code: str | None = Field(default=None, description="Machine-readable error classification code")
    request_id: str | None = Field(default=None, description="Unique trace identifier for request")


class MessageResponse(BaseModel):
    """Generic informational message response schema."""
    message: str = Field(..., description="Informational message")
    data: dict[str, Any] | None = Field(default=None, description="Optional attached payload")
