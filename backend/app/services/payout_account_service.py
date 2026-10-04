"""
Mechanic Payout Account & Settlement Batch Service Layer (Phase 8.8).

Authoritative coordinator for:
- Bank account onboarding and replacement
- Payout account verification (Penny Drop integration via RazorpayX)
- Payout account state machine enforcement (preventing self-verification by mechanics)
- Controlled settlement batch creation & processing
- Provider webhook reconciliation using existing public.webhook_events deduplication
- Audit logging matching PostgreSQL schema
- Masked banking details protection (zero plain account numbers stored or leaked)
"""

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
from typing import Any
import uuid
from fastapi import HTTPException, status
from app.core.audit import record_audit_log, sanitize_audit_payload
from app.core.logging import get_logger
from app.db.supabase import get_supabase_service_client
from app.schemas.payout import PayoutResponse, PayoutStatus
from app.schemas.payout_account import (
    PayoutAccountCreateRequest,
    PayoutAccountResponse,
    PayoutAccountUpdateRequest,
    PayoutAccountVerificationStatus,
    SettlementApprovalAction,
    SettlementApprovalPolicyResponse,
    SettlementApprovalRecordResponse,
    SettlementBatchDetailResponse,
    SettlementBatchListResponse,
    SettlementBatchResponse,
    SettlementBatchStatus,
)
from app.schemas.user import AuthenticatedUser, UserRole
from app.services.notification_service import NotificationService
from app.services.payout_account_state_machine import (
    PayoutAccountStateMachine,
    SettlementBatchStateMachine,
)
from app.services.payout_provider import BasePayoutProvider, RazorpayXProvider
from app.services.payout_service import format_decimal, parse_iso_datetime
from app.services.payout_state_machine import PayoutStateMachine

logger = get_logger("services.payout_account")


def hash_account_number(account_number: str) -> str:
    """Deterministic SHA-256 hash of clean account number for duplicate protection."""
    clean = account_number.strip().replace(" ", "").replace("-", "")
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()


def mask_account_number(account_number: str) -> str:
    """Format account number with leading bullets and last 4 digits visible."""
    clean = account_number.strip().replace(" ", "").replace("-", "")
    if len(clean) <= 4:
        return "•••• " + clean
    last4 = clean[-4:]
    return f"•••• •••• {last4}"


class PayoutAccountService:
    """Authoritative service for mechanic banking accounts, verification, and settlement batches."""

    def __init__(
        self,
        client=None,
        provider: BasePayoutProvider | None = None,
        notification_service: NotificationService | None = None,
    ):
        self.client = client or get_supabase_service_client()
        self.provider = provider or RazorpayXProvider()
        self.notifications = notification_service or NotificationService(client=self.client)

    # ==========================================================================
    # 1. IDENTITY & AUTHORIZATION
    # ==========================================================================

    async def resolve_mechanic_id(
        self,
        current_user: AuthenticatedUser,
        target_mechanic_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """
        Derive authoritative mechanic_profile_id from user session.
        - Mechanic users: Strictly locked to their own mechanic_profile.id.
        - Admin/Support: Can inspect a specific mechanic via target_mechanic_id.
        - Customer users: Rejected with 403 Forbidden.
        """
        user_role_str = (
            current_user.role.value
            if isinstance(current_user.role, UserRole)
            else str(current_user.role)
        )

        if user_role_str == UserRole.CUSTOMER.value:
            logger.warning("payout_account_denied_customer", user_id=str(current_user.id))
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
                    "cross_mechanic_account_access_attempt",
                    user_id=str(current_user.id),
                    attempted_mechanic_id=str(target_mechanic_id),
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: You can only view your own mechanic payout account.",
                )
            return own_profile_id

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Unauthorized role.",
        )

    # ==========================================================================
    # 2. PAYOUT ACCOUNT ONBOARDING & MANAGEMENT
    # ==========================================================================

    async def get_payout_account(self, mechanic_id: uuid.UUID) -> PayoutAccountResponse | None:
        """
        Fetch active primary payout account for mechanic.
        Returns None if not configured.
        """
        res = (
            self.client.table("mechanic_payout_accounts")
            .select("*")
            .eq("mechanic_id", str(mechanic_id))
            .eq("is_active", True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not res.data or len(res.data) == 0:
            return None

        row = res.data[0]
        return PayoutAccountResponse.model_validate(row)

    async def create_or_replace_payout_account(
        self,
        mechanic_id: uuid.UUID,
        payload: PayoutAccountCreateRequest,
        actor_id: uuid.UUID,
        actor_role: str = "mechanic",
    ) -> PayoutAccountResponse:
        """
        Create or replace the mechanic's payout bank account.
        - Deactivates previous primary accounts.
        - Stores masked account number and hash (never raw plain account number).
        - Links contact & fund account with provider.
        - Initializes status as 'pending'.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        mechanic_id_str = str(mechanic_id)

        # 1. Fetch mechanic profile for contact reference
        m_res = (
            self.client.table("mechanic_profiles")
            .select("id, business_name, user_id, profiles:user_id(email, phone, full_name)")
            .eq("id", mechanic_id_str)
            .execute()
        )
        if not m_res.data or len(m_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mechanic profile not found.",
            )
        mech_data = m_res.data[0]
        user_info = mech_data.get("profiles") or {}
        if isinstance(user_info, list) and len(user_info) > 0:
            user_info = user_info[0]

        contact_name = payload.account_holder_name
        contact_email = user_info.get("email")
        contact_phone = user_info.get("phone")

        # 2. Provider Contact & Fund Account creation
        try:
            contact = await self.provider.create_contact(
                name=contact_name,
                email=contact_email,
                phone=contact_phone,
                reference_id=mechanic_id_str,
            )
            fund_account = await self.provider.create_fund_account(
                contact_id=contact["id"],
                account_holder_name=payload.account_holder_name,
                account_number=payload.account_number,
                ifsc_code=payload.ifsc_code,
            )
            provider_contact_id = contact.get("id")
            provider_fund_account_id = fund_account.get("id")
        except Exception as p_err:
            logger.error("payout_provider_account_linking_failed", error=str(p_err))
            provider_contact_id = None
            provider_fund_account_id = None

        # 3. Deactivate existing active accounts for this mechanic
        self.client.table("mechanic_payout_accounts").update({
            "is_active": False,
            "is_primary": False,
            "updated_at": now_iso,
        }).eq("mechanic_id", mechanic_id_str).eq("is_active", True).execute()

        # 4. Insert new payout account
        account_id = uuid.uuid4()
        masked_acc = mask_account_number(payload.account_number)
        acc_hash = hash_account_number(payload.account_number)

        insert_payload = {
            "id": str(account_id),
            "mechanic_id": mechanic_id_str,
            "provider": getattr(self.provider, "PROVIDER_NAME", "razorpayx"),
            "provider_contact_id": provider_contact_id,
            "provider_fund_account_id": provider_fund_account_id,
            "account_holder_name": payload.account_holder_name,
            "account_type": payload.account_type.value,
            "masked_account_number": masked_acc,
            "account_number_hash": acc_hash,
            "ifsc_code": payload.ifsc_code,
            "bank_name": payload.bank_name,
            "verification_status": PayoutAccountVerificationStatus.PENDING.value,
            "verification_error": None,
            "is_primary": True,
            "is_active": True,
            "verified_at": None,
            "metadata": {
                "created_by_role": actor_role,
                "created_by_id": str(actor_id),
            },
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        ins_res = self.client.table("mechanic_payout_accounts").insert(insert_payload).execute()
        created_row = ins_res.data[0] if ins_res.data else insert_payload

        # 5. Audit Logging
        record_audit_log(
            action="payout_account_submitted",
            entity_type="mechanic_payout_account",
            entity_id=account_id,
            actor_id=actor_id,
            actor_role=actor_role,
            new_data={
                "mechanic_id": mechanic_id_str,
                "masked_account": masked_acc,
                "ifsc": payload.ifsc_code,
                "status": "pending",
            },
        )

        return PayoutAccountResponse.model_validate(created_row)

    # ==========================================================================
    # 3. VERIFICATION (PENNY DROP / VALIDATION)
    # ==========================================================================

    async def verify_payout_account(
        self,
        mechanic_id: uuid.UUID,
        actor_id: uuid.UUID,
        actor_role: str = "mechanic",
    ) -> PayoutAccountResponse:
        """
        Initiate or complete bank account verification (Penny Drop / Fund Account Validation).
        - State transition: pending/submitted -> verified (or failed).
        - Mechanics trigger verification request; provider completes it.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        mechanic_id_str = str(mechanic_id)

        # 1. Fetch current active account
        account_res = (
            self.client.table("mechanic_payout_accounts")
            .select("*")
            .eq("mechanic_id", mechanic_id_str)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        if not account_res.data or len(account_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active payout account configured. Please submit bank details first.",
            )

        account = account_res.data[0]
        account_id_str = str(account["id"])
        current_status = account.get("verification_status")

        if current_status == PayoutAccountVerificationStatus.VERIFIED.value:
            return PayoutAccountResponse.model_validate(account)

        # 2. Check transition to SUBMITTED
        PayoutAccountStateMachine.enforce_transition(
            current_status=current_status,
            target_status=PayoutAccountVerificationStatus.SUBMITTED,
            actor_role=actor_role,
        )

        # Update status to submitted
        self.client.table("mechanic_payout_accounts").update({
            "verification_status": PayoutAccountVerificationStatus.SUBMITTED.value,
            "last_verified_at": now_iso,
            "updated_at": now_iso,
        }).eq("id", account_id_str).execute()

        # 3. Call provider Fund Account Validation (Penny Drop)
        fa_id = account.get("provider_fund_account_id") or "fa_simulated"
        try:
            val_res = await self.provider.validate_fund_account(
                fund_account_id=fa_id,
                account_holder_name=account["account_holder_name"],
            )

            is_valid = val_res.get("status") in ["completed", "active"]
            if is_valid:
                target_status = PayoutAccountVerificationStatus.VERIFIED
                ver_error = None
                verified_at = now_iso
            else:
                target_status = PayoutAccountVerificationStatus.FAILED
                ver_error = val_res.get("error_description") or "Penny drop verification rejected by bank."
                verified_at = None

        except Exception as v_err:
            logger.error("fund_account_validation_error", error=str(v_err))
            target_status = PayoutAccountVerificationStatus.FAILED
            ver_error = "Provider verification service temporarily unavailable."
            verified_at = None

        # 4. Final state transition enforcement
        PayoutAccountStateMachine.enforce_transition(
            current_status=PayoutAccountVerificationStatus.SUBMITTED,
            target_status=target_status,
            actor_role="system",
        )

        update_payload = {
            "verification_status": target_status.value,
            "verification_error": ver_error,
            "verified_at": verified_at,
            "last_verified_at": now_iso,
            "updated_at": now_iso,
        }
        upd_res = self.client.table("mechanic_payout_accounts").update(update_payload).eq("id", account_id_str).execute()
        updated_row = upd_res.data[0] if upd_res.data else {**account, **update_payload}

        # 5. Audit Logging
        action_name = (
            "payout_account_verification_succeeded"
            if target_status == PayoutAccountVerificationStatus.VERIFIED
            else "payout_account_verification_failed"
        )
        record_audit_log(
            action=action_name,
            entity_type="mechanic_payout_account",
            entity_id=uuid.UUID(account_id_str),
            actor_id=actor_id,
            actor_role=actor_role,
            new_data={"status": target_status.value, "error": ver_error},
        )
        # 6. Dispatch Notification
        try:
            m_user_res = self.client.table("mechanic_profiles").select("user_id").eq("id", str(mechanic_id)).execute()
            if m_user_res.data and m_user_res.data[0].get("user_id"):
                m_uid = uuid.UUID(str(m_user_res.data[0]["user_id"]))
                if target_status == PayoutAccountVerificationStatus.VERIFIED:
                    await self.notifications.notify_payout_account_verified(
                        mechanic_user_id=m_uid,
                        account_id=uuid.UUID(account_id_str),
                        masked_account_number=updated_row.get("masked_account_number", "•••• ****"),
                    )
                else:
                    await self.notifications.notify_payout_account_failed(
                        mechanic_user_id=m_uid,
                        account_id=uuid.UUID(account_id_str),
                        reason=ver_error,
                    )
        except Exception as notif_err:
            logger.warning("payout_account_verification_notification_failed", error=str(notif_err))

        return PayoutAccountResponse.model_validate(updated_row)

    # ==========================================================================
    # 4. SETTLEMENT BATCHES
    # ==========================================================================

    async def create_settlement_batch(
        self,
        eligible_payout_ids: list[uuid.UUID] | None = None,
        created_by: uuid.UUID | None = None,
    ) -> SettlementBatchResponse:
        """
        Aggregate eligible ledger entries for mechanics with verified accounts into a settlement batch.
        Guarantees ledger records do not belong to multiple active batches.
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        # 1. Query eligible payout ledger records with no batch attached
        query = (
            self.client.table("mechanic_payout_ledger")
            .select("id, booking_id, mechanic_id, net_amount, status, settlement_batch_id")
            .eq("status", PayoutStatus.ELIGIBLE.value)
        )
        if eligible_payout_ids:
            query = query.in_("id", [str(pid) for pid in eligible_payout_ids])

        res = query.execute()
        payouts = res.data or []

        # Filter only payouts without an active batch
        available_payouts = [p for p in payouts if not p.get("settlement_batch_id")]
        if not available_payouts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No eligible payout ledger records available for batching.",
            )

        # 2. Filter payouts whose mechanics have a VERIFIED active payout account
        mechanic_ids = list(set(p["mechanic_id"] for p in available_payouts))
        acc_res = (
            self.client.table("mechanic_payout_accounts")
            .select("id, mechanic_id, verification_status, is_active")
            .in_("mechanic_id", mechanic_ids)
            .eq("is_active", True)
            .eq("verification_status", PayoutAccountVerificationStatus.VERIFIED.value)
            .execute()
        )
        verified_accounts = {str(a["mechanic_id"]): a for a in (acc_res.data or [])}

        qualifying_payouts = []
        for p in available_payouts:
            m_id = str(p["mechanic_id"])
            if m_id in verified_accounts:
                p["_verified_account_id"] = verified_accounts[m_id]["id"]
                qualifying_payouts.append(p)
            else:
                logger.info("payout_skipped_mechanic_account_unverified", payout_id=p["id"], mechanic_id=m_id)

        if not qualifying_payouts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="None of the eligible payouts have verified mechanic payout accounts. Mechanics must complete bank verification first.",
            )

        # 3. Create batch record with policy threshold check
        batch_id = uuid.uuid4()
        batch_number = f"SETTLE-{now.strftime('%Y%m%d')}-{batch_id.hex[:6].upper()}"

        total_amount = sum(Decimal(str(p.get("net_amount") or "0.00")) for p in qualifying_payouts)

        # Evaluate configurable approval policy
        policy = await self.get_approval_policy()
        threshold = Decimal(str(policy.threshold_amount))
        if threshold > Decimal("0.00") and total_amount < threshold:
            initial_status = SettlementBatchStatus.DRAFT.value
            requires_checker = False
        else:
            initial_status = SettlementBatchStatus.APPROVAL_REQUIRED.value
            requires_checker = True

        batch_payload = {
            "id": str(batch_id),
            "batch_number": batch_number,
            "provider": getattr(self.provider, "PROVIDER_NAME", "razorpayx"),
            "status": initial_status,
            "total_amount": float(total_amount),
            "currency": "INR",
            "item_count": len(qualifying_payouts),
            "provider_batch_id": None,
            "error_details": None,
            "metadata": {
                "qualifying_item_ids": [p["id"] for p in qualifying_payouts],
                "requires_checker": requires_checker,
            },
            "created_by": str(created_by) if created_by else None,
            "submitted_at": None,
            "completed_at": None,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        b_ins = self.client.table("settlement_batches").insert(batch_payload).execute()
        created_batch = b_ins.data[0] if b_ins.data else batch_payload

        # 4. Associate ledger entries with this batch
        for p in qualifying_payouts:
            self.client.table("mechanic_payout_ledger").update({
                "settlement_batch_id": str(batch_id),
                "payout_account_id": str(p["_verified_account_id"]),
                "updated_at": now_iso,
            }).eq("id", str(p["id"])).execute()

        # 5. Record initial approval audit trail if checker required
        if requires_checker and created_by:
            self.client.table("settlement_batch_approvals").insert({
                "settlement_batch_id": str(batch_id),
                "action": SettlementApprovalAction.SUBMITTED_FOR_APPROVAL.value,
                "actor_id": str(created_by),
                "actor_role": "admin",
                "reason": "Batch created and submitted for maker-checker review",
            }).execute()

            # Notify checkers/admins
            try:
                admins_res = self.client.table("profiles").select("id").in_("role", ["admin", "support"]).execute()
                for adm in (admins_res.data or []):
                    adm_uid = uuid.UUID(str(adm["id"]))
                    if adm_uid != created_by:
                        await self.notifications.notify_settlement_approval_required(
                            checker_user_id=adm_uid,
                            batch_id=batch_id,
                            batch_number=batch_number,
                            total_amount=total_amount,
                        )
            except Exception as notif_err:
                logger.warning("notify_approval_required_failed", error=str(notif_err))

        # 6. Audit Logging
        record_audit_log(
            action="settlement_batch_created",
            entity_type="settlement_batch",
            entity_id=batch_id,
            actor_id=created_by,
            actor_role="admin" if created_by else "system",
            new_data={
                "batch_number": batch_number,
                "status": initial_status,
                "item_count": len(qualifying_payouts),
                "total_amount": float(total_amount),
            },
            client=self.client,
        )

        return self._format_batch_response(created_batch)

    def _format_batch_response(self, row: dict[str, Any]) -> SettlementBatchResponse:
        """Helper to format dictionary to SettlementBatchResponse."""
        return SettlementBatchResponse(
            id=uuid.UUID(str(row["id"])),
            batch_number=row["batch_number"],
            provider=row["provider"],
            status=SettlementBatchStatus(row["status"]),
            total_amount=format_decimal(row["total_amount"]),
            currency=row.get("currency") or "INR",
            item_count=int(row["item_count"]),
            provider_batch_id=row.get("provider_batch_id"),
            error_details=row.get("error_details"),
            submitted_at=parse_iso_datetime(row["submitted_at"]) if row.get("submitted_at") else None,
            completed_at=parse_iso_datetime(row["completed_at"]) if row.get("completed_at") else None,
            created_at=parse_iso_datetime(row["created_at"]),
            created_by=uuid.UUID(str(row["created_by"])) if row.get("created_by") else None,
        )

    async def get_approval_policy(self) -> SettlementApprovalPolicyResponse:
        """Fetch active settlement approval threshold policy."""
        res = (
            self.client.table("settlement_approval_policies")
            .select("*")
            .eq("is_active", True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if res.data and len(res.data) > 0:
            row = res.data[0]
            return SettlementApprovalPolicyResponse(
                id=uuid.UUID(str(row["id"])),
                threshold_amount=format_decimal(row["threshold_amount"]),
                currency=row.get("currency") or "INR",
                requires_checker=bool(row.get("requires_checker", True)),
                is_active=bool(row.get("is_active", True)),
                created_at=parse_iso_datetime(row["created_at"]),
                updated_at=parse_iso_datetime(row["updated_at"]),
            )
        now = datetime.now(timezone.utc)
        return SettlementApprovalPolicyResponse(
            id=uuid.uuid4(),
            threshold_amount="0.00",
            currency="INR",
            requires_checker=True,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

    async def update_approval_policy(
        self,
        threshold_amount: Decimal | None = None,
        requires_checker: bool | None = None,
        is_active: bool | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> SettlementApprovalPolicyResponse:
        """Update configurable settlement approval policy (Admin only)."""
        current = await self.get_approval_policy()
        updates: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if threshold_amount is not None:
            updates["threshold_amount"] = float(threshold_amount)
        if requires_checker is not None:
            updates["requires_checker"] = requires_checker
        if is_active is not None:
            updates["is_active"] = is_active

        self.client.table("settlement_approval_policies").update(updates).eq("id", str(current.id)).execute()
        record_audit_log(
            action="settlement_policy_updated",
            entity_type="settlement_approval_policy",
            entity_id=current.id,
            actor_id=actor_id,
            actor_role="admin",
            new_data=updates,
        )
        return await self.get_approval_policy()

    async def submit_batch_for_approval(
        self,
        batch_id: uuid.UUID,
        actor_id: uuid.UUID,
        actor_role: str = "admin",
    ) -> SettlementBatchResponse:
        """Maker submits draft settlement batch for checker review."""
        batch_id_str = str(batch_id)
        now_iso = datetime.now(timezone.utc).isoformat()

        b_res = self.client.table("settlement_batches").select("*").eq("id", batch_id_str).execute()
        if not b_res.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Settlement batch not found.")
        batch = b_res.data[0]

        target_status = SettlementBatchStateMachine.enforce_transition(
            current_status=batch["status"],
            target_status=SettlementBatchStatus.APPROVAL_REQUIRED,
            actor_role=actor_role,
        )

        self.client.table("settlement_batches").update({
            "status": target_status.value,
            "updated_at": now_iso,
        }).eq("id", batch_id_str).execute()

        self.client.table("settlement_batch_approvals").insert({
            "settlement_batch_id": batch_id_str,
            "action": SettlementApprovalAction.SUBMITTED_FOR_APPROVAL.value,
            "actor_id": str(actor_id),
            "actor_role": actor_role,
            "reason": "Submitted for maker-checker review",
        }).execute()

        record_audit_log(
            action="settlement_submitted_for_approval",
            entity_type="settlement_batch",
            entity_id=batch_id,
            actor_id=actor_id,
            actor_role=actor_role,
            old_data={"status": batch["status"]},
            new_data={"status": target_status.value},
            client=self.client,
        )

        try:
            admins_res = self.client.table("profiles").select("id").in_("role", ["admin", "support"]).execute()
            for adm in (admins_res.data or []):
                adm_uid = uuid.UUID(str(adm["id"]))
                if adm_uid != actor_id:
                    await self.notifications.notify_settlement_approval_required(
                        checker_user_id=adm_uid,
                        batch_id=batch_id,
                        batch_number=batch["batch_number"],
                        total_amount=batch["total_amount"],
                    )
        except Exception as notif_err:
            logger.warning("notify_approval_required_failed", error=str(notif_err))

        updated_batch = {**batch, "status": target_status.value, "updated_at": now_iso}
        return self._format_batch_response(updated_batch)

    async def approve_settlement_batch(
        self,
        batch_id: uuid.UUID,
        checker_id: uuid.UUID,
        checker_role: str = "admin",
        reason: str | None = None,
    ) -> SettlementBatchResponse:
        """Checker reviews and approves settlement batch. Maker != Checker enforced."""
        batch_id_str = str(batch_id)
        now_iso = datetime.now(timezone.utc).isoformat()

        b_res = self.client.table("settlement_batches").select("*").eq("id", batch_id_str).execute()
        if not b_res.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Settlement batch not found.")
        batch = b_res.data[0]

        if batch["status"] != SettlementBatchStatus.APPROVAL_REQUIRED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Batch cannot be approved in status '{batch['status']}'. Expected 'approval_required'.",
            )

        # Maker != Checker verification
        if batch.get("created_by") and str(batch["created_by"]) == str(checker_id):
            logger.warning(
                "maker_self_approval_attempt_blocked",
                batch_id=batch_id_str,
                checker_id=str(checker_id),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Maker-Checker violation: The user who created this settlement batch cannot approve it.",
            )

        target_status = SettlementBatchStateMachine.enforce_transition(
            current_status=batch["status"],
            target_status=SettlementBatchStatus.APPROVED,
            actor_role=checker_role,
        )

        # Atomic insert into approvals table
        self.client.table("settlement_batch_approvals").insert({
            "settlement_batch_id": batch_id_str,
            "action": SettlementApprovalAction.APPROVED.value,
            "actor_id": str(checker_id),
            "actor_role": checker_role,
            "reason": reason or "Approved for disbursement",
        }).execute()

        self.client.table("settlement_batches").update({
            "status": target_status.value,
            "updated_at": now_iso,
        }).eq("id", batch_id_str).execute()

        record_audit_log(
            action="settlement_approved",
            entity_type="settlement_batch",
            entity_id=batch_id,
            actor_id=checker_id,
            actor_role=checker_role,
            old_data={"status": batch["status"]},
            new_data={"status": target_status.value, "reason": reason},
            client=self.client,
        )

        if batch.get("created_by"):
            try:
                await self.notifications.notify_settlement_approved(
                    maker_user_id=uuid.UUID(str(batch["created_by"])),
                    batch_id=batch_id,
                    batch_number=batch["batch_number"],
                )
            except Exception as notif_err:
                logger.warning("notify_settlement_approved_failed", error=str(notif_err))

        updated_batch = {**batch, "status": target_status.value, "updated_at": now_iso}
        return self._format_batch_response(updated_batch)

    async def reject_settlement_batch(
        self,
        batch_id: uuid.UUID,
        checker_id: uuid.UUID,
        checker_role: str = "admin",
        reason: str | None = None,
    ) -> SettlementBatchResponse:
        """Checker rejects settlement batch. Releases payouts back to eligible."""
        batch_id_str = str(batch_id)
        now_iso = datetime.now(timezone.utc).isoformat()

        b_res = self.client.table("settlement_batches").select("*").eq("id", batch_id_str).execute()
        if not b_res.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Settlement batch not found.")
        batch = b_res.data[0]

        if batch["status"] != SettlementBatchStatus.APPROVAL_REQUIRED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Batch cannot be rejected in status '{batch['status']}'. Expected 'approval_required'.",
            )

        if batch.get("created_by") and str(batch["created_by"]) == str(checker_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Maker-Checker violation: The user who created this settlement batch cannot reject it.",
            )

        target_status = SettlementBatchStateMachine.enforce_transition(
            current_status=batch["status"],
            target_status=SettlementBatchStatus.REJECTED,
            actor_role=checker_role,
        )

        self.client.table("settlement_batch_approvals").insert({
            "settlement_batch_id": batch_id_str,
            "action": SettlementApprovalAction.REJECTED.value,
            "actor_id": str(checker_id),
            "actor_role": checker_role,
            "reason": reason or "Rejected by checker",
        }).execute()

        # Release ledger items back to eligible status
        self.client.table("mechanic_payout_ledger").update({
            "settlement_batch_id": None,
            "updated_at": now_iso,
        }).eq("settlement_batch_id", batch_id_str).execute()

        self.client.table("settlement_batches").update({
            "status": target_status.value,
            "error_details": {"rejection_reason": reason or "Rejected by checker"},
            "updated_at": now_iso,
        }).eq("id", batch_id_str).execute()

        record_audit_log(
            action="settlement_rejected",
            entity_type="settlement_batch",
            entity_id=batch_id,
            actor_id=checker_id,
            actor_role=checker_role,
            old_data={"status": batch["status"]},
            new_data={"status": target_status.value, "reason": reason},
            client=self.client,
        )

        if batch.get("created_by"):
            try:
                await self.notifications.notify_settlement_rejected(
                    maker_user_id=uuid.UUID(str(batch["created_by"])),
                    batch_id=batch_id,
                    batch_number=batch["batch_number"],
                    reason=reason,
                )
            except Exception as notif_err:
                logger.warning("notify_settlement_rejected_failed", error=str(notif_err))

        updated_batch = {**batch, "status": target_status.value, "updated_at": now_iso}
        return self._format_batch_response(updated_batch)

    async def cancel_settlement_batch(
        self,
        batch_id: uuid.UUID,
        actor_id: uuid.UUID,
        actor_role: str = "admin",
        reason: str | None = None,
    ) -> SettlementBatchResponse:
        """Cancels a batch in draft, approval_required, or approved status. Releases ledger items."""
        batch_id_str = str(batch_id)
        now_iso = datetime.now(timezone.utc).isoformat()

        b_res = self.client.table("settlement_batches").select("*").eq("id", batch_id_str).execute()
        if not b_res.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Settlement batch not found.")
        batch = b_res.data[0]

        target_status = SettlementBatchStateMachine.enforce_transition(
            current_status=batch["status"],
            target_status=SettlementBatchStatus.CANCELLED,
            actor_role=actor_role,
        )

        self.client.table("settlement_batch_approvals").insert({
            "settlement_batch_id": batch_id_str,
            "action": SettlementApprovalAction.CANCELLED.value,
            "actor_id": str(actor_id),
            "actor_role": actor_role,
            "reason": reason or "Cancelled by administrator",
        }).execute()

        # Release ledger items
        self.client.table("mechanic_payout_ledger").update({
            "settlement_batch_id": None,
            "updated_at": now_iso,
        }).eq("settlement_batch_id", batch_id_str).execute()

        self.client.table("settlement_batches").update({
            "status": target_status.value,
            "updated_at": now_iso,
        }).eq("id", batch_id_str).execute()

        record_audit_log(
            action="settlement_cancelled",
            entity_type="settlement_batch",
            entity_id=batch_id,
            actor_id=actor_id,
            actor_role=actor_role,
            old_data={"status": batch["status"]},
            new_data={"status": target_status.value, "reason": reason},
            client=self.client,
        )

        updated_batch = {**batch, "status": target_status.value, "updated_at": now_iso}
        return self._format_batch_response(updated_batch)

    async def get_batch_details(self, batch_id: uuid.UUID) -> SettlementBatchDetailResponse:
        """Retrieve batch with approval history and itemized payout records."""
        batch_id_str = str(batch_id)
        b_res = self.client.table("settlement_batches").select("*").eq("id", batch_id_str).execute()
        if not b_res.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Settlement batch not found.")
        batch = b_res.data[0]

        a_res = (
            self.client.table("settlement_batch_approvals")
            .select("*")
            .eq("settlement_batch_id", batch_id_str)
            .order("created_at", desc=False)
            .execute()
        )
        approvals = [
            SettlementApprovalRecordResponse(
                id=uuid.UUID(str(a["id"])),
                settlement_batch_id=uuid.UUID(str(a["settlement_batch_id"])),
                action=a["action"],
                actor_id=uuid.UUID(str(a["actor_id"])),
                actor_role=a["actor_role"],
                reason=a.get("reason"),
                created_at=parse_iso_datetime(a["created_at"]),
            )
            for a in (a_res.data or [])
        ]

        p_res = (
            self.client.table("mechanic_payout_ledger")
            .select("*, bookings(booking_number)")
            .eq("settlement_batch_id", batch_id_str)
            .execute()
        )
        items = p_res.data or []

        return SettlementBatchDetailResponse(
            id=uuid.UUID(str(batch["id"])),
            batch_number=batch["batch_number"],
            provider=batch["provider"],
            status=SettlementBatchStatus(batch["status"]),
            total_amount=format_decimal(batch["total_amount"]),
            currency=batch.get("currency") or "INR",
            item_count=batch["item_count"],
            provider_batch_id=batch.get("provider_batch_id"),
            error_details=batch.get("error_details"),
            submitted_at=parse_iso_datetime(batch["submitted_at"]) if batch.get("submitted_at") else None,
            completed_at=parse_iso_datetime(batch["completed_at"]) if batch.get("completed_at") else None,
            created_at=parse_iso_datetime(batch["created_at"]),
            created_by=uuid.UUID(str(batch["created_by"])) if batch.get("created_by") else None,
            approvals=approvals,
            items=items,
        )

    async def list_batches(
        self,
        status_filter: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SettlementBatchListResponse:
        """List settlement batches with pagination and optional status filter."""
        safe_limit = min(max(1, limit), 100)
        safe_offset = max(0, offset)

        query = self.client.table("settlement_batches").select("*", count="exact")
        if status_filter and status_filter != "all":
            query = query.eq("status", status_filter.lower())
        query = query.order("created_at", desc=True).range(safe_offset, safe_offset + safe_limit - 1)
        res = query.execute()

        rows = res.data or []
        total = res.count if res.count is not None else len(rows)

        items = [self._format_batch_response(r) for r in rows]
        return SettlementBatchListResponse(items=items, total=total, limit=safe_limit, offset=safe_offset)

    async def process_settlement_batch(
        self,
        batch_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        actor_role: str = "admin",
    ) -> SettlementBatchResponse:
        """
        Disburse approved settlement batch through provider:
        - Requires batch status to be 'approved' (enforcing maker-checker).
        - Transitions batch: approved -> processing -> completed.
        - Synchronizes each payout ledger entry (eligible -> processing -> paid).
        - Dispatches mechanic notifications upon completion.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        batch_id_str = str(batch_id)

        # 1. Fetch batch
        b_res = (
            self.client.table("settlement_batches")
            .select("*")
            .eq("id", batch_id_str)
            .execute()
        )
        if not b_res.data or len(b_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Settlement batch not found.",
            )
        batch = b_res.data[0]
        if batch["status"] != SettlementBatchStatus.APPROVED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Batch cannot be processed in status '{batch['status']}'. Batches must be approved by a checker prior to disbursement.",
            )

        # 2. Fetch associated payout ledger records
        p_res = (
            self.client.table("mechanic_payout_ledger")
            .select("*, mechanic_payout_accounts(*)")
            .eq("settlement_batch_id", batch_id_str)
            .execute()
        )
        items = p_res.data or []

        # Update batch to processing
        self.client.table("settlement_batches").update({
            "status": SettlementBatchStatus.PROCESSING.value,
            "submitted_at": now_iso,
            "updated_at": now_iso,
        }).eq("id", batch_id_str).execute()

        # 3. Disburse each payout item
        success_count = 0
        for item in items:
            payout_id_str = str(item["id"])
            net_amt = Decimal(str(item.get("net_amount") or "0.00"))
            acc = item.get("mechanic_payout_accounts")
            if isinstance(acc, list) and len(acc) > 0:
                acc = acc[0]
            fa_id = acc.get("provider_fund_account_id") if acc else "fa_default"

            idempotency_key = f"pout_{payout_id_str}"
            try:
                payout_resp = await self.provider.create_payout(
                    payout_ledger_id=uuid.UUID(payout_id_str),
                    amount=net_amt,
                    currency="INR",
                    fund_account_id=fa_id,
                    idempotency_key=idempotency_key,
                    reference_id=item.get("booking_id") or payout_id_str,
                )

                provider_tx_id = payout_resp.get("id")
                PayoutStateMachine.enforce_transition(PayoutStatus.ELIGIBLE, PayoutStatus.PROCESSING)
                PayoutStateMachine.enforce_transition(PayoutStatus.PROCESSING, PayoutStatus.PAID)

                self.client.table("mechanic_payout_ledger").update({
                    "status": PayoutStatus.PAID.value,
                    "provider_payout_id": provider_tx_id,
                    "settled_at": now_iso,
                    "updated_at": now_iso,
                }).eq("id", payout_id_str).execute()

                record_audit_log(
                    action="payout_settled",
                    entity_type="mechanic_payout_ledger",
                    entity_id=uuid.UUID(payout_id_str),
                    actor_id=actor_id,
                    actor_role=actor_role,
                    old_data={"status": "eligible"},
                    new_data={"status": "paid", "provider_payout_id": provider_tx_id, "batch_id": batch_id_str},
                )
                success_count += 1

                # Notify mechanic of settled payout
                try:
                    m_prof = self.client.table("mechanic_profiles").select("user_id").eq("id", str(item["mechanic_id"])).execute()
                    if m_prof.data and m_prof.data[0].get("user_id"):
                        m_uid = uuid.UUID(str(m_prof.data[0]["user_id"]))
                        await self.notifications.notify_settlement_completed_to_mechanic(
                            mechanic_user_id=m_uid,
                            payout_id=uuid.UUID(payout_id_str),
                            amount=net_amt,
                            batch_number=batch["batch_number"],
                        )
                except Exception as notif_err:
                    logger.warning("notify_mechanic_payout_completed_failed", error=str(notif_err))

            except Exception as disp_err:
                logger.error("payout_item_disbursement_failed", payout_id=payout_id_str, error=str(disp_err))
                self.client.table("mechanic_payout_ledger").update({
                    "status": PayoutStatus.FAILED.value,
                    "failure_reason": str(disp_err),
                    "updated_at": now_iso,
                }).eq("id", payout_id_str).execute()

                try:
                    m_prof = self.client.table("mechanic_profiles").select("user_id").eq("id", str(item["mechanic_id"])).execute()
                    if m_prof.data and m_prof.data[0].get("user_id"):
                        m_uid = uuid.UUID(str(m_prof.data[0]["user_id"]))
                        await self.notifications.notify_payout_failed_to_mechanic(
                            mechanic_user_id=m_uid,
                            payout_id=uuid.UUID(payout_id_str),
                            reason=str(disp_err),
                        )
                except Exception as notif_err:
                    logger.warning("notify_mechanic_payout_failed_error", error=str(notif_err))

        # 4. Mark batch completed if all items disbursed
        final_batch_status = (
            SettlementBatchStatus.COMPLETED.value
            if success_count == len(items)
            else SettlementBatchStatus.FAILED.value
        )
        self.client.table("settlement_batches").update({
            "status": final_batch_status,
            "completed_at": now_iso if final_batch_status == SettlementBatchStatus.COMPLETED.value else None,
            "updated_at": now_iso,
        }).eq("id", batch_id_str).execute()

        record_audit_log(
            action="settlement_submitted",
            entity_type="settlement_batch",
            entity_id=batch_id,
            actor_id=actor_id,
            actor_role=actor_role,
            new_data={"status": final_batch_status, "processed_items": success_count, "total_items": len(items)},
        )

        updated_batch_data = {
            **batch,
            "status": final_batch_status,
            "submitted_at": now_iso,
            "completed_at": now_iso if final_batch_status == SettlementBatchStatus.COMPLETED.value else None,
            "updated_at": now_iso,
        }
        return self._format_batch_response(updated_batch_data)

    async def list_settlements_for_mechanic(
        self,
        mechanic_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List settlement history for the authenticated mechanic."""
        safe_limit = min(max(1, limit), 100)
        safe_offset = max(0, offset)

        res = (
            self.client.table("mechanic_payout_ledger")
            .select("*, settlement_batches(batch_number, status, submitted_at, completed_at)")
            .eq("mechanic_id", str(mechanic_id))
            .in_("status", [PayoutStatus.PAID.value, PayoutStatus.PROCESSING.value, PayoutStatus.FAILED.value])
            .order("settled_at", desc=True)
            .execute()
        )
        records = res.data or []
        paginated = records[safe_offset : safe_offset + safe_limit]

        results = []
        for r in paginated:
            batch_data = r.get("settlement_batches") or {}
            if isinstance(batch_data, list) and len(batch_data) > 0:
                batch_data = batch_data[0]

            results.append({
                "payout_id": r["id"],
                "booking_id": r["booking_id"],
                "batch_id": r.get("settlement_batch_id"),
                "batch_number": batch_data.get("batch_number"),
                "net_amount": format_decimal(r.get("net_amount")),
                "currency": r.get("currency", "INR"),
                "status": r.get("status"),
                "settled_at": r.get("settled_at"),
                "failure_reason": r.get("failure_reason"),
            })

        return results

    # ==========================================================================
    # 5. WEBHOOK RECONCILIATION
    # ==========================================================================

    async def process_payout_webhook(
        self,
        raw_body: bytes,
        signature_header: str | None,
        provider: str = "razorpayx",
    ) -> dict[str, Any]:
        """
        Reconcile RazorpayX payout & penny drop webhooks using existing public.webhook_events.
        """
        import json
        now_iso = datetime.now(timezone.utc).isoformat()

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload in webhook request.",
            )

        event = payload.get("event")
        event_id = payload.get("event_id") or payload.get("id") or str(uuid.uuid4())
        if not event:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing 'event' in payload.")

        # 1. Deduplicate via public.webhook_events
        evt_check = (
            self.client.table("webhook_events")
            .select("id")
            .eq("provider", provider)
            .eq("event_id", event_id)
            .execute()
        )
        if evt_check.data and len(evt_check.data) > 0:
            logger.info("payout_webhook_duplicate_caught", event_id=event_id, provider=provider)
            return {"status": "already_processed", "event_id": event_id}

        try:
            self.client.table("webhook_events").insert({
                "id": str(uuid.uuid4()),
                "provider": provider,
                "event_id": event_id,
                "event_type": event,
                "payload": sanitize_audit_payload(payload),
                "processed_at": now_iso,
            }).execute()
        except Exception as ins_err:
            logger.warning("webhook_events_insert_conflict", error=str(ins_err))
            return {"status": "already_processed", "event_id": event_id}

        # 2. Process events
        payout_entity = payload.get("payload", {}).get("payout", {}).get("entity", {})
        fund_account_validation = payload.get("payload", {}).get("fund_account_validation", {}).get("entity", {})

        if event == "payout.processed" and payout_entity:
            payout_ref = payout_entity.get("reference_id") or payout_entity.get("id")
            p_res = None
            if payout_ref:
                p_res = self.client.table("mechanic_payout_ledger").select("*").eq("id", str(payout_ref)).execute()
            if not p_res or not p_res.data:
                provider_id = payout_entity.get("id")
                if provider_id:
                    p_res = self.client.table("mechanic_payout_ledger").select("*").eq("provider_payout_id", str(provider_id)).execute()

            if p_res and p_res.data and len(p_res.data) > 0:
                p_item = p_res.data[0]
                self.client.table("mechanic_payout_ledger").update({
                    "status": PayoutStatus.PAID.value,
                    "settled_at": now_iso,
                    "updated_at": now_iso,
                }).eq("id", p_item["id"]).execute()
                record_audit_log(
                    action="payout_reconciled",
                    entity_type="mechanic_payout_ledger",
                    entity_id=uuid.UUID(p_item["id"]),
                    actor_role="gateway_webhook",
                    new_data={"status": "paid", "event_id": event_id},
                    client=self.client,
                )
                try:
                    m_prof = self.client.table("mechanic_profiles").select("user_id").eq("id", str(p_item["mechanic_id"])).execute()
                    if m_prof.data and m_prof.data[0].get("user_id"):
                        m_uid = uuid.UUID(str(m_prof.data[0]["user_id"]))
                        await self.notifications.notify_settlement_completed_to_mechanic(
                            mechanic_user_id=m_uid,
                            payout_id=uuid.UUID(p_item["id"]),
                            amount=p_item.get("net_amount", "0.00"),
                        )
                except Exception as notif_err:
                    logger.warning("webhook_notify_payout_completed_failed", error=str(notif_err))

        elif event == "payout.failed" and payout_entity:
            payout_ref = payout_entity.get("reference_id") or payout_entity.get("id")
            p_res = None
            if payout_ref:
                p_res = self.client.table("mechanic_payout_ledger").select("*").eq("id", str(payout_ref)).execute()
            if not p_res or not p_res.data:
                provider_id = payout_entity.get("id")
                if provider_id:
                    p_res = self.client.table("mechanic_payout_ledger").select("*").eq("provider_payout_id", str(provider_id)).execute()

            if p_res and p_res.data and len(p_res.data) > 0:
                p_item = p_res.data[0]
                fail_reason = payout_entity.get("failure_reason") or "Payout failed by provider"
                self.client.table("mechanic_payout_ledger").update({
                    "status": PayoutStatus.FAILED.value,
                    "failure_reason": fail_reason,
                    "updated_at": now_iso,
                }).eq("id", p_item["id"]).execute()
                record_audit_log(
                    action="payout_failed",
                    entity_type="mechanic_payout_ledger",
                    entity_id=uuid.UUID(p_item["id"]),
                    actor_role="gateway_webhook",
                    new_data={"status": "failed", "event_id": event_id},
                    client=self.client,
                )
                try:
                    m_prof = self.client.table("mechanic_profiles").select("user_id").eq("id", str(p_item["mechanic_id"])).execute()
                    if m_prof.data and m_prof.data[0].get("user_id"):
                        m_uid = uuid.UUID(str(m_prof.data[0]["user_id"]))
                        await self.notifications.notify_payout_failed_to_mechanic(
                            mechanic_user_id=m_uid,
                            payout_id=uuid.UUID(p_item["id"]),
                            reason=fail_reason,
                        )
                except Exception as notif_err:
                    logger.warning("webhook_notify_payout_failed_error", error=str(notif_err))

        elif event == "payout.reversed" and payout_entity:
            payout_ref = payout_entity.get("reference_id") or payout_entity.get("id")
            p_res = None
            if payout_ref:
                p_res = self.client.table("mechanic_payout_ledger").select("*").eq("id", str(payout_ref)).execute()
            if not p_res or not p_res.data:
                provider_id = payout_entity.get("id")
                if provider_id:
                    p_res = self.client.table("mechanic_payout_ledger").select("*").eq("provider_payout_id", str(provider_id)).execute()

            if p_res and p_res.data and len(p_res.data) > 0:
                p_item = p_res.data[0]
                rev_reason = payout_entity.get("failure_reason") or "Disbursement reversed by clearinghouse"
                self.client.table("mechanic_payout_ledger").update({
                    "status": PayoutStatus.REVERSED.value,
                    "reversed_at": now_iso,
                    "failure_reason": rev_reason,
                    "updated_at": now_iso,
                }).eq("id", p_item["id"]).execute()
                record_audit_log(
                    action="payout_reversed",
                    entity_type="mechanic_payout_ledger",
                    entity_id=uuid.UUID(p_item["id"]),
                    actor_role="gateway_webhook",
                    new_data={"status": "reversed", "event_id": event_id},
                    client=self.client,
                )
                try:
                    m_prof = self.client.table("mechanic_profiles").select("user_id").eq("id", str(p_item["mechanic_id"])).execute()
                    if m_prof.data and m_prof.data[0].get("user_id"):
                        m_uid = uuid.UUID(str(m_prof.data[0]["user_id"]))
                        await self.notifications.notify_payout_reversed_to_mechanic(
                            mechanic_user_id=m_uid,
                            payout_id=uuid.UUID(p_item["id"]),
                            reason=rev_reason,
                        )
                except Exception as notif_err:
                    logger.warning("webhook_notify_payout_reversed_error", error=str(notif_err))

        elif event == "fund_account.validation.completed" and fund_account_validation:
            fa_id = fund_account_validation.get("fund_account", {}).get("id")
            if fa_id:
                acc_res = (
                    self.client.table("mechanic_payout_accounts")
                    .select("id, mechanic_id, masked_account_number")
                    .eq("provider_fund_account_id", fa_id)
                    .execute()
                )
                if acc_res.data and len(acc_res.data) > 0:
                    acc_row = acc_res.data[0]
                    acc_id = acc_row["id"]
                    self.client.table("mechanic_payout_accounts").update({
                        "verification_status": PayoutAccountVerificationStatus.VERIFIED.value,
                        "verified_at": now_iso,
                        "updated_at": now_iso,
                    }).eq("id", acc_id).execute()
                    record_audit_log(
                        action="payout_account_verification_succeeded",
                        entity_type="mechanic_payout_account",
                        entity_id=uuid.UUID(acc_id),
                        actor_role="gateway_webhook",
                        new_data={"verification_status": "verified"},
                    )
                    try:
                        m_prof = self.client.table("mechanic_profiles").select("user_id").eq("id", str(acc_row["mechanic_id"])).execute()
                        if m_prof.data and m_prof.data[0].get("user_id"):
                            m_uid = uuid.UUID(str(m_prof.data[0]["user_id"]))
                            await self.notifications.notify_payout_account_verified(
                                mechanic_user_id=m_uid,
                                account_id=uuid.UUID(acc_id),
                                masked_account_number=acc_row.get("masked_account_number", "•••• ****"),
                            )
                    except Exception as notif_err:
                        logger.warning("webhook_notify_verification_failed", error=str(notif_err))

        return {"status": "processed", "event": event, "event_id": event_id}
