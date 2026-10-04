# Phase 8.9 — Settlement Notification Dispatch & Idempotency

## 1. Overview & Architectural Guarantees

Settlement notifications inform mechanics, administrators, and finance personnel about batch creation, dual-control decisions, bank processing milestones, and payout receipts.

To guarantee that network retries or concurrent webhook triggers never result in duplicate alerts or multiple financial emails, Phase 8.9 implements **deterministic event identification** and **database-backed idempotency**.

---

## 2. Deterministic Event Identification

Each notification event generates a deterministic, collision-resistant `event_id`:
```
settlement_batch_{batch_id}_{status_or_action}
```
For individual mechanic notifications within a batch:
```
settlement_payout_{payout_id}_{status}
```

### 2.1 Database Deduplication
The platform's notification system queries `public.notifications` for matching `(user_id, event_id)` pairs before inserting. When inserting via SQL or PostgREST, upsert constraints guarantee that duplicates are safely suppressed.

```python
async def send_settlement_notification(
    self,
    recipient_id: str,
    event_type: str,
    event_id: str,
    title: str,
    message: str,
    metadata: dict | None = None
) -> dict:
    # Verify idempotency
    existing = self.client.table("notifications").select("id").eq("user_id", recipient_id).eq("event_id", event_id).execute()
    if existing.data:
        return {"status": "duplicate_suppressed", "event_id": event_id}
        
    payload = {
        "user_id": recipient_id,
        "event_id": event_id,
        "type": event_type,
        "title": title,
        "message": message,
        "data": metadata or {},
        "is_read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    res = self.client.table("notifications").insert(payload).execute()
    return {"status": "dispatched", "notification_id": res.data[0]["id"]}
```

---

## 3. Notification Triggers & Matrix

| Lifecycle Stage | Target Audience | Event Identifier | Delivery Medium | Message Summary |
| :--- | :--- | :--- | :--- | :--- |
| **`batch_created`** (above threshold) | Admins / Checkers | `settlement_batch_{id}_created` | In-app / Email | "Settlement Batch {batch_no} created and awaits dual-control review." |
| **`batch_submitted`** (from draft) | Admins / Checkers | `settlement_batch_{id}_submitted` | In-app | "Batch {batch_no} submitted for approval by {maker_name}." |
| **`batch_approved`** | Maker / Finance | `settlement_batch_{id}_approved` | In-app / Push | "Batch {batch_no} approved by {checker_name}. Scheduled for disbursement." |
| **`batch_rejected`** | Maker | `settlement_batch_{id}_rejected` | In-app / Alert | "Batch {batch_no} rejected by {checker_name}: {reason}." |
| **`payout_processed`** | Mechanic | `settlement_payout_{id}_completed` | In-app / Statement | "Disbursement credit: ₹{net_amount} transferred to account ending in {last4}." |
| **`payout_failed`** | Mechanic & Admin | `settlement_payout_{id}_failed` | In-app / Priority | "Disbursement failure for Booking {booking_no}: {sanitized_reason}." |
| **`batch_cancelled`** | Admins | `settlement_batch_{id}_cancelled` | In-app | "Batch {batch_no} cancelled. Ledger items returned to eligible pool." |

---

## 4. Webhook Reconciliation & Reverse Sync

When third-party banking providers (e.g. RazorpayX) issue webhooks (`payout.processed`, `payout.reversed`, `payout.failed`), the webhook ingress endpoint verifies payload authenticity via HMAC signature before dispatching notifications:

1. **Dual Ledger Identification**: The webhook first checks the platform's `reference_id` or `id` on `mechanic_payout_ledger`. If absent, it queries `provider_payout_id`.
2. **State Transition Guard**: Webhook callbacks will only advance payout statuses from valid antecedent states (e.g., `processing` -> `paid`, or `processing` -> `failed`).
3. **Automated Notification**: On terminal status receipt, `notify_settlement_payout_processed` or `notify_settlement_payout_failed` executes idempotently.
