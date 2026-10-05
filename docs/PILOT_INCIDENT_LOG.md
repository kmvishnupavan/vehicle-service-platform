# Phase 15.1: Controlled Pilot Incident Log

## 1. Incident Classification & Severity Model

| Severity | Definition | Response SLA | Mitigation SLA |
|:---|:---|:---:|:---:|
| **SEV-1** | Critical security compromise, financial ledger discrepancy, duplicate charges, or complete system outage. | $< 15$ mins | $< 1$ hour |
| **SEV-2** | Core customer or mechanic journey blocked (e.g., dispatch failure, approval stuck, payment gateway outage). | $< 30$ mins | $< 4$ hours |
| **SEV-3** | Degraded performance, telemetry latency, non-critical background worker retry, or single-user visual glitch. | $< 2$ hours | $< 24$ hours |
| **SEV-4** | Minor cosmetic defect, non-blocking telemetry warning, documentation clarification. | $< 24$ hours | Next release |

---

## 2. Pre-Pilot Verification Incident Log (Remediated)

The following defect items were identified and resolved during pre-pilot automated regression and test hardening:

### Incident: INC-20261004-01
- **Severity**: SEV-4 (Minor Pre-Pilot Defect)
- **Detected**: 2026-10-04T18:34:12Z
- **Affected Subsystem**: Autonomous Background Job Runner (`jobs.py`)
- **Request / Task ID**: `task-976`
- **Description**: Background job execution returned `TypeError: JobExecutionResult.__init__() got an unexpected keyword argument 'details'`.
- **Root Cause**: `JobExecutionResult` class definition in `runner.py` defined the parameter as `metadata`, whereas `jobs.py` instantiated it as `details`.
- **Mitigation / Resolution**: Refactored `job_dispatch_scheduled_bookings` and `job_retry_failed_notifications` to pass `metadata={...}`. Added unit test in `tests/test_pilot_kill_switches.py`.
- **Status**: **RESOLVED** (100% verified via automated test suite).

### Incident: INC-20261004-02
- **Severity**: SEV-4 (Minor Pre-Pilot Defect)
- **Detected**: 2026-10-04T18:37:45Z
- **Affected Subsystem**: Frontend Web Push Notifications Library (`src/lib/notifications.ts`)
- **Request / Task ID**: `task-999`
- **Description**: TypeScript compiler error during `npm run build` (`TS2322: Type 'Uint8Array' is not assignable to type 'BufferSource'`).
- **Root Cause**: Stricter TypeScript DOM lib definitions for `PushSubscriptionOptionsInit.applicationServerKey`.
- **Mitigation / Resolution**: Applied explicit type cast `applicationServerKey as unknown as BufferSource`. Build verified clean.
- **Status**: **RESOLVED** (Production build compiled in 45.76s).

---

## 3. Live Pilot Incident Record Template

Operators must record all live incidents occurring during the 14-day controlled pilot using the following format:

```markdown
### Incident: INC-YYYYMMDD-XX
- **Severity**: [SEV-1 / SEV-2 / SEV-3 / SEV-4]
- **Time Detected (UTC)**: YYYY-MM-DDTHH:MM:SSZ
- **Time Resolved (UTC)**: YYYY-MM-DDTHH:MM:SSZ
- **Affected Booking ID**: [UUID / None]
- **Correlation Request ID**: [UUID / None]
- **Component / Subsystem**: [API / OSRM / Realtime / Jobs / Frontend]
- **Description**: [Summary of the observed failure]
- **Customer / Mechanic Impact**: [Impact on pilot participants]
- **Root Cause Analysis (RCA)**: [Technical explanation of the fault]
- **Immediate Mitigation Taken**: [Kill switch activated / container restarted / workaround applied]
- **Permanent Resolution**: [Code patch / configuration update / infrastructure change]
- **Preventative Action Items**: [Actionable follow-up tasks]
```
