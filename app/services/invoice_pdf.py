"""ReportLab PDF generation for invoices.

Renders a professional, offline A4 invoice from the shared render model
produced by :func:`app.services.invoice_service.build_render_model`. The
same render model drives the on-screen preview, so the preview and the
printed document always match.

A Unicode TrueType font (Segoe UI / Arial) is registered when available so
the Indian Rupee symbol renders correctly; otherwise ReportLab's built-in
Helvetica is used.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

_FONT = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
_FONT_ITALIC = "Helvetica-Oblique"

_LINE = colors.HexColor("#334155")
_MUTED = colors.HexColor("#64748b")
_DARK = colors.HexColor("#0f172a")
_ACCENT = colors.HexColor("#2563eb")


def _register_unicode_font() -> None:
    """Register a TrueType font that includes the rupee glyph (best effort)."""
    global _FONT, _FONT_BOLD, _FONT_ITALIC  # noqa: PLW0603

    font_dir = None
    windir = os.environ.get("WINDIR")
    if windir:
        font_dir = Path(windir) / "Fonts"

    candidates: list[tuple[Path, Path, Path | None]] = []
    if font_dir is not None:
        candidates = [
            (font_dir / "segoeui.ttf", font_dir / "segoeuib.ttf", font_dir / "segoeuii.ttf"),
            (font_dir / "arial.ttf", font_dir / "arialbd.ttf", font_dir / "ariali.ttf"),
            (font_dir / "arialuni.ttf", font_dir / "arialbd.ttf", None),
        ]
    candidates.append((Path("DejaVuSans.ttf"), Path("DejaVuSans-Bold.ttf"), Path("DejaVuSans-Oblique.ttf")))

    for regular, bold, italic in candidates:
        if not regular.exists() or not bold.exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont("NcsFont", str(regular)))
            pdfmetrics.registerFont(TTFont("NcsFont-Bold", str(bold)))
            italic_name = "NcsFont-Italic"
            if italic is not None and italic.exists():
                pdfmetrics.registerFont(TTFont(italic_name, str(italic)))
            else:
                italic_name = "NcsFont"
            _FONT = "NcsFont"
            _FONT_BOLD = "NcsFont-Bold"
            _FONT_ITALIC = italic_name
            return
        except Exception:  # noqa: BLE001 - font registration is best-effort
            continue

    logger.debug("No Unicode TrueType font found — falling back to Helvetica.")


_register_unicode_font()


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

def _base_style() -> ParagraphStyle:
    return ParagraphStyle("base", fontName=_FONT, fontSize=9.5, leading=13, textColor=_DARK)


_STYLES = {
    "hotel_name": ParagraphStyle(
        "hotel_name", fontName=_FONT_BOLD, fontSize=19, leading=23, textColor=_DARK
    ),
    "hotel_desc": ParagraphStyle(
        "hotel_desc", fontName=_FONT_ITALIC, fontSize=9.5, leading=13, textColor=_MUTED
    ),
    "hotel_line": ParagraphStyle(
        "hotel_line", fontName=_FONT, fontSize=9, leading=12.5, textColor=_DARK
    ),
    "invoice_title": ParagraphStyle(
        "invoice_title", fontName=_FONT_BOLD, fontSize=18, leading=22, textColor=_DARK
    ),
    "section": ParagraphStyle(
        "section", fontName=_FONT_BOLD, fontSize=10.5, leading=14, textColor=_ACCENT,
        spaceAfter=4,
    ),
    "label": ParagraphStyle(
        "label", fontName=_FONT, fontSize=9, leading=13, textColor=_MUTED
    ),
    "value": ParagraphStyle(
        "value", fontName=_FONT, fontSize=9.5, leading=13, textColor=_DARK
    ),
    "value_bold": ParagraphStyle(
        "value_bold", fontName=_FONT_BOLD, fontSize=9.5, leading=13, textColor=_DARK
    ),
    "total_label": ParagraphStyle(
        "total_label", fontName=_FONT, fontSize=10, leading=14, textColor=_DARK
    ),
    "total_value": ParagraphStyle(
        "total_value", fontName=_FONT, fontSize=10, leading=14, textColor=_DARK
    ),
    "grand_label": ParagraphStyle(
        "grand_label", fontName=_FONT_BOLD, fontSize=11, leading=15, textColor=_DARK
    ),
    "grand_value": ParagraphStyle(
        "grand_value", fontName=_FONT_BOLD, fontSize=11, leading=15, textColor=_DARK
    ),
    "status": ParagraphStyle(
        "status", fontName=_FONT_BOLD, fontSize=10, leading=14, textColor=_DARK
    ),
    "footer": ParagraphStyle(
        "footer", fontName=_FONT, fontSize=10, leading=15, textColor=_DARK,
        alignment=1, spaceBefore=6,
    ),
    "sig": ParagraphStyle(
        "sig", fontName=_FONT, fontSize=9.5, leading=13, textColor=_DARK
    ),
}

_PAGE_WIDTH, _PAGE_HEIGHT = A4
_MARGIN = 14 * mm
_CONTENT_WIDTH = _PAGE_WIDTH - 2 * _MARGIN


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _p(text: str, style: str) -> Paragraph:
    return Paragraph(_escape(text), _STYLES[style])


def _escape(text: Any) -> str:
    """Escape XML entities for Paragraph; keep line breaks intact."""
    text = str(text if text is not None else "")
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _label_value_rows(rows: list[tuple[str, str]]) -> Table:
    data = []
    for label, value in rows:
        data.append(
            [
                Paragraph(label, _STYLES["label"]),
                Paragraph(value, _STYLES["value"]),
            ]
        )
    table = Table(data, colWidths=[_CONTENT_WIDTH * 0.32, _CONTENT_WIDTH * 0.68])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def _header_logo(render: dict[str, Any]) -> tuple[list[Any], int]:
    """Return (header_flowables, row_height) for the hotel header."""
    hotel_name = _p(render["hotel_name"], "hotel_name")
    description = _p(render["hotel_description"], "hotel_desc") if render["hotel_description"] else None
    address_paras = [_p(line, "hotel_line") for line in render["hotel_address_lines"]]
    contact = []
    if render["hotel_phone"]:
        contact.append(_p(f"Phone: {render['hotel_phone']}", "hotel_line"))
    if render["hotel_email"]:
        contact.append(_p(f"Email: {render['hotel_email']}", "hotel_line"))
    # Website is only shown when configured — never an empty line.

    right_cell = [hotel_name]
    if description is not None:
        right_cell.append(description)
        right_cell.append(Spacer(1, 2))
    right_cell.extend(address_paras)
    if contact:
        right_cell.append(Spacer(1, 3))
        right_cell.extend(contact)
    right_wrapper = Table([[right_cell]], colWidths=[_CONTENT_WIDTH * 0.78])
    right_wrapper.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    logo_image, logo_height = _load_logo(render.get("logo_path"))
    if logo_image is None:
        return [right_wrapper], 0
    row_height = max(logo_height, 46 * mm if False else 0)
    header_table = Table(
        [[logo_image, right_wrapper]],
        colWidths=[_CONTENT_WIDTH * 0.22, _CONTENT_WIDTH * 0.78],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
                ("VALIGN", (1, 0), (1, 0), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return [header_table], row_height


def _load_logo(logo_path: str | None) -> tuple[Any, float]:
    """Load the hotel logo as a scaled Image; returns (None, 0) on failure."""
    if not logo_path:
        return None, 0
    path = Path(logo_path)
    if not path.exists():
        return None, 0
    try:
        reader = ImageReader(str(path))
        image_width, image_height = reader.getSize()
        if image_width <= 0 or image_height <= 0:
            return None, 0
        max_width = _CONTENT_WIDTH * 0.20
        max_height = 26 * mm
        scale = min(max_width / image_width, max_height / image_height, 1.0)
        return (
            Image(str(path), width=image_width * scale, height=image_height * scale),
            image_height * scale,
        )
    except Exception:  # noqa: BLE001 - never break the invoice over a logo
        logger.warning("Could not load hotel logo %s", logo_path)
        return None, 0


def _charges_table(render: dict[str, Any]) -> Table:
    data = [
        [
            Paragraph("Description", _STYLES["value_bold"]),
            Paragraph("Qty", _STYLES["value_bold"]),
            Paragraph("Rate", _STYLES["value_bold"]),
            Paragraph("Amount", _STYLES["value_bold"]),
        ]
    ]
    for item in render["line_items"]:
        data.append(
            [
                Paragraph(item["description"], _STYLES["value"]),
                Paragraph(str(item["quantity"]), _STYLES["value"]),
                Paragraph(str(item["unit_amount"]), _STYLES["value"]),
                Paragraph(str(item["amount"]), _STYLES["value"]),
            ]
        )
    table = Table(
        data,
        colWidths=[
            _CONTENT_WIDTH * 0.5,
            _CONTENT_WIDTH * 0.1,
            _CONTENT_WIDTH * 0.2,
            _CONTENT_WIDTH * 0.2,
        ],
        repeatRows=1,
    )
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ALIGN", (1, 0), (3, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    table.setStyle(TableStyle(style))
    return table


def _totals_blocks(render: dict[str, Any]) -> list[Any]:
    """Right-aligned totals, then paid/remaining and payment status."""
    flowables: list[Any] = []

    totals_rows = [["Subtotal", Paragraph(render["subtotal"], _STYLES["total_value"])]]
    if render["discount"] is not None:
        totals_rows.append(["Discount", Paragraph(render["discount"], _STYLES["total_value"])])
    totals_rows.append(
        [
            Paragraph("Grand Total", _STYLES["grand_label"]),
            Paragraph(render["grand_total"], _STYLES["grand_value"]),
        ]
    )
    totals_table = Table(totals_rows, colWidths=[_CONTENT_WIDTH * 0.30, _CONTENT_WIDTH * 0.20])
    totals_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LINEABOVE", (0, -1), (1, -1), 0.8, _DARK),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    totals_wrapper = Table([[totals_table]], colWidths=[_CONTENT_WIDTH * 0.5])
    totals_wrapper.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    flowables.append(totals_wrapper)

    paid_rows = [
        ["Paid", Paragraph(render["total_paid"], _STYLES["total_value"])],
        [Paragraph("Remaining", _STYLES["grand_label"]), Paragraph(render["remaining"], _STYLES["grand_value"])],
        [Paragraph("Payment Status", _STYLES["status"]), Paragraph(render["payment_status_label"], _STYLES["status"])],
    ]
    paid_table = Table(paid_rows, colWidths=[_CONTENT_WIDTH * 0.30, _CONTENT_WIDTH * 0.20])
    paid_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LINEABOVE", (0, 0), (1, 0), 0.5, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    paid_wrapper = Table([[paid_table]], colWidths=[_CONTENT_WIDTH * 0.5])
    paid_wrapper.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    flowables.append(Spacer(1, 4))
    flowables.append(paid_wrapper)
    return flowables


def _payment_info(render: dict[str, Any]) -> list[Any]:
    """Payment method / summary section."""
    payments = render["payments"]
    if not payments:
        return []
    flowables: list[Any] = [_p("Payment Information", "section")]
    if len(payments) == 1:
        payment = payments[0]
        rows = [("Payment Method", payment["method"]), ("Amount", payment["amount"])]
        if payment["reference"]:
            rows.append(("Reference No.", payment["reference"]))
        flowables.append(_label_value_rows(rows))
    else:
        flowables.append(_p("Payment Summary", "label"))
        for payment in payments:
            line = f"{payment['date']} — {payment['method']} — {payment['amount']}"
            if payment["reference"]:
                line += f" — Ref: {payment['reference']}"
            flowables.append(_p(line, "value"))
    flowables.append(Spacer(1, 6))
    return flowables


def _guest_stay_table(render: dict[str, Any]) -> Table:
    guest_rows = [
        ("Guest", render["guest_name"]),
        ("Mobile", render["guest_mobile"]),
        ("Address", render["guest_address"]),
    ]
    stay_rows = [
        ("Room", render["room_number"]),
        ("Room Type", render["room_type"]),
        ("Booking Source", render["booking_source"]),
        ("Check-in", render["check_in"]),
        ("Check-out", render["check_out"]),
        ("Nights", str(render["nights"])),
    ]
    left = _label_value_rows(guest_rows)
    right = _label_value_rows(stay_rows)
    table = Table(
        [[left, right]],
        colWidths=[_CONTENT_WIDTH * 0.5, _CONTENT_WIDTH * 0.5],
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def generate_invoice_pdf(render: dict[str, Any], output_path: str | Path) -> Path:
    """Render the render model to a PDF at ``output_path`` and return it."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN,
        title=f"Invoice {render['invoice_number']}",
        author=render["hotel_name"],
        subject=f"Stay Invoice {render['invoice_number']}",
    )

    story: list[Any] = []

    header_flowables, _logo_height = _header_logo(render)
    story.extend(header_flowables)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1, color=_LINE))
    story.append(Spacer(1, 10))

    title_row = Table(
        [
            [
                Paragraph("INVOICE", _STYLES["invoice_title"]),
                Table(
                    [
                        [Paragraph("Invoice No:", _STYLES["label"]),
                         Paragraph(render["invoice_number"], _STYLES["value_bold"])],
                        [Paragraph("Invoice Date:", _STYLES["label"]),
                         Paragraph(render["invoice_date"], _STYLES["value"])],
                    ],
                    colWidths=[_CONTENT_WIDTH * 0.18, _CONTENT_WIDTH * 0.30],
                ),
            ]
        ],
        colWidths=[_CONTENT_WIDTH * 0.52, _CONTENT_WIDTH * 0.48],
    )
    title_row.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(title_row)
    story.append(Spacer(1, 10))

    story.append(_p("Billing Details", "section"))
    story.append(_guest_stay_table(render))
    story.append(Spacer(1, 8))

    story.append(_p("Charges", "section"))
    story.append(_charges_table(render))
    story.append(Spacer(1, 10))

    story.extend(_totals_blocks(render))
    story.extend(_payment_info(render))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.8, color=_LINE))
    story.append(Spacer(1, 6))

    story.append(Paragraph(_escape(render["footer_message"]), _STYLES["footer"]))
    if render["terms"]:
        story.append(Paragraph(_escape(render["terms"]), _STYLES["label"]))

    story.append(Spacer(1, 40))
    sig_table = Table(
        [
            [
                Paragraph("Guest Signature: ____________________", _STYLES["sig"]),
                Paragraph("Receptionist: ______________________", _STYLES["sig"]),
            ]
        ],
        colWidths=[_CONTENT_WIDTH * 0.5, _CONTENT_WIDTH * 0.5],
    )
    sig_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(sig_table)

    doc.build(story)
    logger.info("Invoice PDF written: %s", output_path)
    return output_path
