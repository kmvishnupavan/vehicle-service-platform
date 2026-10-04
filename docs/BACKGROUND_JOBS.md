# Background Jobs & Autonomous Processing Architecture

## 1. Overview
VehicleCare employs a database-backed background job execution system that uses PostgreSQL advisory locks (`pg_try_advisory_xact_lock`) for distributed synchronization. This architecture eliminates external queue dependencies (Redis, RabbitMQ, Celery) while guaranteeing strong ACID auditability and crash safety.

---

## 2. Distributed Locking & Execution Model

### Advisory Lock Hashing
Each job name is mapped to a deterministic 64-bit integer using CRC32 hashing:
```python
def _compute_lock_id(job_name: str) -> int:
    return zlib.crc32(f"vc_job:{job_name}".encode("utf-8"))
```
When a worker invokes a job:
1. It requests `SELECT pg_try_advisory_xact_lock(:lock_id)`.
2. If another instance is running the job, lock acquisition immediately returns `false`, and the invocation terminates cleanly with `status = "skipped_locked"`.
3. If acquired, execution records an audit entry in `public.background_job_executions` with `status = "running"`.
4. When the transaction commits or aborts, PostgreSQL automatically releases the advisory lock.

---

## 3. Core Background Jobs

| Job Name | Frequency | Target Subsystem | Idempotency Mechanism |
|---|---|---|---|
| `expire_mechanic_offers` | 1 min | Matching Engine | `expires_at < clock_timestamp()` filter on `mechanic_assignments` |
| `advance_expired_matching_sessions` | 1 min | Dispatch Pipeline | Checks candidate attempt count vs `MAX_MATCHING_ATTEMPTS` |
| `reconcile_webhook_reservations` | 5 min | Payment Webhooks | Detects stuck `processing` events older than 5 minutes |
| `reconcile_pending_payments` | 15 min | Razorpay Ingress | Scans `payment_pending` bookings > 15m; detects orphan orders |
| `reconcile_payouts` | 30 min | Payout Ledger | Compares internal ledger items against sandbox provider state |
| `retry_failed_notifications` | 2 min | Push/In-App Alert Queue | Exponential backoff (`2^attempt * 30s`) with max 5 retries |
| `dispatch_scheduled_bookings` | 1 min | Scheduled Bookings | Dispatches when `now() >= dispatch_at` and `status = 'scheduled'` |
| `refresh_operational_metrics` | 60 min | Admin Analytics | Aggregates system KPIs into `operational_metrics_snapshots` |

---

## 4. Standalone CLI & Daemon Mode
The background runner can be executed as a one-shot task or continuous daemon:
```bash
# Execute all jobs in a single sweep
python -m app.commands.run_background_jobs --all

# Run as continuous background daemon with 60-second polling interval
python -m app.commands.run_background_jobs --daemon --interval 60

# Run specific job only
python -m app.commands.run_background_jobs --job expire_mechanic_offers
```

---

## 5. Failure Modes & Recovery
- **Worker Crash**: If the Python process dies abruptly, the database connection terminates and PostgreSQL instantly drops the advisory transaction lock. No lingering locks or stuck queues.
- **Job Exceptions**: Caught, sanitized, and stored in `error_summary` in `public.background_job_executions`.
- **Database Network Disconnection**: Worker retries with linear backoff without crashing the FastAPI application.
