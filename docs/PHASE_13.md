# Phase 13: Production Reliability, Background Jobs, Scheduled Bookings, Dynamic ETA & Operational Automation

## 1. Executive Summary
Phase 13 elevates VehicleCare from a "production-ready application" into a "production-grade operational platform." It equips the system with autonomous background processing, resilient dynamic road routing, proactive GPS anomaly detection, decoupled advance appointment scheduling, versioned matching policy governance, automated financial reconciliation, and real-time operational observability.

All changes adhere strictly to:
- **Target Supabase Reference**: `dfigtryvvujhwuiyzdvs` (`vehicle-service-platform`)
- **Untouched Resources**: `ai-code-reviewer` (`mzbdhuftanztvxmfqnhz`) remains 100% untouched.
- **Financial Safety**: `LIVE_PAYOUTS_ENABLED = false` and `PAYOUT_PROVIDER_MODE = sandbox`. No real money moved.
- **Canonical Invariants**: Booking state machine, RLS, audit logging, and financial ledger integrity preserved.

---

## 2. Key Architectural Pillars

### A. Autonomous Background Processing (`public.background_job_executions`)
- Built on **PostgreSQL distributed advisory transaction locks** (`pg_try_advisory_xact_lock`).
- Zero Redis / Celery required; worker instances can safely scale horizontally without colliding or running duplicate maintenance routines.
- 8 automated periodic jobs:
  1. `expire_mechanic_offers`: Atomically reclaims unaccepted offers.
  2. `advance_expired_matching_sessions`: Advances sessions through candidate waterfall.
  3. `reconcile_webhook_reservations`: Sweeps stuck webhook ingress entries.
  4. `reconcile_pending_payments`: Detects orphaned payment intents.
  5. `reconcile_payouts`: Audits payout ledger transfers against sandbox provider.
  6. `retry_failed_notifications`: Drains failed notifications using exponential backoff.
  7. `dispatch_scheduled_bookings`: Dispatches upcoming bookings 30 minutes before window.
  8. `refresh_operational_metrics`: Aggregates hourly KPI snapshots into `operational_metrics_snapshots`.

### B. Scheduled Bookings Subsystem (`public.scheduled_bookings`)
- Decouples appointment scheduling from the canonical booking lifecycle (`pending`, `searching_mechanic`, etc.).
- Enforces strict UTC datetime parsing and customer timezone awareness (e.g. `Asia/Kolkata`).
- Computes automated dispatch time (`dispatch_at = scheduled_start_at - dispatch_window_minutes`).
- Guarantees idempotent dispatch execution and race-safe customer cancellation prior to mechanic assignment.

### C. Resilient Dynamic Road ETA (`OSRMRoutingProvider`)
- Wraps external OpenStreetMap OSRM routing in a 3-strike circuit breaker and exponential backoff retry handler.
- Fallback route generation computes haversine distance with urban tortuosity factor (1.414) and tags `eta_source = 'fallback'`.
- Street-block grid coordinate quantization (~110m scale, 3 decimal places) in `ETACache` with 300s TTL prevents network thrashing.

### D. Location Freshness & GPS Anomaly Detection (`public.mechanic_location_anomalies`)
- Centralized tiered freshness states:
  - `FRESH` (<= 60s)
  - `STALE` (61s - 300s)
  - `OFFLINE` (> 300s)
- Mathematical GPS anomaly detector flags impossible speeds (> 160 km/h), large teleportation jumps, and out-of-bounds coordinates, persisting audit trails without discarding valid telemetry.

### E. Versioned Matching Policy Governance (`public.matching_policies`)
- Dynamic database-backed matching weights validated to sum strictly to `1.000`.
- Supports admin draft creation and atomic single-active policy activation with historical audit log trails.
- Preserves immutable candidate score explanations during matching session runs.

### F. Operations & Reliability Center (Frontend UX)
- Extended Admin Operations Dashboard with tabs for System Health & Background Jobs, Operational KPIs & Alert Thresholds, Scheduled Booking Monitoring, Location Anomaly Ledgers, Matching Policy Administration, and Financial Reconciliation.
- Customer booking interface with interactive date/window picker, confirmed schedule cards, and live countdown timer.
- Mechanic dashboard view displaying upcoming assigned scheduled appointments and tooling preparation requirements.
