# Dynamic Road ETA & Resilient Routing

## 1. Overview
Accurate customer arrival estimates require real-time road-network routing. VehicleCare integrates OpenStreetMap's OSRM routing engine with multi-layered circuit breakers, caching, and fallback providers.

---

## 2. Resilience Architecture

### Circuit Breaker & Retry Mechanism
External network routing calls to OSRM can occasionally timeout or suffer transient latency spikes:
- **Consecutive Failure Threshold**: 3 failures trip the circuit breaker into `OPEN` state.
- **Cool-off Duration**: 60 seconds. During this window, all calls immediately bypass OSRM and use fallback routing.
- **Half-Open Probe**: After 60 seconds, a single request is routed to OSRM; if successful, the circuit breaker resets to `CLOSED`.

### Fallback Routing Engine
When OSRM is unreachable or circuit breaker is tripped:
- Calculates geodesic haversine distance.
- Applies urban street tortuosity multiplier ($d_{road} \approx d_{haversine} \times 1.414$).
- Applies speed heuristics based on urban congestion (30 km/h baseline).
- **Explicit Tagging**: Response payload is explicitly tagged with `eta_source = 'fallback'` and `is_fallback = true` for observability.

---

## 3. ETA Quantization Cache (`ETACache`)
To prevent repeated routing calls between proximate coordinates:
- Coordinates are quantized to 3 decimal places (~110m spatial grid).
- Results are cached in-memory with a 300-second TTL.
- Eliminates redundant network traffic for stationary or slow-moving mechanics.
