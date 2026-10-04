"""
Payout Lifecycle State Machine (Phase 8.7).

Authoritative governor for mechanic payout lifecycle transitions:
- pending: initial ledger creation awaiting payment verification / dispute hold
- eligible: booking payment confirmed settled, payout funds cleared for disbursement
- processing: transfer batch or provider payout instruction dispatched
- paid: funds successfully disbursed and settled to mechanic
- failed: transfer rejected by provider or beneficiary account invalid
- reversed: payout cancelled / clawed back due to customer refund or chargeback
- cancelled: booking cancelled or voided before disbursement

Enforces strict unidirectional and recoverable transitions. Rejects arbitrary status jumps.
"""

from enum import Enum
from fastapi import HTTPException, status
from app.core.logging import get_logger

logger = get_logger("services.payout_state_machine")


class PayoutStatus(str, Enum):
    """Authoritative payout lifecycle status states matching DB constraint."""
    PENDING = "pending"
    ELIGIBLE = "eligible"
    PROCESSING = "processing"
    PAID = "paid"
    FAILED = "failed"
    REVERSED = "reversed"
    CANCELLED = "cancelled"


class PayoutStateMachine:
    """Encapsulates validated state transitions for mechanic payout ledger entries."""

    # Allowed transitions map: Current State -> Set of Permitted Next States
    ALLOWED_TRANSITIONS: dict[PayoutStatus, set[PayoutStatus]] = {
        PayoutStatus.PENDING: {
            PayoutStatus.ELIGIBLE,
            PayoutStatus.CANCELLED,
            PayoutStatus.REVERSED,
        },
        PayoutStatus.ELIGIBLE: {
            PayoutStatus.PROCESSING,
            PayoutStatus.REVERSED,
            PayoutStatus.CANCELLED,
        },
        PayoutStatus.PROCESSING: {
            PayoutStatus.PAID,
            PayoutStatus.FAILED,
            PayoutStatus.REVERSED,
        },
        PayoutStatus.PAID: {
            PayoutStatus.REVERSED,
        },
        PayoutStatus.FAILED: {
            PayoutStatus.PROCESSING,  # Retry allowed
            PayoutStatus.CANCELLED,
            PayoutStatus.REVERSED,
        },
        PayoutStatus.REVERSED: set(),  # Terminal state
        PayoutStatus.CANCELLED: set(), # Terminal state
    }

    @classmethod
    def to_enum(cls, status_val: str | PayoutStatus) -> PayoutStatus:
        """Coerce string to PayoutStatus enum or raise 400 Bad Request."""
        if isinstance(status_val, PayoutStatus):
            return status_val
        try:
            return PayoutStatus(str(status_val).lower())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid payout status: '{status_val}'. Allowed: {[s.value for s in PayoutStatus]}",
            )

    @classmethod
    def can_transition(
        cls,
        current_status: str | PayoutStatus,
        target_status: str | PayoutStatus,
    ) -> bool:
        """Check whether transition from current_status to target_status is permitted."""
        c = cls.to_enum(current_status)
        t = cls.to_enum(target_status)
        if c == t:
            return True  # Idempotent no-op
        return t in cls.ALLOWED_TRANSITIONS.get(c, set())

    @classmethod
    def validate_transition(
        cls,
        current_status: str | PayoutStatus,
        target_status: str | PayoutStatus,
    ) -> tuple[bool, str | None]:
        """
        Validate transition and return (is_valid, error_message).
        """
        c = cls.to_enum(current_status)
        t = cls.to_enum(target_status)
        if c == t:
            return True, None

        allowed = cls.ALLOWED_TRANSITIONS.get(c, set())
        if t not in allowed:
            msg = (
                f"Invalid payout transition from '{c.value}' to '{t.value}'. "
                f"Permitted next states: {[s.value for s in allowed] or ['None (terminal state)']}"
            )
            return False, msg
        return True, None

    @classmethod
    def enforce_transition(
        cls,
        current_status: str | PayoutStatus,
        target_status: str | PayoutStatus,
    ) -> PayoutStatus:
        """
        Validate transition, raising HTTPException(400) if invalid.
        Returns target PayoutStatus enum.
        """
        valid, err = cls.validate_transition(current_status, target_status)
        if not valid:
            logger.warning(
                "payout_invalid_state_transition_attempt",
                current_status=str(current_status),
                target_status=str(target_status),
                error=err,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=err,
            )
        return cls.to_enum(target_status)
