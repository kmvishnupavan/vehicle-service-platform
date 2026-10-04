"""
Settlement Statement & PDF Generation Service (Phase 8.9).

Generates authoritative disbursement statements and PDF documents for mechanics
based exclusively on frozen ledger records in public.mechanic_payout_ledger.
Guarantees:
- Zero raw bank account numbers (masked digits only).
- Zero secrets or provider credentials.
- Strict ownership verification before generation.
- Formally disclaims tax/GST rules as configurable.
"""

from datetime import datetime, timezone
from decimal import Decimal
import io
from typing import Any
import uuid
from fastapi import HTTPException, status
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from app.core.logging import get_logger
from app.db.supabase import get_supabase_service_client
from app.schemas.payout_account import (
    MechanicSettlementStatementResponse,
    SettlementStatementItem,
)

logger = get_logger("services.settlement_statement")


class SettlementStatementService:
    """Handles statement building and server-side PDF generation."""

    def __init__(self, client: Any = None):
        self.client = client or get_supabase_service_client()

    async def get_settlement_statement_data(
        self,
        batch_id: uuid.UUID,
        mechanic_id: uuid.UUID,
    ) -> MechanicSettlementStatementResponse:
        """
        Builds authoritative statement data for a mechanic in a specific settlement batch.
        Verifies ownership: mechanic must have payout records in this batch.
        """
        batch_id_str = str(batch_id)
        mechanic_id_str = str(mechanic_id)

        # 1. Fetch batch
        b_res = (
            self.client.table("settlement_batches")
            .select("*")
            .eq("id", batch_id_str)
            .execute()
        )
        if not b_res.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Settlement batch not found.",
            )
        batch = b_res.data[0]

        # 2. Fetch mechanic ledger records in this batch
        l_res = (
            self.client.table("mechanic_payout_ledger")
            .select("*, bookings(booking_number, service_id, services:service_id(name))")
            .eq("settlement_batch_id", batch_id_str)
            .eq("mechanic_id", mechanic_id_str)
            .execute()
        )
        ledger_items = l_res.data or []
        if not ledger_items:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No payout records found for this mechanic in the specified settlement batch.",
            )

        # 3. Fetch mechanic profile & user display name
        m_res = (
            self.client.table("mechanic_profiles")
            .select("id, user_id, business_name, profiles:user_id(full_name)")
            .eq("id", mechanic_id_str)
            .execute()
        )
        mechanic_name = "Verified Mechanic"
        if m_res.data and len(m_res.data) > 0:
            m_row = m_res.data[0]
            prof = m_row.get("profiles")
            if isinstance(prof, dict) and prof.get("full_name"):
                mechanic_name = prof["full_name"]
            elif m_row.get("business_name"):
                mechanic_name = m_row["business_name"]

        # 4. Fetch payout account details (masked)
        payout_acc_id = ledger_items[0].get("payout_account_id")
        bank_name = None
        masked_acc = "•••• •••• ****"
        ifsc = None

        if payout_acc_id:
            a_res = (
                self.client.table("mechanic_payout_accounts")
                .select("masked_account_number, bank_name, ifsc_code")
                .eq("id", str(payout_acc_id))
                .execute()
            )
            if a_res.data:
                row = a_res.data[0]
                masked_acc = row.get("masked_account_number") or masked_acc
                bank_name = row.get("bank_name")
                ifsc = row.get("ifsc_code")

        # 5. Build statement items
        items: list[SettlementStatementItem] = []
        tot_gross = Decimal("0.00")
        tot_comm = Decimal("0.00")
        tot_ded = Decimal("0.00")
        tot_net = Decimal("0.00")

        for item in ledger_items:
            b_info = item.get("bookings") or {}
            srv_info = b_info.get("services") or {} if isinstance(b_info, dict) else {}
            srv_title = srv_info.get("name") if isinstance(srv_info, dict) else "Vehicle Service"

            gross = Decimal(str(item.get("gross_amount") or "0.00"))
            comm_rate = Decimal(str(item.get("commission_rate") or "0.00"))
            comm_amt = Decimal(str(item.get("commission_amount") or "0.00"))
            ded_amt = Decimal(str(item.get("deduction_amount") or "0.00"))
            net_amt = Decimal(str(item.get("net_amount") or "0.00"))

            tot_gross += gross
            tot_comm += comm_amt
            tot_ded += ded_amt
            tot_net += net_amt

            settled_dt = None
            if item.get("settled_at"):
                try:
                    settled_dt = datetime.fromisoformat(item["settled_at"].replace("Z", "+00:00"))
                except Exception:
                    pass

            items.append(
                SettlementStatementItem(
                    payout_id=str(item["id"]),
                    booking_id=str(item["booking_id"]),
                    booking_number=b_info.get("booking_number") if isinstance(b_info, dict) else None,
                    service_title=srv_title,
                    gross_amount=f"{gross:.2f}",
                    commission_rate=f"{comm_rate * 100:.1f}%",
                    commission_amount=f"{comm_amt:.2f}",
                    deduction_amount=f"{ded_amt:.2f}",
                    net_amount=f"{net_amt:.2f}",
                    currency=item.get("currency") or "INR",
                    status=item.get("status") or "paid",
                    settled_at=settled_dt,
                )
            )

        now = datetime.now(timezone.utc)
        statement_number = f"STM-{batch['batch_number']}-{mechanic_id_str[:8].upper()}"

        return MechanicSettlementStatementResponse(
            statement_number=statement_number,
            statement_date=now,
            mechanic_id=mechanic_id_str,
            mechanic_name=mechanic_name,
            bank_name=bank_name,
            account_number_masked=masked_acc,
            ifsc_code=ifsc,
            batch_id=batch_id_str,
            batch_number=batch["batch_number"],
            batch_status=batch["status"],
            currency="INR",
            total_gross=f"{tot_gross:.2f}",
            total_commission=f"{tot_comm:.2f}",
            total_deductions=f"{tot_ded:.2f}",
            total_net=f"{tot_net:.2f}",
            net_payout=tot_net,
            items=items,
        )

    async def get_mechanic_statement(
        self,
        batch_id: uuid.UUID,
        mechanic_user_id: uuid.UUID,
        actor_role: str = "mechanic",
    ) -> MechanicSettlementStatementResponse:
        """
        Retrieves statement data for a mechanic user, resolving their mechanic_profile ID.
        Strictly enforces that mechanics can only access their own statement.
        """
        # Resolve mechanic profile
        m_res = (
            self.client.table("mechanic_profiles")
            .select("id, user_id, business_name")
            .eq("user_id", str(mechanic_user_id))
            .execute()
        )
        if not m_res.data:
            m_res = (
                self.client.table("mechanic_profiles")
                .select("id, user_id, business_name")
                .eq("id", str(mechanic_user_id))
                .execute()
            )
        if not m_res.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mechanic profile not found for user.",
            )
        profile_row = m_res.data[0]
        mechanic_profile_id = uuid.UUID(str(profile_row["id"]))

        statement = await self.get_settlement_statement_data(
            batch_id=batch_id,
            mechanic_id=mechanic_profile_id,
        )
        if profile_row.get("business_name") and (not statement.mechanic_name or statement.mechanic_name == "Verified Mechanic"):
            statement.mechanic_name = profile_row["business_name"]
        return statement

    async def generate_pdf_statement(
        self,
        batch_id: uuid.UUID,
        mechanic_user_id: uuid.UUID,
        actor_role: str = "mechanic",
    ) -> bytes:
        """Generate binary PDF statement for given batch and mechanic user."""
        statement = await self.get_mechanic_statement(
            batch_id=batch_id,
            mechanic_user_id=mechanic_user_id,
            actor_role=actor_role,
        )
        return self.generate_statement_pdf(statement)

    def generate_statement_pdf(self, statement: MechanicSettlementStatementResponse) -> bytes:
        """
        Generates a professional PDF settlement disbursement statement using ReportLab.
        Returns bytes buffer suitable for streaming HTTP responses.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()
        emerald_color = colors.HexColor("#059669")
        slate_dark = colors.HexColor("#0f172a")
        slate_gray = colors.HexColor("#475569")
        slate_light = colors.HexColor("#f8fafc")
        border_color = colors.HexColor("#cbd5e1")

        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=18,
            textColor=emerald_color,
            spaceAfter=4,
        )
        subtitle_style = ParagraphStyle(
            "DocSubTitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            textColor=slate_gray,
            spaceAfter=12,
        )
        heading_style = ParagraphStyle(
            "SectionHeading",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=12,
            textColor=slate_dark,
            spaceBefore=10,
            spaceAfter=6,
        )
        body_style = ParagraphStyle(
            "Body",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=slate_dark,
            leading=12,
        )
        bold_body = ParagraphStyle(
            "BoldBody",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=slate_dark,
            leading=12,
        )
        disclaimer_style = ParagraphStyle(
            "Disclaimer",
            parent=styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=7.5,
            textColor=slate_gray,
            leading=10,
        )

        elements = []

        # 1. Header Banner
        elements.append(Paragraph("VehicleCare On-Demand Platform", title_style))
        elements.append(Paragraph("SETTLEMENT DISBURSEMENT STATEMENT", subtitle_style))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=emerald_color, spaceAfter=14))

        # 2. Metadata Grid
        date_str = statement.statement_date.strftime("%d %b %Y, %I:%M %p UTC")
        meta_data = [
            [
                Paragraph("<b>Statement Number:</b>", body_style),
                Paragraph(statement.statement_number, bold_body),
                Paragraph("<b>Date of Issue:</b>", body_style),
                Paragraph(date_str, body_style),
            ],
            [
                Paragraph("<b>Settlement Batch:</b>", body_style),
                Paragraph(statement.batch_number, bold_body),
                Paragraph("<b>Batch Status:</b>", body_style),
                Paragraph(statement.batch_status.upper(), bold_body),
            ],
            [
                Paragraph("<b>Mechanic Name:</b>", body_style),
                Paragraph(statement.mechanic_name, bold_body),
                Paragraph("<b>Disbursement Account:</b>", body_style),
                Paragraph(f"{statement.account_number_masked} ({statement.bank_name or 'Bank'})", body_style),
            ],
        ]
        meta_table = Table(meta_data, colWidths=[1.5 * inch, 2.2 * inch, 1.5 * inch, 2.0 * inch])
        meta_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), slate_light),
                ("BOX", (0, 0), (-1, -1), 0.5, border_color),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ])
        )
        elements.append(meta_table)
        elements.append(Spacer(1, 14))

        # 3. Financial Summary Card
        elements.append(Paragraph("Financial Settlement Summary", heading_style))
        summary_data = [
            [
                Paragraph("Total Gross Service", body_style),
                Paragraph("Platform Commission", body_style),
                Paragraph("Deductions", body_style),
                Paragraph("Net Disbursed", bold_body),
            ],
            [
                Paragraph(f"INR {statement.total_gross}", bold_body),
                Paragraph(f"- INR {statement.total_commission}", bold_body),
                Paragraph(f"- INR {statement.total_deductions}", bold_body),
                Paragraph(f"INR {statement.total_net}", ParagraphStyle(
                    "BigNet", parent=bold_body, fontName="Helvetica-Bold", fontSize=11, textColor=emerald_color
                )),
            ],
        ]
        summary_table = Table(summary_data, colWidths=[1.8 * inch, 1.8 * inch, 1.8 * inch, 1.8 * inch])
        summary_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("BACKGROUND", (0, 1), (-1, 1), colors.white),
                ("BOX", (0, 0), (-1, -1), 1, border_color),
                ("LINEBELOW", (0, 0), (-1, 0), 1, emerald_color),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        elements.append(summary_table)
        elements.append(Spacer(1, 14))

        # 4. Itemized Booking Table
        elements.append(Paragraph("Itemized Service Bookings", heading_style))
        item_headers = [
            Paragraph("<b>Booking Ref</b>", bold_body),
            Paragraph("<b>Service Description</b>", bold_body),
            Paragraph("<b>Gross (INR)</b>", bold_body),
            Paragraph("<b>Comm %</b>", bold_body),
            Paragraph("<b>Comm (INR)</b>", bold_body),
            Paragraph("<b>Net (INR)</b>", bold_body),
            Paragraph("<b>Status</b>", bold_body),
        ]
        item_rows = [item_headers]

        for itm in statement.items:
            item_rows.append([
                Paragraph(itm.booking_number or itm.booking_id[:8], body_style),
                Paragraph(itm.service_title or "Service", body_style),
                Paragraph(itm.gross_amount, body_style),
                Paragraph(itm.commission_rate, body_style),
                Paragraph(itm.commission_amount, body_style),
                Paragraph(itm.net_amount, bold_body),
                Paragraph(itm.status.capitalize(), body_style),
            ])

        items_table = Table(
            item_rows,
            colWidths=[1.1 * inch, 1.8 * inch, 0.9 * inch, 0.7 * inch, 0.9 * inch, 0.9 * inch, 0.9 * inch],
        )
        items_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, slate_light]),
            ])
        )
        elements.append(items_table)
        elements.append(Spacer(1, 18))

        # 5. Security & Legal Notice
        elements.append(HRFlowable(width="100%", thickness=0.5, color=border_color, spaceAfter=8))
        elements.append(
            Paragraph(
                "Security & Privacy: Bank details are masked in compliance with data privacy mandates. "
                "Disbursements are routed through RazorpayX regulated banking partner channels.",
                disclaimer_style,
            )
        )
        elements.append(Spacer(1, 4))
        elements.append(
            Paragraph(
                f"Tax & Compliance Notice: {statement.tax_disclaimer}",
                disclaimer_style,
            )
        )

        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()
