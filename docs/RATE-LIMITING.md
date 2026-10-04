# Rate Limiting & API Abuse Protection Architecture

This document details the rate limiting strategy, abuse prevention policies, and implementation guidelines for the Vehicle Service Platform.

---

## 1. Strategy & Architecture Overview

To maintain zero infrastructure bloat and avoid unnecessary Redis operational overhead during this stage, the platform uses an in-memory, thread-safe sliding-window rate limiter (`RateLimitMiddleware`).

### Key Properties
- **Sliding Window Log / Counter**: Requests are timestamped and pruned dynamically per window.
- **Client Identification**: Combines authenticated user ID (when token present) or client IP address (retrieved from `X-Forwarded-For` or client socket).
- **HTTP Response Headers**:
  - `X-RateLimit-Limit`: Maximum requests permitted in the window.
  - `X-RateLimit-Remaining`: Remaining request quota.
  - `X-RateLimit-Reset`: Unix timestamp when quota fully resets.
  - `Retry-After`: Seconds to wait before retrying (on HTTP 429).
- **Standardized 429 Error Envelope**:
  ```json
  {
    "error": {
      "code": "RATE_LIMIT_EXCEEDED",
      "message": "Too many requests. Please retry in 15 seconds.",
      "request_id": "req_8a7d6e5c4b3a"
    }
  }
  ```

---

## 2. Endpoint Tier Matrix

| Tier | Category / Endpoints | Limit | Window | Identification Key | Rationale |
|---|---|---|---|---|---|
| **Tier 1: Auth & Sensitive** | `/auth/login`, `/auth/register`, `/auth/reset-password` | 10 req | 1 minute | Client IP | Prevents credential stuffing, brute force, and account enumeration. |
| **Tier 2: Financial Mutations** | `/payments/create-order`, `/payments/verify`, `/payouts/**`, `/settlements/**` | 30 req | 1 minute | User ID / Client IP | Prevents double-submission, replay attacks, and settlement flooding. |
| **Tier 3: File Storage & I/O** | `/storage/upload`, `/settlements/{id}/statement` | 20 req | 1 minute | User ID / Client IP | Protects storage bandwidth, CPU during PDF compilation, and memory spikes. |
| **Tier 4: Telemetry & Realtime** | `/mechanics/location`, `/chat/messages` | 60 req | 1 minute | User ID | Balances high-frequency GPS pinging (1 ping every 5-10s) while capping abuse. |
| **Tier 5: Webhook Ingestion** | `/payments/webhook` | 120 req | 1 minute | Razorpay IP / Client IP | High capacity for burst payment delivery while shielding against DDoS. |
| **Tier 6: General APIs** | All other `/api/v1/**` endpoints | 120 req | 1 minute | User ID / Client IP | High headroom for standard browsing and dashboard queries. |

---

## 3. Defense-in-Depth Measures

1. **Idempotency Keys**:
   - Financial mutations (payment creation, payout account verification, batch creation, approvals) require idempotency checking at the database level (`idempotency_key`, `razorpay_order_id`, `payout_account_id`).
   - Rate limiting acts as the first line of defense; idempotency guarantees zero duplication even if requests pass the rate limiter.

2. **Webhook Signature Verification**:
   - Razorpay webhook signatures (`X-Razorpay-Signature`) are cryptographically verified using HMAC SHA-256 before any event processing or database queries are executed.

3. **Cloudflare / Reverse Proxy Edge Protection**:
   - When deployed to production behind Cloudflare or AWS ALB, edge rate limiting, bot protection, and IP reputation filtering supplement application-layer rate limiting.

---

## 4. Scaling Path to Redis / Distributed Limiter

If the backend scales horizontally across multiple container instances in the future:
1. The `RateLimitMiddleware` interface remains identical.
2. An adapter replacing the in-memory dictionary with Redis `ZADD` / `ZREMRANGEBYSCORE` sliding window or Redis `INCR` + `EXPIRE` token bucket can be swapped without touching route handlers.
