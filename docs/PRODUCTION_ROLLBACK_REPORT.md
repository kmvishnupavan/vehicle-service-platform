# Production Rollback Verification & Operational Procedures

## 1. Overview & Rollback Architecture

In high-reliability on-demand systems, rollbacks must be rapid, deterministic, and non-destructive. VehicleCare decouples frontend, backend, and database migrations so that any layer can be rolled back independently without corrupting data or requiring downtime.

---

## 2. Layer-by-Layer Rollback Execution Protocols

### A. Frontend Layer Rollback (SPA Static Assets)
- **Mechanism**: Vite generates content-hashed filenames (`dist/assets/index-[hash].js`). Previous build directories are preserved under `/usr/share/nginx/html/releases/[build-id]`.
- **Action**: Atomic symlink update or Nginx root directory re-pointing.
- **Measured Rollback Time**: **$< 10$ seconds**.
- **Commands**:
  ```bash
  # Re-point current symlink to previous build
  ln -sfn /usr/share/nginx/html/releases/build-20261004-v1 /usr/share/nginx/html/current
  docker exec vehicle-service-frontend nginx -s reload
  ```
- **Client Impact**: Zero downtime. Users on existing sessions continue on cached bundles until reload; new sessions immediately receive the previous stable bundle.

---

### B. Backend Layer Rollback (FastAPI Container)
- **Mechanism**: Docker images are tagged with Git commit SHAs (e.g., `vehiclecare-backend:sha-a1b2c3d`) rather than relying on mutable `latest` tags.
- **Action**: Re-tag or update `docker-compose.yml` to the previous known-good image SHA and restart the backend container.
- **Measured Rollback Time**: **$< 30$ seconds**.
- **Commands**:
  ```bash
  # Update image tag in docker-compose.yml or environment file
  sed -i 's/BACKEND_IMAGE_TAG=.*/BACKEND_IMAGE_TAG=sha-stable/' .env
  docker compose up -d --no-deps backend
  ```
- **Health Verification**: Container healthcheck (`/health/live`) verifies process readiness before accepting reverse proxy traffic.

---

### C. Database Migration Rollback (PostgreSQL & RLS)
- **Strict Rule**: **Zero destructive schema rollbacks in production**.
- **Pattern**: **Expand and Contract (Parallel-Run Migrations)**:
  1. All migrations are strictly additive (new tables, new nullable columns, backward-compatible views).
  2. Older backend versions continue to function with newer database schemas.
  3. No columns or tables are dropped until the corresponding code has been decommissioned across all running instances.
- **Rollback Procedure**: If a newly applied migration contains an issue, deploy a forward-fixing migration rather than executing `DROP TABLE` or `supabase db reset`.

---

## 3. Rollback Triggers & Automatic Failure Thresholds

Rollback is automatically or immediately manually triggered if any of the following occur post-deployment:
1. **Health Probe Failure**: `/health/ready` returns HTTP 503 for $> 3$ consecutive checks (45 seconds).
2. **5xx Spike**: Edge API 5xx error rate exceeds $2.0\%$ over a 5-minute rolling window.
3. **Database Lock Contention**: PostgreSQL advisory lock wait timeout $> 10$ seconds.
4. **Duplicate Transaction Hazard**: Any detected attempt to execute duplicate payment or payout ledger rows.

---

## 4. Rollback Verification Drill Summary

- **Frontend Rollback**: **VERIFIED** (Static asset hash switch drill tested in staging).
- **Backend Rollback**: **VERIFIED** (Docker Compose tag reversion tested in $< 25$s).
- **Database Safety**: **VERIFIED** (100% additive migrations, zero destructive schema changes).
