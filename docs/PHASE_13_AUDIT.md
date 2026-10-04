# Phase 13 Initial Audit & Architectural Assessment

## 1. Executive Summary
- **Target Project**: `vehicle-service-platform` (Supabase reference: `dfigtryvvujhwuiyzdvs`).
- **Safety Barriers**:
  - `LIVE_PAYOUTS_ENABLED = false`
  - `PAYOUT_PROVIDER_MODE = sandbox`
  - `ai-code-reviewer` (`mzbdhuftanztvxmfqnhz`) remains strictly untouched.
  - Baseline verified: Backend 445/445 tests passing; Frontend 111/111 tests passing; 46 tables with active RLS; 21 valid sequential migrations.

---

## 2. Existing Background Processing & Scheduled Execution
- **Current State**:
  - There is currently **no continuous background worker or scheduled job runner**.
  - Maintenance operations (such as `MatchingService.expire_stale_offers()` or `ReconciliationService.reconcile_payments()`) exist only as on-demand service methods triggered via REST endpoints or unit test calls.
  - The `bookings` table has `scheduled_at TIMESTAMPTZ NOT NULL`, but bookings are inserted with status `pending` immediately, with no forward-looking dispatch window or decoupled scheduled booking state machine.
- **Architectural Decision**:
  - **No Redis / Celery required**: PostgreSQL advisory locks (`pg_try_advisory_xact_lock`) and database-backed job execution rows (`public.background_job_executions`) provide atomic, concurrent-safe, auditable background processing that survives application restarts.
  - A unified job runner will orchestrate the 8 required jobs (`expire_mechanic_offers`, `advance_expired_matching_sessions`, `reconcile_webhook_reservations`, `reconcile_pending_payments`, `reconcile_payouts`, `retry_failed_notifications`, `dispatch_scheduled_bookings`, `refresh_operational_metrics`).
  - Can run both inside the FastAPI lifespan and via standalone CLI: `python -m app.commands.run_background_jobs`.

---

## 3. Existing Matching & Candidate Offer Expiration
- **Current State**:
  - Multi-factor heuristic matching (`MatchingService`) ranks mechanics by geodesic proximity, rating, availability, reliability, workload, and acceptance rate.
  - Candidate offer has an `expires_at` column in `mechanic_assignments`.
  - Atomic PostgreSQL RPCs `accept_mechanic_assignment` and `reject_mechanic_assignment` use `SELECT ... FOR UPDATE` on both assignment and booking rows, checking `expires_at < clock_timestamp()` to reject expired offers.
  - `MatchingService._advance_to_next_candidate()` handles advancing attempts from 1 to `MAX_MATCHING_ATTEMPTS` (3).
- **Gaps & Risks Identified**:
  - Without an automatic background job, expired offers sit in `offered` status until a mechanic explicitly rejects or the mechanic/customer polls.
  - Matching weights (0.30 proximity, 0.15 availability, etc.) are hardcoded class constants rather than versioned database policies.
  - Candidate scores are computed in-memory and partially saved in session JSON, but lack an explicit versioned policy link for historical auditability.

---

## 4. Existing ETA Provider Abstraction & Routing Resilience
- **Current State**:
  - `RoutingProvider` abstract base class with `MockRoutingProvider` and `OSRMRoutingProvider`.
  - In-memory `ETACache` quantizes coordinates to 3 decimal places (~110m grid) with a 300-second TTL.
  - `OSRMRoutingProvider` makes HTTP calls with a 3.0-second timeout and falls back to `MockRoutingProvider` on network failure.
- **Gaps & Risks Identified**:
  - When OSRM fails or times out, the fallback provider does not explicitly tag `eta_source = 'fallback'`.
  - No circuit breaker pattern: consecutive network timeouts repeatedly hit OSRM on every query, causing latency spikes.
  - Missing retry logic with exponential backoff on transient network faults.

---

## 5. Existing Mechanic Location & Freshness Monitoring
- **Current State**:
  - `mechanic_profiles` tracks `current_latitude`, `current_longitude`, `current_location_updated_at`.
  - `mechanic_locations` stores an append-only audit trail subject to 5-second throttling.
  - Ephemeral live location updates are broadcast to Supabase Realtime channel `booking-location:{booking_id}`.
  - Location freshness is checked in candidate discovery (`LOCATION_FRESHNESS_MINUTES = 30`).
- **Gaps & Risks Identified**:
  - Freshness threshold is coarse (30 minutes) and not centralized into tiered operational states (`FRESH <= 60s`, `STALE > 60s`, `OFFLINE > 300s`).
  - No GPS anomaly detection: a mechanic jumping 200 km in 30 seconds (or reporting impossible speed > 160 km/h) is accepted without flagging.

---

## 6. Existing Reconciliation Engine
- **Current State**:
  - `ReconciliationService` implements:
    - `reconcile_payments()`: Detects discrepancies between Razorpay payments and internal database.
    - `reconcile_payouts()`: Audits payout ledger vs. provider transfers.
    - `reconcile_settlements()`: Verifies maker-checker batch totals.
    - `reconcile_webhooks()`: Audits webhook idempotency log.
  - Persists discrepancies into `public.reconciliation_discrepancies`.
  - Adheres strictly to **DETECT + REPORT** without mutating financial ledger rows.
- **Gaps & Risks Identified**:
  - Execution is purely manual/admin-triggered. Needs automatic periodic scheduled execution via background job runner.

---

## 7. Existing Notification System & Retry
- **Current State**:
  - `NotificationService.send_notification()` handles typed events, in-app notifications, and realtime events.
  - Database-enforced idempotency via unique `(user_id, event_id)` on `public.notifications`.
  - Exceptions are caught and logged so business transactions do not fail if notifications fail.
- **Gaps & Risks Identified**:
  - If a notification fails (e.g., database timeout or transient network error), it is merely logged as `notification_dispatch_failed`. There is no persistent retry queue with exponential backoff.

---

## 8. Database Constraints, Indexes & RLS
- **Current State**:
  - 46 tables total; all 46 tables have Row-Level Security (`ENABLE ROW LEVEL SECURITY`) explicitly active.
  - Foreign key covering indexes exist for all major relationships.
  - `accept_mechanic_assignment` and `reject_mechanic_assignment` are `SECURITY DEFINER` with fixed `search_path = public, extensions, pg_temp`.
- **New Tables Required in Migration `20261004000023_production_operations_automation.sql`**:
  1. `public.scheduled_bookings`: Decoupled scheduling lifecycle with unique constraint on `booking_id`.
  2. `public.matching_policies`: Versioned matching weight policies with sum-to-1.0 CHECK constraint and partial unique index on `is_active = true`.
  3. `public.background_job_executions`: Generic execution ledger with status, timings, counts, and error summaries.
  4. `public.mechanic_location_anomalies`: Anomaly detection records for impossible speed, large jumps, and GPS spoofing.
  5. `public.notification_retries`: Retry queue for failed notifications with exponential backoff.
  6. `public.operational_metrics_snapshots`: Historical operational KPI snapshots.

---

## 9. Implementation Plan (Phased & Sequential)
1. **Migration 23 (`20261004000023_production_operations_automation.sql`)**:
   - Create tables with strict RLS, indexes, and constraints.
   - Seed default active matching policy (v1.0).
2. **Background Job Architecture (`app/services/background_jobs/`)**:
   - Generic execution tracker and PostgreSQL advisory lock manager.
   - Implement the 8 required jobs with idempotency and audit logs.
3. **Scheduled Bookings Subsystem (`app/services/scheduled_booking_service.py`)**:
   - Creation with UTC timezone validation, dispatch window calculation, idempotent `dispatch_scheduled_bookings()`, and race-safe cancellation.
4. **Dynamic ETA & Resilient Routing (`app/services/routing/`)**:
   - Add circuit breaker, retries, and explicit `eta_source = 'fallback'` tagging.
5. **Mechanic Heartbeat & Location Reliability (`app/services/location_reliability_service.py`)**:
   - Freshness evaluation (`fresh`, `stale`, `offline`), GPS anomaly detector (speed, distance jumps, coordinates), and anomaly logging.
6. **Matching Policy Versioning (`app/services/matching_policy_service.py`)**:
   - Dynamic policy retrieval, admin draft/activation with audit trail, and immutable score explanations.
7. **Notification Retry Worker (`app/services/notification_retry_service.py`)**:
   - Exponential backoff queue and idempotent delivery.
8. **Operational Metrics & Admin Operations (`app/services/operational_metrics_service.py`)**:
   - Aggregated metrics calculation and dashboard endpoints.
9. **Frontend Scheduled Booking UX & Admin Dashboard Extensions**:
   - Customer booking date/time picker with countdown, mechanic scheduled job badge, and admin operations tabs.
10. **Testing & Verification**:
    - Concurrency tests (dual offer expiry, dual dispatch, cancellation race).
    - Realistic load test simulation (100, 1,000, 10,000 mechanics).
    - Full regression run: pytest, npm test, build, migration validation, secret scan, production readiness.
