"""
Matching and Real-Time Service Operations Schemas (Phase 11).

Defines Pydantic models for:
- Mechanic availability states
- Service capability matching
- Explainable matching score components and breakdown
- Candidate ranking and routing ETA responses
- Matching session lifecycle and admin audit representations
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
import uuid
from pydantic import BaseModel, Field


class MechanicAvailabilityStatus(str, Enum):
    """Operational availability states for a mechanic profile."""
    OFFLINE = "offline"
    AVAILABLE = "available"
    BUSY = "busy"
    ON_JOB = "on_job"
    PAUSED = "paused"
    SUSPENDED = "suspended"


class MatchingScoreBreakdown(BaseModel):
    """Explainable component breakdown of the composite matching score."""
    distance_score: float = Field(..., ge=0.0, le=1.0, description="Normalized proximity score (0-1)")
    availability_score: float = Field(..., ge=0.0, le=1.0, description="Normalized availability score (0-1)")
    rating_score: float = Field(..., ge=0.0, le=1.0, description="Bayesian smoothed rating score (0-1)")
    reliability_score: float = Field(..., ge=0.0, le=1.0, description="Historical completion reliability score (0-1)")
    workload_score: float = Field(..., ge=0.0, le=1.0, description="Active workload penalty/capacity score (0-1)")
    acceptance_score: float = Field(..., ge=0.0, le=1.0, description="Historical offer acceptance rate score (0-1)")
    total_score: float = Field(..., ge=0.0, le=1.0, description="Deterministic weighted composite score (0-1)")


class CandidateMechanic(BaseModel):
    """A scored candidate mechanic discovered for a booking."""
    mechanic_id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    business_name: str | None = None
    avatar_url: str | None = None
    experience_years: int = 0
    average_rating: float = 0.0
    total_completed_jobs: int = 0
    geodesic_distance_km: float = Field(..., description="PostGIS straight-line spheroid distance in km")
    service_radius_km: float
    road_distance_km: float | None = Field(None, description="Road network distance in km (from routing provider)")
    estimated_arrival_minutes: int | None = Field(None, description="Road transit ETA in minutes")
    active_workload_count: int = 0
    score: float = Field(..., ge=0.0, le=1.0)
    score_breakdown: MatchingScoreBreakdown
    eligibility_notes: list[str] = Field(default_factory=list)


class MatchingSessionResponse(BaseModel):
    """State and explainability metadata for a booking's matching session."""
    session_id: uuid.UUID
    booking_id: uuid.UUID
    status: str
    candidate_count: int
    current_attempt: int
    max_attempts: int
    selected_mechanic_id: uuid.UUID | None = None
    candidates: list[CandidateMechanic] = Field(default_factory=list)
    failure_reason: str | None = None
    started_at: datetime
    completed_at: datetime | None = None


class OfferAssignmentRequest(BaseModel):
    """Dispatch an offer to a candidate mechanic."""
    booking_id: uuid.UUID
    mechanic_id: uuid.UUID | None = Field(None, description="Optional explicit candidate override; if None, top-ranked is chosen")


class OfferResponse(BaseModel):
    """Details of an offered job assignment."""
    assignment_id: uuid.UUID
    booking_id: uuid.UUID
    mechanic_id: uuid.UUID
    assignment_status: str
    expires_at: datetime | None = None
    attempt_number: int = 1
    match_score: float | None = None
    distance_km: float | None = None
    estimated_arrival_minutes: int | None = None


class RejectAssignmentRequest(BaseModel):
    """Mechanic rejection reason."""
    reason: str | None = Field(None, max_length=500, description="Optional rejection reason")


class MechanicCapabilityCreate(BaseModel):
    """Create capability for a mechanic."""
    category_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None


class MechanicCapabilityResponse(BaseModel):
    """Mechanic capability representation."""
    id: uuid.UUID
    mechanic_id: uuid.UUID
    category_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    is_active: bool
    created_at: datetime
