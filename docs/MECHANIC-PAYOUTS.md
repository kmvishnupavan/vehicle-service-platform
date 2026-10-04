# Phase 8.7 — Mechanic Payout Ledger & Settlement Foundation

## 1. Overview & Architecture

Phase 8.7 establishes an authoritative, financially consistent, and auditable **Payout Ledger & Settlement Foundation** for mechanics on the on-demand vehicle service platform (`vehicle-service-platform`, Supabase ref: `dfigtryvvujhwuiyzdvs`).

Prior to Phase 8.7 (Phase 8.6), mechanic earnings were derived dynamically from customer booking totals (`subtotal + additional_charges`). Phase 8.7 eliminates this ambiguity by creating a dedicated, append-only double-entry financial foundation where every rupee paid by the customer is explicitly accounted for across:
1. **Customer Gross Service Revenue**: Base service subtotal + approved additional work charges.
2. **Platform Commission**: Retained fee calculated via active platform commission policies.
3. **Applicable Deductions**: Mechanic tooling, penalties, or platform chargebacks.
4. **Net Attributable Payout**: Exact amount payable to the mechanic.
5. **Settlement Lifecycle State**: Strict state machine tracking funds from hold to cleared, processing, paid, or reversed.

```mermaid
flowchart TD
    A[Customer Completes Payment] --> B[PaymentService._settle_successful_payment]
    B --> C[Payment Captured & Booking Paid]
    C --> D[PayoutService.create_payout_for_booking]
    D --> E[Query Active Commission Policy (e.g. 20%)]
    E --> F[Calculate Components via Strict Decimal Math]
    F --> G[Insert public.mechanic_payout_ledger (status: eligible)]
    G --> H[Record Audit Event: payout_created / payout_eligible]
    
    subgraph Settlement Disbursement
        G --> I[Provider Abstraction: PayoutProvider]
        I --> J[Transition to processing]
        J --> K[Disburse Funds / Bank Settlement]
        K --> L[Transition to paid]
    end
    
    subgraph Refund & Dispute Flow
        M[Gateway Webhook: refund.processed] --> N[PayoutService.handle_payment_refund]
        N -->|Full Refund| O[Transition to reversed & record reversed_at]
        N -->|Partial Refund| P[Adjust gross, commission & net on unsettled payout]
    end
```

---

## 2. Commission Policy Configuration

Platform commissions are governed authoritatively in the database by `public.commission_policies`:

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | `UUID PRIMARY KEY` | Policy unique identifier |
| `name` | `TEXT NOT NULL` | Policy display name (e.g. "Standard Platform Commission (20%)") |
| `commission_rate` | `NUMERIC(5, 4) NOT NULL` | Fraction between 0.0000 and 1.0000 (Check constraint: `commission_rate >= 0.0 AND commission_rate <= 1.0`) |
| `currency` | `TEXT NOT NULL DEFAULT 'INR'` | Currency code |
| `is_active` | `BOOLEAN NOT NULL DEFAULT true` | Policy activation switch |
| `effective_from` | `TIMESTAMPTZ NOT NULL` | Policy start timestamp |
| `effective_to` | `TIMESTAMPTZ NULL` | Policy expiry timestamp |
| `metadata` | `JSONB` | Extensible policy metadata |

### Default Policy
- Initial seeded policy: `id = c0000000-0000-0000-0000-000000000001`
- Display Name: `Standard Platform Commission (20%)`
- Applied Rate: `0.2000` (20% platform commission retained, 80% net mechanic payout).
- Historical Invariance: Payout ledger records permanently store both `commission_rate` and `commission_amount` at creation time. Historical payouts are **never** recalculated when commission policies change.

---

## 3. Financial Calculation Formula (Strict Decimal Money Handling)

All monetary calculations use Python `Decimal` (quantized strictly to `Decimal('0.01')` or 2 decimal places). Floating-point arithmetic is strictly prohibited in backend financial services.

$$\text{Gross Amount} = \text{Booking Subtotal} + \text{Approved Additional Work}$$
$$\text{Platform Commission} = \text{Round}_{0.01}(\text{Gross Amount} \times \text{Commission Rate})$$
$$\text{Net Payout} = \max(0.00, \text{Gross Amount} - \text{Platform Commission} - \text{Deduction Amount})$$

Example:
- Customer Gross Service Amount: ₹1,000.00
- Platform Commission Rate: 20% (0.2000)
- Platform Commission Retained: ₹200.00
- Deductions: ₹0.00
- Net Mechanic Payout: ₹800.00

---

## 4. Payout Lifecycle State Machine

The payout lifecycle is governed by `backend/app/services/payout_state_machine.py` (`PayoutStateMachine`).

### Lifecycle States
1. `pending`: Initial ledger entry awaiting payment verification, dispute window, or settlement hold.
2. `eligible`: Booking payment confirmed settled (`payments.status = 'captured'`), funds cleared for disbursement.
3. `processing`: Payout batch or provider transfer instruction dispatched.
4. `paid`: Funds successfully disbursed and settled to the mechanic's account.
5. `failed`: Payout transfer rejected by banking provider or invalid beneficiary details.
6. `reversed`: Payout clawed back or cancelled due to customer refund or chargeback.
7. `cancelled`: Associated booking cancelled or voided before disbursement.

### Permitted State Transitions
```
pending     ──► eligible, cancelled, reversed
eligible    ──► processing, reversed, cancelled
processing  ──► paid, failed, reversed
paid        ──► reversed
failed      ──► processing (retry), cancelled, reversed
reversed    ──► (Terminal)
cancelled   ──► (Terminal)
```
*Note: Same-state transitions (e.g. `eligible -> eligible`) are treated as idempotent no-ops.* Arbitrary status jumps (e.g. `pending -> paid` or `reversed -> processing`) are rejected with `HTTP 400 Bad Request`.

---

## 5. Refund & Reversal Reconciliation

When Razorpay triggers `refund.processed` or support initiates a refund, `PaymentService.process_webhook` immediately invokes `PayoutService.handle_payment_refund`:

### A. Full Refunds
- If the payout is in an unsettled state (`pending`, `eligible`, `processing`):
  - Transition payout status to `reversed`.
  - Set `reversed_at = NOW()`.
  - Record audit event `payout_reversed`.
- If the payout was already `paid` to the mechanic:
  - Transition payout status to `reversed`.
  - Record reversal timestamp and create an audit log documenting the post-settlement clawback / balance adjustment.

### B. Partial Refunds
- If the payout is unsettled (`pending` or `eligible`):
  - Recalculate gross revenue: $\text{New Gross} = \max(0, \text{Old Gross} - \text{Refund Amount})$.
  - Recalculate platform commission and net mechanic payout using the original applied commission rate.
  - Update `gross_amount`, `commission_amount`, and `net_amount` on the ledger.
  - Record audit log `payout_partial_refund_adjusted`.
- If the payout is already `paid` or `processing`:
  - Preserve settled figures to avoid corrupting banking disbursement records.
  - Append partial refund adjustment metadata and audit log `payout_partial_refund_post_settlement`.

---

## 6. Idempotency & Concurrency

1. **Database-Level Constraint**:
   - `public.mechanic_payout_ledger` enforces a strict unique constraint:
     `CONSTRAINT uq_payout_ledger_booking_mechanic UNIQUE (booking_id, mechanic_id)`
   - Concurrent creation requests or duplicate webhooks for the same booking cannot create duplicate financial ledger lines.
2. **Application-Level Check**:
   - `create_payout_for_booking` queries the ledger by `booking_id` prior to insertion.
   - If a race condition occurs, the unique constraint catches the duplicate and returns the existing ledger row.

---

## 7. Row-Level Security (RLS) & Cross-Mechanic Isolation

1. **Mechanic Profile Isolation**:
   - Mechanics can **only read** their own payout ledger lines:
     `((mechanic_id = get_mechanic_id_for_user(auth.uid())) OR is_admin_or_support())`
   - Mechanics cannot insert, update, or delete payout records.
2. **Customer Prohibition**:
   - Customers have zero access to the payout ledger. Requests to `/api/v1/mechanics/payouts` by customer tokens return `HTTP 403 Forbidden`.
3. **Backend Service Role**:
   - Ledger creation, status transitions, and refund adjustments execute via the privileged backend service client.

---

## 8. Audit Logging

All payout events generate structured audit records in `public.audit_logs`:
- `payout_created`
- `payout_eligible`
- `payout_processing`
- `payout_paid`
- `payout_failed`
- `payout_reversed`
- `payout_partial_refund_adjusted`

Each record captures `actor_id`, `actor_role`, `old_data`, and `new_data` with sanitized payloads (secrets, tokens, and raw bank details stripped).

---

## 9. Provider Abstraction (`PayoutProvider`)

Real bank disbursements are decoupled via `PayoutProvider`:
- File: `backend/app/services/payout_service.py`
- Methods: `create_payout(payout_ledger_id, amount, currency, beneficiary_metadata)`
- Current Implementation: Safe simulation adapter (`test_simulator`) marked strictly for test environments.
- Critical Rule: Money movement is **never faked** in production code.

### Future Real Payout Integration (RazorpayX / Stripe Connect)
- For India: RazorpayX Payouts API (`POST /v1/payouts` with fund accounts and contacts).
- Requirements before enabling live disbursements:
  1. Mechanic Bank Account & IFSC verification (Penny drop verification via RazorpayX).
  2. Mechanic KYC compliance.
  3. Webhook handling for `payout.processed`, `payout.reversed`, and `payout.failed`.
  4. Daily transfer batching with dispute hold periods (e.g. T+2 days hold).

---

## 10. Frontend Implementation

- **Page**: `frontend/src/pages/MechanicPayoutsPage.tsx` (`/mechanic/payouts`)
- **Components**:
  - `PayoutSummaryCards.tsx`: Top-level summary cards (Total Net, Eligible, Paid, Pending) and secondary breakdown (Gross, Commission Retained, Deductions, Reversed).
  - `PayoutFilters.tsx`: Status filter pills (`all`, `eligible`, `pending`, `processing`, `paid`, `reversed`), date range presets (`all`, `today`, `this_week`, `this_month`, custom range), and refresh.
  - `PayoutTable.tsx`: Authoritative ledger table with expandable itemized financial breakdown (`Gross Base - Commission - Deductions = Net Payout`), timestamps, and status badges.
  - `PayoutStatusBadge.tsx`: Color-coded, accessible status badge for all 7 lifecycle states.
- **Dashboard Reconciliation**:
  - Phase 8.6 `MechanicDashboardPage` and `EarningsSummary` updated to link directly to the authoritative Payout Ledger.
  - `mechanic_dashboard_service.py` queries `mechanic_payout_ledger` for earnings calculations, preventing competing financial figures.

---

## 11. Known Limitations & Next Steps

1. **Simulated Payout Provider**: Actual bank disbursements require an active RazorpayX business account with approved penny-drop verification.
2. **KYC & Bank Account Capture**: A future phase should introduce mechanic bank account onboarding and validation UI before funds can transition from `eligible` to `processing`.
3. **Automated Settlement Cron**: Settlement batching should be scheduled via a background cron job (e.g. daily at midnight UTC) to aggregate `eligible` payouts into provider disbursement batches.
