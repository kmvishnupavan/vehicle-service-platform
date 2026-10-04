# Scheduled Bookings Subsystem

## 1. Overview
The Scheduled Bookings subsystem allows customers to book vehicle services days in advance while preserving the existing canonical booking state machine (`pending`, `searching_mechanic`, `mechanic_assigned`, etc.).

---

## 2. Decoupled Lifecycle Entity (`public.scheduled_bookings`)
Instead of mutating the booking status into non-standard states, scheduling is decoupled into an auxiliary scheduling entity:
- `booking_id`: Foreign key to `public.bookings` with unique constraint (`1:1`).
- `scheduled_start_at`: Window start time in UTC.
- `scheduled_end_at`: Window end time in UTC.
- `timezone`: Customer's local timezone (e.g. `Asia/Kolkata`, `UTC`).
- `dispatch_at`: Automatically computed timestamp (`scheduled_start_at - dispatch_window_minutes`).
- `status`: `scheduled` -> `dispatching` -> `dispatched` | `cancelled` | `failed`.

---

## 3. Automated Dispatch & Race-Safe Cancellation

### Automated Dispatch
The `dispatch_scheduled_bookings` background job runs every minute:
1. Queries rows where `now() >= dispatch_at` and `status = 'scheduled'`.
2. Transitions status to `dispatching`.
3. Triggers matching engine session creation via `MatchingService.start_matching_session()`.
4. On assignment creation, transitions status to `dispatched`.

### Customer Cancellation Prior to Dispatch
Customers can cancel a scheduled appointment prior to mechanic dispatch via `DELETE /bookings/{id}/schedule`:
1. Checks that the booking status is `pending` or `searching_mechanic`.
2. Atomically transitions `public.scheduled_bookings.status` to `cancelled`.
3. Sets parent booking `booking_status` to `cancelled` and records an audit log entry.
4. If a mechanic has already accepted and is en-route, cancellation follows standard service cancellation protocols with cancellation fee policies.
