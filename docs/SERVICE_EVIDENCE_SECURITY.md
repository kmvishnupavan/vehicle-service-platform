# Service Evidence Security & Storage Architecture

## 1. Storage Architecture
All diagnostic inspection photos, damaged part evidence, work-in-progress snapshots, and post-service verification photos are stored in Supabase private bucket `service-evidence`.

Under no circumstances are raw private storage URLs or bucket tokens exposed directly to client applications.

---

## 2. Security Controls & Access Authorization
1. **Private Storage & RLS**:
   - The `service-evidence` bucket is configured as private.
   - Row-level security on `service_evidence` and `service_inspections` validates tenant ownership:
     - Customer can only access evidence for their own bookings (`booking.customer_id = auth.uid()`).
     - Mechanic can only access evidence for their assigned bookings (`booking.mechanic_id = auth.uid()`).
     - Admins and Support staff have read-only inspection access for verification and dispute resolution.
2. **Short-Lived Signed URLs**:
   - Viewing or downloading evidence requires generating a time-limited signed URL via `POST /api/v1/bookings/{id}/evidence/signed-url`.
   - Default expiration is 900 seconds (15 minutes).
   - Backend verifies that the caller owns or is assigned to the booking before generating the signed URL.
3. **MIME Type & Size Limits**:
   - Permitted MIME types: `image/jpeg`, `image/png`, `image/webp`, `application/pdf`.
   - Max file size: 10 MB per file.
   - Allowed evidence categories: `completion`, `before_service`, `after_service`, `damage`, `diagnostic`, `disputes`.
4. **Tenant Isolation**:
   - Evidence file keys follow the deterministic path convention: `{booking_id}/{category}/{uuid}.{ext}`.
   - Cross-booking or cross-customer object access is rejected at both the API layer and the storage policy level.
