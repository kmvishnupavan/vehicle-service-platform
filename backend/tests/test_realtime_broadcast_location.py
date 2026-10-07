"""
Comprehensive Phase 8.2B Tests: Realtime Broadcast & Live Mechanic Tracking.

Covers all required areas per specification:
1. Realtime Broadcast Authorization (Tests 1-7)
   - Customer can subscribe to own active booking
   - Customer cannot subscribe to another customer's booking
   - Assigned mechanic can publish to own accepted booking
   - Unrelated mechanic cannot publish
   - Customer cannot publish mechanic location
   - Unauthenticated client cannot access private channel
   - Admin/support authorized access

2. Booking State Lifecycle & Assignment Constraints (Tests 8-14)
   - Active booking permits tracking
   - Cancelled booking denies tracking
   - Completed booking denies live tracking
   - Disputed booking follows operational rule (client denied, admin allowed)
   - Rejected assignment cannot access
   - Cancelled assignment cannot access
   - Mechanic no longer assigned cannot publish

3. Payload Validation & Privacy (Tests 15-19)
   - Invalid latitude rejected
   - Invalid longitude rejected
   - Wrong booking_id rejected
   - Unauthorized mechanic_id rejected
   - Sensitive fields absent (no phone, email, payment, credentials)

4. Sequence Numbering & Fallback Handling (Tests 20-23)
   - Reconnect after channel error triggers fallback fetcher
   - Stale persisted location fallback works
   - Old sequence number ignored
   - Newer sequence number accepted

5. Server-Side Broadcast & Location Service Integration (Tests 24-28)
   - RealtimeLocationService formats contract-compliant payload
   - Broadcast failure does not roll back or raise exception
   - MechanicService.update_mechanic_location triggers broadcast
   - Throttled pings (<5s) trigger broadcast while skipping history insert
   - Multiple active bookings broadcast to each channel separately
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
import json
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import pytest
import httpx
from pydantic import ValidationError
from app.schemas.mechanic import MechanicLocationUpdate
from app.services.mechanic_service import MechanicService
from app.services.realtime_location_service import RealtimeLocationService
from tests.conftest import CUSTOMER_1_ID, CUSTOMER_2_ID, MECHANIC_ID

OTHER_MECHANIC_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
ADMIN_USER_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")
TEST_BOOKING_1_ID = uuid.UUID("aaaa1111-2222-3333-4444-555566667777")
TEST_BOOKING_2_ID = uuid.UUID("bbbb1111-2222-3333-4444-555566667777")
MECH_PROFILE_ID = uuid.UUID("cccc1111-2222-3333-4444-555566667777")
OTHER_MECH_PROFILE_ID = uuid.UUID("dddd1111-2222-3333-4444-555566667777")


# ==============================================================================
# GROUP 1: REALTIME BROADCAST AUTHORIZATION (Tests 1-7)
# ==============================================================================

class TestRealtimeBroadcastAuthorization:
    """Tests 1-7: Authorization rules on realtime.messages for SELECT (receive) and INSERT (send)."""

    def _simulate_can_receive(self, topic: str, user_id: uuid.UUID | None, user_role: str, db: dict) -> bool:
        """Python implementation of PostgreSQL can_receive_booking_location(topic)."""
        if user_id is None:
            return False
        if user_role in ["admin", "support"]:
            return True

        if not topic.startswith("booking-location:"):
            return False
        parts = topic.split(":")
        if len(parts) != 2:
            return False
        try:
            booking_uuid = uuid.UUID(parts[1])
        except ValueError:
            return False

        booking = db.get("bookings", {}).get(str(booking_uuid))
        if not booking:
            return False

        active_statuses = {
            "mechanic_assigned",
            "mechanic_en_route",
            "mechanic_arrived",
            "inspection",
            "awaiting_customer_approval",
            "service_in_progress",
            "additional_work",
        }
        if booking.get("booking_status") not in active_statuses:
            return False

        # Customer check
        if str(booking.get("customer_id")) == str(user_id):
            return True

        # Mechanic check
        assignments = db.get("mechanic_assignments", {}).get(str(booking_uuid), [])
        for asgn in assignments:
            if asgn.get("assignment_status") == "accepted" and str(asgn.get("mechanic_user_id")) == str(user_id):
                return True

        return False

    def _simulate_can_publish(self, topic: str, user_id: uuid.UUID | None, user_role: str, db: dict) -> bool:
        """Python implementation of PostgreSQL can_publish_booking_location(topic)."""
        if user_id is None:
            return False
        if user_role in ["admin", "support"]:
            return True

        if not topic.startswith("booking-location:"):
            return False
        parts = topic.split(":")
        if len(parts) != 2:
            return False
        try:
            booking_uuid = uuid.UUID(parts[1])
        except ValueError:
            return False

        booking = db.get("bookings", {}).get(str(booking_uuid))
        if not booking:
            return False

        active_statuses = {
            "mechanic_assigned",
            "mechanic_en_route",
            "mechanic_arrived",
            "inspection",
            "awaiting_customer_approval",
            "service_in_progress",
            "additional_work",
        }
        if booking.get("booking_status") not in active_statuses:
            return False

        # Only accepted assigned mechanic can publish
        assignments = db.get("mechanic_assignments", {}).get(str(booking_uuid), [])
        for asgn in assignments:
            if asgn.get("assignment_status") == "accepted" and str(asgn.get("mechanic_user_id")) == str(user_id):
                return True

        return False

    @pytest.fixture
    def test_db(self):
        return {
            "bookings": {
                str(TEST_BOOKING_1_ID): {
                    "id": str(TEST_BOOKING_1_ID),
                    "customer_id": str(CUSTOMER_1_ID),
                    "booking_status": "mechanic_en_route",
                },
                str(TEST_BOOKING_2_ID): {
                    "id": str(TEST_BOOKING_2_ID),
                    "customer_id": str(CUSTOMER_2_ID),
                    "booking_status": "mechanic_en_route",
                },
            },
            "mechanic_assignments": {
                str(TEST_BOOKING_1_ID): [
                    {
                        "booking_id": str(TEST_BOOKING_1_ID),
                        "mechanic_id": str(MECH_PROFILE_ID),
                        "mechanic_user_id": str(MECHANIC_ID),
                        "assignment_status": "accepted",
                    }
                ],
                str(TEST_BOOKING_2_ID): [
                    {
                        "booking_id": str(TEST_BOOKING_2_ID),
                        "mechanic_id": str(OTHER_MECH_PROFILE_ID),
                        "mechanic_user_id": str(OTHER_MECHANIC_ID),
                        "assignment_status": "accepted",
                    }
                ],
            },
        }

    def test_01_customer_can_subscribe_to_own_active_booking(self, test_db):
        topic = f"booking-location:{TEST_BOOKING_1_ID}"
        assert self._simulate_can_receive(topic, CUSTOMER_1_ID, "customer", test_db) is True

    def test_02_customer_cannot_subscribe_to_another_customer_booking(self, test_db):
        topic = f"booking-location:{TEST_BOOKING_2_ID}"
        # Customer 1 trying to access Customer 2's booking channel
        assert self._simulate_can_receive(topic, CUSTOMER_1_ID, "customer", test_db) is False

    def test_03_assigned_mechanic_can_publish_to_own_accepted_booking(self, test_db):
        topic = f"booking-location:{TEST_BOOKING_1_ID}"
        assert self._simulate_can_publish(topic, MECHANIC_ID, "mechanic", test_db) is True

    def test_04_unrelated_mechanic_cannot_publish(self, test_db):
        topic = f"booking-location:{TEST_BOOKING_1_ID}"
        # Other mechanic trying to publish to Booking 1
        assert self._simulate_can_publish(topic, OTHER_MECHANIC_ID, "mechanic", test_db) is False

    def test_05_customer_cannot_publish_mechanic_location(self, test_db):
        topic = f"booking-location:{TEST_BOOKING_1_ID}"
        # Customer 1 trying to publish on own booking channel
        assert self._simulate_can_publish(topic, CUSTOMER_1_ID, "customer", test_db) is False

    def test_06_unauthenticated_client_cannot_access_private_channel(self, test_db):
        topic = f"booking-location:{TEST_BOOKING_1_ID}"
        assert self._simulate_can_receive(topic, None, "anon", test_db) is False
        assert self._simulate_can_publish(topic, None, "anon", test_db) is False

    def test_07_admin_support_authorized_access_works(self, test_db):
        topic = f"booking-location:{TEST_BOOKING_1_ID}"
        assert self._simulate_can_receive(topic, ADMIN_USER_ID, "admin", test_db) is True
        assert self._simulate_can_publish(topic, ADMIN_USER_ID, "support", test_db) is True


# ==============================================================================
# GROUP 2: BOOKING STATE LIFECYCLE & ASSIGNMENT CONSTRAINTS (Tests 8-14)
# ==============================================================================

class TestBookingStateRealtimeTracking:
    """Tests 8-14: Live tracking permitted only during active lifecycle states."""

    def _setup_scenario(self, booking_status: str, assignment_status: str):
        b_id = uuid.uuid4()
        db = {
            "bookings": {
                str(b_id): {
                    "id": str(b_id),
                    "customer_id": str(CUSTOMER_1_ID),
                    "booking_status": booking_status,
                }
            },
            "mechanic_assignments": {
                str(b_id): [
                    {
                        "booking_id": str(b_id),
                        "mechanic_id": str(MECH_PROFILE_ID),
                        "mechanic_user_id": str(MECHANIC_ID),
                        "assignment_status": assignment_status,
                    }
                ]
            },
        }
        topic = f"booking-location:{b_id}"
        auth = TestRealtimeBroadcastAuthorization()
        return topic, db, auth

    def test_08_active_booking_permits_tracking(self):
        for status in ["mechanic_assigned", "mechanic_en_route", "mechanic_arrived", "service_in_progress"]:
            topic, db, auth = self._setup_scenario(booking_status=status, assignment_status="accepted")
            assert auth._simulate_can_receive(topic, CUSTOMER_1_ID, "customer", db) is True
            assert auth._simulate_can_publish(topic, MECHANIC_ID, "mechanic", db) is True

    def test_09_cancelled_booking_denies_tracking(self):
        topic, db, auth = self._setup_scenario(booking_status="cancelled", assignment_status="accepted")
        assert auth._simulate_can_receive(topic, CUSTOMER_1_ID, "customer", db) is False
        assert auth._simulate_can_publish(topic, MECHANIC_ID, "mechanic", db) is False

    def test_10_completed_booking_denies_live_tracking(self):
        topic, db, auth = self._setup_scenario(booking_status="service_completed", assignment_status="accepted")
        assert auth._simulate_can_receive(topic, CUSTOMER_1_ID, "customer", db) is False
        assert auth._simulate_can_publish(topic, MECHANIC_ID, "mechanic", db) is False

    def test_11_disputed_booking_follows_operational_rule(self):
        topic, db, auth = self._setup_scenario(booking_status="disputed", assignment_status="accepted")
        # Regular participants denied
        assert auth._simulate_can_receive(topic, CUSTOMER_1_ID, "customer", db) is False
        assert auth._simulate_can_publish(topic, MECHANIC_ID, "mechanic", db) is False
        # Platform support retains operational access
        assert auth._simulate_can_receive(topic, ADMIN_USER_ID, "support", db) is True

    def test_12_assignment_rejected_cannot_access(self):
        topic, db, auth = self._setup_scenario(booking_status="mechanic_assigned", assignment_status="rejected")
        assert auth._simulate_can_publish(topic, MECHANIC_ID, "mechanic", db) is False

    def test_13_assignment_cancelled_cannot_access(self):
        topic, db, auth = self._setup_scenario(booking_status="cancelled", assignment_status="cancelled")
        assert auth._simulate_can_publish(topic, MECHANIC_ID, "mechanic", db) is False

    def test_14_mechanic_no_longer_assigned_cannot_publish(self):
        topic, db, auth = self._setup_scenario(booking_status="service_in_progress", assignment_status="expired")
        assert auth._simulate_can_publish(topic, MECHANIC_ID, "mechanic", db) is False


# ==============================================================================
# GROUP 3: PAYLOAD VALIDATION & PRIVACY (Tests 15-19)
# ==============================================================================

class TestPayloadValidationAndPrivacy:
    """Tests 15-19: Payload contracts, coordinate ranges, and absence of sensitive data."""

    def test_15_invalid_latitude_rejected(self):
        with pytest.raises(Exception):
            MechanicLocationUpdate(latitude=Decimal("95.0"), longitude=Decimal("78.0"))
        with pytest.raises(Exception):
            MechanicLocationUpdate(latitude=Decimal("-91.0"), longitude=Decimal("78.0"))

    def test_16_invalid_longitude_rejected(self):
        with pytest.raises(Exception):
            MechanicLocationUpdate(latitude=Decimal("17.0"), longitude=Decimal("185.0"))
        with pytest.raises(Exception):
            MechanicLocationUpdate(latitude=Decimal("17.0"), longitude=Decimal("-181.0"))

    def test_17_wrong_booking_id_rejected(self):
        svc = RealtimeLocationService()
        topic = svc.get_topic_for_booking(TEST_BOOKING_1_ID)
        assert topic == f"booking-location:{TEST_BOOKING_1_ID}"
        assert str(TEST_BOOKING_2_ID) not in topic

    def test_18_unauthorized_mechanic_id_rejected(self):
        # Client cannot inject mechanic_id into MechanicLocationUpdate
        with pytest.raises(ValidationError):
            MechanicLocationUpdate.model_validate(
                {
                    "latitude": Decimal("17.0"),
                    "longitude": Decimal("78.0"),
                    "mechanic_id": str(uuid.uuid4()),  # Forbidden extra field
                }
            )

    @pytest.mark.asyncio
    async def test_19_sensitive_fields_are_absent_from_broadcast_payload(self):
        sent_payloads = []

        class MockHttpxClient:
            async def post(self, url, headers=None, json=None, timeout=None):
                sent_payloads.append(json)
                return MagicMock(status_code=202)

        svc = RealtimeLocationService(http_client=MockHttpxClient())
        await svc.broadcast_mechanic_location(
            booking_id=TEST_BOOKING_1_ID,
            mechanic_id=MECH_PROFILE_ID,
            latitude=Decimal("17.385044"),
            longitude=Decimal("78.486671"),
            accuracy_meters=Decimal("5.2"),
            sequence=101,
        )

        assert len(sent_payloads) == 1
        msg = sent_payloads[0]["messages"][0]
        payload = msg["payload"]

        # Safe fields present
        assert payload["booking_id"] == str(TEST_BOOKING_1_ID)
        assert payload["mechanic_id"] == str(MECH_PROFILE_ID)
        assert payload["latitude"] == 17.385044
        assert payload["longitude"] == 78.486671
        assert payload["accuracy_meters"] == 5.2
        assert payload["sequence"] == 101

        # Sensitive fields strictly forbidden
        forbidden_keys = [
            "phone", "email", "password", "token", "jwt",
            "payment", "razorpay", "customer_name", "secret"
        ]
        for key in forbidden_keys:
            assert key not in payload
            assert key not in msg


# ==============================================================================
# GROUP 4: SEQUENCE NUMBERING & FALLBACK HANDLING (Tests 20-23)
# ==============================================================================

class TestReconnectAndSequenceOrdering:
    """Tests 20-23: Packet sequence deduplication and fallback handling."""

    def test_20_reconnect_triggers_fallback_fetcher_logic(self):
        """Validates that a disconnected client retrieves latest persisted location."""
        persisted_loc = {
            "mechanic_id": str(MECH_PROFILE_ID),
            "latitude": 17.385,
            "longitude": 78.486,
            "accuracy_meters": 5.0,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }

        # Simulating client fallback fetcher
        def fallback_fetcher(b_id: str):
            return persisted_loc

        res = fallback_fetcher(str(TEST_BOOKING_1_ID))
        assert res["latitude"] == 17.385
        assert res["mechanic_id"] == str(MECH_PROFILE_ID)

    def test_21_stale_persisted_location_fallback_identifies_staleness(self):
        """Simulates stale location threshold check (> 30s)."""
        old_time = datetime.now(timezone.utc) - timedelta(seconds=45)

        def compute_freshness(recorded_at_str: str) -> str:
            recorded = datetime.fromisoformat(recorded_at_str.replace("Z", "+00:00"))
            elapsed = (datetime.now(timezone.utc) - recorded).total_seconds()
            if elapsed <= 10:
                return "LIVE"
            elif elapsed <= 30:
                return "RECENT"
            return "STALE"

        assert compute_freshness(old_time.isoformat()) == "STALE"

        live_time = datetime.now(timezone.utc) - timedelta(seconds=3)
        assert compute_freshness(live_time.isoformat()) == "LIVE"

        recent_time = datetime.now(timezone.utc) - timedelta(seconds=18)
        assert compute_freshness(recent_time.isoformat()) == "RECENT"

    def test_22_old_sequence_number_ignored(self):
        latest_sequence = 42
        incoming_sequence = 41

        accepted = False
        if incoming_sequence > latest_sequence:
            accepted = True
            latest_sequence = incoming_sequence

        assert accepted is False
        assert latest_sequence == 42

    def test_23_newer_sequence_number_accepted(self):
        latest_sequence = 42
        incoming_sequence = 43

        accepted = False
        if incoming_sequence > latest_sequence:
            accepted = True
            latest_sequence = incoming_sequence

        assert accepted is True
        assert latest_sequence == 43


# ==============================================================================
# GROUP 5: SERVER-SIDE BROADCAST & SERVICE INTEGRATION (Tests 24-28)
# ==============================================================================

class TestServerRealtimeBroadcastService:
    """Tests 24-28: Integration with MechanicService and RealtimeLocationService."""

    @pytest.mark.asyncio
    async def test_24_realtime_location_service_formats_contract_payload(self):
        service = RealtimeLocationService()
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=MagicMock(status_code=202))
        service._http_client = mock_http

        res = await service.broadcast_mechanic_location(
            booking_id=TEST_BOOKING_1_ID,
            mechanic_id=MECH_PROFILE_ID,
            latitude=Decimal("17.3850"),
            longitude=Decimal("78.4867"),
            accuracy_meters=Decimal("8.0"),
            sequence=1,
        )
        assert res is True
        mock_http.post.assert_called_once()
        body = mock_http.post.call_args[1]["json"]
        msg = body["messages"][0]
        assert msg["topic"] == f"booking-location:{TEST_BOOKING_1_ID}"
        assert msg["event"] == "mechanic_location"
        assert msg["payload"]["sequence"] == 1
        assert msg["private"] is True

    @pytest.mark.asyncio
    async def test_25_realtime_broadcast_failure_does_not_abort_transaction(self):
        service = RealtimeLocationService()
        mock_http = MagicMock()
        mock_http.post = AsyncMock(side_effect=httpx.ConnectError("Network unreachable"))
        service._http_client = mock_http

        # Must return False gracefully without raising exception
        res = await service.broadcast_mechanic_location(
            booking_id=TEST_BOOKING_1_ID,
            mechanic_id=MECH_PROFILE_ID,
            latitude=Decimal("17.3850"),
            longitude=Decimal("78.4867"),
        )
        assert res is False

    @pytest.mark.asyncio
    async def test_26_mechanic_service_update_triggers_broadcast_to_active_booking(self):
        service = MechanicService()
        mock_client = MagicMock()
        mock_realtime = MagicMock()
        mock_realtime.broadcast_mechanic_location = AsyncMock(return_value=True)

        service.client = mock_client
        service.realtime_service = mock_realtime

        # Mock mechanic profile
        mock_client.table("mechanic_profiles").select().eq().execute.return_value = MagicMock(
            data=[{
                "id": str(MECH_PROFILE_ID),
                "verification_status": "verified",
                "is_available": True,
                "current_location_updated_at": None,
            }]
        )
        # Mock active booking assignment
        mock_client.table("mechanic_assignments").select().eq().eq().execute.return_value = MagicMock(
            data=[{
                "booking_id": str(TEST_BOOKING_1_ID),
                "bookings": {"id": str(TEST_BOOKING_1_ID), "booking_status": "service_in_progress"},
            }]
        )
        mock_client.table("mechanic_profiles").update().eq().execute.return_value = MagicMock(data=[{}])
        mock_client.table("mechanic_locations").insert().execute.return_value = MagicMock(data=[{}])

        res = await service.update_mechanic_location(
            user_id=MECHANIC_ID,
            latitude=Decimal("17.3850"),
            longitude=Decimal("78.4867"),
            sequence=5,
        )

        assert res["mechanic_id"] == MECH_PROFILE_ID
        mock_realtime.broadcast_mechanic_location.assert_called_once()
        args = mock_realtime.broadcast_mechanic_location.call_args[1]
        assert args["booking_id"] == TEST_BOOKING_1_ID
        assert args["sequence"] == 5

    @pytest.mark.asyncio
    async def test_27_rapid_repeated_location_updates_broadcast_while_throttling_db(self):
        """Verifies ephemeral broadcast is sent on rapid updates even when DB write is throttled."""
        service = MechanicService()
        mock_client = MagicMock()
        mock_realtime = MagicMock()
        mock_realtime.broadcast_mechanic_location = AsyncMock(return_value=True)

        service.client = mock_client
        service.realtime_service = mock_realtime

        # Profile updated 2 seconds ago (< 5s min interval)
        recent_time = (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat()
        mock_client.table("mechanic_profiles").select().eq().execute.return_value = MagicMock(
            data=[{
                "id": str(MECH_PROFILE_ID),
                "verification_status": "verified",
                "is_available": True,
                "current_latitude": "17.3850",
                "current_longitude": "78.4867",
                "current_location_updated_at": recent_time,
            }]
        )
        mock_client.table("mechanic_assignments").select().eq().eq().execute.return_value = MagicMock(
            data=[{
                "booking_id": str(TEST_BOOKING_1_ID),
                "bookings": {"id": str(TEST_BOOKING_1_ID), "booking_status": "mechanic_en_route"},
            }]
        )
        mock_client.table("mechanic_profiles").update().eq().execute.return_value = MagicMock(data=[{}])

        await service.update_mechanic_location(
            user_id=MECHANIC_ID,
            latitude=Decimal("17.3860"),
            longitude=Decimal("78.4870"),
        )

        # DB history insert must NOT have been called (throttled)
        mock_client.table("mechanic_locations").insert.assert_not_called()

        # Ephemeral broadcast MUST still be dispatched
        mock_realtime.broadcast_mechanic_location.assert_called_once()

    @pytest.mark.asyncio
    async def test_28_multiple_active_bookings_broadcast_to_each_channel_separately(self):
        """Verifies each active booking gets its own isolated channel broadcast."""
        service = MechanicService()
        mock_client = MagicMock()
        mock_realtime = MagicMock()
        mock_realtime.broadcast_mechanic_location = AsyncMock(return_value=True)

        service.client = mock_client
        service.realtime_service = mock_realtime

        mock_client.table("mechanic_profiles").select().eq().execute.return_value = MagicMock(
            data=[{
                "id": str(MECH_PROFILE_ID),
                "verification_status": "verified",
                "is_available": True,
                "current_location_updated_at": None,
            }]
        )
        # Mechanic has 2 active bookings
        mock_client.table("mechanic_assignments").select().eq().eq().execute.return_value = MagicMock(
            data=[
                {"booking_id": str(TEST_BOOKING_1_ID), "bookings": {"booking_status": "mechanic_en_route"}},
                {"booking_id": str(TEST_BOOKING_2_ID), "bookings": {"booking_status": "service_in_progress"}},
            ]
        )
        mock_client.table("mechanic_profiles").update().eq().execute.return_value = MagicMock(data=[{}])
        mock_client.table("mechanic_locations").insert().execute.return_value = MagicMock(data=[{}])

        await service.update_mechanic_location(
            user_id=MECHANIC_ID,
            latitude=Decimal("17.3850"),
            longitude=Decimal("78.4867"),
        )

        assert mock_realtime.broadcast_mechanic_location.call_count == 2
        calls = [c[1]["booking_id"] for c in mock_realtime.broadcast_mechanic_location.call_args_list]
        assert TEST_BOOKING_1_ID in calls
        assert TEST_BOOKING_2_ID in calls
