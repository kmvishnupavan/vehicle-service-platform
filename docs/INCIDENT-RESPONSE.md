# Security & Operational Incident Response Plan

This document establishes the standardized emergency procedures, incident classification framework, and response playbooks for the Vehicle Service Platform.

---

## 1. Incident Management Lifecycle

Every incident follows a rigorous 6-stage lifecycle:
1. **Detect**: Automated alert firing, health check failure, or customer report.
2. **Contain**: Immediate action to halt financial loss, isolate affected components, or disable impacted endpoints.
3. **Investigate**: Root cause analysis using request tracing (`X-Request-ID`, `operation_id`), audit logs, and provider logs.
4. **Reconcile**: Verify transactional invariants, audit ledgers, and detect discrepancies without destructive mutations.
5. **Recover**: Re-enable endpoints, replay missed events, and return platform to `HEALTHY` state.
6. **Document**: Post-mortem report with timeline, impact analysis, and preventive action items.

---

## 2. Severity Classification Matrix

| Level | Definition | Response SLA | Escalation | Examples |
|---|---|---|---|---|
| **SEV-1 (Critical)** | Core platform down; financial risk; unauthorized live payout attempt; credential compromise. | < 15 mins | PagerDuty, Lead Eng, Exec | Payment gateway failure, live payout guard trigger, breach. |
| **SEV-2 (Major)** | Major feature failure; webhook delivery backlog; realtime down; mechanic tracking failed. | < 45 mins | On-Call Engineer, Team Lead | Realtime websocket drop, stuck settlement batches. |
| **SEV-3 (Minor)** | Non-blocking degradation; PDF statement generation delayed; minor UI glitch. | < 4 hours | Support Engineer | Statement download retry required, stale cached profile. |
| **SEV-4 (Low)** | Informational discrepancy; non-urgent operational anomaly. | Next business day | Backlog triage | Occasional 429 on aggressive client, minor log format typo. |

---

## 3. Incident Playbooks

### 3.1. Payment Gateway Outage (Razorpay Down)
- **Detect**: Readiness probe flags `provider.razorpay = degraded`; sudden spike in HTTP 502/504 on `/payments/create-order`.
- **Contain**: Display frontend checkout warning ("Payment processing temporarily unavailable. Please retry shortly."); reject new checkout attempts gracefully.
- **Investigate**: Check status.razorpay.com; verify network egress from backend container; inspect provider logs for API timeouts.
- **Reconcile**: Run `/admin/reconciliation/payments` to flag all transactions stuck in `pending`.
- **Recover**: Once gateway reports operational, poll checkout status for pending orders and resume normal order creation.
- **Document**: Record duration, lost order volume, and gateway incident ticket in post-mortem.

### 3.2. Payout Provider Outage (RazorpayX Down)
- **Detect**: Payout execution errors during settlement batch dispatch; warning alerts on batch status `processing`.
- **Contain**: Halt execution of queued settlement batches. Prevent new batch approvals in `SettlementManagementPage`.
- **Investigate**: Check RazorpayX API availability and partner bank processing hours.
- **Reconcile**: Run `/admin/reconciliation/payouts` to confirm which transfers were accepted vs failed before outage.
- **Recover**: Once provider recovers, retry remaining transfers individually or re-dispatch uncompleted batch items.
- **Document**: Confirm zero duplicate payouts occurred.

### 3.3. Accidental Live Payout Attempt
- **Detect**: Critical alert `PRODUCTION_SAFETY_GUARD_TRIGGERED` logged by `ProductionSafetyGuard`.
- **Contain**: The hard safety guard in `safety.py` automatically raises HTTP 403 / `RuntimeError` and aborts request before reaching provider network.
- **Investigate**: Identify caller (user ID, IP, endpoint) from `X-Request-ID` and audit log entry.
- **Reconcile**: Verify `LIVE_PAYOUTS_ENABLED` is `false` in environment; verify zero provider live calls in RazorpayX dashboard.
- **Recover**: Review code path or admin action that initiated the call.
- **Document**: File immediate security advisory.

### 3.4. Supabase Database / Storage Outage
- **Detect**: Readiness probe `/health/ready` returns 503; database connection pool exhaustion.
- **Contain**: Put frontend into read-only maintenance mode via Cloudflare or CDN banner.
- **Investigate**: Check status.supabase.com, database CPU/RAM utilization, and connection metrics in Supabase console.
- **Reconcile**: Upon restoration, verify schema integrity, run reconciliation scanners, and re-sync any offline state.
- **Recover**: Clear application connection pools and remove maintenance banner.
- **Document**: Review pool configuration and connection limits.

### 3.5. Webhook Ingestion Outage
- **Detect**: Webhook processing latency spikes; `webhook_events` backlog growing; provider reports delivery failures.
- **Contain**: Webhooks are acknowledged with atomic reservation (`processing`). If unhandled crashes occur, auto-recovery reclaims reservations after 5 minutes.
- **Investigate**: Check application server logs for unhandled exception traces in webhook processor.
- **Reconcile**: Execute `/admin/reconciliation/webhooks` to identify pending/stale webhooks.
- **Recover**: Trigger Razorpay webhook re-delivery for missed intervals.
- **Document**: Update webhook error handling if unknown payload schema was received.

### 3.6. Compromised Admin / API Credentials
- **Detect**: Security event `UNAUTHORIZED_PAYOUT_ACCESS` or unexpected logins from anomalous geo-locations.
- **Contain**: Revoke active user sessions in Supabase Auth; immediately rotate compromised API keys.
- **Investigate**: Audit user actions in `public.audit_logs` matching the compromised actor ID.
- **Reconcile**: Review financial mutations and settlement batches modified by actor.
- **Recover**: Restore altered records if maker-checker was bypassed; enforce multi-factor authentication.
- **Document**: Complete full security breach report.
