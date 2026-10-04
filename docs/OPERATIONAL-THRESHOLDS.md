# Operational Thresholds & Anomaly Detection

This document specifies the operational thresholds, anomaly detection rules, and automated monitoring boundaries for the Vehicle Service Platform.

It strictly separates **Business Service Level Agreements (SLAs)** from **Technical Monitoring Thresholds (Alerts)**.

---

## 1. SLA vs. Technical Monitoring Principles

- **Business SLA**: The customer/mechanic-facing contractual or expected commitment for a lifecycle step (e.g., maximum target time to dispatch a mechanic or complete a settlement batch).
- **Technical Monitoring Threshold**: The infrastructure and observability triggers that fire automated warnings or critical incident tickets before or when an SLA is breached or when system invariants stall.
- **Configurability**: All operational thresholds are exposed as environment variables or platform configuration records rather than hardcoded magic numbers.

---

## 2. Core Thresholds Matrix

| Domain | State / Metric | Business SLA | Warning Threshold (Warn) | Critical Threshold (Pager) | Configuration Variable |
|---|---|---|---|---|---|
| **Bookings** | `searching_mechanic` | 10 minutes | 5 minutes | 10 minutes | `THRESHOLD_BOOKING_SEARCH_TIMEOUT_MIN=5` |
| **Bookings** | `mechanic_en_route` | 45 minutes | 30 minutes | 60 minutes | `THRESHOLD_MECHANIC_EN_ROUTE_MAX_MIN=30` |
| **Bookings** | `in_service` | 4 hours (standard) | 3 hours | 6 hours (without note) | `THRESHOLD_SERVICE_IN_PROGRESS_MAX_HOURS=3` |
| **Payments** | `pending` / checkout | 15 minutes | 10 minutes | 30 minutes | `THRESHOLD_PAYMENT_PENDING_MAX_MIN=15` |
| **Payments** | Gateway Verification | 5 seconds | 3 seconds | 10 seconds | `THRESHOLD_PAYMENT_VERIFY_LATENCY_SEC=3` |
| **Webhooks** | Reserved (`processing`) | < 30 seconds | 2 minutes | 5 minutes (recovery initiated) | `THRESHOLD_WEBHOOK_STUCK_MIN=5` |
| **Payouts** | Single Payout `processing` | 24 hours | 2 hours | 6 hours | `THRESHOLD_PAYOUT_PROCESSING_WARN_HOURS=2` |
| **Settlements** | Maker-Checker Approval | 48 hours | 24 hours | 48 hours | `THRESHOLD_SETTLEMENT_APPROVAL_WARN_HOURS=24` |
| **Settlements** | Batch Execution | 2 hours | 30 minutes | 1 hour | `THRESHOLD_SETTLEMENT_BATCH_EXEC_MIN=30` |
| **Mechanics** | Location Stale (Active Shift) | Live (< 60s) | 90 seconds | 5 minutes | `THRESHOLD_LOCATION_STALE_SEC=90` |
| **Notifications**| Delivery Latency | < 30 seconds | 60 seconds | 5 minutes | `THRESHOLD_NOTIFICATION_MAX_LATENCY_SEC=60` |
| **Auth** | Failed Login Rate | N/A | 5 failures / 15m / IP | 15 failures / 15m / IP | `RATE_LIMIT_AUTH_PER_MINUTE=10` |

---

## 3. Anomaly Scenarios & Automated Actions

### 3.1. Booking Stuck in `searching_mechanic`
- **Symptom**: Booking created and status is `searching_mechanic` with `created_at < NOW() - INTERVAL '5 minutes'`.
- **Root Causes**: Mechanic supply deficit, radius configuration too narrow, location query failure, or dispatch event dropped.
- **Monitoring Trigger**: Warning logged at 5 minutes; automated customer re-prompt at 7 minutes; auto-escalation/cancellation offer at 10 minutes.
- **Action**: Alert displayed in Admin Operations Dashboard (`BOOKING_DISPATCH_TIMEOUT`).

### 3.2. Booking Stuck in `mechanic_en_route`
- **Symptom**: Assigned mechanic has not arrived on-site within 45 minutes; location telemetry ceases or distance to customer does not decrease.
- **Root Causes**: Traffic delay, mechanic app crash, battery dead, or route deviation.
- **Monitoring Trigger**: Telemetry freshness check fails if no ping in > 5 minutes.
- **Action**: In-app push notification sent to mechanic inquiring on status; customer support notified if no reply within 5 minutes.

### 3.3. Payment Pending Too Long
- **Symptom**: Razorpay checkout opened (`payment_status = 'pending'`), but no webhook (`payment.captured` or `payment.failed`) received within 15 minutes.
- **Root Causes**: Customer abandoned checkout, bank 3DS drop, or webhook delivery delayed.
- **Monitoring Trigger**: Reconciliation job scans payments in `pending` older than 15 minutes.
- **Action**: Mark payment expired internally or poll Razorpay API status to confirm terminal state.

### 3.4. Payout Stuck in `processing`
- **Symptom**: Payout item in `processing` state for > 2 hours without provider webhook receipt.
- **Root Causes**: RazorpayX banking partner queued transfer, NEFT window delay, or dropped payout webhook.
- **Monitoring Trigger**: Reconciliation scanner flags payout item as `STUCK_PAYOUT_PROCESSING`.
- **Action**: Query RazorpayX `/payouts/{payout_id}` provider API in read-only mode to retrieve provider status. Discrepancy logged for admin review.

### 3.5. Webhook Reservation Stuck
- **Symptom**: `webhook_events` record with `status = 'processing'` and `processing_started_at < NOW() - INTERVAL '5 minutes'`.
- **Root Causes**: Server process killed by SIGKILL, OOM, or unhandled network freeze during webhook handler execution.
- **Automated Recovery**: Atomic acquisition reclaims stale reservation, increments `processing_attempts`, and re-dispatches handler. If `processing_attempts >= 3`, marked `failed` and alerts sent.

### 3.6. Settlement Approval Pending Too Long
- **Symptom**: Batch status is `approval_required` and created more than 24 hours ago.
- **Root Causes**: Admin checker unassigned, notifications overlooked.
- **Action**: Escalation email sent to secondary finance admin; highlighted on Operations Dashboard.

### 3.7. Stale Mechanic Location
- **Symptom**: Mechanic is `available` or `assigned`, but `last_location_update` is older than 5 minutes.
- **Root Causes**: App in background without background location permissions, battery optimization killing worker, GPS disabled.
- **Action**: Mechanic marked temporarily `inactive_offline` in search results until new coordinates are posted.

---

## 4. Operational Dashboard Indicators

The Admin Operations Dashboard evaluates these thresholds continuously:
1. **Health Banner**: Liveness and deep readiness status.
2. **Lifecycle Counts**: Realtime active breakdown across Bookings, Payments, Payouts, Webhooks, and Notifications.
3. **Discrepancy Table**: Ranked by severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
