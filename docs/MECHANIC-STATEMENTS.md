# Phase 8.9 — Authoritative Mechanic Settlement Statements & PDF Invoicing

## 1. Overview & Regulatory Rationale

Mechanics operating on the vehicle service platform require formal, authoritative disbursement statements for accounting, tax reporting (GST and Income Tax Act Section 194C / 194M TDS), and dispute reconciliation.

Phase 8.9 provides:
1. **JSON & PDF Statements**: Structured data via REST API and high-fidelity, server-side PDF generation using ReportLab 5.0.1.
2. **Strict Sensitive Data Masking**: All bank account numbers are permanently masked to the trailing 4 digits (`•••• •••• {last4}`). Full account numbers and provider API credentials never appear in statements.
3. **Tenant Isolation & RLS**: Mechanics can only retrieve statements for batches in which they possess completed ledger entries. Admins maintain platform-wide statement generation rights.
4. **Authoritative Tax & Financial Breakdown**: Itemized gross booking value, platform commission, TDS deductions, net disbursement, and statutory disclaimers.

---

## 2. Statement Data Schema

### 2.1 REST API Representation (`MechanicSettlementStatementResponse`)
```json
{
  "statement_number": "STMT-20261003-8A2F",
  "statement_date": "2026-10-03T12:00:00Z",
  "mechanic_id": "01940b3c-0000-7000-8000-000000000001",
  "mechanic_name": "Apex Auto Solutions",
  "bank_name": "HDFC Bank",
  "account_number_masked": "•••• •••• 4589",
  "ifsc_code": "HDFC0001234",
  "batch_id": "01940b3c-1111-7000-8000-000000000001",
  "batch_number": "BATCH-20261003-0001",
  "batch_status": "completed",
  "currency": "INR",
  "total_gross": "14500.00",
  "total_commission": "1450.00",
  "total_deductions": "145.00",
  "total_net": "12905.00",
  "net_payout": 12905.00,
  "items": [
    {
      "payout_id": "01940b3c-2222-7000-8000-000000000001",
      "booking_id": "01940b3c-3333-7000-8000-000000000001",
      "booking_number": "BK-2026-1001",
      "service_title": "Full Brake Pad Replacement",
      "gross_amount": "4500.00",
      "commission_rate": "0.10",
      "commission_amount": "450.00",
      "deduction_amount": "45.00",
      "net_amount": "4005.00",
      "currency": "INR",
      "status": "paid",
      "settled_at": "2026-10-03T12:30:00Z"
    }
  ],
  "tax_disclaimer": "GST liability is assessed in accordance with applicable tax regulations. TDS under Section 194C / 194M has been withheld where statutory thresholds apply."
}
```

---

## 3. Server-Side PDF Generation (ReportLab 5.0.1)

### 3.1 Design Principles
- **No Client-Side Dependencies**: Generated 100% server-side in Python to guarantee unalterable authenticity.
- **Canvas Metrics & Typography**: Uses `reportlab.pdfgen.canvas` and standard Helvetica fonts with standard point sizes.
- **Header Banner**: Prominent platform branding (`VehicleCare Platform`) and authoritative document title (`SETTLEMENT DISBURSEMENT STATEMENT`).
- **Tabular Layout**: Column alignment for Date, Booking #, Service Description, Gross, Commission, TDS, and Net Disbursed.
- **Statutory Footers**: Legal disclaimers, generation timestamp, and unique cryptographic statement reference.

### 3.2 Security & Data Hygiene
```python
# Security Masking Verification
def mask_account_number(acc: str | None) -> str:
    if not acc:
        return "•••• •••• ••••"
    clean = re.sub(r"\s+", "", acc)
    last4 = clean[-4:] if len(clean) >= 4 else clean
    return f"•••• •••• {last4}"
```
- **Zero Raw Secrets**: Neither Razorpay secret keys, account passwords, nor full credit/debit coordinates are processed by or stored in the PDF generation pipeline.

---

## 4. API Endpoints

### 4.1 JSON Statement
- **Endpoint**: `GET /api/v1/payout-accounts/settlements/{batch_id}/statement?mechanic_id={uuid}`
- **Security**: JWT Bearer. Mechanics may only query their own statement; Admins may query any mechanic in the batch.
- **Response**: `MechanicSettlementStatementResponse`

### 4.2 Streaming PDF Statement
- **Endpoint**: `GET /api/v1/payout-accounts/settlements/{batch_id}/statement/pdf?mechanic_id={uuid}`
- **Response**: `application/pdf` binary stream with `Content-Disposition: inline; filename="settlement_statement_{batch_no}.pdf"`.
- **Frontend Integration**: Clickable "PDF" download button in mechanic settlement history tables, streaming direct blob responses via URL object.
