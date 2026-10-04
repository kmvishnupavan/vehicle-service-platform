# Location Privacy and Real-Time Tracking Security (Phase 11)

## Overview
VehicleCare enforces strict privacy controls around geographic coordinates and tracking streams. GPS data is considered highly sensitive operational information.

---

## 1. Zero Public Exposure
- Public mechanic profiles (`GET /api/v1/mechanics/{id}`) **never** return `current_latitude`, `current_longitude`, phone number, email, or government documents.
- Customers cannot enumerate all mechanic locations on an open map.

---

## 2. Customer Access Scoping
A customer can observe their assigned mechanic's live location stream **only** under the following strict conditions:
1. **Direct Ownership**: The customer must own the booking (`bookings.customer_id = auth.uid()`).
2. **Active Assignment**: The mechanic must have accepted the assignment (`mechanic_assignments.assignment_status = 'accepted'`).
3. **Active Lifecycle State**: The booking status must be one of:
   - `mechanic_assigned`
   - `mechanic_en_route`
   - `mechanic_arrived`
   - `inspection`
   - `awaiting_customer_approval`
   - `service_in_progress`
   - `additional_work`
4. **Immediate Revocation**: Once a booking reaches `service_completed`, `paid`, or `cancelled`, the customer immediately loses access to the live tracking channel and REST endpoint.

---

## 3. Mechanic Access Scoping
- A technician cannot view arbitrary customer addresses or coordinates.
- Prior to accepting an offer, the mechanic is only shown the **neighborhood / locality** (e.g. "Indiranagar, Bengaluru") and the estimated distance/ETA.
- The precise customer street address and coordinates are revealed only **after** the assignment is accepted.

---

## 4. Multi-Layer Enforcement Architecture

1. **Row Level Security (RLS)**:
   - `public.mechanic_locations` SELECT policy permits reads only if the requester is the customer of an active booking linked to that mechanic, recorded after the assignment offer time.
2. **Supabase Realtime Broadcast Authorization**:
   - `public.can_receive_booking_location(topic)` function validates that the subscriber is authorized to listen to `booking-location:{booking_id}`.
   - `public.can_broadcast_booking_location(topic)` function validates that only the assigned mechanic can broadcast GPS updates to the topic.
3. **REST API Authorization**:
   - Backend route handlers enforce ownership and reject unauthenticated requests with HTTP 401 and unauthorized requests with HTTP 403.
