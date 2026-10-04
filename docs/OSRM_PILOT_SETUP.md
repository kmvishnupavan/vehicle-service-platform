# Phase 15.1: Dedicated OSRM Engine Pilot Setup

## 1. Executive Summary & Current Status

The VehicleCare platform utilizes Open Source Routing Machine (OSRM) for road routing, turn-by-turn polylines, and dynamic transit ETA calculations.

### Current Status:
- **Provider Implementation**: Production-hardened [`OSRMProvider`](file:///c:/Users/kmvis/OneDrive/Documents/vehicle-service-platform/backend/app/services/routing/osrm_provider.py) operational with dynamic endpoint configuration via `OSRM_BASE_URL`.
- **Resilience**: 3-failure circuit breaker, in-memory spatial cache (~110m block grid), and automatic failover to the Haversine speed-matrix estimation engine.
- **Map Data Status**: **OSRM DATA NOT PROVISIONED IN LOCAL REPO** (Map data `.osrm` graphs are strictly excluded from Git repository to prevent repository bloat; provisioned directly onto host volumes during containerized deployment).

---

## 2. Pilot Region & Data Source

- **Target Pilot Region**: **Bangalore East (Karnataka, India)**
  - Bounding Box: Latitude `12.8500` to `13.1000` N, Longitude `77.5500` to `77.8000` E.
  - Key Operational Hubs: Indiranagar, Whitefield, Marathahalli, Bellandur, HSR Layout, Koramangala.
- **OSM Data Source**: Geofabrik Sub-Region Extract:
  - Source URL: `https://download.geofabrik.de/asia/india/southern-zone-latest.osm.pbf`
  - Alternative: `https://download.geofabrik.de/asia/india/karnataka-latest.osm.pbf` (~95 MB compressed).

---

## 3. Step-by-Step Data Preparation (Host Provisioning)

Execute the following commands on the pilot host server outside the Git working directory:

```bash
# 1. Create persistent storage directory on host
mkdir -p /opt/osrm/data
cd /opt/osrm/data

# 2. Download official Karnataka OSM extract
curl -O https://download.geofabrik.de/asia/india/karnataka-latest.osm.pbf

# 3. Extract road network graph using car profile
docker run -t -v /opt/osrm/data:/data osrm/osrm-backend:latest \
    osrm-extract -p /opt/car.lua /data/karnataka-latest.osm.pbf

# 4. Partition the Multi-Level Dijkstra (MLD) graph
docker run -t -v /opt/osrm/data:/data osrm/osrm-backend:latest \
    osrm-partition /data/karnataka-latest.osrm

# 5. Customize the graph weights and turns
docker run -t -v /opt/osrm/data:/data osrm/osrm-backend:latest \
    osrm-customize /data/karnataka-latest.osrm
```

---

## 4. Container Execution & Orchestration

Add or enable the `osrm` service in `docker-compose.yml`:

```yaml
services:
  osrm:
    image: osrm/osrm-backend:latest
    container_name: vehiclecare_osrm
    restart: unless-stopped
    command: osrm-routed --algorithm mld /data/karnataka-latest.osrm --port 5000 --max-table-size 1000
    volumes:
      - /opt/osrm/data:/data:ro
    ports:
      - "127.0.0.1:5000:5000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://127.0.0.1:5000/route/v1/driving/77.5946,12.9716;77.6000,12.9800"]
      interval: 10s
      timeout: 3s
      retries: 3
      start_period: 15s

  backend:
    environment:
      - OSRM_BASE_URL=http://osrm:5000
```

---

## 5. Health Verification & Probe Endpoints

```bash
# 1. Container Health Check
curl -s "http://localhost:5000/route/v1/driving/77.5946,12.9716;77.6000,12.9800?overview=false" | jq .code
# Expected output: "Ok"

# 2. Backend Health Probe
curl -s "http://localhost:8000/api/v1/health/ready" | jq .
```

---

## 6. Circuit Breaker & Fail-Safe Architecture

1. **Failure Tolerance**:
   - If the dedicated OSRM instance experiences 3 consecutive timeouts ($> 3$ seconds) or HTTP 5xx errors, the circuit breaker opens for 60 seconds (`circuit_cooldown_seconds=60`).
2. **Immediate Fallback**:
   - While the circuit is open, all route calculations immediately resolve to the in-memory [`MockRoutingProvider`](file:///c:/Users/kmvis/OneDrive/Documents/vehicle-service-platform/backend/app/services/routing/mock_provider.py) using the Haversine distance formula with urban speed calibration (25 km/h base).
   - Responses are tagged with `provider_source="fallback"`.
3. **Emergency Override**:
   - Setting `KILL_SWITCH_FORCE_ROUTING_FALLBACK=true` in `backend/.env` immediately forces all routing calls to the mathematical fallback without attempting HTTP connections.
