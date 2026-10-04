"""
Reconciliation Engine (Phase 9).

Performs read-only scanning, verification, and discrepancy detection across:
1. Payments & Invoices (Stuck pending, captured without paid booking, transaction duplicates)
2. Payouts (Stuck processing, paid without provider ref, unapproved batch disbursement)
3. Settlement Batches (Total amount mismatches, terminal item batch lag, approval SLA breach)
4. Webhooks (Stuck processing reservations, repeated failures, unhandled events)

SAFETY INVARIANT:
Does NOT mutate financial records automatically during scanning. Detects and reports discrepancies
for administrative inspection and remediation.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any
import uuid
from app.core.logging import get_logger
from app.db.supabase import get_supabase_service_client

logger = get_logger("services.reconciliation")


class ReconciliationService:
    """Detects discrepancies between platform records and external provider states."""

    def __init__(self, client: Any = None, db: Any = None):
        self.client = client or db or get_supabase_service_client()

    async def reconcile_payments(
        self, persist_discrepancies: bool = False, persist: bool | None = None
    ) -> list[dict[str, Any]]:
        """
        Scan payment transactions and bookings for financial inconsistencies.
        """
        if persist is not None:
            persist_discrepancies = persist
        discrepancies: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        stuck_threshold = now - timedelta(minutes=15)

        # 1. Fetch recent payments
        try:
            p_res = self.client.table("payments").select("*, bookings(id, payment_status, total_amount)").execute()
            payments = p_res.data or []
        except Exception as e:
            logger.error("reconciliation_payments_fetch_failed", error=str(e))
            return []

        for p in payments:
            p_id = p.get("id")
            p_status = p.get("status")
            provider_ref = p.get("provider_payment_id")
            booking = p.get("bookings") or {}
            b_payment_status = booking.get("payment_status")
            created_at_str = p.get("created_at")

            # Check 1: Captured payment with unpaid booking
            if p_status == "captured" and b_payment_status != "paid":
                discrepancies.append({
                    "internal_id": p_id,
                    "entity_type": "payment",
                    "entity_id": p_id,
                    "provider_reference": provider_ref,
                    "internal_status": p_status,
                    "provider_status": "captured",
                    "discrepancy_type": "captured_payment_booking_unpaid",
                    "severity": "high",
                    "details": {
                        "booking_id": p.get("booking_id"),
                        "booking_payment_status": b_payment_status,
                        "payment_amount": str(p.get("amount")),
                    },
                    "detected_at": now.isoformat(),
                    "resolution_status": "open",
                })

            # Check 2: Payment stuck in pending (> 15 mins)
            if p_status == "pending" and created_at_str:
                try:
                    c_dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    if c_dt < stuck_threshold:
                        discrepancies.append({
                            "internal_id": p_id,
                            "entity_type": "payment",
                            "entity_id": p_id,
                            "provider_reference": provider_ref,
                            "internal_status": "pending",
                            "provider_status": "unknown",
                            "discrepancy_type": "PAYMENT_PENDING_TOO_LONG",
                            "severity": "HIGH",
                            "details": {
                                "booking_id": p.get("booking_id"),
                                "age_minutes": round((now - c_dt).total_seconds() / 60, 1),
                                "amount": str(p.get("amount")),
                            },
                            "detected_at": now.isoformat(),
                            "resolution_status": "open",
                        })
                except Exception:
                    pass

        # 2. Check for duplicate provider transactions
        try:
            tx_res = self.client.table("payment_transactions").select("id, provider_transaction_id, status, payment_id").execute()
            transactions = tx_res.data or []
            tx_map: dict[str, list[dict[str, Any]]] = {}
            for tx in transactions:
                pt_id = tx.get("provider_transaction_id")
                if pt_id:
                    tx_map.setdefault(pt_id, []).append(tx)

            for pt_id, items in tx_map.items():
                if len(items) > 1:
                    discrepancies.append({
                        "internal_id": items[0]["id"],
                        "entity_type": "payment_transaction",
                        "entity_id": items[0]["id"],
                        "provider_reference": pt_id,
                        "internal_status": items[0]["status"],
                        "provider_status": "duplicate",
                        "discrepancy_type": "duplicate_provider_transaction",
                        "severity": "high",
                        "details": {
                            "duplicate_count": len(items),
                            "payment_ids": [it.get("payment_id") for it in items],
                        },
                        "detected_at": now.isoformat(),
                        "resolution_status": "open",
                    })
        except Exception as e:
            logger.warning("reconciliation_transactions_check_failed", error=str(e))

        if persist_discrepancies:
            await self._persist_discrepancies(discrepancies)

        return discrepancies

    async def reconcile_payouts(
        self, persist_discrepancies: bool = False, persist: bool | None = None
    ) -> list[dict[str, Any]]:
        """
        Scan mechanic payout ledger records for financial anomalies.
        """
        if persist is not None:
            persist_discrepancies = persist
        discrepancies: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        stuck_payout_threshold = now - timedelta(hours=2)

        try:
            p_res = self.client.table("mechanic_payout_ledger").select("*, settlement_batches(status)").execute()
            payouts = p_res.data or []
        except Exception as e:
            logger.error("reconciliation_payouts_fetch_failed", error=str(e))
            return []

        for p in payouts:
            p_id = p.get("id")
            p_status = p.get("status")
            provider_ref = p.get("provider_payout_id")
            updated_at_str = p.get("updated_at") or p.get("created_at")
            batch_rel = p.get("settlement_batches")
            batch_status = batch_rel.get("status") if isinstance(batch_rel, dict) else None

            # Check 1: Paid payout without provider reference
            if p_status == "paid" and not provider_ref:
                discrepancies.append({
                    "internal_id": p_id,
                    "entity_type": "payout",
                    "entity_id": p_id,
                    "provider_reference": None,
                    "internal_status": p_status,
                    "provider_status": "missing",
                    "discrepancy_type": "paid_payout_missing_provider_id",
                    "severity": "critical",
                    "details": {
                        "mechanic_id": p.get("mechanic_id"),
                        "net_amount": str(p.get("net_amount")),
                    },
                    "detected_at": now.isoformat(),
                    "resolution_status": "open",
                })

            # Check 2: Payout stuck in processing (> 2 hours)
            if p_status == "processing" and updated_at_str:
                try:
                    u_dt = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                    if u_dt < stuck_payout_threshold:
                        discrepancies.append({
                            "internal_id": p_id,
                            "entity_type": "payout",
                            "entity_id": p_id,
                            "provider_reference": provider_ref,
                            "internal_status": p_status,
                            "provider_status": "stuck_processing",
                            "discrepancy_type": "STUCK_PAYOUT_PROCESSING",
                            "severity": "HIGH",
                            "details": {
                                "hours_in_processing": round((now - u_dt).total_seconds() / 3600, 1),
                                "mechanic_id": p.get("mechanic_id"),
                                "net_amount": str(p.get("net_amount")),
                            },
                            "detected_at": now.isoformat(),
                            "resolution_status": "open",
                        })
                except Exception:
                    pass

            # Check 3: Paid ledger item attached to an unapproved/draft batch
            if p_status == "paid" and batch_status and batch_status in ("draft", "rejected", "cancelled"):
                discrepancies.append({
                    "internal_id": p_id,
                    "entity_type": "payout",
                    "entity_id": p_id,
                    "provider_reference": provider_ref,
                    "internal_status": p_status,
                    "provider_status": batch_status,
                    "discrepancy_type": "payout_paid_in_unapproved_batch",
                    "severity": "critical",
                    "details": {
                        "batch_id": p.get("settlement_batch_id"),
                        "batch_status": batch_status,
                    },
                    "detected_at": now.isoformat(),
                    "resolution_status": "open",
                })

        if persist_discrepancies:
            await self._persist_discrepancies(discrepancies)

        return discrepancies

    async def reconcile_settlements(
        self, persist_discrepancies: bool = False, persist: bool | None = None
    ) -> list[dict[str, Any]]:
        """
        Verify settlement batch amount aggregations and lifecycle consistency.
        """
        if persist is not None:
            persist_discrepancies = persist
        discrepancies: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        sla_approval_threshold = now - timedelta(hours=24)

        try:
            b_res = self.client.table("settlement_batches").select("*, mechanic_payout_ledger(id, net_amount, status)").execute()
            batches = b_res.data or []
        except Exception as e:
            logger.error("reconciliation_settlements_fetch_failed", error=str(e))
            return []

        for b in batches:
            b_id = b.get("id")
            b_num = b.get("batch_number")
            b_status = b.get("status")
            total_amt = Decimal(str(b.get("total_amount") or "0.00"))
            items = b.get("mechanic_payout_ledger") or []
            created_at_str = b.get("created_at")

            # Check 1: Financial aggregation sum verification
            actual_sum = sum(Decimal(str(it.get("net_amount") or "0.00")) for it in items)
            if items and abs(actual_sum - total_amt) > Decimal("0.01"):
                discrepancies.append({
                    "internal_id": b_id,
                    "entity_type": "settlement_batch",
                    "entity_id": b_id,
                    "provider_reference": b.get("provider_batch_id"),
                    "internal_status": b_status,
                    "provider_status": "amount_mismatch",
                    "discrepancy_type": "settlement_batch_total_mismatch",
                    "severity": "critical",
                    "details": {
                        "recorded_total": str(total_amt),
                        "calculated_sum": str(actual_sum),
                        "delta": str(actual_sum - total_amt),
                        "batch_number": b_num,
                    },
                    "detected_at": now.isoformat(),
                    "resolution_status": "open",
                })

            # Check 2: Batch in processing but all line items terminal
            if b_status == "processing" and items:
                all_terminal = all(it.get("status") in ("paid", "failed") for it in items)
                if all_terminal:
                    discrepancies.append({
                        "internal_id": b_id,
                        "entity_type": "settlement_batch",
                        "entity_id": b_id,
                        "provider_reference": b.get("provider_batch_id"),
                        "internal_status": b_status,
                        "provider_status": "items_completed",
                        "discrepancy_type": "settlement_batch_lagging_completion",
                        "severity": "medium",
                        "details": {
                            "batch_number": b_num,
                            "item_count": len(items),
                            "note": "All line items are terminal; batch status can be resolved.",
                        },
                        "detected_at": now.isoformat(),
                        "resolution_status": "open",
                    })

            # Check 3: SLA breach: approval_required for > 24 hours
            if b_status == "approval_required" and created_at_str:
                try:
                    c_dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    if c_dt < sla_approval_threshold:
                        discrepancies.append({
                            "internal_id": b_id,
                            "entity_type": "settlement_batch",
                            "entity_id": b_id,
                            "provider_reference": b.get("provider_batch_id"),
                            "internal_status": b_status,
                            "provider_status": "pending_checker",
                            "discrepancy_type": "settlement_approval_sla_breach",
                            "severity": "low",
                            "details": {
                                "batch_number": b_num,
                                "hours_pending": round((now - c_dt).total_seconds() / 3600, 1),
                                "total_amount": str(total_amt),
                            },
                            "detected_at": now.isoformat(),
                            "resolution_status": "open",
                        })
                except Exception:
                    pass

        if persist_discrepancies:
            await self._persist_discrepancies(discrepancies)

        return discrepancies

    async def reconcile_webhooks(
        self, persist_discrepancies: bool = False, persist: bool | None = None
    ) -> list[dict[str, Any]]:
        """
        Scan webhook events for stuck reservations or repeated failures.
        """
        if persist is not None:
            persist_discrepancies = persist
        discrepancies: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        stuck_webhook_threshold = now - timedelta(minutes=5)

        try:
            w_res = self.client.table("webhook_events").select("*").execute()
            events = w_res.data or []
        except Exception as e:
            logger.error("reconciliation_webhooks_fetch_failed", error=str(e))
            return []

        for w in events:
            w_id = w.get("id")
            w_status = w.get("status")
            event_id = w.get("event_id")
            attempts = w.get("processing_attempts") or 1
            started_at_str = w.get("processing_started_at") or w.get("processed_at")

            # Check 1: Stuck processing reservation (> 5 mins)
            if w_status == "processing" and started_at_str:
                try:
                    s_dt = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
                    if s_dt < stuck_webhook_threshold:
                        discrepancies.append({
                            "internal_id": w_id,
                            "entity_type": "webhook_event",
                            "entity_id": w_id,
                            "provider_reference": event_id,
                            "internal_status": w_status,
                            "provider_status": "stuck_in_reservation",
                            "discrepancy_type": "STUCK_WEBHOOK_RESERVATION",
                            "severity": "HIGH",
                            "details": {
                                "event_type": w.get("event_type"),
                                "attempts": attempts,
                                "minutes_running": round((now - s_dt).total_seconds() / 60, 1),
                            },
                            "detected_at": now.isoformat(),
                            "resolution_status": "open",
                        })
                except Exception:
                    pass

            # Check 2: Repeated failure attempts (> 3 attempts)
            if attempts > 3:
                discrepancies.append({
                    "internal_id": w_id,
                    "entity_type": "webhook_event",
                    "entity_id": w_id,
                    "provider_reference": event_id,
                    "internal_status": w_status,
                    "provider_status": "repeated_failure",
                    "discrepancy_type": "repeated_webhook_failure",
                    "severity": "high",
                    "details": {
                        "attempts": attempts,
                        "last_error": w.get("last_error"),
                    },
                    "detected_at": now.isoformat(),
                    "resolution_status": "open",
                })

        if persist_discrepancies:
            await self._persist_discrepancies(discrepancies)

        return discrepancies

    async def _persist_discrepancies(self, discrepancies: list[dict[str, Any]]) -> None:
        """Upsert detected discrepancies into public.reconciliation_discrepancies without duplicates."""
        for d in discrepancies:
            try:
                # Deduplicate by entity_type, entity_id, discrepancy_type where status = 'open'
                existing = (
                    self.client.table("reconciliation_discrepancies")
                    .select("id")
                    .eq("entity_type", d["entity_type"])
                    .eq("entity_id", str(d["entity_id"]))
                    .eq("discrepancy_type", d["discrepancy_type"])
                    .eq("status", "open")
                    .execute()
                )
                if not existing.data:
                    self.client.table("reconciliation_discrepancies").insert({
                        "entity_type": d["entity_type"],
                        "entity_id": str(d["entity_id"]) if d["entity_id"] else None,
                        "provider_reference": d.get("provider_reference"),
                        "discrepancy_type": d["discrepancy_type"],
                        "severity": d["severity"],
                        "internal_status": d.get("internal_status"),
                        "provider_status": d.get("provider_status"),
                        "details": d.get("details") or {},
                        "status": "open",
                    }).execute()
            except Exception as e:
                logger.warning("failed_to_persist_discrepancy", error=str(e))
