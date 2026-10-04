# Phase 15 Baseline: Deployment Discovery & Operational Posture

## Overview

In accordance with Phase 15 Step 1, this document records the rigorous architectural discovery of the **VehicleCare (On-Demand Vehicle Service Platform)** deployment configuration, environment boundaries, and external dependencies following Phase 14 certification.

---

## 1. Authoritative Deployment Discovery

| Question | Status | Factual Evidence |
| :--- | :--- | :--- |
| **CURRENTLY DEPLOYED?** | **NO** | The repository contains complete containerization (`Dockerfile`, `docker-compose.yml`), GitHub Actions deployment workflows (`deploy-staging.yml`, `deploy-production.yml`), and verified production builds (`dist/`). However, no live public production virtual machine or Kubernetes cluster is currently bound or running external public traffic. |
| **STAGING AVAILABLE?** | **YES (Simulated / Local & Cloud)** | Staging is active via local/Docker container orchestration connected to live Supabase cloud PostgreSQL (`https://dfigtryvvujhwuiyzdvs.supabase.co`). Staging workflows and readiness probes are fully operational. |
| **PRODUCTION AVAILABLE?** | **NO** | Production environment is architected and container-ready, but pending cloud cluster provisioning and public DNS binding. |
| **CUSTOM DOMAIN AVAILABLE?** | **NO** | Target domain `vehiclecare.app` and `api.vehiclecare.app` are designated in configuration templates and Nginx specs, but registrar DNS delegation has not been bound to a public IP. |
| **HTTPS AVAILABLE?** | **PARTIAL (Cloud HTTPS / Local HTTP)** | Cloud database, auth, and realtime traffic via Supabase are 100% TLS/HTTPS (`https://...` and `wss://...`). Local development and container testing endpoints operate over HTTP (`http://localhost:8000`, `http://localhost:3000`). |

---

## 2. Certified System Capabilities (Phase 14 Baseline)

The certified platform enters Phase 15 with:
- **Backend Test Suite**: 468 tests passed, 0 failures (Pytest).
- **Frontend Unit Suite**: 121 tests passed, 0 failures (Vitest).
- **Browser E2E Suite**: 18 tests passed across 8 test suites (Playwright Chromium).
- **Database Migrations**: 22 version-controlled migrations producing 52 tables with Row-Level Security (RLS) active on all 52 tables.
- **Production Readiness Probes**: 6/6 probe suites reported `OVERALL RESULT: READY`.
- **Client Security Scan**: Static code and production bundle scans confirm 0 leaked secrets or service-role keys.
- **Financial Safety**: `LIVE_PAYOUTS_ENABLED = false` and `PAYOUT_PROVIDER_MODE = sandbox`. No real money moved.

---

## 3. Environment Separation Matrix

| Configuration Component | Development | Staging (Local / CI) | Production (Target) |
| :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | `development` | `staging` | `production` |
| `DEBUG` | `true` | `false` | `false` |
| `API_BASE_URL` | `http://localhost:8000/api/v1` | `http://localhost:8000/api/v1` or staging host | `https://api.vehiclecare.app/api/v1` |
| `SUPABASE_URL` | `https://dfigtryvvujhwuiyzdvs.supabase.co` | `https://dfigtryvvujhwuiyzdvs.supabase.co` | Isolated production project |
| `LIVE_PAYOUTS_ENABLED` | `false` (Enforced) | `false` (Enforced) | `false` (Locked for Pilot) |
| `PAYOUT_PROVIDER_MODE` | `sandbox` | `sandbox` | `sandbox` (Pilot phase) |
| `CORS_ORIGINS` | Localhost ports 3000, 5173 | Staging origins | Explicit production domain list |
| `ROUTING_PROVIDER` | `osrm` (with Haversine fallback) | `osrm` | Dedicated self-hosted container / managed |

---

## 4. Operational Risk Areas Identified for Phase 15

1. **Routing Provider Dependency**:
   - The public OSRM demo server (`http://router.project-osrm.org`) has strict rate limits. Phase 15 introduces dynamic `OSRM_BASE_URL` and a self-hosted container profile in `docker-compose.yml` to insulate the platform.
2. **Push Notifications in Browser Contexts**:
   - Modern browsers require HTTPS and an active Service Worker for native Web Push. Phase 15 introduces `sw.js` and `frontend/src/lib/notifications.ts` with in-app notification fallbacks.
3. **Pilot Cohort Containment**:
   - Before any public marketing, a controlled pilot of 5–20 trusted users with limited operating hours is required to validate real-world mechanic dispatch, GPS tracking under mobile network variability, and invoice approvals.
