# Routing and Road Transit ETA Architecture (Phase 11)

## Overview
VehicleCare strictly separates **geographic straight-line geodesic distance** from **road network routing and transit ETA**. 
- Straight-line distance is computed directly in the database using PostGIS `ST_Distance` on WGS84 geography (`EPSG:4326`).
- Road routing distance, turn-by-turn routes, and estimated transit times are managed by the pluggable `RoutingProvider` abstraction layer.

---

## 1. Provider Abstraction Layer

The platform defines an abstract interface in `backend/app/services/routing/base.py`:

```python
class RoutingProvider(ABC):
    @abstractmethod
    async def calculate_route(
        self, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float
    ) -> RouteResult: ...

    @abstractmethod
    async def calculate_eta(
        self, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float
    ) -> ETAResult: ...
```

### Available Implementations:

1. **`MockRoutingProvider`** (`backend/app/services/routing/mock_provider.py`):
   - Deterministic mathematical heuristic for unit tests and local development.
   - Calculates great-circle Haversine distance.
   - Applies an urban road detour factor of **1.35x** to model street grid navigation.
   - Assumes an average urban velocity of **25 km/h** with a **3-minute base dispatch overhead** and **5-minute minimum transit time**.

2. **`OSRMRoutingProvider`** (`backend/app/services/routing/osrm_provider.py`):
   - Connects to OpenStreetMap / OSRM REST driving service (`/route/v1/driving/`).
   - Parses road network distances and GeoJSON polylines.
   - Resilient design: automatically catches network timeouts or service unavailability and seamlessly falls back to the deterministic heuristic provider.

---

## 2. In-Memory Thread-Safe Spatial ETA Cache

To prevent redundant HTTP requests and API rate-limiting, the routing subsystem includes an in-memory `ETACache` (`backend/app/services/routing/cache.py`):

- **Spatial Quantization**: Coordinates are quantized to 3 decimal places (~110 meters):
  $$\text{Key} = \text{round}(\text{lat}_1, 3):\text{round}(\text{lng}_1, 3) \rightarrow \text{round}(\text{lat}_2, 3):\text{round}(\text{lng}_2, 3)$$
- **Configurable TTL**: Default TTL is 300 seconds (5 minutes).
- **Thread Safety**: Controlled by a thread-safe mutex (`threading.Lock`).
- **Memory Bounding**: Automatically evicts expired or oldest entries when reaching max capacity (1,000 entries).
