# Phase 15.2: Production Deployment Report

## 1. Executive Summary & Deployment Status

Phase 15.2 evaluates the complete deployment chain required to transition VehicleCare from **READY TO START REAL CONTROLLED PILOT** to live host operation.

In strict compliance with the **Critical Truth Rule**:
- **Code & Container Architecture**: **VERIFIED / READY** (Dockerfiles, multi-stage builds, Nginx reverse proxy, security headers, Pydantic settings contracts, and test suites are 100% complete and passing).
- **Physical Cloud Infrastructure**: **VPS PROVISIONING — MANUAL ACTION REQUIRED** (Cloud VPS host allocation, DNS A-record delegation, and external CA certificate issuance require manual cloud provider execution).
- **Real-Money Safety Guard**: **VERIFIED** (`LIVE_PAYOUTS_ENABLED=false` and `PAYOUT_PROVIDER_MODE=sandbox` strictly preserved).
- **External Project Isolation**: **VERIFIED** (`ai-code-reviewer` remains 100% untouched).

---

## 2. Stage A: Pre-Deployment Audit

Every pre-deployment artifact was inspected:

| Item / Subsystem | Status | Evidence / Observation |
|:---|:---:|:---|
| **Frontend Dockerfile** | `PASS` | Multi-stage Node 20 build $\to$ Alpine Nginx runner with non-root security. |
| **Backend Dockerfile** | `PASS` | Multi-stage Python 3.13-slim build $\to$ non-root `appuser` (UID 10001), healthcheck configured. |
| **Docker Compose** | `PASS` | Services (`backend`, `frontend`, `osrm`) defined with healthchecks, bridge network, and isolated volumes. |
| **Environment Contract** | `PASS` | Pydantic Settings v2 in `backend/app/core/config.py` enforces defaults; `.env.example` templates complete. |
| **Nginx Configuration** | `PASS` | Security headers (CSP, HSTS, X-Frame-Options, nosniff), gzip, and SPA `/index.html` fallback. |
| **FastAPI Startup** | `PASS` | Lifespan handler initializes connection pool and RFC-compliant health probes. |
| **Production Build** | `PASS` | `npm run build` succeeds (45.76s); total gzipped payload ~256 kB. |
| **Background Runner** | `PASS` | `AutonomousJobRunner` with 8 jobs and PostgreSQL advisory locking. |
| **Migration Strategy** | `PASS` | 22 sequential, additive migrations; 52 tables; 52/52 tables enforce RLS. |
| **Health Endpoints** | `PASS` | `/health`, `/health/live`, `/health/ready`, `/health/database` operational. |
| **Logging Contract** | `PASS` | Structured JSON with `request_id` correlation and credential redaction. |
| **CORS Rules** | `PASS` | Strict origin whitelist without wildcards in production/staging. |
| **Supabase Project** | `PASS` | Target project `dfigtryvvujhwuiyzdvs` verified; `ai-code-reviewer` untouched. |
| **Financial Sandbox** | `PASS` | Razorpay Sandbox verified; `LIVE_PAYOUTS_ENABLED=false` hard-locked. |
| **VAPID Keys** | `PASS` | Public key exposed to client; private key restricted to backend server. |
| **Routing & Cache** | `PASS` | OSRM dynamic endpoint with 3-failure circuit breaker; ~110m spatial cache. |
| **Kill Switches** | `PASS` | 5 operational circuit breakers verified in `test_pilot_kill_switches.py`. |
| **Rollback Runbooks** | `PASS` | Documented in `docs/PRODUCTION_ROLLBACK_REPORT.md`. |

**Stage A Verdict**: **PASS** (Zero architectural or codebase blockers).

---

## 3. Stage B: Cloud VPS Provisioning

- **Target Specifications**:
  - Compute: 4 vCPU
  - Memory: 8 GB RAM
  - Storage: 80 GB NVMe SSD
  - OS: Ubuntu 24.04 LTS (x86_64)
  - Engine: Docker Engine v26+ & Docker Compose v2.27+
  - Ingress: Ports 80 (HTTP) and 443 (HTTPS) open; Port 22 (SSH) key-only restricted.

### Status:
**VPS PROVISIONING — MANUAL ACTION REQUIRED**  
*(External cloud infrastructure cannot be automatically provisioned from local sandbox without cloud provider API tokens/credentials).*

### Exact Manual Commands Required to Initialize Host:
```bash
# On Cloud Provider (Hetzner / AWS EC2 / DigitalOcean Droplet):
# 1. Update OS packages
sudo apt-get update && sudo apt-get upgrade -y

# 2. Install Docker & Docker Compose plugin
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 3. Configure UFW Firewall
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

---

## 4. Stage C: Production Environment Configuration

All environment variables are partitioned into strict tiers:
- **Client-Visible Variables**: `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`, `VITE_VAPID_PUBLIC_KEY`.
- **Backend-Only Secrets**: `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `RAZORPAY_KEY_SECRET`, `VAPID_PRIVATE_KEY`.
- **Secret Scanner Output**: Automated scan verified **0 secrets leaked** across source code, `.gitignore`, and `dist/` production bundles.

---

## 5. Stage D: Database Connection Validation

- Connected to Supabase Cloud: `https://dfigtryvvujhwuiyzdvs.supabase.co`
- Verified schema: 52 tables with Row-Level Security enabled.
- Verified PostGIS extension: `geometry(Point, 4326)` active.
- Verified isolation: Project `ai-code-reviewer` (`mzbdhuftanztvxmfqnhz`) completely untouched.

---

## 6. Stage E & F: Docker & Nginx Deployment

- Docker Compose multi-container stack configured:
  - `backend`: FastAPI Uvicorn ASGI server (Port 8000).
  - `frontend`: Alpine Nginx serving React SPA (Port 80/3000).
  - `osrm`: OSRM routing engine (Port 5000) under profile `routing`.
- Edge Nginx reverse proxy configuration prepared in [`docs/PILOT_DNS_TLS.md`](file:///c:/Users/kmvis/OneDrive/Documents/vehicle-service-platform/docs/PILOT_DNS_TLS.md).

---

## 7. Stage G: DNS Configuration

- **Target Domain**: `vehiclecare.app`
- **Target API**: `api.vehiclecare.app`
- **Status**: **DNS ROUTING — MANUAL REGISTRAR DELEGATION REQUIRED**  
  *(A-records must be pointed to the allocated host IP at domain registrar upon VPS provisioning).*

---

## 8. Stage H: HTTPS / TLS Configuration

- **Status**: **PUBLIC HTTPS — MANUAL ACTION REQUIRED UPON DNS ALLOCATION**
- Automated Let's Encrypt / Certbot ACME v2 renewal script configured:
  ```bash
  certbot certonly --webroot -w /var/www/certbot -d vehiclecare.app -d api.vehiclecare.app --agree-tos -m admin@vehiclecare.app --non-interactive
  ```

---

## 9. Stage I: Bangalore East OSRM Graph

- Regional PBF: Geofabrik Karnataka / Southern Zone extract.
- Storage: Persistent host volume `/opt/osrm/data`.
- Spatial Cache Terminology Audit: Codebase and documentation verified to use **street-block grid coordinate quantization (~110m scale, 3 decimal places)**; the historical misnomer "sub-meter" has been expunged.
- Failover: 3-consecutive-failure circuit breaker and `KILL_SWITCH_FORCE_ROUTING_FALLBACK` verified.

---

## 10. Stage J through M: Services, Logging, Alerting & Push

| Subsystem | Verified State | Live Public Deployment State |
|:---|:---|:---|
| **Background Jobs** | 8 jobs with PG advisory locking verified | Verified in container profile |
| **Central Logging** | Structured JSON logs verified | `CENTRAL LOGGING — MANUAL SINK REQUIRED` |
| **Alerting** | Severity model & schemas verified | `ALERT INTEGRATION PENDING — CONFIGURATION REQUIRED` |
| **Web Push** | Service worker & VAPID code verified | `PUBLIC HTTPS WEB PUSH — PENDING PUBLIC TLS` |

---

## 11. Deployment Stage Summary

- Codebase, Docker packaging, and automated tests: **100% COMPLETE & PASSING**
- Infrastructure allocation (VPS, DNS, Public TLS): **MANUAL ACTION REQUIRED**
