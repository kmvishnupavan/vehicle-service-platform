# Phase 14 Baseline Architecture & System Discovery

## 1. Executive Summary
This document establishes the verified baseline of the VehicleCare platform at the start of Phase 14 (Production Launch Certification & Real-World E2E Validation). The system is an on-demand doorstep vehicle service platform with complete booking lifecycles, intelligent mechanic matching, dynamic road ETA routing, automated background processing, maker-checker financial settlement, and operational observability.

---

## 2. Existing Platform Capabilities

### A. Customer Experience
- **Authentication**: Email/password registration and login with Supabase JWT and role claims (`customer`).
- **Vehicle Garage**: Register, view, update, and manage vehicle profiles (make, model, license plate, fuel type, VIN).
- **Service Catalog**: Browse categorized service offerings with transparent base pricing and labor estimates.
- **Booking & Scheduling**:
  - Immediate on-demand dispatch or scheduled future appointment window (`public.scheduled_bookings`).
  - Automatic dispatch countdown and pre-dispatch race-safe cancellation.
- **Live Mechanic Tracking**: Turn-by-turn road navigation, dynamic OSRM ETA, and ephemeral location tracking via Supabase Realtime (`booking-location:{booking_id}`).
- **Inspection & Customer Approval**: Interactive review of multi-point inspection items, mechanic-recommended additional work, and line-item estimates with cryptographic customer approval gating.
- **Payments & Reviews**: Integrated Razorpay sandbox payment processing with webhook idempotency, followed by verified mechanic ratings and reviews.

### B. Mechanic Operations
- **Dashboard & Workbenches**: Real-time incoming job offer modal with 60-second countdown timer, atomic acceptance/rejection, and daily earnings breakdown.
- **Service Operations Lifecycle**: En-route tracking, arrival confirmation, digital inspection checklists, photo evidence uploads, and additional work estimation.
- **Payout Accounts**: Onboarding bank accounts with IFSC validation and penny-drop verification.
- **Upcoming Scheduled Jobs**: Advance visibility into future scheduled service appointments with required tooling preparation instructions.

### C. Admin & Operations Center
- **System Health & Readiness**: Live readiness probe reporting API, PostgreSQL database connectivity, and background worker status.
- **Operational Metrics**: Real-time KPI aggregation (matching sessions, exhaustion rate, average time to match, offer acceptance/expiration, average ETA, routing fallback rate, stale location rate, and notification failure rate).
- **Configurable Alert Thresholds**: Dynamic sensitivity controls for operational anomaly alerting.
- **Background Job Runner**: On-demand and daemon execution tracking via PostgreSQL advisory locks (`pg_try_advisory_xact_lock`).
- **Matching Policy Governance**: Dynamic weight management for proximity, rating, availability, reliability, workload, and acceptance with sum-to-1.0 validation.
- **Settlement Maker-Checker**: Tiered payout batch approvals requiring checker approval for high-value transactions.
- **Reconciliation Engine**: Automated discrepancy detection across payments, payouts, maker-checker settlements, and webhook ingress logs.

---

## 3. Verified Baseline Test Metrics (Phase 13)

| Component | Test Runner | Files | Total Tests | Status |
|---|---|---|---|---|
| **Backend API & Services** | `pytest` | 31 test files | **468 passed**, 0 failures | PASS |
| **Frontend UI & Components** | `vitest` | 10 test files | **121 passed**, 0 failures | PASS |
| **Frontend Production Build** | `tsc && vite build` | — | Bundled in 11.85s | PASS |
| **Database Migrations** | `validate_migrations.py` | 22 files | 52 tables with RLS verified | PASS |
| **Secret Exposure Scanner** | `verify_secret_exposure.py` | Source & Dist | Zero secrets exposed | PASS |
| **Production Readiness** | `production_readiness.py` | Core probes | All 6 probes passed | READY |

---

## 4. Environment Variables & Configuration Matrix

| Variable | Scope | Expected Setting (Phase 14) | Purpose |
|---|---|---|---|
| `ENVIRONMENT` | Backend | `staging` / `development` / `production` | Deployment environment tag |
| `SUPABASE_URL` | Backend / Frontend | `https://dfigtryvvujhwuiyzdvs.supabase.co` | Target Supabase Postgres instance |
| `SUPABASE_PUBLISHABLE_KEY` | Backend / Frontend | Public anon key | Client-side API token |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend Only | Secure service role key | Elevated server-side administrative access |
| `SUPABASE_JWT_SECRET` | Backend Only | Minimum 32-char secret | JWT signature verification |
| `LIVE_PAYOUTS_ENABLED` | Backend Only | **`false`** (Mandatory Safety Guard) | Prevents real money disbursement |
| `PAYOUT_PROVIDER_MODE` | Backend Only | **`sandbox`** | Razorpay route test/mock mode |
| `VITE_API_BASE_URL` | Frontend Only | `http://localhost:8000/api/v1` | Backend REST endpoint URL |

---

## 5. External Dependencies & Architectural Assumptions
1. **Supabase PostgreSQL & PostGIS**: Hosts all 52 relational tables with active Row-Level Security and geospatial distance functions (`ST_DWithin`, `ST_DistanceSphere`).
2. **OpenStreetMap OSRM**: Public routing API (`http://router.project-osrm.org`) used for road distance and duration calculations, protected by an internal 3-strike circuit breaker and urban fallback engine.
3. **Razorpay Sandbox**: Payment gateway test mode for customer checkout intents and webhook notifications.
4. **PostgreSQL Advisory Locking**: Distributed synchronization for background workers without external Redis or Celery overhead.

---

## 6. Audit of Spatial Quantization (Step 10 Discovery)
- **Phase 13 Documentation Wording**: Earlier documentation referenced *"sub-meter grid coordinate quantization"*.
- **Code Audit in `app/services/routing/cache.py`**:
  ```python
  def generate_spatial_key(origin_lat, origin_lng, dest_lat, dest_lng):
      return f"{round(origin_lat, 3)}:{round(origin_lng, 3)}->{round(dest_lat, 3)}:{round(dest_lng, 3)}"
  ```
- **Mathematical Evaluation**:
  - $0.001^\circ$ (3 decimal places) $\approx 111\text{ meters}$ at the equator.
  - Literal "sub-meter" quantization ($0.00001^\circ \approx 1.1\text{m}$) would be counter-productive for vehicular routing caches, causing near 0% cache hit rates due to GPS jitter.
  - **Decision**: 3 decimal places (~110m block-level spatial quantization) is mathematically optimal for road network route caching and will be accurately documented and verified in Phase 14.

---

## 7. Current Risk Areas & Phase 14 Focus
1. **Browser E2E Coverage**: While backend and component tests are comprehensive (468 + 121 tests), end-to-end multi-role browser journeys (Customer -> Mechanic -> Admin) require automated execution.
2. **Multi-Mechanic Concurrency**: Simultaneous acceptance of a single booking offer must be proven strictly race-free under database-level concurrency tests.
3. **Realtime Broadcast Resilience**: Handling network disconnects, reconnections, and out-of-order state transitions.
4. **Disaster Recovery & Rollback Drill**: Formally documenting and simulating disaster recovery RPO/RTO and zero-downtime forward migration rollback procedures.
