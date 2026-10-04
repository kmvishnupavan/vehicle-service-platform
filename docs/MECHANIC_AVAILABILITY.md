# Mechanic Availability & Operational States (Phase 11)

## Overview
Mechanic profiles maintain strict operational lifecycle states to guarantee that only technicians who are physically online, available, verified, and unburdened by active jobs receive automated job offers.

---

## 1. Availability State Graph

The `availability_status` column on `public.mechanic_profiles` enforces six discrete operational states:

| State | Description | Eligible for Automated Matching? |
| :--- | :--- | :---: |
| **`available`** | Online, ready, within operating hours, location fresh | **YES** |
| **`offline`** | Off duty, app closed, or manually toggled offline | **NO** |
| **`busy`** | Temporarily engaged in local preparation | **NO** |
| **`on_job`** | Currently assigned to an active accepted booking | **NO** |
| **`paused`** | On break, taking lunch, or resting | **NO** |
| **`suspended`** | Account restricted due to compliance or dispute | **NO** |

---

## 2. Backward Compatibility & Synchronization

To preserve 100% backward compatibility with existing code and tests that query the boolean `is_available` column, a PostgreSQL database trigger (`trg_sync_mechanic_availability`) automatically synchronizes both fields:

- `is_available` is `true` **only if** `availability_status = 'available'` **and** `verification_status = 'verified'`.
- If `verification_status = 'suspended'`, `availability_status` is forced to `'suspended'` and `is_available` is set to `false`.

---

## 3. Location Freshness Threshold

A technician cannot be matched if their location is stale:
- Threshold: **30 minutes** (`LOCATION_FRESHNESS_MINUTES = 30`).
- If `current_location_updated_at` is older than 30 minutes, or coordinates are null, the candidate is automatically excluded from dispatch.
- Technicians periodically broadcast GPS pings via `POST /api/v1/mechanics/location`.

---

## 4. Workload Capacity Balancing

A technician can have at most **1 active job** (`MAX_CONCURRENT_JOBS_PER_MECHANIC = 1`) across any of the active service statuses:
- `mechanic_assigned`
- `mechanic_en_route`
- `mechanic_arrived`
- `inspection`
- `awaiting_customer_approval`
- `service_in_progress`
- `additional_work`

Once a mechanic accepts an assignment, their workload count increments to 1, causing them to be excluded from any other matching searches until the active job reaches `service_completed`, `paid`, or `cancelled`.
