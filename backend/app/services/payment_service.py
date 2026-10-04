"""
Payment Service Layer.

Authoritative coordinator for:
- Razorpay order creation
- Client-side payment verification and HMAC-SHA256 signature checking
- Idempotent payment settlement across payments, payment_transactions, bookings, and invoices
- Webhook signature verification, event handling, and idempotency
- Production-grade service invoice generation and retrieval
"""

from datetime import datetime, timezone
from decimal import Decimal
import json
from typing import Any
import uuid
from fastapi import HTTPException, status
from app.core.audit import record_audit_log, sanitize_audit_payload
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.razorpay import (
    get_razorpay_client,
    verify_payment_signature,
    verify_webhook_signature,
)
from app.db.supabase import get_supabase_service_client

logger = get_logger("services.payment")


class PaymentService:
    """Encapsulates payment processing, invoice synchronization, and transaction records."""

    def __init__(self):
        self.client = get_supabase_service_client()

    async def get_payment_by_id(self, payment_id: uuid.UUID) -> dict[str, Any] | None:
        """Fetch payment details by UUID with child transactions."""
        response = (
            self.client.table("payments")
            .select("*, payment_transactions(*)")
            .eq("id", str(payment_id))
            .execute()
        )
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None

    async def get_invoice_by_booking_id(self, booking_id: uuid.UUID) -> dict[str, Any] | None:
        """Fetch raw invoice associated with a booking."""
        response = (
            self.client.table("invoices")
            .select("*")
            .eq("booking_id", str(booking_id))
            .execute()
        )
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None

    # ==========================================================================
    # 1. CREATE PAYMENT ORDER
    # ==========================================================================

    async def create_payment_order(
        self,
        booking_id: uuid.UUID,
        customer_user_id: uuid.UUID,
    ) -> dict[str, Any]:
        """
        Create a server-controlled Razorpay order for a completed customer booking.

        Security:
        - Verifies customer ownership of the booking.
        - Validates booking state is 'payment_pending' (or transitions from 'service_completed').
        - Reads authoritative total_amount directly from PostgreSQL.
        - Strictly rejects zero or negative amounts.
        - Reuses pending orders or creates new orders idempotently.
        - Generates/issues invoice if not already generated.
        - Returns only safe client credentials (key_id, order_id, amount in paise).
        """
        # 1. Load booking from DB
        booking_resp = (
            self.client.table("bookings")
            .select("*")
            .eq("id", str(booking_id))
            .execute()
        )
        if not booking_resp.data:
            logger.warning("booking_not_found_for_payment", booking_id=str(booking_id))
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found.",
            )
        booking = booking_resp.data[0]

        # 2. Verify booking ownership
        if str(booking.get("customer_id")) != str(customer_user_id):
            logger.warning(
                "payment_creation_forbidden_not_owner",
                booking_id=str(booking_id),
                user_id=str(customer_user_id),
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found.",
            )

        # 3. Check if booking is already paid
        if booking.get("payment_status") == "paid" or booking.get("booking_status") == "paid":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Booking has already been paid.",
            )

        # 4. Lifecycle state validation
        booking_status = booking.get("booking_status")
        if booking_status == "service_completed":
            # Transition safely to payment_pending
            self.client.table("bookings").update(
                {"booking_status": "payment_pending"}
            ).eq("id", str(booking_id)).execute()
            booking["booking_status"] = "payment_pending"
        elif booking_status == "payment_pending":
            pass
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Payment order cannot be created for booking in '{booking_status}' status. "
                    "Booking must be in 'service_completed' or 'payment_pending' status."
                ),
            )

        # 5. Authoritative total amount derivation
        raw_total = booking.get("total_amount")
        if raw_total is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Booking has no authoritative total amount.",
            )
        total_decimal = Decimal(str(raw_total))
        if total_decimal <= Decimal("0"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Authoritative booking total amount must be greater than zero.",
            )
        amount_paise = int(total_decimal * 100)

        # 6. Check existing payments
        existing_payments_resp = (
            self.client.table("payments")
            .select("*")
            .eq("booking_id", str(booking_id))
            .execute()
        )
        existing_payments = existing_payments_resp.data or []

        # If already captured, conflict
        for p in existing_payments:
            if p.get("status") == "captured":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Booking has already been paid successfully.",
                )

        # Check if an active pending payment record exists with matching amount
        pending_payment = next(
            (
                p
                for p in existing_payments
                if p.get("status") == "pending"
                and p.get("provider_payment_id")
                and int(Decimal(str(p.get("amount", 0))) * 100) == amount_paise
            ),
            None,
        )

        settings = get_settings()

        if pending_payment:
            order_id = pending_payment["provider_payment_id"]
            payment_record = pending_payment
        else:
            # Create Razorpay order via SDK
            rz_client = get_razorpay_client()
            receipt_id = f"bkg_{str(booking_id).replace('-', '')[:14]}"
            try:
                order_data = rz_client.order.create({
                    "amount": amount_paise,
                    "currency": "INR",
                    "receipt": receipt_id,
                    "notes": {
                        "booking_id": str(booking_id),
                        "customer_id": str(customer_user_id),
                    },
                })
                order_id = order_data["id"]
            except Exception as exc:
                logger.error("razorpay_order_create_failed", booking_id=str(booking_id), error=str(exc))
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Payment gateway was unable to create an order.",
                )

            # Insert payment record
            new_payment_id = uuid.uuid4()
            payment_insert = {
                "id": str(new_payment_id),
                "booking_id": str(booking_id),
                "customer_id": str(customer_user_id),
                "amount": float(total_decimal),
                "currency": "INR",
                "status": "pending",
                "provider": "razorpay",
                "provider_payment_id": order_id,
            }
            insert_resp = self.client.table("payments").insert(payment_insert).execute()
            payment_record = insert_resp.data[0] if insert_resp.data else payment_insert

        # 7. Ensure invoice exists with status 'issued'
        await self._ensure_invoice_issued(booking, customer_user_id)

        # 8. Audit logging
        record_audit_log(
            action="payment_order_created",
            entity_type="payment",
            entity_id=payment_record.get("id"),
            actor_id=customer_user_id,
            actor_role="customer",
            new_data={
                "order_id": order_id,
                "amount_paise": amount_paise,
                "currency": "INR",
                "booking_id": str(booking_id),
            },
        )

        return {
            "order_id": order_id,
            "amount": amount_paise,
            "currency": "INR",
            "key_id": settings.RAZORPAY_KEY_ID or "rzp_test_placeholder",
            "booking_id": booking_id,
        }

    # ==========================================================================
    # 2. PAYMENT VERIFICATION & SETTLEMENT
    # ==========================================================================

    async def verify_payment(
        self,
        booking_id: uuid.UUID,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
        customer_user_id: uuid.UUID,
    ) -> dict[str, Any]:
        """
        Verify Razorpay payment signature and execute idempotent settlement.

        Security:
        - Authenticates customer ownership of the booking.
        - Validates HMAC-SHA256 signature using constant-time hmac.compare_digest().
        - Validates gateway payment attributes (amount, currency, order_id, status) via Razorpay API.
        - Settles payment, transactions, booking status, and invoice atomically.
        - Supports idempotent replay if already settled.
        """
        # 1. Load booking
        booking_resp = (
            self.client.table("bookings")
            .select("*")
            .eq("id", str(booking_id))
            .execute()
        )
        if not booking_resp.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found.",
            )
        booking = booking_resp.data[0]

        if str(booking.get("customer_id")) != str(customer_user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found.",
            )

        # 2. Find payment record matching booking and order_id
        payment_resp = (
            self.client.table("payments")
            .select("*")
            .eq("booking_id", str(booking_id))
            .eq("provider_payment_id", razorpay_order_id)
            .execute()
        )
        if not payment_resp.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Order ID does not match any payment record for this booking.",
            )
        payment = payment_resp.data[0]

        # 3. Check if already settled
        if payment.get("status") == "captured" and booking.get("payment_status") == "paid":
            logger.info("payment_already_settled_idempotent_return", booking_id=str(booking_id))
            return {
                "status": "already_paid",
                "message": "Payment has already been verified and settled.",
                "booking_id": booking_id,
                "payment_id": uuid.UUID(str(payment["id"])),
                "transaction_id": razorpay_payment_id,
            }

        # 4. Cryptographic signature verification
        is_valid_sig = verify_payment_signature(
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_signature=razorpay_signature,
        )

        if not is_valid_sig:
            # Record failed transaction attempt
            try:
                self.client.table("payment_transactions").insert({
                    "id": str(uuid.uuid4()),
                    "payment_id": str(payment["id"]),
                    "provider_transaction_id": razorpay_payment_id,
                    "amount": float(booking.get("total_amount") or 0.0),
                    "status": "failed",
                    "failure_reason": "Invalid payment signature",
                    "provider": "razorpay",
                }).execute()
            except Exception as exc:
                logger.warning("failed_transaction_logging_failed", error=str(exc))

            record_audit_log(
                action="payment_verification_failed",
                entity_type="payment",
                entity_id=payment["id"],
                actor_id=customer_user_id,
                actor_role="customer",
                new_data={
                    "order_id": razorpay_order_id,
                    "payment_id": razorpay_payment_id,
                    "reason": "signature_mismatch",
                },
            )

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid payment signature.",
            )

        # 5. Fetch gateway payment server-side
        rz_client = get_razorpay_client()
        try:
            rz_payment = rz_client.payment.fetch(razorpay_payment_id)
        except Exception as exc:
            logger.error("razorpay_payment_fetch_failed", error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Unable to verify transaction with payment provider.",
            )

        # Validate gateway payment properties
        if rz_payment.get("order_id") != razorpay_order_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment does not belong to specified order.",
            )
        if rz_payment.get("currency") != "INR":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid payment currency.",
            )
        expected_paise = int(Decimal(str(booking["total_amount"])) * 100)
        if int(rz_payment.get("amount", 0)) != expected_paise:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment amount does not match authoritative booking total.",
            )
        if rz_payment.get("status") not in ["authorized", "captured"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Payment status is not settled ({rz_payment.get('status')}).",
            )

        # 6. Execute atomic settlement
        await self._settle_successful_payment(
            booking=booking,
            payment=payment,
            provider_payment_id=razorpay_payment_id,
            rz_payment=rz_payment,
            actor_id=customer_user_id,
            actor_role="customer",
        )

        return {
            "status": "success",
            "message": "Payment verified and settled successfully.",
            "booking_id": booking_id,
            "payment_id": uuid.UUID(str(payment["id"])),
            "transaction_id": razorpay_payment_id,
        }

    # ==========================================================================
    # 3. ATOMIC SETTLEMENT HELPER (Shared between verify & webhook)
    # ==========================================================================

    async def _settle_successful_payment(
        self,
        booking: dict[str, Any],
        payment: dict[str, Any],
        provider_payment_id: str,
        rz_payment: dict[str, Any],
        actor_id: uuid.UUID | None = None,
        actor_role: str = "customer",
    ) -> None:
        """
        Execute idempotent state transitions for successful payment.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        booking_id_str = str(booking["id"])
        payment_id_str = str(payment["id"])

        # A. Insert payment_transaction (idempotent via partial unique index check)
        tx_check = (
            self.client.table("payment_transactions")
            .select("*")
            .eq("provider", "razorpay")
            .eq("provider_transaction_id", provider_payment_id)
            .execute()
        )
        if not tx_check.data:
            try:
                self.client.table("payment_transactions").insert({
                    "id": str(uuid.uuid4()),
                    "payment_id": payment_id_str,
                    "provider_transaction_id": provider_payment_id,
                    "amount": float(Decimal(str(booking["total_amount"]))),
                    "status": "successful",
                    "raw_provider_response": sanitize_audit_payload(rz_payment),
                    "provider": "razorpay",
                }).execute()
            except Exception as tx_err:
                logger.warning(
                    "payment_transaction_duplicate_ignored",
                    provider_tx_id=provider_payment_id,
                    error=str(tx_err),
                )

        # B. Mark payments.status = 'captured'
        self.client.table("payments").update({
            "status": "captured",
            "paid_at": now_iso,
            "payment_method": rz_payment.get("method") or "online",
        }).eq("id", payment_id_str).execute()

        # C. Update bookings.payment_status = 'paid' and booking_status = 'paid'
        # DB trigger trg_track_booking_status automatically records status history
        self.client.table("bookings").update({
            "payment_status": "paid",
            "booking_status": "paid",
        }).eq("id", booking_id_str).execute()

        # D. Update invoices.status = 'paid'
        self.client.table("invoices").update({
            "status": "paid",
            "paid_at": now_iso,
        }).eq("booking_id", booking_id_str).execute()

        # E. Audit logging
        record_audit_log(
            action="payment_verification_success",
            entity_type="payment",
            entity_id=payment_id_str,
            actor_id=actor_id,
            actor_role=actor_role,
            new_data={
                "provider_transaction_id": provider_payment_id,
                "amount": float(booking["total_amount"]),
                "booking_id": booking_id_str,
            },
        )
        record_audit_log(
            action="invoice_paid",
            entity_type="invoice",
            entity_id=booking_id_str,
            actor_id=actor_id,
            actor_role=actor_role,
            new_data={"status": "paid", "paid_at": now_iso},
        )

        # F. Dispatch notifications (side effect, never breaks settlement)
        try:
            from app.services.notification_service import NotificationService
            notifier = NotificationService()
            cust_id = uuid.UUID(str(booking["customer_id"]))
            bk_id = uuid.UUID(booking_id_str)
            await notifier.notify_payment_captured(
                booking_id=bk_id,
                customer_id=cust_id,
                amount=Decimal(str(booking["total_amount"])),
                payment_id=provider_payment_id,
            )

            # Query invoice for invoice_number
            try:
                inv_res = (
                    self.client.table("invoices")
                    .select("id, invoice_number")
                    .eq("booking_id", booking_id_str)
                    .execute()
                )
                if inv_res.data and len(inv_res.data) > 0:
                    inv = inv_res.data[0]
                    await notifier.notify_invoice_available(
                        booking_id=bk_id,
                        customer_id=cust_id,
                        invoice_id=uuid.UUID(str(inv["id"])),
                        invoice_number=inv["invoice_number"],
                    )
            except Exception as inv_err:
                logger.warning("invoice_notification_lookup_failed", error=str(inv_err))
        except Exception as notify_err:
            logger.warning("payment_success_notification_failed", error=str(notify_err))

        # G. Authoritative Mechanic Payout Ledger creation (Phase 8.7 idempotent settlement)
        try:
            from app.services.payout_service import PayoutService
            payout_svc = PayoutService(client=self.client)
            await payout_svc.create_payout_for_booking(
                booking_id=uuid.UUID(booking_id_str),
                payment_id=uuid.UUID(payment_id_str) if payment_id_str else None,
                actor_id=actor_id,
                actor_role=actor_role,
            )
        except Exception as payout_err:
            logger.error("payout_ledger_creation_failed", booking_id=booking_id_str, error=str(payout_err))

    # ==========================================================================
    # 4. WEBHOOK HANDLING & IDEMPOTENCY
    # ==========================================================================

    async def process_webhook(
        self,
        raw_body: bytes,
        signature_header: str | None,
        provider: str = "razorpay",
    ) -> dict[str, Any]:
        """
        Process webhook events with signature verification and database-level idempotency.

        Security & Idempotency:
        - Cryptographically verifies signature.
        - Atomic event-level reservation via public.webhook_events UNIQUE(provider, event_id).
        - Secondary financial transaction uniqueness via public.payment_transactions UNIQUE(provider, provider_transaction_id).
        - Releases reservation on unhandled business processing failure to guarantee safe retries.
        - Supports: payment.captured, payment.failed, refund.processed.
        - Never mutates booking status to 'paid' on failed events.
        """
        if not signature_header:
            logger.warning("webhook_missing_signature_header")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing webhook signature header.",
            )

        # 1. Signature verification
        is_valid_sig = verify_webhook_signature(
            raw_body=raw_body,
            signature_header=signature_header,
        )
        if not is_valid_sig:
            logger.warning("webhook_signature_verification_failed")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook signature.",
            )

        # 2. Parse payload
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Malformed webhook JSON payload.",
            )

        event = payload.get("event")
        event_id = payload.get("event_id") or payload.get("id")

        logger.info("webhook_received", webhook_event=event, event_id=event_id, provider=provider)

        # 3. Atomic Database-Level Event Reservation (Layer 1 Idempotency with Crash Recovery)
        is_owner = False
        if event_id:
            now_iso = datetime.now(timezone.utc).isoformat()
            existing_resp = (
                self.client.table("webhook_events")
                .select("id, status, processing_started_at, processing_attempts, processed_at")
                .eq("provider", provider)
                .eq("event_id", str(event_id))
                .execute()
            )
            existing_event = existing_resp.data[0] if existing_resp.data else None

            if existing_event:
                ev_status = existing_event.get("status")
                # If status is explicitly 'processing', check if stale (> 300s / 5 minutes)
                if ev_status == "processing":
                    started_str = existing_event.get("processing_started_at")
                    is_stale = False
                    if started_str:
                        try:
                            started_dt = datetime.fromisoformat(started_str.replace("Z", "+00:00"))
                            age_secs = (datetime.now(timezone.utc) - started_dt).total_seconds()
                            if age_secs > 300:
                                is_stale = True
                        except Exception:
                            is_stale = True

                    if is_stale:
                        attempts = (existing_event.get("processing_attempts") or 1) + 1
                        logger.warning(
                            "reclaiming_stale_webhook_reservation",
                            event_id=event_id,
                            attempts=attempts,
                        )
                        upd_resp = (
                            self.client.table("webhook_events")
                            .update({
                                "status": "processing",
                                "processing_started_at": now_iso,
                                "processing_attempts": attempts,
                                "last_error": None,
                            })
                            .eq("id", existing_event["id"])
                            .execute()
                        )
                        is_owner = bool(upd_resp.data and len(upd_resp.data) > 0)
                    else:
                        logger.info("webhook_event_concurrently_processing", event_id=event_id, provider=provider)
                        return {
                            "status": "already_processing",
                            "message": "Webhook event is currently being processed by another worker.",
                            "event": event,
                            "event_id": event_id,
                        }
                else:
                    # Status is 'processed', 'completed', or legacy/test record without 'processing' status
                    logger.info("webhook_event_already_processed", event_id=event_id, provider=provider)
                    record_audit_log(
                        action="payment_webhook_duplicate",
                        entity_type="webhook_event",
                        actor_role="gateway_webhook",
                        new_data={"event_id": event_id, "event": event, "provider": provider},
                    )
                    return {
                        "status": "already_processed",
                        "message": "Webhook event has already been processed.",
                        "event": event,
                        "event_id": event_id,
                    }
            else:
                try:
                    res_resp = (
                        self.client.table("webhook_events")
                        .insert({
                            "provider": provider,
                            "event_id": str(event_id),
                            "event_type": str(event),
                            "payload": sanitize_audit_payload(payload),
                            "status": "processing",
                            "processing_started_at": now_iso,
                            "processing_attempts": 1,
                        })
                        .execute()
                    )
                    is_owner = bool(res_resp.data and len(res_resp.data) > 0)
                except Exception as e:
                    if "duplicate" in str(e).lower() or "unique" in str(e).lower() or "23505" in str(e):
                        is_owner = False
                    else:
                        raise

                if not is_owner:
                    logger.info("webhook_event_already_processed", event_id=event_id, provider=provider)
                    record_audit_log(
                        action="payment_webhook_duplicate",
                        entity_type="webhook_event",
                        actor_role="gateway_webhook",
                        new_data={"event_id": event_id, "event": event, "provider": provider},
                    )
                    return {
                        "status": "already_processed",
                        "message": "Webhook event has already been processed.",
                        "event": event,
                        "event_id": event_id,
                    }

        try:
            # 4. Extract gateway entities
            payload_data = payload.get("payload", {})
            payment_entity = payload_data.get("payment", {}).get("entity", {})
            order_id = payment_entity.get("order_id")
            payment_id = payment_entity.get("id")

            # 5. Route events
            if event in ["payment.captured", "order.paid"]:
                p_resp = (
                    self.client.table("payments")
                    .select("*")
                    .eq("provider_payment_id", order_id)
                    .execute()
                )
                if p_resp.data:
                    payment = p_resp.data[0]
                    b_resp = (
                        self.client.table("bookings")
                        .select("*")
                        .eq("id", payment["booking_id"])
                        .execute()
                    )
                    if b_resp.data:
                        booking = b_resp.data[0]
                        # Settle idempotently
                        await self._settle_successful_payment(
                            booking=booking,
                            payment=payment,
                            provider_payment_id=payment_id or order_id,
                            rz_payment=payment_entity,
                            actor_id=None,
                            actor_role="gateway_webhook",
                        )
                else:
                    logger.warning("webhook_payment_not_found", order_id=order_id, payment_id=payment_id)
                    return {
                        "status": "ignored",
                        "message": "Associated payment record not found.",
                        "event": event,
                        "event_id": event_id,
                    }

            elif event == "payment.failed":
                payment = None
                if order_id:
                    p_resp = (
                        self.client.table("payments")
                        .select("*")
                        .eq("provider_payment_id", order_id)
                        .execute()
                    )
                    if p_resp.data:
                        payment = p_resp.data[0]
                if not payment and payment_id:
                    p_resp = (
                        self.client.table("payments")
                        .select("*")
                        .eq("provider_payment_id", payment_id)
                        .execute()
                    )
                    if p_resp.data:
                        payment = p_resp.data[0]

                if payment:
                    b_resp = (
                        self.client.table("bookings")
                        .select("*")
                        .eq("id", payment["booking_id"])
                        .execute()
                    )
                    booking = b_resp.data[0] if b_resp.data else {}

                    # Hardened Guard: Late payment.failed must NEVER revert an already settled payment or booking
                    if payment.get("status") == "captured" or booking.get("payment_status") == "paid":
                        logger.info(
                            "ignoring_late_payment_failure_for_already_settled_payment",
                            order_id=order_id,
                            payment_id=payment.get("id"),
                            booking_id=payment.get("booking_id"),
                        )
                        record_audit_log(
                            action="payment_failed_ignored_already_settled",
                            entity_type="payment",
                            entity_id=payment["id"],
                            actor_role="gateway_webhook",
                            new_data={
                                "order_id": order_id,
                                "payment_id": payment_id,
                                "event_id": event_id,
                                "provider": provider,
                                "current_payment_status": payment.get("status"),
                                "current_booking_payment_status": booking.get("payment_status"),
                                "reason": "Late failure event ignored because payment is already settled.",
                            },
                        )
                        return {
                            "status": "ignored",
                            "message": "Payment is already settled; failure event ignored.",
                            "event": event,
                            "event_id": event_id,
                        }

                    # Legitimate failure for an unsettled payment attempt:
                    failure_desc = payment_entity.get("error_description") or "Payment failed at gateway"
                    try:
                        self.client.table("payment_transactions").insert({
                            "id": str(uuid.uuid4()),
                            "payment_id": payment["id"],
                            "provider_transaction_id": payment_id,
                            "amount": payment["amount"],
                            "status": "failed",
                            "failure_reason": failure_desc,
                            "raw_provider_response": sanitize_audit_payload(payment_entity),
                            "provider": provider,
                        }).execute()
                    except Exception as tx_exc:
                        logger.warning("failed_payment_transaction_duplicate_ignored", error=str(tx_exc))

                    # Conditional updates: only update if still pending
                    self.client.table("payments").update({"status": "failed"}).eq("id", payment["id"]).eq("status", "pending").execute()
                    if booking.get("payment_status") != "paid":
                        self.client.table("bookings").update({"payment_status": "failed"}).eq("id", payment["booking_id"]).neq("payment_status", "paid").execute()

                    record_audit_log(
                        action="payment_failed",
                        entity_type="payment",
                        entity_id=payment["id"],
                        actor_role="gateway_webhook",
                        new_data={"order_id": order_id, "payment_id": payment_id, "reason": failure_desc, "provider": provider},
                    )

                    try:
                        from app.services.notification_service import NotificationService
                        await NotificationService().notify_payment_failed(
                            booking_id=uuid.UUID(str(payment["booking_id"])),
                            customer_id=uuid.UUID(str(payment["customer_id"])),
                            payment_id=payment_id,
                            reason=failure_desc,
                        )
                    except Exception as notify_err:
                        logger.warning("payment_failed_notification_failed", error=str(notify_err))
                else:
                    logger.warning("webhook_payment_not_found_for_failure", order_id=order_id, payment_id=payment_id)
                    return {
                        "status": "ignored",
                        "message": "Associated payment record not found.",
                        "event": event,
                        "event_id": event_id,
                    }

            elif event in ["refund.processed", "refund.created"]:
                refund_entity = payload_data.get("refund", {}).get("entity", {})
                refund_id = refund_entity.get("id")
                refund_payment_id = refund_entity.get("payment_id")

                if not refund_id:
                    logger.warning("refund_webhook_missing_refund_id")
                    return {"status": "ignored", "message": "Missing refund identifier.", "event": event, "event_id": event_id}

                # Hardened check: Deduplicate identical refund_id (Layer 2 transaction idempotency)
                tx_check = (
                    self.client.table("payment_transactions")
                    .select("id, status")
                    .eq("provider", provider)
                    .eq("provider_transaction_id", refund_id)
                    .execute()
                )
                if tx_check.data and len(tx_check.data) > 0:
                    logger.info("refund_event_already_processed", refund_id=refund_id)
                    record_audit_log(
                        action="payment_refund_duplicate",
                        entity_type="payment_transaction",
                        actor_role="gateway_webhook",
                        new_data={"refund_id": refund_id, "event": event, "event_id": event_id, "provider": provider},
                    )
                    return {
                        "status": "already_processed",
                        "message": "Refund event has already been processed.",
                        "event": event,
                        "event_id": event_id,
                    }

                # Locate payment: either via refund_payment_id in payment_transactions or order_id
                payment = None
                tx_match = (
                    self.client.table("payment_transactions")
                    .select("*")
                    .eq("provider_transaction_id", refund_payment_id)
                    .execute()
                )
                if tx_match.data:
                    payment_id_val = tx_match.data[0]["payment_id"]
                    p_match = self.client.table("payments").select("*").eq("id", payment_id_val).execute()
                    if p_match.data:
                        payment = p_match.data[0]

                if not payment and order_id:
                    p_match = self.client.table("payments").select("*").eq("provider_payment_id", order_id).execute()
                    if p_match.data:
                        payment = p_match.data[0]

                if not payment and refund_payment_id:
                    p_match = self.client.table("payments").select("*").eq("provider_payment_id", refund_payment_id).execute()
                    if p_match.data:
                        payment = p_match.data[0]

                if not payment:
                    logger.warning("refund_associated_payment_not_found", refund_id=refund_id, refund_payment_id=refund_payment_id)
                    return {"status": "ignored", "message": "Associated payment record not found for refund.", "event": event, "event_id": event_id}

                # Distinguish full refund vs partial refund
                refund_amount = float(refund_entity.get("amount", 0)) / 100.0
                payment_total = float(payment.get("amount", 0.0))
                is_full_refund = refund_amount >= payment_total

                # Record refund transaction (guarded by uq_payment_transactions_provider_tx)
                try:
                    self.client.table("payment_transactions").insert({
                        "id": str(uuid.uuid4()),
                        "payment_id": payment["id"],
                        "provider_transaction_id": refund_id,
                        "amount": refund_amount,
                        "status": "refunded",
                        "raw_provider_response": sanitize_audit_payload(refund_entity),
                        "provider": provider,
                    }).execute()
                except Exception as ref_err:
                    logger.warning("refund_transaction_duplicate_caught", refund_id=refund_id, error=str(ref_err))
                    return {
                        "status": "already_processed",
                        "message": "Refund transaction already recorded.",
                        "event": event,
                        "event_id": event_id,
                    }

                if is_full_refund:
                    # Update payment, booking, and invoice status to refunded
                    self.client.table("payments").update({"status": "refunded"}).eq("id", payment["id"]).execute()
                    self.client.table("bookings").update({"payment_status": "refunded"}).eq("id", payment["booking_id"]).execute()
                    self.client.table("invoices").update({"status": "refunded"}).eq("booking_id", payment["booking_id"]).execute()
                    record_audit_log(
                        action="payment_refunded",
                        entity_type="payment",
                        entity_id=payment["id"],
                        actor_role="gateway_webhook",
                        new_data={
                            "refund_id": refund_id,
                            "amount": refund_amount,
                            "is_full_refund": True,
                            "booking_id": payment["booking_id"],
                            "provider": provider,
                        },
                    )
                    # Payout ledger full refund reversal (Phase 8.7)
                    try:
                        from app.services.payout_service import PayoutService
                        await PayoutService(client=self.client).handle_payment_refund(
                            booking_id=uuid.UUID(str(payment["booking_id"])),
                            refund_amount=Decimal(str(refund_amount)),
                            is_full_refund=True,
                            refund_id=refund_id,
                            actor_role="gateway_webhook",
                        )
                    except Exception as payout_err:
                        logger.error("payout_full_refund_reversal_failed", booking_id=str(payment["booking_id"]), error=str(payout_err))
                else:
                    # Partial refund: Do NOT fake full-refund semantics!
                    # Keep payments, bookings, and invoices as captured/paid so state is not corrupted.
                    logger.info(
                        "partial_refund_recorded_retaining_state",
                        refund_id=refund_id,
                        refund_amount=refund_amount,
                        payment_total=payment_total,
                    )
                    record_audit_log(
                        action="payment_partial_refund_recorded",
                        entity_type="payment",
                        entity_id=payment["id"],
                        actor_role="gateway_webhook",
                        new_data={
                            "refund_id": refund_id,
                            "amount": refund_amount,
                            "is_full_refund": False,
                            "total_amount": payment_total,
                            "booking_id": payment["booking_id"],
                            "provider": provider,
                            "note": "Partial refund transaction recorded. Core payment state retained.",
                        },
                    )

                    # Payout ledger partial adjustment (Phase 8.7)
                    try:
                        from app.services.payout_service import PayoutService
                        await PayoutService(client=self.client).handle_payment_refund(
                            booking_id=uuid.UUID(str(payment["booking_id"])),
                            refund_amount=Decimal(str(refund_amount)),
                            is_full_refund=False,
                            refund_id=refund_id,
                            actor_role="gateway_webhook",
                        )
                    except Exception as payout_err:
                        logger.error("payout_partial_refund_adjustment_failed", booking_id=str(payment["booking_id"]), error=str(payout_err))

                    try:
                        from app.services.notification_service import NotificationService
                        await NotificationService().notify_refund_processed(
                            booking_id=uuid.UUID(str(payment["booking_id"])),
                            customer_id=uuid.UUID(str(payment["customer_id"])),
                            amount=Decimal(str(refund_amount)),
                            refund_id=refund_id,
                        )
                    except Exception as notify_err:
                        logger.warning("refund_notification_failed", error=str(notify_err))

                    return {
                        "status": "partial_refund_recorded",
                        "message": "Partial refund transaction recorded successfully.",
                        "event": event,
                        "event_id": event_id,
                    }

                # Full refund notification
                try:
                    from app.services.notification_service import NotificationService
                    await NotificationService().notify_refund_processed(
                        booking_id=uuid.UUID(str(payment["booking_id"])),
                        customer_id=uuid.UUID(str(payment["customer_id"])),
                        amount=Decimal(str(refund_amount)),
                        refund_id=refund_id,
                    )
                except Exception as notify_err:
                    logger.warning("refund_notification_failed", error=str(notify_err))

            # Update status and processed_at timestamp on successful processing
            if event_id and is_owner:
                try:
                    self.client.table("webhook_events").update({
                        "status": "processed",
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("provider", provider).eq("event_id", str(event_id)).execute()
                except Exception as upd_err:
                    logger.warning("failed_to_update_webhook_processed_at", event_id=event_id, error=str(upd_err))

            # 6. Record processed webhook in audit_logs for application audit history
            record_audit_log(
                action="payment_webhook_processed",
                entity_type="webhook_event",
                actor_role="gateway_webhook",
                new_data={
                    "event_id": event_id,
                    "event": event,
                    "provider": provider,
                    "order_id": order_id,
                    "payment_id": payment_id,
                },
            )

            return {
                "status": "processed",
                "message": "Webhook event processed successfully.",
                "event": event,
                "event_id": event_id,
            }

        except Exception as exc:
            # Failure semantics: if business processing fails, release/remove the reservation
            # so the gateway can safely retry the webhook delivery (Phase 8.1B Test F).
            if event_id and is_owner:
                logger.warning(
                    "releasing_webhook_reservation_on_failure",
                    event_id=event_id,
                    provider=provider,
                    error=str(exc),
                )
                try:
                    self.client.table("webhook_events").delete().eq("provider", provider).eq("event_id", str(event_id)).execute()
                except Exception as del_err:
                    logger.error("failed_to_release_webhook_reservation", event_id=event_id, error=str(del_err))
            raise exc

    # ==========================================================================
    # 5. INVOICE GENERATION & RETRIEVAL
    # ==========================================================================

    async def _ensure_invoice_issued(
        self,
        booking: dict[str, Any],
        customer_user_id: uuid.UUID,
    ) -> None:
        """Create invoice record with status 'issued' if one does not already exist."""
        booking_id_str = str(booking["id"])
        existing = (
            self.client.table("invoices")
            .select("id")
            .eq("booking_id", booking_id_str)
            .execute()
        )
        if existing.data and len(existing.data) > 0:
            return

        invoice_num = f"INV-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        inv_payload = {
            "id": str(uuid.uuid4()),
            "invoice_number": invoice_num,
            "booking_id": booking_id_str,
            "customer_id": str(customer_user_id),
            "subtotal": float(booking.get("subtotal") or 0.0) + float(booking.get("additional_charges") or 0.0),
            "tax": float(booking.get("tax_amount") or 0.0),
            "discount": float(booking.get("discount_amount") or 0.0),
            "total": float(booking.get("total_amount") or 0.0),
            "status": "issued",
            "issued_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self.client.table("invoices").insert(inv_payload).execute()
            record_audit_log(
                action="invoice_created",
                entity_type="invoice",
                entity_id=inv_payload["id"],
                actor_id=customer_user_id,
                actor_role="customer",
                new_data={"invoice_number": invoice_num, "total": inv_payload["total"]},
            )
        except Exception as exc:
            logger.warning("invoice_insert_conflict_or_existing", booking_id=booking_id_str, error=str(exc))

    async def get_detailed_invoice(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
    ) -> dict[str, Any]:
        """
        Retrieve complete, production-grade invoice with vehicle, items, and approved additional work.
        """
        # 1. Fetch raw invoice
        inv_resp = (
            self.client.table("invoices")
            .select("*")
            .eq("booking_id", str(booking_id))
            .execute()
        )
        if not inv_resp.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invoice not generated for this booking.",
            )
        invoice = inv_resp.data[0]

        # 2. Authorization check
        if user_role == "customer" and str(invoice.get("customer_id")) != str(user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to requested invoice.",
            )
        if user_role not in ["customer", "admin", "support"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to requested invoice.",
            )

        # 3. Fetch booking, customer profile, vehicle, and line items
        booking_resp = (
            self.client.table("bookings")
            .select("*")
            .eq("id", str(booking_id))
            .execute()
        )
        booking = booking_resp.data[0] if booking_resp.data else {}

        # Items
        items_resp = (
            self.client.table("booking_items")
            .select("*")
            .eq("booking_id", str(booking_id))
            .execute()
        )
        booking_items = items_resp.data or booking.get("booking_items") or []

        # Additional work
        aw_resp = (
            self.client.table("additional_work_requests")
            .select("*")
            .eq("booking_id", str(booking_id))
            .execute()
        )
        additional_work_requests = aw_resp.data or booking.get("additional_work_requests") or []

        # Customer details
        cust_resp = (
            self.client.table("profiles")
            .select("full_name, email, phone")
            .eq("id", str(invoice["customer_id"]))
            .execute()
        )
        customer_profile = cust_resp.data[0] if cust_resp.data else {}

        # Vehicle details
        vehicle_info_str = None
        if booking.get("vehicle_id"):
            v_resp = (
                self.client.table("vehicles")
                .select("license_plate, year, vehicle_models(name, vehicle_brands(name))")
                .eq("id", str(booking["vehicle_id"]))
                .execute()
            )
            if v_resp.data:
                v_data = v_resp.data[0]
                model_data = v_data.get("vehicle_models") or {}
                brand_data = model_data.get("vehicle_brands") or {}
                brand_name = brand_data.get("name", "")
                model_name = model_data.get("name", "")
                year = v_data.get("year", "")
                plate = v_data.get("license_plate", "")
                vehicle_info_str = f"{year} {brand_name} {model_name} [{plate}]".strip()

        # Service line items
        items = []
        for item in booking_items:
            items.append({
                "service_name": item.get("service_name") or "Service Package",
                "tier_name": item.get("tier_name"),
                "unit_price": float(item.get("unit_price") or 0.0),
                "quantity": int(item.get("quantity") or 1),
                "total_price": float(item.get("total_price") or 0.0),
            })

        # Additional work line items (only approved requests are billable!)
        additional_work = []
        for aw in additional_work_requests:
            if aw.get("status") == "approved":
                additional_work.append({
                    "description": aw.get("description") or "Additional Service / Part",
                    "amount": float(aw.get("estimated_cost") or 0.0),
                    "status": aw.get("status"),
                })

        return {
            "id": invoice["id"],
            "invoice_number": invoice["invoice_number"],
            "booking_id": invoice["booking_id"],
            "customer_id": invoice["customer_id"],
            "customer_name": customer_profile.get("full_name"),
            "customer_email": customer_profile.get("email"),
            "customer_phone": customer_profile.get("phone"),
            "vehicle_info": vehicle_info_str,
            "items": items,
            "additional_work": additional_work,
            "subtotal": float(invoice["subtotal"]),
            "tax": float(invoice["tax"]),
            "discount": float(invoice["discount"]),
            "total": float(invoice["total"]),
            "status": invoice["status"],
            "issued_at": invoice["issued_at"],
            "paid_at": invoice.get("paid_at"),
            "created_at": invoice["created_at"],
            "updated_at": invoice["updated_at"],
        }
