# Customer Approval Workflow & Concurrency Controls

## 1. Approval Overview
When additional parts, repairs, or diagnostic recommendations are identified during inspection or service:
1. Mechanics cannot unilaterally add fees or charges to customer bookings.
2. An explicit customer approval step is enforced via state `awaiting_customer_approval`.
3. The customer tracking interface displays the `CustomerApprovalModal` with an itemized breakdown:
   - Base Package Price
   - Diagnostic Additional Work Items (with explanations)
   - Replacement Parts Required
   - Technician Labor
   - Applied Discounts
   - 18% GST (Calculated deterministically)
   - Final Total Amount

---

## 2. Concurrency & Atomicity Safeguards
Customer approvals are protected against race conditions and invalid state changes:
- **Double-Approval Prevention**: Approval endpoint (`POST /api/v1/bookings/{id}/approve-estimate`) validates that `booking.booking_status == 'awaiting_customer_approval'`. A concurrent or duplicate approval request fails with HTTP 409 Conflict.
- **Race vs Cancellation**: If a booking is cancelled by support or timeout expires before approval, the status check fails and rejects the approval transaction.
- **Ownership Verification**: Only the customer who owns the booking (`booking.customer_id == user.id`) can execute approval or rejection.
- **Atomic Transition**:
  - Approving sets `booking.booking_status = 'service_in_progress'` and records `price_snapshot`.
  - Rejecting sets `booking.booking_status = 'service_in_progress'` (reverting to base service only) or `cancelled` depending on customer decision.
  - Generates audit event in `public.booking_audit_logs`.
  - Dispatches immediate realtime event and notification to the assigned mechanic.
