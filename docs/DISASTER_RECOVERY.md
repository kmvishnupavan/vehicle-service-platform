# Disaster Recovery & Business Continuity Architecture (Phase 10)

This document formalizes the disaster recovery (DR) procedures, data preservation strategies, and recovery objectives for the Vehicle Service Platform.

> [!IMPORTANT]
> **Scope & Verification Transparency**:
> - **Tested In Codebase**: Idempotent schema migrations (`supabase/migrations/*.sql`), non-destructive migration validator (`scripts/validate_migrations.py`), financial reconciliation scanning (`ReconciliationService`), webhook crash idempotency (`webhook_events`), and audit logging (`audit_logs`).
> - **Application-Controlled**: Configuration fail-safe gates, database connectivity health probes, and live payout safety blocks.
> - **Platform/Provider-Managed**: Supabase physical PostgreSQL backups, Point-In-Time-Recovery (PITR), AWS S3 storage persistence, and multi-AZ database failover.
> - **Operational Requirement**: Offsite automated backup scripts and live PITR restoration tests require production tier subscriptions and must be scheduled by infrastructure operators prior to live launch. Physical disaster recovery was NOT tested with production data during this development phase.

---

## 1. Recovery Objectives (RPO & RTO)

| Metric | Target | Rationale & Mechanism |
|---|---|---|
| **Recovery Point Objective (RPO)** | **< 5 minutes** | Supabase continuous WAL archiving (PITR) preserves transactions up to seconds before an incident. |
| **Financial Ledgers RPO** | **0 data loss** | Every payment, ledger entry, and batch is backed by Razorpay / RazorpayX external records; discrepancy recovery reconstructs missing local state. |
| **Recovery Time Objective (RTO)** | **< 30 minutes** | Containerized backend re-deployment (< 5 min) + database snapshot restore or warm standby promotion (< 25 min). |

---

## 2. Backup Architecture & Responsibilities

### 2.1. What Supabase Provides (Managed Cloud Tier)
- **Continuous WAL Archiving**: Point-In-Time-Recovery enables rolling back database state to any specific second within the retention window (7 to 30 days).
- **Automated Daily Backups**: Daily full physical snapshots stored in geographically redundant AWS S3 buckets.
- **High Availability (HA)**: Automatic instance restart and storage volume durability (99.999999999% on AWS EBS/S3).

### 2.2. What the Application Controls
- **Deterministic Schema Reconstruction**: All 41 tables, foreign keys, and indexes are defined as sequential, non-destructive SQL files in `supabase/migrations/`.
- **Financial Reconciliation Engine**: Detects payments stuck in pending, payouts missing provider references, and line item amount mismatches (`ReconciliationService`).
- **Idempotent Webhook Replay**: All incoming provider webhooks are stored in `webhook_events` before processing; replay of events recovers dropped updates without double charges.
- **Immutable Audit Logging**: Records all critical state alterations with timestamps, actor IDs, and request IDs in `audit_logs`.

### 2.3. What Must Be Manually Configured by Platform Operators
- **Supabase PITR Activation**: Must be enabled in Supabase Project Settings -> Database -> Backups.
- **Offsite Logical Backups**: Scheduled cron job running `pg_dump -Fc` to a separate cloud account (e.g. Google Cloud Storage or Cloudflare R2).
- **Secret Vault**: Master credentials stored in external secrets manager (AWS Secrets Manager, HashiCorp Vault, or Doppler).

---

## 3. Step-by-Step Restoration Procedures

### 3.1. Database Corruption or Accidental Data Modification
1. **Identify Timestamp of Corruption**:
   - Inspect `audit_logs` to find the exact UTC timestamp immediately prior to the corrupting event:
     ```sql
     SELECT id, action, entity_type, created_at, request_id
     FROM audit_logs
     ORDER BY created_at DESC
     LIMIT 50;
     ```
2. **Execute Supabase PITR Restore**:
   - In Supabase Dashboard, navigate to **Database** -> **Backups** -> **Point in Time**.
   - Select the target timestamp (1 minute prior to the corruption).
   - Initiate restore to a new cloned database instance.
3. **Verify Restored Database State**:
   - Run readiness check against the restored database:
     ```bash
     python -m app.commands.production_readiness
     ```
4. **Promote Restored Database**:
   - Update `SUPABASE_URL` and keys in backend container environment variables.
   - Restart backend instances.

### 3.2. Complete Cloud Region Loss / Catastrophic Provider Outage
1. **Provision New Database in Alternative Region**:
   - Create new PostgreSQL 15+ cluster or Supabase project in backup region.
2. **Apply All Version-Controlled Migrations**:
   - Execute the 19 migration files in sequential order:
     ```bash
     python scripts/validate_migrations.py
     # Apply to new instance
     supabase db push --db-url "$NEW_DB_URL"
     ```
3. **Restore Data from Cold Dump**:
   ```bash
   pg_restore --clean --if-exists --no-owner --no-privileges -d "$NEW_DB_URL" latest_backup.dump
   ```
4. **Reconcile External Financial Providers**:
   - Execute reconciliation scans to pull provider states for recent transactions:
     ```bash
     curl -X GET "https://api.vehiclecare.app/api/v1/admin/reconciliation/payments?persist=true" -H "Authorization: Bearer $ADMIN_JWT"
     curl -X GET "https://api.vehiclecare.app/api/v1/admin/reconciliation/payouts?persist=true" -H "Authorization: Bearer $ADMIN_JWT"
     ```

### 3.3. Storage Bucket Recovery
- Inspection photos and repair evidence attachments are stored in Supabase Storage (`attachments` bucket).
- In the event of bucket loss, public URLs are retrieved from the `evidence_attachments` database table.
- Storage replication across regions should be enabled on production S3 buckets.

### 3.4. Secrets Recovery
- If runtime secrets are compromised or lost:
  1. Revoke existing Supabase service-role keys in Supabase Dashboard.
  2. Regenerate Razorpay webhook secret and update webhook endpoints in Razorpay Dashboard.
  3. Update secrets in CI/CD and deployment container environments.
  4. Perform rolling restart of backend containers.

---

## 4. Verification Checklist After Disaster Recovery

Following any database or infrastructure restore, execute this verification protocol:

- [ ] **Liveness Probe**: `GET /health/live` returns HTTP 200 `{"status": "ok"}`.
- [ ] **Readiness Probe**: `GET /health/ready` returns HTTP 200 with all subsystems `healthy`.
- [ ] **Database Connectivity**: `GET /health/database` returns HTTP 200 `{"status": "connected"}`.
- [ ] **Schema Integrity**: Validate all 41 tables exist with RLS enabled via `validate_migrations.py`.
- [ ] **Financial Safety**: Verify `LIVE_PAYOUTS_ENABLED` is `false` and payout mode is `sandbox`.
- [ ] **Automated Smoke Test**: Execute `pytest tests/test_deployment_smoke.py` (all 10 smoke tests pass).
- [ ] **Reconciliation Scan**: Run `/api/v1/admin/reconciliation/payments` to ensure zero unaccounted transactions.
