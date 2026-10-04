# Environment Configuration & Secret Management Guide (Phase 10)

This document establishes the single authoritative configuration specification for the Vehicle Service Platform across its four operating environments: `development`, `test`, `staging`, and `production`.

---

## 1. Operating Environments Classification

| Environment | Purpose | Target Host | Provider Mode | Live Payouts | CORS Origins |
|---|---|---|---|---|---|
| **`development`** | Local developer testing | `localhost:8000` / `localhost:5173` | Sandbox | **DISABLED** (Hard error if True) | `http://localhost:*`, `http://127.0.0.1:*` |
| **`test`** | Automated CI/CD test runners | Ephemeral test runners | Mock / Sandbox | **DISABLED** (Hard error if True) | Ephemeral / Mock client |
| **`staging`** | Pre-production validation | `staging-api.vehiclecare.app` | Sandbox | **DISABLED** (Hard error if True) | `https://staging.vehiclecare.app` (Strict, no wildcards) |
| **`production`** | Live end-user traffic | `api.vehiclecare.app` | Live (Protected) | **DISABLED by default** (Requires 4 conditions) | Explicit production FQDNs only (No `*`, No localhost) |

---

## 2. Configuration Parameters Matrix

### 2.1. Application & Platform Settings
| Variable Name | Required In | Default (Dev) | Scope | Description |
|---|---|---|---|---|
| `ENVIRONMENT` | All | `development` | Backend | Must be `development`, `test`, `staging`, or `production`. |
| `DEBUG` | All | `true` (Dev only) | Backend | Must be `false` in `production`. |
| `PROJECT_NAME` | All | `Vehicle Service Platform API` | Backend | API title reported in OpenAPI docs. |
| `APP_NAME` | All | `Vehicle Service Platform` | Shared | Brand display name. |
| `API_V1_PREFIX` | All | `/api/v1` | Backend | API version prefix. |
| `FRONTEND_URL` | All | `http://localhost:5173` | Backend | Base URL of web client for email/deep links. |

### 2.2. Supabase Integration (Database, Auth, Storage, Realtime)
| Variable Name | Required In | Sensitivity | Scope | Description |
|---|---|---|---|---|
| `SUPABASE_URL` | All | Low | Backend & Frontend | HTTPS URL of target Supabase instance (`https://dfigtryvvujhwuiyzdvs.supabase.co`). |
| `SUPABASE_PUBLISHABLE_KEY` | All | Low | Backend & Frontend | Anon/Publishable key. Safe for client-side inclusion subject to RLS. |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend | **CRITICAL SECRET** | **BACKEND ONLY** | Privileged bypass key. NEVER expose to frontend or git. |
| `SUPABASE_JWT_SECRET` | Backend | **CRITICAL SECRET** | **BACKEND ONLY** | HMAC secret used to verify access tokens. >= 32 chars in production. |
| `STORAGE_BUCKET_ATTACHMENTS`| Backend | Low | Backend | Bucket for inspection photos & repair work proof (`attachments`). |
| `STORAGE_BUCKET_AVATARS` | Backend | Low | Backend | Bucket for user avatar images (`avatars`). |

### 2.3. Payments & Gateway (Razorpay)
| Variable Name | Required In | Sensitivity | Scope | Description |
|---|---|---|---|---|
| `RAZORPAY_KEY_ID` | Staging / Prod | Moderate | Backend | Razorpay public key ID (`rzp_test_...` or `rzp_live_...`). |
| `RAZORPAY_KEY_SECRET` | Staging / Prod | **CRITICAL SECRET** | **BACKEND ONLY** | Secret used to sign payment orders and capture payments. |
| `RAZORPAY_WEBHOOK_SECRET`| Staging / Prod | **CRITICAL SECRET** | **BACKEND ONLY** | Secret used to verify HMAC-SHA256 signatures on incoming webhooks. |

### 2.4. Mechanic Payouts & Financial Safety Guards
| Variable Name | Required In | Sensitivity | Scope | Description |
|---|---|---|---|---|
| `PAYOUT_PROVIDER_MODE` | All | High | Backend | `sandbox` in dev/test/staging. `live` permitted ONLY in production when approved. |
| `LIVE_PAYOUTS_ENABLED` | All | **SAFETY GUARD**| Backend | Master circuit breaker. MUST be `false` unless explicitly authorized for real money. |
| `RAZORPAYX_ACCOUNT_NUMBER`| Staging / Prod| Moderate | Backend | RazorpayX virtual business account number for fund transfers. |

### 2.5. Security & Ingress Guards
| Variable Name | Required In | Sensitivity | Scope | Description |
|---|---|---|---|---|
| `CORS_ORIGINS` | All | High | Backend | JSON array or comma-separated list of allowed origins. Wildcards (`*`) forbidden in staging and production. |
| `RATE_LIMIT_PER_MINUTE` | All | Low | Backend | Global API requests per IP per minute (Default: `120`). |
| `RATE_LIMIT_AUTH_PER_MINUTE`| All | Low | Backend | Authentication requests per IP per minute (Default: `15`). |

---

## 3. Frontend-Exposed Variables (Vite)

Only environment variables prefixed with `VITE_` are compiled into the client-side bundle:
- `VITE_API_BASE_URL`: Target backend API endpoint (e.g. `https://api.vehiclecare.app/api/v1`).
- `VITE_SUPABASE_URL`: Target Supabase URL.
- `VITE_SUPABASE_PUBLISHABLE_KEY`: Target Supabase anon/publishable key.

> [!CAUTION]
> **Zero Secret Leakage Guarantee**:
> The automated secret scanner (`scripts/verify_secret_exposure.py`) validates during CI that `SUPABASE_SERVICE_ROLE_KEY`, `RAZORPAY_KEY_SECRET`, and `RAZORPAY_WEBHOOK_SECRET` are never referenced in `frontend/src` or present in `frontend/dist`.

---

## 4. Environment Enforcement Architecture

Application startup runs `validate_environment_configuration(settings)` in `app.core.safety`:
1. If any universal variable (`SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`) is missing, startup fails.
2. In `production` or `staging`, any invalid configuration (wildcard CORS, debug mode enabled in prod, placeholder service role key) raises `RuntimeError` during FastAPI lifespan initialization, aborting startup before accepting network traffic.
3. In `development` or `test`, `LIVE_PAYOUTS_ENABLED=true` is strictly prohibited and fails startup validation with an actionable error.
