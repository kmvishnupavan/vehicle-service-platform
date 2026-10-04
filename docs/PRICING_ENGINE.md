# Centralized Pricing Engine & Price Snapshot Architecture

## 1. Principles & Financial Determinism
All monetary arithmetic across the platform follows strict financial safeguards:
1. **Decimal Arithmetic Only**: Calculations in Python use `decimal.Decimal` with explicit rounding (`ROUND_HALF_UP`) to two decimal places (`Decimal('0.01')`). Never use IEEE-754 binary floating-point (`float`) for currency.
2. **Deterministic Tax Computation**: Taxable base equals:
   $$\text{Taxable Base} = \max(0, \text{Base Price} + \text{Parts} + \text{Labor} + \text{Approved Additional Work} - \text{Discount})$$
   Applicable GST is calculated deterministically at 18%:
   $$\text{Tax Amount} = \text{round}(\text{Taxable Base} \times 0.18, 2)$$
   $$\text{Final Total} = \text{Taxable Base} + \text{Tax Amount}$$
3. **No Hidden Surcharges**: All fees (parts, labor, additional work, statutory tax) are explicitly itemized.

---

## 2. Immutable Price Snapshots
To prevent race conditions, post-approval price creep, or mutable quote manipulation:
- When a quote is presented to the customer and approved, an immutable JSON snapshot is generated and stored in `public.bookings.price_snapshot`.
- **Snapshot Schema**:
  ```json
  {
    "base_service_amount": 1500.00,
    "parts_total": 800.00,
    "labor_total": 200.00,
    "additional_work_total": 500.00,
    "discount_amount": 100.00,
    "taxable_base": 2900.00,
    "tax_rate": 0.18,
    "tax_amount": 522.00,
    "total_amount": 3422.00,
    "snapshot_timestamp": "2026-10-04T06:15:00Z",
    "approved_by": "customer-uuid",
    "version": 1
  }
  ```
- Subsequent invoice creation (`PaymentService.create_invoice_for_booking`) derives line items and totals directly from this immutable snapshot.
- Any legitimate post-approval charge must be submitted as a new formal `additional_work_requests` item and approved explicitly by the customer.

---

## 3. Python Service Implementation
- Located in `backend/app/services/pricing_engine.py`:
  - `calculate_service_pricing(...) -> PricingBreakdown`: Pure financial calculation service.
  - `create_price_snapshot(...) -> PriceSnapshot`: Builds frozen immutable dictionary representation.
  - `verify_price_snapshot(...) -> bool`: Validates cryptographic/mathematical consistency before invoice generation.
