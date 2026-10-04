# Mechanic Location Reliability & GPS Anomaly Detection

## 1. Overview
Ensuring reliable mechanic dispatch requires active validation of GPS telemetry. VehicleCare enforces location freshness tiers and detects GPS anomalies (spoofing, impossible speed, large jumps).

---

## 2. Location Freshness Tiers

| Tier | Age Criteria | Operational State | Impact on Dispatch |
|---|---|---|---|
| `FRESH` | $\Delta t \le 60\text{ s}$ | Active Real-time | Eligible for instant matching & live tracking |
| `STALE` | $60\text{ s} < \Delta t \le 300\text{ s}$ | Heartbeat Degraded | Eligible with ranking penalty |
| `OFFLINE` | $\Delta t > 300\text{ s}$ | Inactive / Disconnected | Excluded from candidate discovery |

---

## 3. GPS Anomaly Detection Model (`public.mechanic_location_anomalies`)

When a mechanic sends a location ping via `POST /mechanics/me/location`:
1. **Coordinate Boundary Check**: Latitude must be between $-90^\circ$ and $+90^\circ$, longitude between $-180^\circ$ and $+180^\circ$.
2. **Speed Calculation**:
   $$\text{speed} = \frac{\text{haversine\_distance}(p_{old}, p_{new})}{\Delta t}$$
3. **Anomaly Flags**:
   - `impossible_speed`: Speed exceeds $160\text{ km/h}$.
   - `large_location_jump`: Distance jump exceeds $10\text{ km}$ in $\le 60\text{ s}$.
   - `coordinates_out_of_bounds`: Out of geographical range.
4. **Action**: Anomalies are inserted into `public.mechanic_location_anomalies` for admin auditing. Telemetry updates that fail physical reality checks are rejected to prevent customer confusion.
