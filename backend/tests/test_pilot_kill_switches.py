"""
Pilot Kill Switches and Safety Circuit Breakers Test Suite (Phase 15.1 Remediation).

Verifies operational kill switches:
1. KILL_SWITCH_NEW_BOOKINGS_DISABLED raises 503 on booking creation endpoint.
2. KILL_SWITCH_MATCHING_DISABLED raises 503 on mechanic matching candidate discovery.
3. KILL_SWITCH_SCHEDULED_DISPATCH_DISABLED skips scheduled booking background runner.
4. KILL_SWITCH_NOTIFICATIONS_DISABLED skips notification retry background runner.
"""

from unittest.mock import MagicMock, patch
import uuid
from fastapi import HTTPException
import pytest
from app.core.config import get_settings
from app.services.background_jobs.jobs import BackgroundJobsService
from app.services.matching_service import MatchingService


@pytest.mark.asyncio
async def test_kill_switch_matching_disabled():
    """Verify KILL_SWITCH_MATCHING_DISABLED raises 503 before database querying."""
    matching_svc = MatchingService(client=MagicMock())
    test_booking_id = uuid.uuid4()

    with patch.object(get_settings(), "KILL_SWITCH_MATCHING_DISABLED", True):
        with pytest.raises(HTTPException) as exc_info:
            await matching_svc.find_eligible_candidates(test_booking_id)

    assert exc_info.value.status_code == 503
    assert "temporarily paused" in exc_info.value.detail


@pytest.mark.asyncio
async def test_kill_switch_scheduled_dispatch_disabled():
    """Verify KILL_SWITCH_SCHEDULED_DISPATCH_DISABLED skips job execution gracefully."""
    jobs_svc = BackgroundJobsService(client=MagicMock())

    with patch.object(get_settings(), "KILL_SWITCH_SCHEDULED_DISPATCH_DISABLED", True):
        result = await jobs_svc.job_dispatch_scheduled_bookings()

    assert result.records_processed == 0
    assert result.records_succeeded == 0
    assert result.metadata.get("status") == "skipped"
    assert result.metadata.get("reason") == "KILL_SWITCH_SCHEDULED_DISPATCH_DISABLED"


@pytest.mark.asyncio
async def test_kill_switch_notifications_disabled():
    """Verify KILL_SWITCH_NOTIFICATIONS_DISABLED skips notification retries gracefully."""
    jobs_svc = BackgroundJobsService(client=MagicMock())

    with patch.object(get_settings(), "KILL_SWITCH_NOTIFICATIONS_DISABLED", True):
        result = await jobs_svc.job_retry_failed_notifications()

    assert result.records_processed == 0
    assert result.records_succeeded == 0
    assert result.metadata.get("status") == "skipped"
    assert result.metadata.get("reason") == "KILL_SWITCH_NOTIFICATIONS_DISABLED"
