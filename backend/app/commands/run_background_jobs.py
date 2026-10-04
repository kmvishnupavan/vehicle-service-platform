"""
Background Job Daemon / One-Shot Runner CLI (Phase 13).

Usage:
  python -m app.commands.run_background_jobs --once
  python -m app.commands.run_background_jobs --interval 30
"""

import argparse
import asyncio
import sys
from typing import Any

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.services.background_jobs import BackgroundJobRunner, BackgroundJobsService

logger = get_logger("commands.run_background_jobs")


async def run_all_jobs(runner: BackgroundJobRunner, jobs_svc: BackgroundJobsService) -> list[dict[str, Any]]:
    """Execute all 8 operational jobs in sequence with distributed locks."""
    job_map = [
        ("expire_mechanic_offers", jobs_svc.job_expire_mechanic_offers),
        ("advance_expired_matching_sessions", jobs_svc.job_advance_expired_matching_sessions),
        ("reconcile_webhook_reservations", jobs_svc.job_reconcile_webhook_reservations),
        ("reconcile_pending_payments", jobs_svc.job_reconcile_pending_payments),
        ("reconcile_payouts", jobs_svc.job_reconcile_payouts),
        ("retry_failed_notifications", jobs_svc.job_retry_failed_notifications),
        ("dispatch_scheduled_bookings", jobs_svc.job_dispatch_scheduled_bookings),
        ("refresh_operational_metrics", jobs_svc.job_refresh_operational_metrics),
    ]

    results = []
    for job_name, job_fn in job_map:
        try:
            summary = await runner.execute_job(job_name, job_fn)
            results.append(summary)
        except Exception as exc:
            logger.error("job_runner_iteration_error", job_name=job_name, error=str(exc))
    return results


async def main():
    parser = argparse.ArgumentParser(description="VehicleCare Background Jobs Runner")
    parser.add_argument("--once", action="store_true", help="Run a single pass of all jobs and exit")
    parser.add_argument("--interval", type=int, default=30, help="Loop interval in seconds (default: 30)")
    args = parser.parse_args()

    configure_logging()
    settings = get_settings()
    logger.info("background_jobs_runner_started", environment=settings.ENVIRONMENT, mode="once" if args.once else f"loop({args.interval}s)")

    runner = BackgroundJobRunner()
    jobs_svc = BackgroundJobsService()

    if args.once:
        summaries = await run_all_jobs(runner, jobs_svc)
        print("=" * 60)
        print("VehicleCare Background Job Execution Pass Completed")
        print("=" * 60)
        for s in summaries:
            print(f"[{s.get('status', 'UNKNOWN').upper()}] {s.get('job_name')}: processed={s.get('records_processed', 0)}, succeeded={s.get('records_succeeded', 0)}, failed={s.get('records_failed', 0)}")
        sys.exit(0)
    else:
        while True:
            await run_all_jobs(runner, jobs_svc)
            await asyncio.sleep(args.interval)


if __name__ == "__main__":
    asyncio.run(main())
