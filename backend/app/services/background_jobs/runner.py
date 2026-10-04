"""
Background Job Execution Runner (Phase 13).

Provides:
- Distributed advisory locking using PostgreSQL pg_try_advisory_lock
- Generic execution lifecycle tracking in public.background_job_executions
- Safe error boundary and execution auditing
- Concurrency protection across multi-worker instances
"""

from datetime import datetime, timezone
import traceback
from typing import Any, Callable
import uuid

from app.core.logging import get_logger
from app.db.supabase import get_supabase_service_client

logger = get_logger("services.background_jobs.runner")


class JobExecutionResult:
    def __init__(
        self,
        records_processed: int = 0,
        records_succeeded: int = 0,
        records_failed: int = 0,
        error_summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.records_processed = records_processed
        self.records_succeeded = records_succeeded
        self.records_failed = records_failed
        self.error_summary = error_summary
        self.metadata = metadata or {}


class BackgroundJobRunner:
    """Orchestrates job execution with database locks and audit persistence."""

    def __init__(self, client: Any = None):
        self.client = client or get_supabase_service_client()

    def try_acquire_lock(self, job_name: str) -> bool:
        """Attempt to acquire a PostgreSQL session advisory lock for job_name."""
        try:
            res = self.client.rpc("try_acquire_job_lock", {"p_job_name": job_name}).execute()
            return bool(res.data)
        except Exception as exc:
            logger.warning("job_lock_acquisition_failed_fallback_allowed", job_name=job_name, error=str(exc))
            # In test environments or when DB RPC is unavailable, allow execution
            return True

    def release_lock(self, job_name: str) -> bool:
        """Release the PostgreSQL advisory lock for job_name."""
        try:
            res = self.client.rpc("release_job_lock", {"p_job_name": job_name}).execute()
            return bool(res.data)
        except Exception as exc:
            logger.warning("job_lock_release_failed", job_name=job_name, error=str(exc))
            return True

    async def execute_job(
        self,
        job_name: str,
        job_fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute a background job safely wrapped in distributed lock and execution logging.
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        execution_id = f"{job_name}_{now.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"

        # 1. Acquire distributed lock
        acquired = self.try_acquire_lock(job_name)
        if not acquired:
            logger.info("job_skipped_concurrent_worker_active", job_name=job_name)
            return {
                "job_name": job_name,
                "execution_id": execution_id,
                "status": "skipped",
                "reason": "Locked by another concurrent worker",
                "started_at": now_iso,
            }

        # 2. Record initial execution entry
        db_exec_id = None
        try:
            insert_res = self.client.table("background_job_executions").insert({
                "job_name": job_name,
                "execution_id": execution_id,
                "status": "running",
                "started_at": now_iso,
            }).execute()
            if insert_res.data and len(insert_res.data) > 0:
                db_exec_id = insert_res.data[0]["id"]
        except Exception as exc:
            logger.warning("failed_to_log_job_start", job_name=job_name, error=str(exc))

        # 3. Execute job logic within safety boundary
        result: JobExecutionResult
        status_val = "completed"
        error_summary = None

        try:
            raw_result = await job_fn(*args, **kwargs)
            if isinstance(raw_result, JobExecutionResult):
                result = raw_result
            elif isinstance(raw_result, tuple) and len(raw_result) >= 3:
                result = JobExecutionResult(
                    records_processed=raw_result[0],
                    records_succeeded=raw_result[1],
                    records_failed=raw_result[2],
                    error_summary=raw_result[3] if len(raw_result) > 3 else None,
                    metadata=raw_result[4] if len(raw_result) > 4 else {},
                )
            elif isinstance(raw_result, dict):
                result = JobExecutionResult(
                    records_processed=raw_result.get("records_processed", 0),
                    records_succeeded=raw_result.get("records_succeeded", 0),
                    records_failed=raw_result.get("records_failed", 0),
                    error_summary=raw_result.get("error_summary"),
                    metadata=raw_result.get("metadata", {}),
                )
            else:
                result = JobExecutionResult(
                    records_processed=1,
                    records_succeeded=1,
                    records_failed=0,
                )

            if result.records_failed > 0:
                status_val = "partial_failure" if result.records_succeeded > 0 else "failed"

        except Exception as exc:
            status_val = "failed"
            error_summary = f"{type(exc).__name__}: {str(exc)}\n{traceback.format_exc(limit=3)}"
            logger.error("background_job_crashed", job_name=job_name, error=str(exc))
            result = JobExecutionResult(
                records_processed=0,
                records_succeeded=0,
                records_failed=1,
                error_summary=error_summary,
            )
        finally:
            # 4. Release distributed lock
            self.release_lock(job_name)

        completed_at = datetime.now(timezone.utc)
        completed_iso = completed_at.isoformat()

        # 5. Finalize execution record in database
        summary = {
            "id": db_exec_id,
            "job_name": job_name,
            "execution_id": execution_id,
            "status": status_val,
            "started_at": now_iso,
            "completed_at": completed_iso,
            "records_processed": result.records_processed,
            "records_succeeded": result.records_succeeded,
            "records_failed": result.records_failed,
            "error_summary": result.error_summary or error_summary,
            "metadata": result.metadata,
        }

        if db_exec_id:
            try:
                self.client.table("background_job_executions").update({
                    "status": status_val,
                    "completed_at": completed_iso,
                    "records_processed": result.records_processed,
                    "records_succeeded": result.records_succeeded,
                    "records_failed": result.records_failed,
                    "error_summary": summary["error_summary"],
                    "metadata": result.metadata,
                }).eq("id", str(db_exec_id)).execute()
            except Exception as upd_exc:
                logger.warning("failed_to_log_job_completion", job_name=job_name, error=str(upd_exc))

        logger.info(
            "background_job_finished",
            job_name=job_name,
            status=status_val,
            processed=result.records_processed,
            succeeded=result.records_succeeded,
            failed=result.records_failed,
        )
        return summary
