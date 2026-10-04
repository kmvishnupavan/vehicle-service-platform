# Disaster Recovery & Business Continuity Plan

This document details the disaster recovery (DR) procedures, backup strategies, and recovery workflows for the Vehicle Service Platform.

> [!IMPORTANT]
> **Verified Capability vs. Recommended Operational Procedure**:
> - **Verified In Codebase**: Idempotent database migrations, provider reconciliation tools (`ReconciliationService`), webhook crash-recovery semantics (`webhook_events`), and immutable audit logging.
> - **Operational Dependency**: Automated Point-In-Time Recovery (PITR) and physical WAL backups depend on Supabase Pro/Team tier managed service capabilities and must be verified in the production cloud console before go-live.

---

## 1. Backup Strategy & Recovery Point Objective (RPO)

### 1.1. Recovery Targets
- **Recovery Point Objective (RPO)**:
  - Target: < 5 minutes for transactional data.
  - Financial data (Ledgers, Batches): 0 data loss (reconstructible via provider reconciliation + webhook event replay).
- **Recovery Time Objective (RTO)**:
  - Target: < 30 minutes for complete platform restore.

### 1.2. Backup Architecture
1. **Supabase Managed Automated Daily Backups**:
   - Stored in geographically isolated cloud storage (AWS S3).
   - Retained for 7 to 30 days depending on Supabase subscription tier.
2. **Logical Dumps (`pg_dump`)**:
   - Automated offsite backup runs daily via GitHub Actions / cron worker using `pg_dump -Fc`.
   - Encrypted at rest (AES-256) and stored in dedicated cold storage.
3. **Migration Version Control**:
   - All schema evolutions exist in `supabase/migrations/` under Git version control.
   - Any database can be provisioned from clean state using sequentially numbered migrations.

---

## 2. Recovery Procedures

### 2.1. Complete Database Loss / Region Outage
1. **Provision New Database Instance**:
   - Spin up target Supabase instance or PostgreSQL 15+ cluster in alternate region.
2. **Apply Schema Migrations**:
   ```bash
   supabase db push
   # or execute sequentially:
   # 20261001000001_core_schema.sql ... 20261003000020_production_operations.sql
   ```
3. **Restore Data from Cold Dump**:
   ```bash
   pg_restore --clean --if-exists -d "$NEW_DATABASE_URL" latest_backup.dump
   ```
4. **Update Application DNS / Secrets**:
   - Update `SUPABASE_URL` and keys in deployment environment.
   - Restart backend instances.

### 2.2. Provider Reconciliation After Outage
When payment gateway or payout provider connections are restored after a network partition or downtime:
1. Run the administrative reconciliation scanner:
   ```bash
   GET /api/v1/admin/reconciliation/payments
   GET /api/v1/admin/reconciliation/payouts
   GET /api/v1/admin/reconciliation/settlements
   ```
2. Identify all stuck records (e.g. `PAYMENT_PENDING_TOO_LONG`, `STUCK_PAYOUT_PROCESSING`).
3. For payments: Fetch transaction status directly from Razorpay `/orders/{order_id}/payments`.
4. For payouts: Fetch status from RazorpayX `/payouts/{payout_id}`.
5. Apply state transitions idempotently through the service layer.

### 2.3. Webhook Replay Workflow
If webhooks failed to deliver during an API outage:
1. In the Razorpay Dashboard, navigate to **Settings > Webhooks**.
2. Identify the outage window and select **Re-deliver Webhooks**.
3. The platform processes each webhook through `process_webhook()`:
   - If the `event_id` exists with status `processed`, it is treated as a duplicate and acknowledged (`200 OK`) without double-crediting.
   - If missing, it is reserved atomically and executed safely.

### 2.4. Settlement State Recovery
If an unhandled exception occurred mid-batch payout execution:
1. The batch remains in `processing` or `approval_required`.
2. Inspect `mechanic_payout_ledger` records for the batch ID:
   - Rows marked `paid` have valid `payout_provider_reference`.
   - Rows marked `processing` or `eligible` are verified against the provider.
3. Maker-checker locks prevent double approval or double disbursement.

---

## 3. Secret Rotation Procedures

### 3.1. Supabase Service Role Key Compromise
1. In Supabase Dashboard > Project Settings > API, generate a new Service Role Key.
2. Update backend secret management (AWS Secrets Manager / Doppler / Railway env).
3. Trigger rolling restart of backend services.
4. Revoke previous key in Supabase console.

### 3.2. Razorpay / RazorpayX Key Compromise
1. Generate new API Key Pair in Razorpay Dashboard.
2. Keep old key active temporarily if dual-key window is supported.
3. Update `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`.
4. Restart backend and verify live health probe `/health/ready`.
5. Deactivate old key.

### 3.3. Webhook Secret Rotation
1. Update `RAZORPAY_WEBHOOK_SECRET` in backend.
2. Update webhook configuration in Razorpay Dashboard.
3. Send test webhook to verify signature validation.

---

## 4. Rollback Procedures

### 4.1. Application Code Rollback
- Revert Git commit on `main` and trigger CI/CD deployment or rollback container image tag to previous SHA.

### 4.2. Database Migration Rollback
- Each migration file in `supabase/migrations/` is accompanied by forward-only, additive changes wherever possible.
- If a migration must be reverted, write an explicit compensating migration (e.g., `20261003000021_revert_feature.sql`) and deploy via standard CI/CD. Do NOT drop tables or columns directly without audit.
