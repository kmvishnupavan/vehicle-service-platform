"""
Notification Service Layer (Phase 8.2A).

Dispatches in-app notifications and realtime event triggers via public.notifications.
Enforces:
- service_role database client
- database-enforced event idempotency via (user_id, event_id)
- server-generated notification content
- strict non-leaking error handling (notifications never fail business workflows)
"""

from decimal import Decimal
from typing import Any
import uuid
from app.core.logging import get_logger
from app.db.supabase import get_supabase_service_client

logger = get_logger("services.notification")


class NotificationService:
    """Encapsulates notification dispatch, typed lifecycle events, and idempotency tracking."""

    def __init__(self, client: Any = None):
        self.client = client or get_supabase_service_client()

    async def send_notification(
        self,
        user_id: uuid.UUID,
        title: str,
        message: str,
        notification_type: str = "info",
        data: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Insert notification record for user; triggers realtime publication.
        Guarantees idempotency when event_id is supplied.
        """
        payload = {
            "user_id": str(user_id),
            "title": title,
            "message": message,
            "type": notification_type,
            "data": data or {},
            "is_read": False,
        }
        if event_id:
            payload["event_id"] = str(event_id)

        try:
            if event_id:
                response = (
                    self.client.table("notifications")
                    .upsert(payload, on_conflict="user_id,event_id", ignore_duplicates=True)
                    .execute()
                )
            else:
                response = self.client.table("notifications").insert(payload).execute()

            if response.data and len(response.data) > 0:
                logger.info(
                    "notification_dispatched",
                    user_id=str(user_id),
                    notification_type=notification_type,
                    event_id=event_id,
                )
                return response.data[0]

            logger.info(
                "notification_already_dispatched",
                user_id=str(user_id),
                event_id=event_id,
            )
            return payload
        except Exception as exc:
            # Notifications are treated as a side effect and must not fail business transactions
            logger.warning(
                "notification_dispatch_failed",
                user_id=str(user_id),
                notification_type=notification_type,
                event_id=event_id,
                error=str(exc),
            )
            return None

    # =========================================================================
    # Typed Lifecycle Notification Helpers
    # =========================================================================

    async def notify_booking_status_change(
        self,
        booking_id: uuid.UUID,
        customer_id: uuid.UUID,
        new_status: str,
        mechanic_user_id: uuid.UUID | None = None,
        booking_number: str | None = None,
    ) -> None:
        """Dispatches status progression notifications to booking participants."""
        ref_text = f" #{booking_number}" if booking_number else ""
        event_id_base = f"booking_status:{booking_id}:{new_status}"

        # Status text templates
        status_messages: dict[str, tuple[str, str, str]] = {
            "mechanic_assigned": (
                "Mechanic Assigned",
                f"A mechanic has accepted your booking{ref_text} and has been assigned.",
                "booking_update",
            ),
            "mechanic_en_route": (
                "Mechanic En Route",
                f"Your mechanic is on the way to your service location{ref_text}.",
                "booking_update",
            ),
            "mechanic_arrived": (
                "Mechanic Arrived",
                f"Your mechanic has arrived at your location{ref_text}.",
                "booking_update",
            ),
            "inspection": (
                "Inspection Started",
                f"Your vehicle inspection has started for booking{ref_text}.",
                "booking_update",
            ),
            "awaiting_customer_approval": (
                "Approval Required",
                f"Additional work proposal submitted for booking{ref_text}. Please review and approve.",
                "booking_action_required",
            ),
            "service_in_progress": (
                "Service In Progress",
                f"Vehicle service is currently in progress for booking{ref_text}.",
                "booking_update",
            ),
            "service_completed": (
                "Service Completed",
                f"Vehicle service completed for booking{ref_text}. Please proceed to payment.",
                "booking_action_required",
            ),
            "payment_pending": (
                "Payment Pending",
                f"Invoice generated. Payment is pending for booking{ref_text}.",
                "payment_update",
            ),
            "paid": (
                "Booking Paid",
                f"Payment successful! Thank you for using our service platform.",
                "payment_update",
            ),
            "cancelled": (
                "Booking Cancelled",
                f"Booking{ref_text} has been cancelled.",
                "booking_alert",
            ),
            "disputed": (
                "Dispute Registered",
                f"A dispute has been recorded for booking{ref_text}. Platform support has been notified.",
                "booking_alert",
            ),
        }

        template = status_messages.get(new_status)
        if not template:
            return

        title, message, n_type = template

        # Notify Customer
        await self.send_notification(
            user_id=customer_id,
            title=title,
            message=message,
            notification_type=n_type,
            data={"booking_id": str(booking_id), "status": new_status},
            event_id=f"{event_id_base}:customer",
        )

        # Notify Mechanic on terminal/alert states if assigned
        if mechanic_user_id and new_status in ["cancelled", "disputed"]:
            await self.send_notification(
                user_id=mechanic_user_id,
                title=title,
                message=f"Booking{ref_text} has transitioned to {new_status}.",
                notification_type=n_type,
                data={"booking_id": str(booking_id), "status": new_status},
                event_id=f"{event_id_base}:mechanic",
            )

    async def notify_additional_work_requested(
        self,
        booking_id: uuid.UUID,
        customer_id: uuid.UUID,
        request_id: uuid.UUID,
        title: str,
        price: Decimal | str,
    ) -> None:
        """Notifies customer when mechanic submits an additional work proposal."""
        amt_str = f"₹{price:.2f}" if isinstance(price, (int, float, Decimal)) else f"₹{price}"
        await self.send_notification(
            user_id=customer_id,
            title="Additional Work Proposed",
            message=f"Mechanic proposed additional work '{title}' for {amt_str}.",
            notification_type="additional_work_requested",
            data={
                "booking_id": str(booking_id),
                "request_id": str(request_id),
                "title": title,
                "price": str(price),
            },
            event_id=f"additional_work_req:{request_id}",
        )

    async def notify_additional_work_approved(
        self,
        booking_id: uuid.UUID,
        mechanic_user_id: uuid.UUID,
        request_id: uuid.UUID,
        title: str,
    ) -> None:
        """Notifies mechanic when customer approves an additional work proposal."""
        await self.send_notification(
            user_id=mechanic_user_id,
            title="Additional Work Approved",
            message=f"Customer approved additional work '{title}'. You may proceed with the job.",
            notification_type="additional_work_approved",
            data={"booking_id": str(booking_id), "request_id": str(request_id), "title": title},
            event_id=f"additional_work_appr:{request_id}",
        )

    async def notify_additional_work_rejected(
        self,
        booking_id: uuid.UUID,
        mechanic_user_id: uuid.UUID,
        request_id: uuid.UUID,
        title: str,
        reason: str | None = None,
    ) -> None:
        """Notifies mechanic when customer declines an additional work proposal."""
        reason_msg = f" Reason: {reason}" if reason else ""
        await self.send_notification(
            user_id=mechanic_user_id,
            title="Additional Work Declined",
            message=f"Customer declined additional work '{title}'.{reason_msg}",
            notification_type="additional_work_rejected",
            data={"booking_id": str(booking_id), "request_id": str(request_id), "title": title},
            event_id=f"additional_work_rej:{request_id}",
        )

    async def notify_payment_captured(
        self,
        booking_id: uuid.UUID,
        customer_id: uuid.UUID,
        amount: Decimal | str,
        payment_id: str,
    ) -> None:
        """Notifies customer of successful payment capture."""
        amt_str = f"₹{amount:.2f}" if isinstance(amount, (int, float, Decimal)) else f"₹{amount}"
        await self.send_notification(
            user_id=customer_id,
            title="Payment Successful",
            message=f"Payment of {amt_str} has been confirmed for your booking.",
            notification_type="payment_success",
            data={"booking_id": str(booking_id), "payment_id": payment_id, "amount": str(amount)},
            event_id=f"payment_captured:{booking_id}:{payment_id}",
        )

    async def notify_payment_failed(
        self,
        booking_id: uuid.UUID,
        customer_id: uuid.UUID,
        payment_id: str,
        reason: str | None = None,
    ) -> None:
        """Notifies customer of payment failure."""
        reason_text = f" Reason: {reason}" if reason else ""
        await self.send_notification(
            user_id=customer_id,
            title="Payment Failed",
            message=f"Payment could not be completed.{reason_text} Please retry.",
            notification_type="payment_failed",
            data={"booking_id": str(booking_id), "payment_id": payment_id},
            event_id=f"payment_failed:{booking_id}:{payment_id}",
        )

    async def notify_refund_processed(
        self,
        booking_id: uuid.UUID,
        customer_id: uuid.UUID,
        amount: Decimal | str,
        refund_id: str,
    ) -> None:
        """Notifies customer of processed refund."""
        amt_str = f"₹{amount:.2f}" if isinstance(amount, (int, float, Decimal)) else f"₹{amount}"
        await self.send_notification(
            user_id=customer_id,
            title="Refund Processed",
            message=f"A refund of {amt_str} has been processed to your original payment method.",
            notification_type="refund_processed",
            data={"booking_id": str(booking_id), "refund_id": refund_id, "amount": str(amount)},
            event_id=f"refund_processed:{booking_id}:{refund_id}",
        )

    async def notify_invoice_available(
        self,
        booking_id: uuid.UUID,
        customer_id: uuid.UUID,
        invoice_id: uuid.UUID,
        invoice_number: str,
    ) -> None:
        """Notifies customer when invoice is ready for download."""
        await self.send_notification(
            user_id=customer_id,
            title="Invoice Available",
            message=f"Invoice #{invoice_number} is now available for your service booking.",
            notification_type="invoice_available",
            data={
                "booking_id": str(booking_id),
                "invoice_id": str(invoice_id),
                "invoice_number": invoice_number,
            },
            event_id=f"invoice_available:{booking_id}:{invoice_id}",
        )

    # =========================================================================
    # Phase 8.9 Settlement & Maker-Checker Notification Helpers
    # =========================================================================

    async def notify_payout_account_verified(
        self,
        mechanic_user_id: uuid.UUID,
        account_id: uuid.UUID,
        masked_account_number: str,
    ) -> None:
        """Notifies mechanic that their bank payout account was verified successfully."""
        await self.send_notification(
            user_id=mechanic_user_id,
            title="Bank Account Verified",
            message=f"Your bank account ({masked_account_number}) was successfully verified via penny-drop validation.",
            notification_type="payout_account_verified",
            data={"account_id": str(account_id), "masked_account": masked_account_number},
            event_id=f"payout_acc_verified:{account_id}",
        )

    async def notify_payout_account_failed(
        self,
        mechanic_user_id: uuid.UUID,
        account_id: uuid.UUID,
        reason: str | None = None,
    ) -> None:
        """Notifies mechanic that bank account verification failed."""
        msg = f"Bank account verification failed: {reason}" if reason else "Bank account verification failed. Please check your details."
        await self.send_notification(
            user_id=mechanic_user_id,
            title="Bank Verification Failed",
            message=msg,
            notification_type="payout_account_verification_failed",
            data={"account_id": str(account_id), "reason": reason or ""},
            event_id=f"payout_acc_failed:{account_id}",
        )

    async def notify_settlement_approval_required(
        self,
        checker_user_id: uuid.UUID,
        batch_id: uuid.UUID,
        batch_number: str,
        total_amount: Decimal | str,
    ) -> dict[str, Any] | None:
        """Notifies checker/admin that a settlement batch is pending maker-checker review."""
        amt_str = f"₹{total_amount:.2f}" if isinstance(total_amount, (int, float, Decimal)) else f"₹{total_amount}"
        return await self.send_notification(
            user_id=checker_user_id,
            title="Settlement Approval Required",
            message=f"Settlement batch {batch_number} for {amt_str} requires maker-checker approval before disbursement.",
            notification_type="settlement_approval_required",
            data={"batch_id": str(batch_id), "batch_number": batch_number, "total_amount": str(total_amount)},
            event_id=f"settle_appr_req:{batch_id}:{checker_user_id}",
        )

    async def notify_settlement_approved(
        self,
        maker_user_id: uuid.UUID,
        batch_id: uuid.UUID,
        batch_number: str,
        checker_name: str | None = None,
    ) -> dict[str, Any] | None:
        """Notifies maker that their settlement batch was approved by the checker."""
        by_text = f" by {checker_name}" if checker_name else ""
        return await self.send_notification(
            user_id=maker_user_id,
            title="Settlement Batch Approved",
            message=f"Settlement batch {batch_number} has been approved{by_text} and is eligible for disbursement.",
            notification_type="settlement_approved",
            data={"batch_id": str(batch_id), "batch_number": batch_number},
            event_id=f"settle_appr:{batch_id}",
        )

    async def notify_settlement_rejected(
        self,
        maker_user_id: uuid.UUID,
        batch_id: uuid.UUID,
        batch_number: str,
        reason: str | None = None,
    ) -> dict[str, Any] | None:
        """Notifies maker that their settlement batch was rejected."""
        reason_text = f" Reason: {reason}" if reason else ""
        return await self.send_notification(
            user_id=maker_user_id,
            title="Settlement Batch Rejected",
            message=f"Settlement batch {batch_number} was rejected by checker.{reason_text}",
            notification_type="settlement_rejected",
            data={"batch_id": str(batch_id), "batch_number": batch_number, "reason": reason or ""},
            event_id=f"settle_rej:{batch_id}",
        )

    async def notify_settlement_submitted_to_mechanic(
        self,
        mechanic_user_id: uuid.UUID,
        batch_number: str,
        amount: Decimal | str,
    ) -> dict[str, Any] | None:
        """Notifies mechanic that their payout batch was submitted for bank transfer."""
        amt_str = f"₹{amount:.2f}" if isinstance(amount, (int, float, Decimal)) else f"₹{amount}"
        return await self.send_notification(
            user_id=mechanic_user_id,
            title="Payout In Progress",
            message=f"Payout disbursement of {amt_str} (Batch {batch_number}) was submitted to your bank.",
            notification_type="payout_processing",
            data={"batch_number": batch_number, "amount": str(amount)},
            event_id=f"payout_submitted:{batch_number}:{mechanic_user_id}",
        )

    async def notify_settlement_completed_to_mechanic(
        self,
        mechanic_user_id: uuid.UUID,
        payout_id: uuid.UUID,
        amount: Decimal | str,
        batch_number: str | None = None,
    ) -> dict[str, Any] | None:
        """Notifies mechanic of completed direct payout disbursement."""
        amt_str = f"₹{amount:.2f}" if isinstance(amount, (int, float, Decimal)) else f"₹{amount}"
        batch_text = f" ({batch_number})" if batch_number else ""
        return await self.send_notification(
            user_id=mechanic_user_id,
            title="Payout Settled",
            message=f"Disbursement of {amt_str}{batch_text} has been credited to your bank account.",
            notification_type="payout_completed",
            data={"payout_id": str(payout_id), "amount": str(amount)},
            event_id=f"payout_completed:{payout_id}",
        )

    async def notify_payout_failed_to_mechanic(
        self,
        mechanic_user_id: uuid.UUID,
        payout_id: uuid.UUID,
        reason: str | None = None,
    ) -> dict[str, Any] | None:
        """Notifies mechanic if provider payout disbursement fails."""
        reason_text = f" Reason: {reason}" if reason else ""
        return await self.send_notification(
            user_id=mechanic_user_id,
            title="Payout Failed",
            message=f"Disbursement could not be completed by your bank.{reason_text} Our support team has been alerted.",
            notification_type="payout_failed",
            data={"payout_id": str(payout_id), "reason": reason or ""},
            event_id=f"payout_failed:{payout_id}",
        )

    async def notify_payout_reversed_to_mechanic(
        self,
        mechanic_user_id: uuid.UUID,
        payout_id: uuid.UUID,
        reason: str | None = None,
    ) -> dict[str, Any] | None:
        """Notifies mechanic if provider payout is reversed."""
        reason_text = f" Reason: {reason}" if reason else ""
        return await self.send_notification(
            user_id=mechanic_user_id,
            title="Payout Reversed",
            message=f"A previous disbursement was reversed by the clearinghouse.{reason_text}",
            notification_type="payout_reversed",
            data={"payout_id": str(payout_id), "reason": reason or ""},
            event_id=f"payout_reversed:{payout_id}",
        )

