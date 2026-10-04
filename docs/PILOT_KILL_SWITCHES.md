# Phase 15.1: Controlled Pilot Emergency Kill Switches

## 1. Purpose & Architectural Principles

During the Controlled Production Pilot, operational anomalies (e.g., GPS telemetry corruption, external provider outages, unexpected surge, or financial reconciliation discrepancies) must be instantly containable without requiring code modifications or emergency rollbacks.

VehicleCare implements **six high-impact operational kill switches** managed via Pydantic configuration (`Settings`) and environment overrides.

---

## 2. Kill Switch Catalog

| Flag / Setting | Default | Component Affected | Immediate Behavior When `true` |
|:---|:---:|:---|:---|
| **`KILL_SWITCH_NEW_BOOKINGS_DISABLED`** | `false` | `POST /api/v1/bookings` | Immediately halts new customer booking creation with HTTP 503 Service Unavailable ("New booking creation is temporarily paused by pilot safety kill switch"). Ongoing bookings proceed normally. |
| **`KILL_SWITCH_MATCHING_DISABLED`** | `false` | `MatchingService.find_eligible_candidates` | Halts automated mechanic dispatch and candidate discovery with HTTP 503. Prevents incorrect mechanic offers during dispatch anomalies. |
| **`KILL_SWITCH_SCHEDULED_DISPATCH_DISABLED`** | `false` | `job_dispatch_scheduled_bookings` | Instructs the background worker to skip scheduled appointment auto-dispatch without throwing errors or locking rows. |
| **`KILL_SWITCH_NOTIFICATIONS_DISABLED`** | `false` | `job_retry_failed_notifications` | Immediately pauses the notification retry queue processor. Prevents retry storming if push/SMS provider fails. |
| **`KILL_SWITCH_FORCE_ROUTING_FALLBACK`** | `false` | `OSRMRoutingProvider` | Completely bypasses the OSRM HTTP endpoint and immediately calculates distances and transit ETAs via the local mathematical Haversine model. |
| **`LIVE_PAYOUTS_ENABLED`** | `false` | `PayoutService` / Settlements | **Immutable Financial Safety Barrier**: Hard-rejects all attempts to trigger live bank payouts or debit accounts. Locked to `false` throughout the pilot. |

---

## 3. Activation Procedures

### Method 1: Environment Variable Override (`.env`)
Update the container environment and restart the backend service:
```bash
# Example: Disable matching and force routing fallback during map server outage
sed -i 's/KILL_SWITCH_MATCHING_DISABLED=false/KILL_SWITCH_MATCHING_DISABLED=true/' /opt/vehiclecare/backend/.env
sed -i 's/KILL_SWITCH_FORCE_ROUTING_FALLBACK=false/KILL_SWITCH_FORCE_ROUTING_FALLBACK=true/' /opt/vehiclecare/backend/.env

docker compose -f /opt/vehiclecare/docker-compose.yml restart backend
```

### Method 2: Docker Environment Injection (Zero-Downtime)
```bash
docker exec -e KILL_SWITCH_NEW_BOOKINGS_DISABLED=true vehiclecare_backend kill -HUP 1
```

---

## 4. Deactivation & Verification

Once the underlying incident has been mitigated (e.g., OSRM map data restored or external dependency recovered):
1. Reset the corresponding variable to `false` in `.env`.
2. Restart or reload the backend container: `docker compose restart backend`.
3. Verify normal operation using the readiness endpoint: `curl -s http://localhost:8000/api/v1/health/ready | jq .`
4. Log the deactivation event in [`docs/PILOT_INCIDENT_LOG.md`](file:///c:/Users/kmvis/OneDrive/Documents/vehicle-service-platform/docs/PILOT_INCIDENT_LOG.md).
