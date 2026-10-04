# Platform Operational Runbook (Phase 13)

## 1. Routine Operational Checks

### Daily Standup Probes
1. Navigate to **Admin -> Operations & Reliability Center** (`/admin/operations`).
2. Verify **System Readiness** is `READY`.
3. Check the **Operational KPIs** tab:
   - Matching Exhaustion Rate $< 10\%$
   - Stale Location Rate $< 5\%$
   - Routing Fallback Rate $< 5\%$
   - Notification Failure Rate $< 2\%$
4. Check **Background Job Runner**:
   - Ensure all 8 jobs have executed recently with `status = completed`.

---

## 2. Incident Response Playbooks

### A. High Matching Exhaustion
- **Symptom**: Exhaustion rate exceeds 10%; customer bookings timing out in `searching_mechanic`.
- **Diagnostic Steps**:
  1. Open `/admin/operations` -> **Location Reliability** tab. Check count of mechanics in `OFFLINE` or `STALE` status.
  2. Open **Matching Policies** tab. Verify active policy weights.
- **Remediation**:
  - Broadcast push notification to mechanics to go online.
  - Temporarily adjust `max_concurrent_jobs` or proximity search radius.

### B. Routing Provider Outage (OSRM Down)
- **Symptom**: `routing_fallback_rate` jumps to 100%; `circuit_breaker_open = true` logged.
- **Diagnostic Steps**:
  - Check OSRM upstream server latency and HTTP responses.
- **Remediation**:
  - System automatically uses fallback haversine routing ($d_{road} = 1.414 \times d_{haversine}$).
  - Restart or scale OSRM container; circuit breaker will automatically probe and recover in half-open state.

### C. Unprocessed Scheduled Bookings
- **Symptom**: Scheduled bookings remain in `scheduled` status past `dispatch_at`.
- **Diagnostic Steps**:
  - Check `dispatch_scheduled_bookings` background job in `/admin/operations`.
- **Remediation**:
  - Click **Trigger All Jobs Now** on the Operations dashboard.
  - Or run CLI: `python -m app.commands.run_background_jobs --job dispatch_scheduled_bookings`.
