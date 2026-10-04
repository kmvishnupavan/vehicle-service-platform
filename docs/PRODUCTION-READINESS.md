# Production Readiness & Deployment Verification

This document specifies the operational checklist, environment classifications, and automated verification procedures required prior to deploying the Vehicle Service Platform to staging or production environments.

---

## 1. Environment Classifications

The platform operates under four strictly defined environments:

1. **`development`**:
   - Local developer machines.
   - Placeholder credentials tolerated for non-local integrations.
   - CORS permits `http://localhost:5173`, `http://localhost:3000`.
   - Sandbox payout mode only.
2. **`test`**:
   - CI/CD test runners (pytest, Vitest).
   - In-memory database mocks or ephemeral test databases.
   - Sandbox payout mode only.
3. **`staging`**:
   - Pre-production staging cluster mirroring production topology.
   - Live Supabase project connectivity, Razorpay Test Mode keys.
   - Explicit CORS domain (e.g. `https://staging.vehiclecare.app`).
   - Sandbox payout mode only.
4. **`production`**:
   - Live production environment.
   - Strict configuration validation: missing service keys or wildcard CORS will fail startup immediately.
   - Live payouts remain **strictly disabled** unless explicitly verified and approved.

---

## 2. Automated Readiness Command

The platform includes a CLI readiness utility:

```bash
# Within backend directory:
python -m app.commands.production_readiness
```

### Verification Criteria Checked by CLI:
- [x] **Environment Configuration**: Validates `ENVIRONMENT`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`.
- [x] **CORS Configuration**: Verifies no wildcard `*` origins exist when credentials are used.
- [x] **Database Connectivity**: Executes a live query (`SELECT 1`) against Supabase.
- [x] **Schema Validation**: Asserts all 41 core tables exist and have RLS enabled.
- [x] **Privileged Functions**: Asserts security-definer RPCs exist (`accept_booking_atomic`, `verify_mechanic_payout_account`, `approve_settlement_batch`).
- [x] **Payout Provider Mode**: Confirms payout mode is `sandbox`.
- [x] **Live Payout Safety Guard**: Verifies `LIVE_PAYOUTS_ENABLED=false`.

### Expected Verification Output:
```text
============================================================
PLATFORM PRODUCTION READINESS CHECK
============================================================
ENVIRONMENT: development
PAYOUT MODE: sandbox
LIVE PAYOUTS ENABLED: False

[1/7] Environment Configuration: OK
[2/7] CORS Policy: OK
[3/7] Database Connectivity: OK
[4/7] Database Schema (41/41 tables verified): OK
[5/7] Privileged Security-Definer RPCs (3/3 functions verified): OK
[6/7] Payout Mode: OK (sandbox)
[7/7] Live Payout Safety Guard: OK (BLOCKED)

============================================================
OVERALL RESULT: READY
REAL-MONEY PAYOUTS: DISABLED
============================================================
```

---

## 3. Production Deployment Checklist

### Pre-Deployment
- [ ] Run full test suites:
  - Backend: `pytest -q` (all tests passing)
  - Frontend: `npm test -- --run` (all tests passing)
- [ ] Production build succeeds: `npm run build` (0 TypeScript / bundling errors).
- [ ] Database migrations applied:
  - Verify `supabase db push` or check `supabase/migrations/` in Supabase dashboard.
- [ ] Verify Row Level Security (RLS) is enabled on all tables:
  ```sql
  SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public';
  ```
- [ ] Verify Storage Buckets have correct RLS policies and size limits.

### Deployment & Smoke Testing
- [ ] Deploy backend container to production cluster.
- [ ] Verify liveness probe: `GET /health/live` returns HTTP 200 `{"status": "ok"}`.
- [ ] Verify readiness probe: `GET /health/ready` returns HTTP 200 with all checks `healthy`.
- [ ] Verify security headers:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- [ ] Verify Request Tracing: Confirm `X-Request-ID` is returned on all responses.
- [ ] Admin login and sanity check on `/admin/operations`.

### Post-Deployment
- [ ] Confirm `REAL-MONEY PAYOUTS: DISABLED`.
- [ ] Monitor rate-limit counters and structured log streams for unexpected exceptions.
