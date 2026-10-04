"""
Mechanic Payout Ledger & Settlement Service (Phase 8.7).

Authoritative coordinator for:
- Commission policy retrieval and application
- Idempotent payout ledger creation on booking payment settlement
- Payout state machine transitions (pending, eligible, processing, paid, failed, reversed, cancelled)
- Strict Decimal monetary handling (gross, commission, deductions, net)
- Full and partial refund handling (adjustments vs reversals)
- Comprehensive audit logging matching PostgreSQL schema
- Payout summary aggregation and paginated listing
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
import uuid
from fastapi import HTTPException, status
from app.core.audit import record_audit_log, sanitize_audit_payload
from app.core.logging import get_logger
from app.db.supabase import get_supabase_service_client
from app.schemas.payout import (
    CommissionPolicyResponse,
    PayoutListResponse,
    PayoutResponse,
    PayoutSummary,
)
from app.schemas.user import AuthenticatedUser, UserRole
from app.services.payout_state_machine import PayoutStateMachine, PayoutStatus

logger = get_logger("services.payout")

DEFAULT_COMMISSION_RATE = Decimal("0.2000")  # 20% platform commission default policy


def format_decimal(val: Any) -> str:
    """Safely format numeric/string value to 2 decimal places using Decimal."""
    if val is None:
        return "0.00"
    try:
        dec = Decimal(str(val)).quantize(Decimal("0.01"))
        return f"{dec:.2f}"
    except Exception:
        return "0.00"


def parse_iso_datetime(dt_str: str | None, is_end_of_day: bool = False) -> datetime | None:
    """Parse and validate ISO date string; raises 422 if invalid."""
    if not dt_str:
        return None
    try:
        if len(dt_str) == 10 and dt_str[4] == "-" and dt_str[7] == "-":
            d = date.fromisoformat(dt_str)
            if is_end_of_day:
                return datetime(d.year, d.month, d.day, 23, 59, 59, 999999, tzinfo=timezone.utc)
            return datetime(d.year, d.month, d.day, 0, 0, 0, 0, tzinfo=timezone.utc)
        dt_clean = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(dt_clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid ISO date format: '{dt_str}'. Expected format: YYYY-MM-DD or ISO timestamp.",
        )


class PayoutProvider:
    """
    Payout processor provider abstraction (Phase 8.7).
    Provides interface for bank transfer / settlement disbursement.
    Marked strictly as TEST/MOCK provider until live RazorpayX / Stripe Connect integration.
    """

    PROVIDER_NAME = "test_simulator"

    async def create_payout(
        self,
        payout_ledger_id: uuid.UUID,
        amount: Decimal,
        currency: str = "INR",
        beneficiary_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Simulate payout dispatch with external provider."""
        return {
            "status": "processing",
            "provider": self.PROVIDER_NAME,
            "provider_payout_id": f"pout_sim_{uuid.uuid4().hex[:12]}",
            "amount": float(amount),
            "currency": currency,
            "simulated": True,
        }


class PayoutService:
    """Authoritative service for mechanic payouts, commission policies, and settlement."""

    def __init__(self, client=None, provider: PayoutProvider | None = None):
        self.client = client or get_supabase_service_client()
        self.provider = provider or PayoutProvider()

    async def resolve_mechanic_id(
        self,
        current_user: AuthenticatedUser,
        target_mechanic_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """
        Derive authoritative mechanic_profile_id from user session.
        - Mechanic users: Strictly locked to their own mechanic_profile.id. Client query param cannot override.
        - Admin/Support: Can inspect a specific mechanic via target_mechanic_id.
        - Customer users: Rejected with 403 Forbidden.
        """
        user_role_str = (
            current_user.role.value
            if isinstance(current_user.role, UserRole)
            else str(current_user.role)
        )

        if user_role_str == UserRole.CUSTOMER.value:
            logger.warning(
                "payouts_access_denied_customer",
                user_id=str(current_user.id),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Operation requires mechanic role.",
            )

        if user_role_str in [UserRole.ADMIN.value, UserRole.SUPPORT.value]:
            if target_mechanic_id:
                m_res = (
                    self.client.table("mechanic_profiles")
                    .select("id")
                    .eq("id", str(target_mechanic_id))
                    .execute()
                )
                if not m_res.data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Mechanic profile not found.",
                    )
                return target_mechanic_id
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query parameter 'mechanic_id' is required for admin/support users.",
            )

        if user_role_str == UserRole.MECHANIC.value:
            m_res = (
                self.client.table("mechanic_profiles")
                .select("id")
                .eq("user_id", str(current_user.id))
                .execute()
            )
            if not m_res.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Mechanic profile details not found.",
                )
            own_profile_id = uuid.UUID(str(m_res.data[0]["id"]))

            if target_mechanic_id and target_mechanic_id != own_profile_id:
                logger.warning(
                    "cross_mechanic_payout_access_attempt",
                    user_id=str(current_user.id),
                    attempted_mechanic_id=str(target_mechanic_id),
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: You can only view your own mechanic payouts.",
                )
            return own_profile_id

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Unauthorized role.",
        )

    # ==========================================================================
    # 1. COMMISSION POLICY RETRIEVAL
    # ==========================================================================

    async def get_active_commission_policy(self) -> dict[str, Any]:
        """
        Retrieve active platform commission policy from public.commission_policies.
        Falls back safely to documented default (20%) if unconfigured.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            res = (
                self.client.table("commission_policies")
                .select("*")
                .eq("is_active", True)
                .lte("effective_from", now_iso)
                .order("effective_from", desc=True)
                .limit(1)
                .execute()
            )
            if res.data and len(res.data) > 0:
                p = res.data[0]
                # Check effective_to if present
                eff_to = p.get("effective_to")
                if not eff_to or eff_to > now_iso:
                    return {
                        "policy_id": uuid.UUID(str(p["id"])),
                        "name": p.get("name", "Standard Commission"),
                        "commission_rate": Decimal(str(p["commission_rate"])),
                        "currency": p.get("currency", "INR"),
                    }
        except Exception as exc:
            logger.warning("commission_policy_query_failed_using_default", error=str(exc))

        # Default fallback
        return {
            "policy_id": None,
            "name": "Standard Platform Commission (20%)",
            "commission_rate": DEFAULT_COMMISSION_RATE,
            "currency": "INR",
        }

    # ==========================================================================
    # 2. FINANCIAL CALCULATION CORE
    # ==========================================================================

    @staticmethod
    def calculate_payout_components(
        gross_amount: Decimal,
        commission_rate: Decimal,
        deduction_amount: Decimal = Decimal("0.00"),
    ) -> tuple[Decimal, Decimal, Decimal]:
        """
        Centrally compute financial payout components using strict Decimal precision:
        commission_amount = gross_amount * commission_rate (quantized to 0.01)
        net_amount = gross_amount - commission_amount - deduction_amount
        """
        if gross_amount < Decimal("0.00"):
            raise ValueError("Gross amount cannot be negative.")
        if commission_rate < Decimal("0.00") or commission_rate > Decimal("1.00"):
            raise ValueError("Commission rate must be between 0.0 and 1.0.")
        if deduction_amount < Decimal("0.00"):
            raise ValueError("Deduction amount cannot be negative.")

        commission_amt = (gross_amount * commission_rate).quantize(Decimal("0.01"))
        net_amt = (gross_amount - commission_amt - deduction_amount).quantize(Decimal("0.01"))
        net_amt = max(net_amt, Decimal("0.00"))

        return commission_amt, deduction_amount, net_amt

    # ==========================================================================
    # 3. IDEMPOTENT PAYOUT LEDGER CREATION
    # ==========================================================================

    async def create_payout_for_booking(
        self,
        booking_id: uuid.UUID,
        payment_id: uuid.UUID | None = None,
        payment_transaction_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        actor_role: str = "system",
    ) -> dict[str, Any] | None:
        """
        Idempotently create an authoritative payout ledger entry for a completed booking.
        Guarded against concurrency by DB UNIQUE constraint on (booking_id, mechanic_id).
        """
        booking_id_str = str(booking_id)

        # 1. Idempotency Check: Existing ledger record
        existing = (
            self.client.table("mechanic_payout_ledger")
            .select("*")
            .eq("booking_id", booking_id_str)
            .execute()
        )
        if existing.data and len(existing.data) > 0:
            logger.info("payout_ledger_already_exists_for_booking", booking_id=booking_id_str)
            return existing.data[0]

        # 2. Fetch authoritative booking
        b_res = (
            self.client.table("bookings")
            .select("id, booking_number, booking_status, payment_status, subtotal, additional_charges, total_amount")
            .eq("id", booking_id_str)
            .execute()
        )
        if not b_res.data or len(b_res.data) == 0:
            logger.warning("booking_not_found_for_payout_creation", booking_id=booking_id_str)
            return None
        booking = b_res.data[0]

        # Guard: Reject cancelled or unpaid bookings
        if booking.get("booking_status") == "cancelled" or booking.get("payment_status") in ["failed", "refunded"]:
            logger.info(
                "payout_skipped_ineligible_booking_status",
                booking_id=booking_id_str,
                booking_status=booking.get("booking_status"),
                payment_status=booking.get("payment_status"),
            )
            return None

        # 3. Find assigned mechanic
        asgn_res = (
            self.client.table("mechanic_assignments")
            .select("id, mechanic_id, assignment_status")
            .eq("booking_id", booking_id_str)
            .in_("assignment_status", ["accepted", "completed"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not asgn_res.data or len(asgn_res.data) == 0:
            logger.warning("no_accepted_mechanic_assignment_for_payout", booking_id=booking_id_str)
            return None
        mechanic_id_str = str(asgn_res.data[0]["mechanic_id"])

        # 4. Fetch active commission policy
        policy = await self.get_active_commission_policy()
        comm_rate = policy["commission_rate"]

        # 5. Calculate gross and net payout amounts
        gross_amt = (
            Decimal(str(booking.get("subtotal") or "0.00")) +
            Decimal(str(booking.get("additional_charges") or "0.00"))
        )
        comm_amt, ded_amt, net_amt = self.calculate_payout_components(
            gross_amount=gross_amt,
            commission_rate=comm_rate,
            deduction_amount=Decimal("0.00"),
        )

        # 6. Lifecycle status determination
        is_paid = booking.get("payment_status") == "paid" or booking.get("booking_status") == "paid"
        now_iso = datetime.now(timezone.utc).isoformat()
        initial_status = PayoutStatus.ELIGIBLE if is_paid else PayoutStatus.PENDING
        eligible_at = now_iso if is_paid else None

        # 7. Insert ledger record with concurrency idempotency handling
        payout_id = uuid.uuid4()
        insert_payload = {
            "id": str(payout_id),
            "booking_id": booking_id_str,
            "mechanic_id": mechanic_id_str,
            "payment_id": str(payment_id) if payment_id else None,
            "payment_transaction_id": str(payment_transaction_id) if payment_transaction_id else None,
            "policy_id": str(policy["policy_id"]) if policy.get("policy_id") else None,
            "gross_amount": float(gross_amt),
            "commission_rate": float(comm_rate),
            "commission_amount": float(comm_amt),
            "deduction_amount": float(ded_amt),
            "net_amount": float(net_amt),
            "currency": "INR",
            "status": initial_status.value,
            "created_at": now_iso,
            "updated_at": now_iso,
            "eligible_at": eligible_at,
            "provider": "manual",
            "metadata": {
                "policy_name": policy["name"],
                "booking_number": booking.get("booking_number"),
            },
        }

        try:
            insert_res = self.client.table("mechanic_payout_ledger").insert(insert_payload).execute()
            created_record = insert_res.data[0] if insert_res.data else insert_payload
        except Exception as insert_err:
            # Handle unique constraint race condition
            logger.warning("payout_insert_conflict_re-querying", error=str(insert_err))
            existing_after = (
                self.client.table("mechanic_payout_ledger")
                .select("*")
                .eq("booking_id", booking_id_str)
                .execute()
            )
            if existing_after.data and len(existing_after.data) > 0:
                return existing_after.data[0]
            raise insert_err

        # 8. Record audit log
        record_audit_log(
            action="payout_created",
            entity_type="mechanic_payout_ledger",
            entity_id=str(payout_id),
            actor_id=actor_id,
            actor_role=actor_role,
            new_data={
                "booking_id": booking_id_str,
                "mechanic_id": mechanic_id_str,
                "gross_amount": float(gross_amt),
                "commission_amount": float(comm_amt),
                "net_amount": float(net_amt),
                "status": initial_status.value,
            },
        )
        if initial_status == PayoutStatus.ELIGIBLE:
            record_audit_log(
                action="payout_eligible",
                entity_type="mechanic_payout_ledger",
                entity_id=str(payout_id),
                actor_id=actor_id,
                actor_role=actor_role,
                new_data={"status": "eligible", "eligible_at": eligible_at},
            )

        return created_record

    # ==========================================================================
    # 4. REFUND & REVERSAL HANDLING
    # ==========================================================================

    async def handle_payment_refund(
        self,
        booking_id: uuid.UUID,
        refund_amount: Decimal,
        is_full_refund: bool,
        refund_id: str | None = None,
        actor_id: uuid.UUID | None = None,
        actor_role: str = "gateway_webhook",
    ) -> dict[str, Any] | None:
        """
        Reconcile payout ledger on customer refund:
        - Full refund on unsettled payout -> marks 'reversed' (or 'cancelled') with reversed_at.
        - Full refund on already paid payout -> marks 'reversed' with reversal audit record.
        - Partial refund on unsettled payout -> recalculates gross, commission, and net.
        """
        booking_id_str = str(booking_id)
        p_res = (
            self.client.table("mechanic_payout_ledger")
            .select("*")
            .eq("booking_id", booking_id_str)
            .execute()
        )
        if not p_res.data or len(p_res.data) == 0:
            logger.info("no_payout_ledger_found_for_refund_reconciliation", booking_id=booking_id_str)
            return None

        payout = p_res.data[0]
        current_status_str = payout.get("status")
        now_iso = datetime.now(timezone.utc).isoformat()
        payout_id_str = str(payout["id"])

        if is_full_refund:
            # Full Refund Reversal
            target_status = PayoutStatus.REVERSED
            # Enforce state transition
            PayoutStateMachine.enforce_transition(current_status_str, target_status)

            update_data = {
                "status": target_status.value,
                "reversed_at": now_iso,
                "metadata": {
                    **(payout.get("metadata") or {}),
                    "reversal_reason": "customer_full_refund",
                    "refund_id": refund_id,
                    "previous_status": current_status_str,
                },
            }
            upd_res = self.client.table("mechanic_payout_ledger").update(update_data).eq("id", payout_id_str).execute()
            updated_payout = upd_res.data[0] if upd_res.data else {**payout, **update_data}

            record_audit_log(
                action="payout_reversed",
                entity_type="mechanic_payout_ledger",
                entity_id=payout_id_str,
                actor_id=actor_id,
                actor_role=actor_role,
                old_data={"status": current_status_str},
                new_data={"status": "reversed", "reversed_at": now_iso, "refund_id": refund_id},
            )
            return updated_payout

        else:
            # Partial Refund Adjustment
            # If unsettled, adjust gross and net
            if current_status_str in [PayoutStatus.PENDING.value, PayoutStatus.ELIGIBLE.value]:
                old_gross = Decimal(str(payout.get("gross_amount") or "0.00"))
                comm_rate = Decimal(str(payout.get("commission_rate") or DEFAULT_COMMISSION_RATE))
                ded_amt = Decimal(str(payout.get("deduction_amount") or "0.00"))

                new_gross = max(Decimal("0.00"), old_gross - refund_amount)
                new_comm, _, new_net = self.calculate_payout_components(new_gross, comm_rate, ded_amt)

                update_data = {
                    "gross_amount": float(new_gross),
                    "commission_amount": float(new_comm),
                    "net_amount": float(new_net),
                    "metadata": {
                        **(payout.get("metadata") or {}),
                        "partial_refund_adjusted": True,
                        "refund_id": refund_id,
                        "refund_amount": float(refund_amount),
                    },
                }
                upd_res = self.client.table("mechanic_payout_ledger").update(update_data).eq("id", payout_id_str).execute()
                updated_payout = upd_res.data[0] if upd_res.data else {**payout, **update_data}

                record_audit_log(
                    action="payout_partial_refund_adjusted",
                    entity_type="mechanic_payout_ledger",
                    entity_id=payout_id_str,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    old_data={"gross_amount": float(old_gross), "net_amount": float(payout["net_amount"])},
                    new_data={"gross_amount": float(new_gross), "net_amount": float(new_net), "refund_id": refund_id},
                )
                return updated_payout
            else:
                # If already paid or processing, record metadata note without mutating settled amounts
                logger.info(
                    "partial_refund_recorded_on_settled_payout",
                    payout_id=payout_id_str,
                    refund_amount=float(refund_amount),
                )
                record_audit_log(
                    action="payout_partial_refund_post_settlement",
                    entity_type="mechanic_payout_ledger",
                    entity_id=payout_id_str,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    new_data={"refund_amount": float(refund_amount), "refund_id": refund_id},
                )
                return payout

    # ==========================================================================
    # 5. STATE MACHINE TRANSITIONS
    # ==========================================================================

    async def transition_payout_status(
        self,
        payout_id: uuid.UUID,
        target_status: PayoutStatus,
        provider_payout_id: str | None = None,
        failure_reason: str | None = None,
        actor_id: uuid.UUID | None = None,
        actor_role: str = "system",
    ) -> dict[str, Any]:
        """
        Transition payout status with strict validation against PayoutStateMachine.
        """
        p_res = (
            self.client.table("mechanic_payout_ledger")
            .select("*")
            .eq("id", str(payout_id))
            .execute()
        )
        if not p_res.data or len(p_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payout record not found.",
            )
        payout = p_res.data[0]
        current_status = PayoutStateMachine.to_enum(payout["status"])

        # Enforce transition
        valid_next = PayoutStateMachine.enforce_transition(current_status, target_status)

        now_iso = datetime.now(timezone.utc).isoformat()
        update_data: dict[str, Any] = {
            "status": valid_next.value,
            "updated_at": now_iso,
        }

        if valid_next == PayoutStatus.ELIGIBLE and not payout.get("eligible_at"):
            update_data["eligible_at"] = now_iso
        elif valid_next == PayoutStatus.PAID:
            update_data["settled_at"] = now_iso
        elif valid_next == PayoutStatus.REVERSED:
            update_data["reversed_at"] = now_iso
        elif valid_next == PayoutStatus.FAILED and failure_reason:
            update_data["failure_reason"] = failure_reason

        if provider_payout_id:
            update_data["provider_payout_id"] = provider_payout_id

        upd_res = (
            self.client.table("mechanic_payout_ledger")
            .update(update_data)
            .eq("id", str(payout_id))
            .execute()
        )
        updated_record = upd_res.data[0] if upd_res.data else {**payout, **update_data}

        # Audit logging
        record_audit_log(
            action=f"payout_{valid_next.value}",
            entity_type="mechanic_payout_ledger",
            entity_id=str(payout_id),
            actor_id=actor_id,
            actor_role=actor_role,
            old_data={"status": current_status.value},
            new_data={"status": valid_next.value, **update_data},
        )

        return updated_record

    # ==========================================================================
    # 6. QUERY & REPORTING (PAYOUT SUMMARY & LISTING)
    # ==========================================================================

    async def get_payout_summary(self, mechanic_id: uuid.UUID) -> PayoutSummary:
        """
        Aggregate authoritative financial sums across all ledger entries for a mechanic.
        """
        res = (
            self.client.table("mechanic_payout_ledger")
            .select("gross_amount, commission_amount, deduction_amount, net_amount, status")
            .eq("mechanic_id", str(mechanic_id))
            .execute()
        )
        records = res.data or []

        total_gross = Decimal("0.00")
        total_comm = Decimal("0.00")
        total_ded = Decimal("0.00")
        total_net = Decimal("0.00")

        pending_amt = Decimal("0.00")
        eligible_amt = Decimal("0.00")
        processing_amt = Decimal("0.00")
        paid_amt = Decimal("0.00")
        reversed_amt = Decimal("0.00")

        for r in records:
            gross = Decimal(str(r.get("gross_amount") or "0.00"))
            comm = Decimal(str(r.get("commission_amount") or "0.00"))
            ded = Decimal(str(r.get("deduction_amount") or "0.00"))
            net = Decimal(str(r.get("net_amount") or "0.00"))
            st = str(r.get("status", "")).lower()

            total_gross += gross
            total_comm += comm
            total_ded += ded
            total_net += net

            if st == PayoutStatus.PAID.value:
                paid_amt += net
            elif st == PayoutStatus.ELIGIBLE.value:
                eligible_amt += net
            elif st == PayoutStatus.PROCESSING.value:
                processing_amt += net
            elif st == PayoutStatus.PENDING.value:
                pending_amt += net
            elif st == PayoutStatus.REVERSED.value:
                reversed_amt += net

        return PayoutSummary(
            total_gross=format_decimal(total_gross),
            total_commission=format_decimal(total_comm),
            total_deductions=format_decimal(total_ded),
            total_net=format_decimal(total_net),
            pending_amount=format_decimal(pending_amt),
            eligible_amount=format_decimal(eligible_amt),
            processing_amount=format_decimal(processing_amt),
            paid_amount=format_decimal(paid_amt),
            reversed_amount=format_decimal(reversed_amt),
            currency="INR",
        )

    async def list_payouts(
        self,
        mechanic_id: uuid.UUID,
        from_date: str | None = None,
        to_date: str | None = None,
        status_filter: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> PayoutListResponse:
        """
        List paginated payout ledger entries for the mechanic.
        """
        safe_limit = min(max(1, limit), 100)
        safe_offset = max(0, offset)

        from_dt = parse_iso_datetime(from_date, is_end_of_day=False)
        to_dt = parse_iso_datetime(to_date, is_end_of_day=True)

        res = (
            self.client.table("mechanic_payout_ledger")
            .select("*, bookings(booking_number)")
            .eq("mechanic_id", str(mechanic_id))
            .order("created_at", desc=True)
            .execute()
        )
        records = res.data or []

        filtered_items: list[PayoutResponse] = []
        for r in records:
            r_st = str(r.get("status", "")).lower()
            if status_filter and status_filter.lower() != "all":
                if r_st != status_filter.lower():
                    continue

            created_str = r.get("created_at")
            c_dt = parse_iso_datetime(created_str) if created_str else None
            if from_dt and c_dt and c_dt < from_dt:
                continue
            if to_dt and c_dt and c_dt > to_dt:
                continue

            # Extract booking number
            booking_info = r.get("bookings")
            if isinstance(booking_info, list) and len(booking_info) > 0:
                booking_info = booking_info[0]
            b_num = (
                booking_info.get("booking_number")
                if isinstance(booking_info, dict)
                else (r.get("metadata", {}).get("booking_number"))
            )

            filtered_items.append(
                PayoutResponse(
                    id=uuid.UUID(str(r["id"])),
                    booking_id=uuid.UUID(str(r["booking_id"])),
                    mechanic_id=uuid.UUID(str(r["mechanic_id"])),
                    booking_number=b_num,
                    payment_id=uuid.UUID(str(r["payment_id"])) if r.get("payment_id") else None,
                    payment_transaction_id=uuid.UUID(str(r["payment_transaction_id"])) if r.get("payment_transaction_id") else None,
                    gross_amount=format_decimal(r.get("gross_amount")),
                    commission_rate=f"{Decimal(str(r.get('commission_rate') or '0')):.4f}",
                    commission_amount=format_decimal(r.get("commission_amount")),
                    deduction_amount=format_decimal(r.get("deduction_amount")),
                    net_amount=format_decimal(r.get("net_amount")),
                    currency=r.get("currency", "INR"),
                    status=PayoutStatus(r_st),
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                    eligible_at=r.get("eligible_at"),
                    settled_at=r.get("settled_at"),
                    reversed_at=r.get("reversed_at"),
                    provider=r.get("provider", "manual"),
                    provider_payout_id=r.get("provider_payout_id"),
                    failure_reason=r.get("failure_reason"),
                    metadata=sanitize_audit_payload(r.get("metadata") or {}),
                )
            )

        total_count = len(filtered_items)
        paginated_items = filtered_items[safe_offset : safe_offset + safe_limit]

        return PayoutListResponse(
            items=paginated_items,
            total=total_count,
            limit=safe_limit,
            offset=safe_offset,
        )

    async def get_payout_by_id(
        self,
        payout_id: uuid.UUID,
        mechanic_id: uuid.UUID | None = None,
    ) -> PayoutResponse:
        """
        Fetch single payout ledger record. If mechanic_id provided, enforces ownership.
        """
        res = (
            self.client.table("mechanic_payout_ledger")
            .select("*, bookings(booking_number)")
            .eq("id", str(payout_id))
            .execute()
        )
        if not res.data or len(res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payout record not found.",
            )
        r = res.data[0]
        if mechanic_id and str(r["mechanic_id"]) != str(mechanic_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not have permission to view this payout.",
            )

        booking_info = r.get("bookings")
        if isinstance(booking_info, list) and len(booking_info) > 0:
            booking_info = booking_info[0]
        b_num = (
            booking_info.get("booking_number")
            if isinstance(booking_info, dict)
            else (r.get("metadata", {}).get("booking_number"))
        )

        return PayoutResponse(
            id=uuid.UUID(str(r["id"])),
            booking_id=uuid.UUID(str(r["booking_id"])),
            mechanic_id=uuid.UUID(str(r["mechanic_id"])),
            booking_number=b_num,
            payment_id=uuid.UUID(str(r["payment_id"])) if r.get("payment_id") else None,
            payment_transaction_id=uuid.UUID(str(r["payment_transaction_id"])) if r.get("payment_transaction_id") else None,
            gross_amount=format_decimal(r.get("gross_amount")),
            commission_rate=f"{Decimal(str(r.get('commission_rate') or '0')):.4f}",
            commission_amount=format_decimal(r.get("commission_amount")),
            deduction_amount=format_decimal(r.get("deduction_amount")),
            net_amount=format_decimal(r.get("net_amount")),
            currency=r.get("currency", "INR"),
            status=PayoutStatus(str(r.get("status")).lower()),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            eligible_at=r.get("eligible_at"),
            settled_at=r.get("settled_at"),
            reversed_at=r.get("reversed_at"),
            provider=r.get("provider", "manual"),
            provider_payout_id=r.get("provider_payout_id"),
            failure_reason=r.get("failure_reason"),
            metadata=sanitize_audit_payload(r.get("metadata") or {}),
        )
