# Vehicle Inspection & Diagnostic Workflow

## 1. Structured Inspection Model
Doorstep mechanics record vehicle condition using structured data contracts rather than unformatted free text. The data is persisted in `public.service_inspections` and extended in migration `20261004000022_vehicle_service_operations.sql`:

- `odometer_reading` (integer): Authoritative mileage at arrival.
- `vehicle_condition` (varchar): High-level physical rating (e.g. `Excellent`, `Good`, `Fair`, `Poor`, `Critical`).
- `checklist_results` (jsonb): Key-value evaluation of baseline physical systems.
- `diagnostic_findings` (jsonb): Normalized array of diagnostic findings:
  ```json
  [
    {
      "category": "BRAKES",
      "finding": "Front brake pads worn below 2.5mm safe limit",
      "severity": "high",
      "recommended_action": "Replace front brake pad set"
    }
  ]
  ```
- `recommended_services` (jsonb): Recommended additional services with itemized pricing:
  ```json
  [
    {
      "title": "Front Brake Pad Replacement",
      "description": "OEM spec ceramic pads",
      "is_required": true,
      "estimated_price": 2400.00
    }
  ]
  ```
- `parts_required` (jsonb): Itemized parts required for repairs.
- `labor_requirements` (text): Estimated technician labor and installation requirements.
- `evidence_file_paths` (text[]): Private Supabase storage paths for pre-service photo/diagnostic evidence.

---

## 2. API Contract
- **Endpoint**: `POST /api/v1/bookings/{booking_id}/structured-inspection`
- **Caller**: Assigned mechanic for the booking.
- **Valid Current States**: `mechanic_arrived`, `inspection`.
- **State Transition**: Transitions booking state to `awaiting_customer_approval` if recommended services or additional costs are proposed; otherwise directly to `service_in_progress` if baseline service requires no customer signoff.
- **Idempotency & Upsert**: If an inspection record already exists for the booking, it is updated in place and stamped with updated audit metadata.

---

## 3. Customer Transparency
Upon submission:
1. Customer receives in-app and push notification that inspection results are ready for review.
2. In the Customer Tracking UI, the `InspectionReportCard` displays:
   - Current vehicle odometer and condition rating.
   - Diagnostic findings with severity badges (`low`, `medium`, `high`, `critical`).
   - Categorized recommendations labeled clearly as **MANDATORY** (safety critical) vs **OPTIONAL** (preventative maintenance).
   - Estimated additional costs before asking for consent.
