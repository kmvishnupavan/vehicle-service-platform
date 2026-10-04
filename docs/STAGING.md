# Staging Environment Architecture & Isolation Guide (Phase 10)

This document specifies the deployment topology, isolation boundaries, and verification procedures for the pre-production **Staging** environment.

---

## 1. Staging Purpose & Design Principles

The Staging environment mirrors the production architecture as closely as possible to validate end-to-end integration, migration scripts, and real-time telemetry before production releases, while enforcing absolute financial and operational safety.

### Core Principles
1. **Financial Isolation**: Real-money payouts are strictly impossible in Staging (`LIVE_PAYOUTS_ENABLED=false`, `PAYOUT_PROVIDER_MODE=sandbox`).
2. **Topology Parity**: Uses identical containerized backend and compiled static frontend artifacts as production.
3. **Database Isolation**: Dedicated Supabase project isolated from production data.
4. **Third-Party Sandbox**: Connects exclusively to Razorpay Test Mode and sandbox payout accounts.

---

## 2. Infrastructure & Networking Topology

| Component | Staging Specification | Production Comparison |
|---|---|---|
| **Frontend URL** | `https://staging.vehiclecare.app` | `https://app.vehiclecare.com` |
| **Backend API URL** | `https://staging-api.vehiclecare.app/api/v1` | `https://api.vehiclecare.app/api/v1` |
| **CORS Policy** | Explicitly `["https://staging.vehiclecare.app"]` (No `*`) | Explicit production domains (No `*`) |
| **Database** | Supabase Staging Project (Postgres 15) | Supabase Production Project |
| **Payment Gateway** | Razorpay Test Mode (`rzp_test_...`) | Razorpay Live Mode (Separate account) |
| **Payout Provider** | RazorpayX Sandbox Mock (`fa_apex_01`) | RazorpayX Live (Disabled) |
| **Storage Buckets** | Staging `attachments` & `avatars` | Production `attachments` & `avatars` |

---

## 3. Database Isolation Strategy

To guarantee zero crossover between development, staging, and production:

### Recommended Project Topology
- **Development**: Local developer environments + ephemeral test fixtures.
- **Staging**: Dedicated Supabase Staging Project (e.g. `vehicle-service-staging`).
- **Production**: Target Supabase Production Project (`dfigtryvvujhwuiyzdvs`).

> [!WARNING]
> **Strict Prohibition on Unrelated Projects**:
> Never point Staging or any test harness at unrelated projects in the organization (such as `ai-code-reviewer` / `mzbdhuftanztvxmfqnhz`). All schema migrations and smoke tests must execute exclusively against the dedicated Vehicle Service Platform project.

---

## 4. Staging Configuration Template (`.env.staging`)

```env
# Application
ENVIRONMENT=staging
DEBUG=false
PROJECT_NAME="Vehicle Service Platform API (Staging)"
API_V1_PREFIX=/api/v1
FRONTEND_URL=https://staging.vehiclecare.app

# Server
HOST=0.0.0.0
PORT=8000

# CORS (Strictly no wildcards)
CORS_ORIGINS=["https://staging.vehiclecare.app"]

# Supabase Staging Project
SUPABASE_URL=https://staging-project-ref.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_staging_anon_key
SUPABASE_SERVICE_ROLE_KEY=staging_service_role_secret_key
SUPABASE_JWT_SECRET=staging_jwt_secret_min_32_characters_long

# Payment Gateway (Razorpay Test Keys)
RAZORPAY_KEY_ID=rzp_test_staging_key_12345
RAZORPAY_KEY_SECRET=staging_razorpay_secret_key_67890
RAZORPAY_WEBHOOK_SECRET=staging_webhook_secret_abcde

# Financial Safety Guards (HARD ENFORCED)
PAYOUT_PROVIDER_MODE=sandbox
LIVE_PAYOUTS_ENABLED=false

# Storage Buckets
STORAGE_BUCKET_ATTACHMENTS=attachments
STORAGE_BUCKET_AVATARS=avatars
```

---

## 5. Staging Verification Protocol

Following deployment to Staging:
1. **Health Diagnostics**:
   - `curl https://staging-api.vehiclecare.app/health/live` -> HTTP 200 `{"status": "ok"}`
   - `curl https://staging-api.vehiclecare.app/health/ready` -> HTTP 200 `{"status": "ready"}`
2. **Automated Smoke Test**:
   ```bash
   pytest tests/test_deployment_smoke.py -v
   ```
3. **End-to-End User Acceptance Test (UAT)**:
   - Create customer booking using Razorpay Test Card (`4000 0000 0000 0002`).
   - Confirm receipt of simulated webhook in `webhook_events`.
   - Mechanics accept booking and update GPS telemetry.
   - Admin verifies settlement batch creation in Maker-Checker dashboard.
   - Confirm that zero real money moved and all payouts execute in sandbox mode.
