# Phase 15.1: Pilot Deployment Architecture

## 1. Overview & Architectural Philosophy

For the **Controlled Production Pilot** (12 customers, 5 mechanics, 2 administrators in Bangalore East), simplicity, resilience, deterministic rollback, and low operational overhead take precedence over complex multi-region orchestrators.

Kubernetes introduces unnecessary ingress controllers, CNI overlay networks, and etcd cluster management overhead that would obscure root-cause isolation during an initial 14-day cohort. Therefore, the pilot uses a **hardened single-node VPS / containerized Docker Compose architecture** behind an Nginx reverse proxy with automated TLS termination.

---

## 2. Deployment Topology Diagram

```text
                                 INTERNET
                                    |
                            [ HTTPS / TLS 1.3 ]
                         (Let's Encrypt / Certbot)
                                    |
                        +-----------------------+
                        |  NGINX Reverse Proxy  |
                        |   (Host Port 80/443)  |
                        +-----------+-----------+
                                    |
            +-----------------------+-----------------------+
            | (Path: / )                                    | (Path: /api/v1/*, /health*)
            v                                               v
+-----------------------+                       +-----------------------+
|   Frontend Container  |                       |   FastAPI Backend     |
|   (Alpine Nginx SPA)  |                       |   (Python 3.13 ASGI)  |
|   Port 80 (internal)  |                       |   Port 8000 (internal)|
+-----------------------+                       +-----------+-----------+
                                                            |
                        +-----------------------------------+-----------------------------------+
                        |                                   |                                   |
                        v                                   v                                   v
            +-----------------------+           +-----------------------+           +-----------------------+
            |  Supabase Cloud DB    |           | Dedicated OSRM Engine |           | Autonomous Job Runner |
            |  (PostgreSQL 15 + RLS)|           | (Bangalore OSM Graph) |           | (PG Advisory Locking) |
            |  Project: dfigtry...  |           | Port 5000 (internal)  |           | 8 Periodic Cron Jobs  |
            +-----------+-----------+           +-----------------------+           +-----------------------+
                        |
                        v
            +-----------------------+
            |   Supabase Realtime   |
            |   (WSS Broadcasts)    |
            +-----------------------+
```

---

## 3. Component Breakdown

| Layer | Technology | Role | Resilience & Fail-Safe |
|:---|:---|:---|:---|
| **Edge / Ingress** | Nginx 1.25 (Alpine) | SSL termination, HTTP $\to$ HTTPS redirect, gzip compression, rate limiting | Rejects invalid host headers; buffers slowloris |
| **Frontend** | React 18 / Vite 5 SPA | User interface for Customer, Mechanic, and Admin | Static asset caching with immutable hashes; Service Worker offline fallback |
| **Backend API** | FastAPI / Uvicorn | Authoritative business logic, RBAC, PostGIS discovery | Stateless container; scales to multi-worker Uvicorn |
| **Database** | Supabase Cloud PostgreSQL | 52 tables, 100% RLS enforcement, PostGIS spatial queries | Continuous WAL archiving + daily automated snapshot |
| **Realtime** | Supabase Realtime (WSS) | Mechanic location telemetry, offer countdowns, booking updates | Automatic client reconnection + REST polling fallback |
| **Routing / ETA** | Dedicated OSRM Container | Street-level road distance, turn-by-turn geometry, transit ETA | 3-failure circuit breaker $\to$ Haversine speed matrix fallback |
| **Background Jobs** | In-process asyncio runner | 8 periodic maintenance and reconciliation workers | PostgreSQL advisory locking (`pg_try_advisory_xact_lock`) |

---

## 4. Operational Characteristics

1. **Failure Isolation**: An OSRM container failure does not crash the API; the circuit breaker immediately switches to mathematical distance estimation.
2. **Deterministic Rollback**:
   - Frontend: Update symlink or re-point Nginx root to previous `dist/` hash ($< 10$s).
   - Backend: Stop container and restart previous Docker image tag ($< 30$s).
3. **Observability**: Standard Docker `json-file` logging driver with automatic log rotation (50MB max file size, 5 file retention).
4. **Zero Live Money**: Environment strictly configured with `LIVE_PAYOUTS_ENABLED=false` and `PAYOUT_PROVIDER_MODE=sandbox`.
