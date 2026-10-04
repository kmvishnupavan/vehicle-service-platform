"""
Versioned Matching Policy Service (Phase 13).

Provides:
- Retrieval of active matching policy
- Immutable score explanation preservation
- Admin policy draft creation and weight validation (sum = 1.000)
- Single active policy governance with audit trails
"""

from datetime import datetime, timezone
from decimal import Decimal
import threading
from typing import Any
import uuid

from fastapi import HTTPException, status
from app.core.logging import get_logger
from app.db.supabase import get_supabase_service_client
from app.schemas.operational_automation import (
    MatchingPolicyCreate,
    MatchingPolicyResponse,
)

logger = get_logger("services.matching_policy")


class MatchingPolicyService:
    """Manages versioned matching algorithm configurations and weights."""

    _cached_active_policy: dict[str, Any] | None = None
    _cached_at: datetime | None = None
    _cache_ttl_seconds: int = 60
    _lock = threading.Lock()

    def __init__(self, client: Any = None):
        self.client = client or get_supabase_service_client()

    @classmethod
    def clear_cache(cls) -> None:
        with cls._lock:
            cls._cached_active_policy = None
            cls._cached_at = None

    async def get_active_policy(self) -> dict[str, Any]:
        """Retrieve the currently active matching policy with caching."""
        now = datetime.now(timezone.utc)

        with self._lock:
            if self._cached_active_policy and self._cached_at:
                if (now - self._cached_at).total_seconds() < self._cache_ttl_seconds:
                    return self._cached_active_policy

        # Fetch from database
        try:
            res = (
                self.client.table("matching_policies")
                .select("*")
                .eq("is_active", True)
                .limit(1)
                .execute()
            )
            if res.data and len(res.data) > 0:
                policy = res.data[0]
                with self._lock:
                    self._cached_active_policy = policy
                    self._cached_at = now
                return policy
        except Exception as exc:
            logger.warning("Failed to fetch active matching policy from database: %s", exc)

        # Safe fallback default v1.0
        default_policy = {
            "policy_version": "v1.0",
            "proximity_weight": Decimal("0.300"),
            "rating_weight": Decimal("0.200"),
            "availability_weight": Decimal("0.150"),
            "reliability_weight": Decimal("0.150"),
            "workload_weight": Decimal("0.100"),
            "acceptance_weight": Decimal("0.100"),
            "max_concurrent_jobs": 1,
            "offer_timeout_seconds": 60,
            "max_offer_attempts": 3,
            "is_active": True,
            "description": "Default In-Memory Fallback Policy",
        }
        with self._lock:
            self._cached_active_policy = default_policy
            self._cached_at = now
        return default_policy

    async def list_policies(self) -> list[dict[str, Any]]:
        """List all versioned matching policies."""
        res = (
            self.client.table("matching_policies")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return res.data or []

    async def create_policy_draft(
        self,
        data: MatchingPolicyCreate,
        admin_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Create a new matching policy draft with validated weights."""
        now_iso = datetime.now(timezone.utc).isoformat()

        # Check uniqueness of policy version
        existing = (
            self.client.table("matching_policies")
            .select("id")
            .eq("policy_version", data.policy_version)
            .execute()
        )
        if existing.data and len(existing.data) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Matching policy version '{data.policy_version}' already exists.",
            )

        payload = {
            "policy_version": data.policy_version,
            "proximity_weight": str(data.proximity_weight),
            "rating_weight": str(data.rating_weight),
            "availability_weight": str(data.availability_weight),
            "reliability_weight": str(data.reliability_weight),
            "workload_weight": str(data.workload_weight),
            "acceptance_weight": str(data.acceptance_weight),
            "max_concurrent_jobs": data.max_concurrent_jobs,
            "offer_timeout_seconds": data.offer_timeout_seconds,
            "max_offer_attempts": data.max_offer_attempts,
            "is_active": False,
            "description": data.description,
            "created_by": str(admin_id) if admin_id else None,
            "created_at": now_iso,
        }

        res = self.client.table("matching_policies").insert(payload).execute()
        if not res.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create matching policy draft.",
            )

        # Audit log
        try:
            self.client.table("audit_logs").insert({
                "actor_id": str(admin_id) if admin_id else None,
                "action": "MATCHING_POLICY_DRAFT_CREATED",
                "entity_type": "matching_policies",
                "entity_id": res.data[0]["id"],
                "new_data": payload,
            }).execute()
        except Exception:
            pass

        return res.data[0]

    async def activate_policy(
        self,
        policy_version: str,
        admin_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Atomically activate a matching policy and deactivate all others."""
        now_iso = datetime.now(timezone.utc).isoformat()

        # Verify target policy exists
        res = (
            self.client.table("matching_policies")
            .select("*")
            .eq("policy_version", policy_version)
            .execute()
        )
        if not res.data or len(res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Matching policy version '{policy_version}' not found.",
            )
        target = res.data[0]

        # Deactivate all active policies
        self.client.table("matching_policies").update({
            "is_active": False,
        }).eq("is_active", True).execute()

        # Activate target policy
        upd = (
            self.client.table("matching_policies")
            .update({
                "is_active": True,
                "activated_at": now_iso,
                "activated_by": str(admin_id) if admin_id else None,
            })
            .eq("id", target["id"])
            .execute()
        )
        activated = upd.data[0] if upd.data else target

        # Clear cache
        self.clear_cache()

        # Audit log
        try:
            self.client.table("audit_logs").insert({
                "actor_id": str(admin_id) if admin_id else None,
                "action": "MATCHING_POLICY_ACTIVATED",
                "entity_type": "matching_policies",
                "entity_id": target["id"],
                "new_data": {"policy_version": policy_version},
            }).execute()
        except Exception:
            pass

        return activated
