"""
Centralized Booking State Machine.

Defines the single authoritative state transition graph, lifecycle rules,
and role-based transition authorization for all booking status changes in the platform.
"""

from enum import Enum
from typing import Any
from app.core.logging import get_logger
from app.schemas.booking import BookingStatus

logger = get_logger("services.booking_state_machine")


class BookingStateMachine:
    """
    Authoritative state machine governing booking lifecycle progression.

    Rules:
    - 14 database status values are supported.
    - Transitions must follow the defined directed graph.
    - 'cancelled' is a strict terminal state.
    - Only authorized actors (customer owner, assigned mechanic, admin/support) can execute transitions.
    - Transition to 'paid' is reserved for payment processing and blocked from generic status endpoints.
    """

    # Authoritative forward transition graph
    VALID_TRANSITIONS: dict[BookingStatus, set[BookingStatus]] = {
        BookingStatus.PENDING: {
            BookingStatus.SEARCHING_MECHANIC,
            BookingStatus.MECHANIC_ASSIGNED,
            BookingStatus.CANCELLED,
        },
        BookingStatus.SEARCHING_MECHANIC: {
            BookingStatus.MECHANIC_ASSIGNED,
            BookingStatus.CANCELLED,
        },
        BookingStatus.MECHANIC_ASSIGNED: {
            BookingStatus.MECHANIC_EN_ROUTE,
            BookingStatus.CANCELLED,
        },
        BookingStatus.MECHANIC_EN_ROUTE: {
            BookingStatus.MECHANIC_ARRIVED,
            BookingStatus.CANCELLED,
        },
        BookingStatus.MECHANIC_ARRIVED: {
            BookingStatus.INSPECTION,
            BookingStatus.CANCELLED,
        },
        BookingStatus.INSPECTION: {
            BookingStatus.AWAITING_CUSTOMER_APPROVAL,
            BookingStatus.SERVICE_IN_PROGRESS,
            BookingStatus.CANCELLED,
        },
        BookingStatus.AWAITING_CUSTOMER_APPROVAL: {
            BookingStatus.SERVICE_IN_PROGRESS,
            BookingStatus.CANCELLED,
        },
        BookingStatus.SERVICE_IN_PROGRESS: {
            BookingStatus.ADDITIONAL_WORK,
            BookingStatus.SERVICE_COMPLETED,
            BookingStatus.CANCELLED,
        },
        BookingStatus.ADDITIONAL_WORK: {
            BookingStatus.AWAITING_CUSTOMER_APPROVAL,
            BookingStatus.SERVICE_IN_PROGRESS,
            BookingStatus.CANCELLED,
        },
        BookingStatus.SERVICE_COMPLETED: {
            BookingStatus.PAYMENT_PENDING,
            BookingStatus.DISPUTED,
        },
        BookingStatus.PAYMENT_PENDING: {
            BookingStatus.PAID,
            BookingStatus.DISPUTED,
        },
        BookingStatus.PAID: {
            BookingStatus.DISPUTED,
        },
        BookingStatus.CANCELLED: set(),  # Terminal state: no outgoing transitions
        BookingStatus.DISPUTED: {
            # Only admin/support can transition out of disputed
            BookingStatus.PAID,
            BookingStatus.SERVICE_COMPLETED,
            BookingStatus.CANCELLED,
        },
    }

    # Pre-service and in-service states where customer cancellation is allowed
    CUSTOMER_CANCELLABLE_STATES: set[BookingStatus] = {
        BookingStatus.PENDING,
        BookingStatus.SEARCHING_MECHANIC,
        BookingStatus.MECHANIC_ASSIGNED,
        BookingStatus.MECHANIC_EN_ROUTE,
        BookingStatus.MECHANIC_ARRIVED,
        BookingStatus.INSPECTION,
        BookingStatus.AWAITING_CUSTOMER_APPROVAL,
        BookingStatus.SERVICE_IN_PROGRESS,
        BookingStatus.ADDITIONAL_WORK,
    }

    # States where mechanic cancellation is permitted
    MECHANIC_CANCELLABLE_STATES: set[BookingStatus] = {
        BookingStatus.MECHANIC_ASSIGNED,
        BookingStatus.MECHANIC_EN_ROUTE,
        BookingStatus.MECHANIC_ARRIVED,
        BookingStatus.INSPECTION,
        BookingStatus.AWAITING_CUSTOMER_APPROVAL,
        BookingStatus.SERVICE_IN_PROGRESS,
        BookingStatus.ADDITIONAL_WORK,
    }

    # Post-service states where customer dispute is allowed
    DISPUTABLE_STATES: set[BookingStatus] = {
        BookingStatus.SERVICE_COMPLETED,
        BookingStatus.PAYMENT_PENDING,
        BookingStatus.PAID,
    }

    # Mechanic-driven normal progression steps
    MECHANIC_PROGRESSION_TRANSITIONS: dict[BookingStatus, set[BookingStatus]] = {
        BookingStatus.MECHANIC_ASSIGNED: {BookingStatus.MECHANIC_EN_ROUTE},
        BookingStatus.MECHANIC_EN_ROUTE: {BookingStatus.MECHANIC_ARRIVED},
        BookingStatus.MECHANIC_ARRIVED: {BookingStatus.INSPECTION},
        BookingStatus.INSPECTION: {
            BookingStatus.AWAITING_CUSTOMER_APPROVAL,
            BookingStatus.SERVICE_IN_PROGRESS,
        },
        BookingStatus.AWAITING_CUSTOMER_APPROVAL: {BookingStatus.SERVICE_IN_PROGRESS},
        BookingStatus.SERVICE_IN_PROGRESS: {
            BookingStatus.ADDITIONAL_WORK,
            BookingStatus.SERVICE_COMPLETED,
        },
        BookingStatus.ADDITIONAL_WORK: {
            BookingStatus.AWAITING_CUSTOMER_APPROVAL,
            BookingStatus.SERVICE_IN_PROGRESS,
        },
        BookingStatus.SERVICE_COMPLETED: {BookingStatus.PAYMENT_PENDING},
    }

    @classmethod
    def to_enum(cls, status_val: BookingStatus | str) -> BookingStatus:
        """Coerce string or enum to BookingStatus enum."""
        if isinstance(status_val, BookingStatus):
            return status_val
        try:
            return BookingStatus(str(status_val))
        except ValueError:
            raise ValueError(f"Invalid booking status: '{status_val}'.")

    @classmethod
    def is_valid_transition(
        cls,
        current_status: BookingStatus | str,
        new_status: BookingStatus | str,
    ) -> bool:
        """Check if transition exists in the directed state graph."""
        try:
            cur = cls.to_enum(current_status)
            target = cls.to_enum(new_status)
        except ValueError:
            return False

        allowed_targets = cls.VALID_TRANSITIONS.get(cur, set())
        return target in allowed_targets

    @classmethod
    def get_allowed_transitions(
        cls,
        current_status: BookingStatus | str,
    ) -> set[BookingStatus]:
        """Return the set of valid next states from current status."""
        try:
            cur = cls.to_enum(current_status)
        except ValueError:
            return set()
        return cls.VALID_TRANSITIONS.get(cur, set()).copy()

    @classmethod
    def validate_transition(
        cls,
        current_status: BookingStatus | str,
        new_status: BookingStatus | str,
        actor_role: str,
        is_customer_owner: bool = False,
        is_assigned_mechanic: bool = False,
        reason: str | None = None,
    ) -> tuple[bool, str]:
        """
        Validate whether the given actor is authorized to perform the requested transition.

        Returns:
            (True, "") if allowed.
            (False, error_detail) with specific rejection explanation if disallowed.
        """
        try:
            cur = cls.to_enum(current_status)
            target = cls.to_enum(new_status)
        except ValueError as exc:
            return False, str(exc)

        # 1. No-op check
        if cur == target:
            return False, f"Booking is already in '{cur.value}' status."

        # 2. Check if current status is terminal
        if cur == BookingStatus.CANCELLED:
            return False, "Cannot transition from 'cancelled'; booking is in terminal state."

        # 3. Check graph transition validity
        if not cls.is_valid_transition(cur, target):
            return False, f"Invalid status transition from '{cur.value}' to '{target.value}'."

        # 4. Block direct manual transitions to 'paid' from generic status endpoint
        if target == BookingStatus.PAID and actor_role not in ["admin", "support"]:
            return False, "Transition to 'paid' is reserved for payment processing."

        # 5. Role-specific authorization
        role = actor_role.lower()

        # --- CUSTOMER ROLE ---
        if role == "customer":
            if not is_customer_owner:
                return False, "Customer does not own this booking."

            # Cancellation
            if target == BookingStatus.CANCELLED:
                if cur in cls.CUSTOMER_CANCELLABLE_STATES:
                    return True, ""
                return False, f"Customer cannot cancel booking from '{cur.value}' status."

            # Customer approval
            if cur == BookingStatus.AWAITING_CUSTOMER_APPROVAL and target == BookingStatus.SERVICE_IN_PROGRESS:
                return True, ""

            # Dispute
            if target == BookingStatus.DISPUTED:
                if cur in cls.DISPUTABLE_STATES:
                    return True, ""
                return False, f"Dispute can only be raised for completed or paid bookings (current status: '{cur.value}')."

            return False, f"Customers are not permitted to transition booking to '{target.value}'."

        # --- MECHANIC ROLE ---
        elif role == "mechanic":
            # Assignment acceptance (mechanic accepts an offered assignment)
            if target == BookingStatus.MECHANIC_ASSIGNED:
                if cur in {BookingStatus.PENDING, BookingStatus.SEARCHING_MECHANIC}:
                    return True, ""
                return False, f"Cannot accept assignment when booking is in '{cur.value}' status."

            if not is_assigned_mechanic:
                return False, "Only the assigned mechanic for this booking can update its lifecycle."

            # Cancellation
            if target == BookingStatus.CANCELLED:
                if cur in cls.MECHANIC_CANCELLABLE_STATES:
                    return True, ""
                return False, f"Mechanic cannot cancel booking from '{cur.value}' status."

            # Journey & Work Progression
            allowed_progression = cls.MECHANIC_PROGRESSION_TRANSITIONS.get(cur, set())
            if target in allowed_progression:
                return True, ""

            return False, f"Mechanic is not authorized to transition booking from '{cur.value}' to '{target.value}'."

        # --- ADMIN / SUPPORT ROLES ---
        elif role in ["admin", "support"]:
            # Admin cannot transition out of terminal cancelled state (already checked above)
            # Admin can resolve disputes
            if cur == BookingStatus.DISPUTED:
                if target in cls.VALID_TRANSITIONS[BookingStatus.DISPUTED]:
                    return True, ""
                return False, f"Disputes can only transition to 'paid', 'service_completed', or 'cancelled'."

            # Block setting paid even for admin without payment gateway context
            if target == BookingStatus.PAID:
                return False, "Transition to 'paid' is reserved for payment gateway integration."

            return True, ""

        return False, f"Role '{actor_role}' is not authorized to perform booking status transitions."
