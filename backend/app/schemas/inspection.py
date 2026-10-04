"""
Inspection Pydantic Schemas.

Maps to database table:
- public.service_inspections
"""

from datetime import datetime
from decimal import Decimal
import re
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator


class InspectionCreate(BaseModel):
    """
    Mechanic input for submitting service inspection findings.
    Strictly forbids client-injected identity or booking parameters.
    """
    model_config = ConfigDict(extra="forbid")

    findings: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Detailed findings, vehicle diagnostic notes, and repair recommendations",
    )
    vehicle_condition: str | None = Field(
        default=None,
        max_length=500,
        description="Optional summary of overall vehicle physical or mechanical condition",
    )
    estimated_additional_cost: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        description="Estimated monetary cost for additional repairs discovered (>= 0)",
    )
    evidence_file_paths: list[str] = Field(
        default=[],
        description="Optional storage object paths within service-evidence bucket",
    )

    @field_validator("findings")
    @classmethod
    def validate_findings_non_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Inspection findings must not be empty.")
        return stripped


class InspectionUpdate(BaseModel):
    """
    Assigned mechanic update schema for existing inspection findings.
    Strictly forbids client-injected identity, booking_id, or mechanic_id.
    """
    model_config = ConfigDict(extra="forbid")

    findings: str | None = Field(
        default=None,
        min_length=1,
        max_length=5000,
        description="Updated diagnostic findings",
    )
    vehicle_condition: str | None = Field(
        default=None,
        max_length=500,
        description="Updated vehicle condition summary",
    )
    estimated_additional_cost: Decimal | None = Field(
        default=None,
        ge=Decimal("0.00"),
        description="Updated estimated additional cost (>= 0)",
    )
    evidence_file_paths: list[str] | None = Field(
        default=None,
        description="Updated storage paths for evidence",
    )

    @field_validator("findings")
    @classmethod
    def validate_findings_not_blank(cls, v: str | None) -> str | None:
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("Findings must not be empty if provided.")
            return stripped
        return v


class InspectionResponse(BaseModel):
    """Authoritative inspection details response schema."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    mechanic_id: uuid.UUID
    findings: str
    vehicle_condition: str | None = None
    estimated_additional_cost: Decimal
    evidence_file_paths: list[str] = Field(default=[])
    created_at: datetime
    updated_at: datetime
