"""
Payout Account Verification State Machine (Phase 8.8).

Enforces verified state transitions for mechanic payout accounts:
- not_configured: Initial default state before details are submitted.
- pending: Bank details entered, awaiting verification initiation.
- submitted: Verification request (e.g. Penny Drop) sent to banking provider.
- verified: Account successfully verified by provider or authorized admin.
- failed: Account verification rejected (e.g. invalid IFSC or name mismatch).
- suspended: Account frozen or deactivated due to risk or mechanic replacement.
"""

from fastapi import HTTPException, status
from app.core.logging import get_logger
from app.schemas.payout_account import PayoutAccountVerificationStatus

logger = get_logger("services.payout_account_state_machine")


class PayoutAccountStateMachine:
    """Governs allowed verification lifecycle transitions."""

    ALLOWED_TRANSITIONS: dict[
        PayoutAccountVerificationStatus, set[PayoutAccountVerificationStatus]
    ] = {
        PayoutAccountVerificationStatus.NOT_CONFIGURED: {
            PayoutAccountVerificationStatus.PENDING,
            PayoutAccountVerificationStatus.SUBMITTED,
        },
        PayoutAccountVerificationStatus.PENDING: {
            PayoutAccountVerificationStatus.SUBMITTED,
            PayoutAccountVerificationStatus.VERIFIED,  # Admin / Test mock only
            PayoutAccountVerificationStatus.FAILED,
            PayoutAccountVerificationStatus.SUSPENDED,
        },
        PayoutAccountVerificationStatus.SUBMITTED: {
            PayoutAccountVerificationStatus.VERIFIED,
            PayoutAccountVerificationStatus.FAILED,
            PayoutAccountVerificationStatus.SUSPENDED,
            PayoutAccountVerificationStatus.PENDING,  # Re-edit
        },
        PayoutAccountVerificationStatus.VERIFIED: {
            PayoutAccountVerificationStatus.SUSPENDED,
            PayoutAccountVerificationStatus.PENDING,  # Details replaced
        },
        PayoutAccountVerificationStatus.FAILED: {
            PayoutAccountVerificationStatus.PENDING,
            PayoutAccountVerificationStatus.SUBMITTED,
            PayoutAccountVerificationStatus.SUSPENDED,
        },
        PayoutAccountVerificationStatus.SUSPENDED: {
            PayoutAccountVerificationStatus.PENDING,
            PayoutAccountVerificationStatus.VERIFIED,  # Admin reactivation
        },
    }

    @classmethod
    def can_transition(
        cls,
        current_status: str | PayoutAccountVerificationStatus,
        target_status: str | PayoutAccountVerificationStatus,
    ) -> bool:
        """Return True if transition from current to target is allowed."""
        c = (
            current_status
            if isinstance(current_status, PayoutAccountVerificationStatus)
            else PayoutAccountVerificationStatus(str(current_status).lower())
        )
        t = (
            target_status
            if isinstance(target_status, PayoutAccountVerificationStatus)
            else PayoutAccountVerificationStatus(str(target_status).lower())
        )
        if c == t:
            return True
        return t in cls.ALLOWED_TRANSITIONS.get(c, set())

    @classmethod
    def enforce_transition(
        cls,
        current_status: str | PayoutAccountVerificationStatus,
        target_status: str | PayoutAccountVerificationStatus,
        actor_role: str = "system",
    ) -> PayoutAccountVerificationStatus:
        """
        Validate and return target status.
        Guards against unauthorized client self-verification:
        Mechanics can NEVER mark themselves as verified directly.
        """
        c = (
            current_status
            if isinstance(current_status, PayoutAccountVerificationStatus)
            else PayoutAccountVerificationStatus(str(current_status).lower())
        )
        t = (
            target_status
            if isinstance(target_status, PayoutAccountVerificationStatus)
            else PayoutAccountVerificationStatus(str(target_status).lower())
        )

        # Security guard: mechanic role cannot self-verify
        if t == PayoutAccountVerificationStatus.VERIFIED and actor_role == "mechanic":
            logger.warning(
                "mechanic_self_verification_prohibited",
                current_status=c.value,
                target_status=t.value,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Mechanics cannot self-verify bank accounts. Verification requires provider confirmation.",
            )

        if not cls.can_transition(c, t):
            logger.warning(
                "invalid_account_verification_transition",
                current_status=c.value,
                target_status=t.value,
                actor_role=actor_role,
            )
            allowed = [s.value for s in cls.ALLOWED_TRANSITIONS.get(c, set())]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid verification transition from '{c.value}' to '{t.value}'. Allowed: {allowed}",
            )

        return t


class SettlementBatchStateMachine:
    """Governs allowed settlement batch lifecycle transitions (Phase 8.9 Maker-Checker)."""

    from app.schemas.payout_account import SettlementBatchStatus

    ALLOWED_TRANSITIONS: dict[
        SettlementBatchStatus, set[SettlementBatchStatus]
    ] = {
        SettlementBatchStatus.DRAFT: {
            SettlementBatchStatus.APPROVAL_REQUIRED,
            SettlementBatchStatus.APPROVED,  # When policy does not require checker
            SettlementBatchStatus.CANCELLED,
        },
        SettlementBatchStatus.APPROVAL_REQUIRED: {
            SettlementBatchStatus.APPROVED,
            SettlementBatchStatus.REJECTED,
            SettlementBatchStatus.CANCELLED,
        },
        SettlementBatchStatus.APPROVED: {
            SettlementBatchStatus.SUBMITTED,
            SettlementBatchStatus.PROCESSING,
            SettlementBatchStatus.CANCELLED,
        },
        SettlementBatchStatus.REJECTED: set(),  # Terminal state
        SettlementBatchStatus.SUBMITTED: {
            SettlementBatchStatus.PROCESSING,
            SettlementBatchStatus.FAILED,
        },
        SettlementBatchStatus.PROCESSING: {
            SettlementBatchStatus.COMPLETED,
            SettlementBatchStatus.PARTIALLY_FAILED,
            SettlementBatchStatus.FAILED,
        },
        SettlementBatchStatus.COMPLETED: set(),  # Terminal state
        SettlementBatchStatus.PARTIALLY_FAILED: set(),  # Terminal state
        SettlementBatchStatus.FAILED: set(),  # Terminal state
        SettlementBatchStatus.CANCELLED: set(),  # Terminal state
    }

    @classmethod
    def can_transition(
        cls,
        current_status: str | SettlementBatchStatus,
        target_status: str | SettlementBatchStatus,
    ) -> bool:
        from app.schemas.payout_account import SettlementBatchStatus

        c = (
            current_status
            if isinstance(current_status, SettlementBatchStatus)
            else SettlementBatchStatus(str(current_status).lower())
        )
        t = (
            target_status
            if isinstance(target_status, SettlementBatchStatus)
            else SettlementBatchStatus(str(target_status).lower())
        )
        if c == t:
            return True
        return t in cls.ALLOWED_TRANSITIONS.get(c, set())

    @classmethod
    def enforce_transition(
        cls,
        current_status: str | SettlementBatchStatus,
        target_status: str | SettlementBatchStatus,
        actor_role: str = "admin",
    ) -> SettlementBatchStatus:
        from app.schemas.payout_account import SettlementBatchStatus

        c = (
            current_status
            if isinstance(current_status, SettlementBatchStatus)
            else SettlementBatchStatus(str(current_status).lower())
        )
        t = (
            target_status
            if isinstance(target_status, SettlementBatchStatus)
            else SettlementBatchStatus(str(target_status).lower())
        )

        # Security guard: mechanics and customers can NEVER alter batch status
        if actor_role in ["mechanic", "customer"]:
            logger.warning(
                "unauthorized_settlement_batch_transition_attempt",
                actor_role=actor_role,
                current_status=c.value,
                target_status=t.value,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Only authorized administrators or finance operations can manage settlement batches.",
            )

        if not cls.can_transition(c, t):
            logger.warning(
                "invalid_settlement_batch_transition",
                current_status=c.value,
                target_status=t.value,
                actor_role=actor_role,
            )
            allowed = [s.value for s in cls.ALLOWED_TRANSITIONS.get(c, set())]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid settlement batch transition from '{c.value}' to '{t.value}'. Allowed: {allowed}",
            )

        return t

    validate_transition = enforce_transition

    @classmethod
    def validate_financial_mutation(cls, batch_status: str | SettlementBatchStatus) -> None:
        """
        Enforces Phase 8.9 Section 8 financial immutability rule:
        Once a settlement batch enters approved, submitted, processing, or completed,
        its financial amounts and ledger membership are strictly immutable.
        """
        from app.schemas.payout_account import SettlementBatchStatus

        st = (
            batch_status
            if isinstance(batch_status, SettlementBatchStatus)
            else SettlementBatchStatus(str(batch_status).lower())
        )
        immutable_statuses = {
            SettlementBatchStatus.APPROVED,
            SettlementBatchStatus.SUBMITTED,
            SettlementBatchStatus.PROCESSING,
            SettlementBatchStatus.COMPLETED,
        }
        if st in immutable_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Financial mutation rejected: Settlement batch records in status '{st.value}' are strictly immutable.",
            )

