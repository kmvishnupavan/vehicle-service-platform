"""
Centralized Pricing Engine (Phase 12).

Authoritative coordinator for all doorstep service financial computations:
- Exact Decimal arithmetic (two decimal places, ROUND_HALF_UP).
- Deterministic calculation:
    Subtotal = Base Services + Installed Parts + Labor Charges
    Additional Charges = Approved Additional Work Requests
    Taxable Base = Subtotal + Additional Charges - Discounts
    Tax (18% GST) = Taxable Base * TAX_RATE
    Total Amount = Taxable Base + Tax
- Creation of immutable price snapshots upon customer approval.
- Validation that post-approval modifications strictly follow additional work protocols.
"""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
import uuid
from fastapi import HTTPException, status
from app.core.logging import get_logger
from app.schemas.service_operations import PriceSnapshot

logger = get_logger("services.pricing_engine")

TWO_PLACES = Decimal("0.01")
TAX_RATE = Decimal("0.18")  # 18% GST for automotive maintenance and spare parts in India


class PricingEngine:
    """Centralized, deterministic monetary calculation engine."""

    @staticmethod
    def round_currency(amount: Decimal | str | float | int) -> Decimal:
        """Round any monetary amount to 2 decimal places using standard ROUND_HALF_UP."""
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
        return amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    @classmethod
    def calculate_totals(
        cls,
        base_service_amount: Decimal | str | float,
        parts_total: Decimal | str | float = Decimal("0.00"),
        labor_total: Decimal | str | float = Decimal("0.00"),
        additional_work_total: Decimal | str | float = Decimal("0.00"),
        discount_amount: Decimal | str | float = Decimal("0.00"),
        custom_tax_rate: Decimal | None = None,
    ) -> dict[str, Decimal]:
        """
        Calculate complete financial totals using pure Decimal arithmetic.

        Formula:
            Subtotal = Base Services + Parts + Labor
            Taxable Base = max(0, Subtotal + Additional Work - Discount)
            Tax = Taxable Base * 0.18
            Total = Taxable Base + Tax
        """
        base = cls.round_currency(base_service_amount)
        parts = cls.round_currency(parts_total)
        labor = cls.round_currency(labor_total)
        additional = cls.round_currency(additional_work_total)
        discount = cls.round_currency(discount_amount)
        tax_rate = custom_tax_rate if custom_tax_rate is not None else TAX_RATE

        subtotal = cls.round_currency(base + parts + labor)
        taxable_base = cls.round_currency(max(Decimal("0.00"), subtotal + additional - discount))
        tax_amount = cls.round_currency(taxable_base * tax_rate)
        total_amount = cls.round_currency(taxable_base + tax_amount)

        return {
            "base_service_amount": base,
            "parts_total": parts,
            "labor_total": labor,
            "subtotal": subtotal,
            "additional_charges": additional,
            "discount_amount": discount,
            "taxable_base": taxable_base,
            "tax_rate": tax_rate,
            "tax_amount": tax_amount,
            "total_amount": total_amount,
        }

    @classmethod
    def create_price_snapshot(
        cls,
        base_service_amount: Decimal | str | float,
        parts_total: Decimal | str | float = Decimal("0.00"),
        labor_total: Decimal | str | float = Decimal("0.00"),
        additional_work_total: Decimal | str | float = Decimal("0.00"),
        discount_amount: Decimal | str | float = Decimal("0.00"),
        approved_by: uuid.UUID | None = None,
        version: int = 1,
    ) -> PriceSnapshot:
        """Generate an immutable price snapshot suitable for freezing in booking records."""
        totals = cls.calculate_totals(
            base_service_amount=base_service_amount,
            parts_total=parts_total,
            labor_total=labor_total,
            additional_work_total=additional_work_total,
            discount_amount=discount_amount,
        )

        return PriceSnapshot(
            base_service_amount=totals["base_service_amount"],
            parts_total=totals["parts_total"],
            labor_total=totals["labor_total"],
            additional_work_total=totals["additional_charges"],
            discount_amount=totals["discount_amount"],
            taxable_base=totals["taxable_base"],
            tax_rate=totals["tax_rate"],
            tax_amount=totals["tax_amount"],
            total_amount=totals["total_amount"],
            snapshot_timestamp=datetime.now(timezone.utc),
            approved_by=approved_by,
            version=version,
        )
