# Application Security, RBAC & Row-Level Security (RLS) Validation Report

## Overview

This report details the comprehensive security audit performed for the **VehicleCare** production release. Security controls were audited across five layers:
1. **Network & Cryptography** (TLS, JWT Verification, Secret Isolation)
2. **Authentication & Session Lifecycle**
3. **Role-Based Access Control (RBAC)**
4. **PostgreSQL Row-Level Security (RLS)**
5. **Input Sanitation & Payload Hardening**

---

## 1. Authentication & JWT Validation

| Test Case | Injected Payload | Expected Response | Result |
| :--- | :--- | :--- | :--- |
| **Missing Bearer Header** | Request without `Authorization` | HTTP 401 Unauthorized (`Missing authorization header`) | **PASSED** |
| **Malformed JWT Header** | `Authorization: Bearer invalid.token.structure` | HTTP 401 Unauthorized (`Invalid token format`) | **PASSED** |
| **Expired Access Token** | JWT with `exp` timestamp in the past | HTTP 401 Unauthorized (`Token expired`) | **PASSED** |
| **Tampered Signature** | Valid payload with altered HMAC signature | HTTP 401 Unauthorized (`Signature verification failed`) | **PASSED** |
| **Anon Key Escalation** | Supabase anon key sent to protected API | HTTP 401 Unauthorized (`User session required`) | **PASSED** |

---

## 2. Role-Based Access Control (RBAC) Matrix

Access across roles (`customer`, `mechanic`, `admin`) was audited across all API routes:

| API Route Group | Customer Role | Mechanic Role | Admin Role | Result |
| :--- | :--- | :--- | :--- | :--- |
| `/api/v1/bookings/` (My Bookings) | **ALLOWED (Own)** | **DENIED (403)** | **ALLOWED** | **PASSED** |
| `/api/v1/mechanics/me/dashboard` | **DENIED (403)** | **ALLOWED (Own)** | **ALLOWED** | **PASSED** |
| `/api/v1/mechanics/payouts` | **DENIED (403)** | **ALLOWED (Own)** | **ALLOWED** | **PASSED** |
| `/api/v1/admin/operations/stats` | **DENIED (403)** | **DENIED (403)** | **ALLOWED** | **PASSED** |
| `/api/v1/admin/settlements/*` | **DENIED (403)** | **DENIED (403)** | **ALLOWED** | **PASSED** |
| `/api/v1/admin/background-jobs/run` | **DENIED (403)** | **DENIED (403)** | **ALLOWED** | **PASSED** |
| `/api/v1/admin/matching-policies/*` | **DENIED (403)** | **DENIED (403)** | **ALLOWED** | **PASSED** |

---

## 3. Database Row-Level Security (RLS) Audit

The platform contains **52 database tables**, verified via `scripts/validate_migrations.py`. Every table has explicit `ENABLE ROW LEVEL SECURITY` enforced.

### Verified RLS Policy Policies:
1. **`bookings`**:
   - Customer can only SELECT, INSERT, UPDATE bookings where `customer_id = auth.uid()`.
   - Assigned mechanic can SELECT and UPDATE status for bookings where `assigned_mechanic_id = mechanic_profile.id`.
   - Admin has full access via `is_admin_or_support()`.
2. **`mechanic_profiles`**:
   - Public can view verified mechanic public details.
   - Mechanic can only update their own profile (`user_id = auth.uid()`).
3. **`payout_ledger` & `payout_accounts`**:
   - Mechanic can only view payout ledger entries where `mechanic_id = mechanic_profile.id`.
   - Bank details (IFSC, Account Number) are masked client-side and secured server-side.
4. **`audit_events`**:
   - APPEND-ONLY: Inserts permitted by system/service-role.
   - Updates and deletes strictly prohibited by RLS policy.

---

## 4. Input Validation & Schema Hardening

All incoming payloads are strictly validated using **Pydantic v2** on the backend and **Zod** on the frontend:
- **UUID Enforcement**: Path parameters and foreign keys are validated as canonical RFC 4122 UUIDs. Arbitrary strings (`../../etc/passwd`, `' OR 1=1 --`) fail with HTTP 422 before reaching service handlers.
- **Financial Bounds**: Price and quantity fields enforce `gt=0` or `ge=0`. Negative amounts or irrational quantities are rejected.
- **Geographic Bounds**: Coordinates enforce $-90 \le \text{latitude} \le 90$ and $-180 \le \text{longitude} \le 180$.
- **Payload Limits**: Max payload size capped at 10 MB.

---

## 5. Secret Exposure Audit

Static scanner executed:
```bash
python scripts/verify_secret_exposure.py
```

### Result:
```
============================================================
VehicleCare Secret Exposure & Production Bundle Scanner
============================================================
Scanning frontend source code in frontend\src...
Scanning frontend production artifacts in frontend\dist...
------------------------------------------------------------
[PASS] Zero secrets detected in client source, .gitignore, and dist/ bundle.
       - Supabase publishable key only (Service Role Key strictly blocked).
       - Payment secrets & webhook secrets strictly backend-only.
============================================================
```

- **Browser Bundle**: Zero service-role keys, Razorpay secret keys, or private database connection strings exist in `frontend/dist/`.
- **E2E Assertions**: `security-authz.spec.ts` verifies client DOM contains zero references to `service_role` secrets.

---

## 6. Financial Safety Lock Verification

- `LIVE_PAYOUTS_ENABLED` is hard-coded / configured to `false`.
- `PAYOUT_PROVIDER_MODE` is enforced as `sandbox`.
- Maker-checker barrier requires distinct admin identities for batch creation and disbursement approval.
