"""Invoice service.

Produces and manages invoice documents from bookings.

An invoice freezes the information it was created with into a JSON
snapshot (``snapshot_json``). Once an invoice is ``FINALIZED`` it is
immutable: reprints and PDF regeneration read only the snapshot, so later
edits to the guest record or the booking never silently change an issued
invoice. GST is disabled for this property, so no GST figures are ever
printed or stored as payable amounts.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time as dtime
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import (
    KEY_GST_ENABLED,
    KEY_HOTEL_ADDRESS,
    KEY_HOTEL_DESCRIPTION,
    KEY_HOTEL_EMAIL,
    KEY_HOTEL_NAME,
    KEY_HOTEL_PHONE,
    KEY_HOTEL_WEBSITE,
    KEY_INVOICE_FOOTER,
    KEY_INVOICE_PREFIX,
    KEY_INVOICE_TERMS,
    KEY_LOGO_PATH,
)
from app.core.constants import (
    APP_NAME,
    BookingStatus,
    ChargeType,
    INVOICE_PREFIX,
    InvoiceStatus,
    PaymentRecordStatus,
    PaymentStatus,
)
from app.database.models import Booking, Invoice
from app.services import financial_service, settings_service
from app.services.invoice_pdf import generate_invoice_pdf
from app.services.money import to_decimal
from app.ui.formatters import format_date, format_date_time, format_money

logger = logging.getLogger(__name__)

SNAPSHOT_VERSION = 1

# Manual charge types that the financial summary actually counts. Manual
# rows of any other type are not part of the financial totals and are
# therefore excluded from the printed line items so the invoice always
# reconciles with the booking's financial summary.
_COUNTED_MANUAL_TYPES = (
    ChargeType.ROOM,
    ChargeType.EXTRA_MATTRESS,
    ChargeType.MISCELLANEOUS,
    ChargeType.OTHER,
)


class InvoiceError(Exception):
    """Base exception for invoice domain errors."""


class InvoiceStateError(InvoiceError):
    """Raised when an action is not valid for the booking/invoice state."""


class DuplicateFinalizedInvoiceError(InvoiceError):
    """Raised when a finalized invoice already exists for a booking.

    ``invoice`` carries the existing finalized invoice.
    """

    def __init__(self, message: str, *, invoice: Invoice) -> None:
        super().__init__(message)
        self.invoice = invoice


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_invoice_or_raise(session: Session, invoice_id: int) -> Invoice:
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise InvoiceError(f"Invoice {invoice_id!r} not found")
    return invoice


def _get_booking_or_raise(session: Session, booking_id: int) -> Booking:
    booking = session.get(Booking, booking_id)
    if booking is None:
        raise InvoiceError(f"Booking {booking_id!r} not found")
    return booking


def _validate_invoiceable_status(booking: Booking) -> None:
    if booking.status in (BookingStatus.CANCELLED.value, BookingStatus.NO_SHOW.value):
        raise InvoiceStateError(
            "An invoice cannot be generated for a cancelled or no-show booking."
        )
    if booking.status != BookingStatus.CHECKED_OUT.value:
        raise InvoiceStateError(
            "An invoice can be generated only after the booking is checked out."
        )


def _snap_decimal(snapshot: dict, key: str) -> Any:
    return to_decimal(snapshot.get(key, 0))


def _iso(day: date | None) -> str:
    return day.isoformat() if day else ""


def _time_to_str(value: dtime | None) -> str:
    return value.strftime("%H:%M") if value else ""


def _guest_address(guest) -> str:  # noqa: ANN001
    address = str(guest.address or "").strip()
    if address:
        return address
    parts = [guest.city, guest.state, guest.country]
    cleaned = [str(part).strip() for part in parts if part and str(part).strip()]
    return ", ".join(cleaned)


def _wrap_address(address: str, max_len: int = 42) -> list[str]:
    """Wrap a comma-separated address into readable lines."""
    parts = [part.strip() for part in (address or "").split(",") if part and part.strip()]
    lines: list[str] = []
    current = ""
    for part in parts:
        candidate = f"{current}, {part}" if current else part
        if current and len(candidate) > max_len:
            lines.append(current)
            current = part
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _format_stay_date_time(iso_date: str, iso_time: str) -> str:
    if not iso_date:
        return "—"
    try:
        day = date.fromisoformat(iso_date)
    except ValueError:
        return iso_date
    time_value: dtime | None = None
    if iso_time:
        try:
            time_value = dtime.fromisoformat(iso_time)
        except ValueError:
            time_value = None
    return format_date_time(day, time_value)


# ---------------------------------------------------------------------------
# Invoice number
# ---------------------------------------------------------------------------

def generate_invoice_number(session: Session, year: int | None = None) -> str:
    """Generate the next unique invoice number: NCS-INV-2026-000001.

    The sequence is derived from the highest existing number in the
    database, so it is unique, sequential, survives restarts and is never
    reused. The year segment is included in the number.
    """
    year = year or datetime.now().year
    prefix = (
        settings_service.get_setting(session, KEY_INVOICE_PREFIX, default=INVOICE_PREFIX)
        or INVOICE_PREFIX
    ).strip() or INVOICE_PREFIX
    full_prefix = f"{prefix}-INV-{year}-"
    rows = (
        session.query(Invoice.invoice_number)
        .filter(Invoice.invoice_number.like(f"{full_prefix}%"))
        .all()
    )
    max_sequence = 0
    for (invoice_number,) in rows:
        try:
            max_sequence = max(max_sequence, int(invoice_number.rsplit("-", 1)[1]))
        except (ValueError, IndexError):
            continue
    return f"{full_prefix}{max_sequence + 1:06d}"


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def _counted_manual_items(session: Session, booking: Booking) -> list[dict[str, Any]]:
    from app.database.models import BookingCharge

    rows = (
        session.query(BookingCharge)
        .filter(BookingCharge.booking_id == booking.id)
        .order_by(BookingCharge.id)
        .all()
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        try:
            charge_type = ChargeType(row.charge_type)
        except ValueError:
            continue
        if charge_type not in _COUNTED_MANUAL_TYPES:
            continue
        amount = to_decimal(row.total_amount)
        if amount <= 0:
            continue
        items.append(
            {
                "description": row.description,
                "quantity": row.quantity,
                "unit_amount": str(to_decimal(row.unit_amount)),
                "amount": str(amount),
                "charge_type": row.charge_type,
            }
        )
    return items


def build_snapshot(session: Session, booking_id: int) -> dict[str, Any]:
    """Capture everything printed on an invoice for a booking.

    The snapshot is a plain JSON-serializable dict; all money values are
    stored as decimal strings so they round-trip exactly.
    """
    booking = _get_booking_or_raise(session, booking_id)
    guest = booking.guest
    room = booking.room
    source = booking.source
    summary = financial_service.get_financial_summary(session, booking_id)
    settings = settings_service.get_settings(session)
    payments = financial_service.get_payment_history(session, booking_id)

    completed = [p for p in payments if p.status == PaymentRecordStatus.COMPLETED.value]

    gst_enabled = settings_service.get_bool_setting(session, KEY_GST_ENABLED, default=False)

    line_items = []
    derived_room = financial_service.calculate_room_charge(booking)
    nights = summary.nights
    if derived_room > 0:
        line_items.append(
            {
                "description": f"Room Stay - {room.room_type} Room" if room else "Room Stay",
                "quantity": nights,
                "unit_amount": str(to_decimal(booking.room_rate)),
                "amount": str(derived_room),
                "charge_type": ChargeType.ROOM.value,
            }
        )
    for description, value, charge_type in (
        ("Extra Person", booking.extra_person_charge, ChargeType.EXTRA_PERSON.value),
        ("Early Check-in", booking.early_check_in_charge, ChargeType.EARLY_CHECK_IN.value),
        ("Late Check-out", booking.late_check_out_charge, ChargeType.LATE_CHECK_OUT.value),
    ):
        amount = to_decimal(value)
        if amount > 0:
            line_items.append(
                {
                    "description": description,
                    "quantity": 1,
                    "unit_amount": str(amount),
                    "amount": str(amount),
                    "charge_type": charge_type,
                }
            )
    line_items.extend(_counted_manual_items(session, booking))

    return {
        "version": SNAPSHOT_VERSION,
        "hotel": {
            "name": (settings.get(KEY_HOTEL_NAME, "") or APP_NAME).strip() or APP_NAME,
            "description": (settings.get(KEY_HOTEL_DESCRIPTION, "") or "").strip(),
            "address": (settings.get(KEY_HOTEL_ADDRESS, "") or "").strip(),
            "phone": (settings.get(KEY_HOTEL_PHONE, "") or "").strip(),
            "email": (settings.get(KEY_HOTEL_EMAIL, "") or "").strip(),
            "website": (settings.get(KEY_HOTEL_WEBSITE, "") or "").strip(),
            "logo_path": (settings.get(KEY_LOGO_PATH, "") or "").strip(),
        },
        "guest": {
            "name": guest.guest_name if guest else "",
            "mobile": guest.mobile_number if guest else "",
            "address": _guest_address(guest) if guest else "",
        },
        "room": {
            "number": room.room_number if room else "",
            "type": room.room_type if room else "",
        },
        "stay": {
            "check_in_date": _iso(booking.check_in_date),
            "check_in_time": _time_to_str(booking.check_in_time),
            "check_out_date": _iso(booking.check_out_date),
            "check_out_time": _time_to_str(booking.check_out_time),
            "nights": summary.nights,
            "source": source.name if source else "",
            "adults": booking.adults,
            "children": booking.children,
        },
        "line_items": line_items,
        "subtotal": str(summary.subtotal),
        "discount": str(summary.discount),
        "gst": str(summary.gst),
        "gst_enabled": gst_enabled,
        "grand_total": str(summary.grand_total),
        "total_paid": str(summary.total_paid),
        "remaining": str(summary.remaining),
        "payment_status": summary.payment_status.value,
        "payments": [
            {
                "date": _iso(p.payment_date),
                "method": p.payment_method,
                "amount": str(to_decimal(p.amount)),
                "reference": (p.reference_number or "").strip(),
            }
            for p in completed
        ],
        "footer_message": (
            (settings.get(KEY_INVOICE_FOOTER, "") or "").strip()
            or "Thank you for staying with us!"
        ),
        "terms": (settings.get(KEY_INVOICE_TERMS, "") or "").strip(),
    }


def parse_snapshot(snapshot_json: str | None) -> dict[str, Any]:
    if not snapshot_json:
        return {}
    try:
        data = json.loads(snapshot_json)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _apply_snapshot_financials(invoice: Invoice, snapshot: dict[str, Any]) -> None:
    invoice.subtotal = _snap_decimal(snapshot, "subtotal")
    invoice.discount = _snap_decimal(snapshot, "discount")
    invoice.grand_total = _snap_decimal(snapshot, "grand_total")
    invoice.total_paid = _snap_decimal(snapshot, "total_paid")
    invoice.remaining_amount = _snap_decimal(snapshot, "remaining")
    invoice.payment_status = snapshot.get("payment_status", PaymentStatus.UNPAID.value)


# ---------------------------------------------------------------------------
# Shared render model (used by both the Qt preview and the PDF)
# ---------------------------------------------------------------------------

def _payment_method_label(method: str) -> str:
    from app.core.constants import PaymentMethod

    try:
        return PaymentMethod(method).label
    except ValueError:
        return method or ""


def build_render_model(invoice: Invoice) -> dict[str, Any]:
    """Build the fully formatted display data shared by preview and PDF."""
    snap = parse_snapshot(invoice.snapshot_json)
    hotel = snap.get("hotel", {})
    guest = snap.get("guest", {})
    room = snap.get("room", {})
    stay = snap.get("stay", {})
    try:
        payment_status = PaymentStatus(snap.get("payment_status", PaymentStatus.UNPAID.value))
    except ValueError:
        payment_status = PaymentStatus.UNPAID
    try:
        invoice_status = InvoiceStatus(invoice.status)
    except ValueError:
        invoice_status = InvoiceStatus.DRAFT

    discount = _snap_decimal(snap, "discount")

    return {
        "invoice_number": invoice.invoice_number,
        "invoice_date": format_date(invoice.invoice_date),
        "invoice_status": invoice_status.value,
        "invoice_status_label": invoice_status.label,
        "payment_status": payment_status.value,
        "payment_status_label": payment_status.label,
        "hotel_name": (hotel.get("name") or APP_NAME).strip() or APP_NAME,
        "hotel_description": (hotel.get("description") or "").strip(),
        "hotel_address_lines": _wrap_address(hotel.get("address", "")),
        "hotel_phone": (hotel.get("phone") or "").strip() or None,
        "hotel_email": (hotel.get("email") or "").strip() or None,
        "hotel_website": (hotel.get("website") or "").strip() or None,
        "logo_path": (hotel.get("logo_path") or "").strip() or None,
        "guest_name": (guest.get("name") or "").strip(),
        "guest_mobile": (guest.get("mobile") or "").strip(),
        "guest_address": (guest.get("address") or "").strip(),
        "room_number": (room.get("number") or "").strip(),
        "room_type": (room.get("type") or "").strip(),
        "booking_source": (stay.get("source") or "").strip(),
        "check_in": _format_stay_date_time(stay.get("check_in_date", ""), stay.get("check_in_time", "")),
        "check_out": _format_stay_date_time(stay.get("check_out_date", ""), stay.get("check_out_time", "")),
        "nights": int(stay.get("nights", 0) or 0),
        "line_items": [
            {
                "description": item.get("description", ""),
                "quantity": str(item.get("quantity", 1)),
                "unit_amount": format_money(item.get("unit_amount", 0)),
                "amount": format_money(item.get("amount", 0)),
                "charge_type": item.get("charge_type", ""),
            }
            for item in snap.get("line_items", [])
        ],
        "subtotal": format_money(snap.get("subtotal", 0)),
        "discount": format_money(discount) if discount > 0 else None,
        "grand_total": format_money(snap.get("grand_total", 0)),
        "total_paid": format_money(snap.get("total_paid", 0)),
        "remaining": format_money(snap.get("remaining", 0)),
        "payments": [
            {
                "date": _format_payment_date(item.get("date", "")),
                "method": _payment_method_label(item.get("method", "")),
                "amount": format_money(item.get("amount", 0)),
                "reference": (item.get("reference") or "").strip(),
            }
            for item in snap.get("payments", [])
        ],
        "footer_message": (snap.get("footer_message") or "Thank you for staying with us!"),
        "terms": (snap.get("terms") or "").strip(),
        "gst": None,  # GST is disabled — never shown.
    }


def _format_payment_date(iso_date: str) -> str:
    if not iso_date:
        return "—"
    try:
        return format_date(date.fromisoformat(iso_date))
    except ValueError:
        return iso_date


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------

def get_finalized_invoice_for_booking(session: Session, booking_id: int) -> Invoice | None:
    for invoice in get_invoices_for_booking(session, booking_id):
        if invoice.status == InvoiceStatus.FINALIZED.value:
            return invoice
    return None


def get_invoices_for_booking(session: Session, booking_id: int) -> list[Invoice]:
    return (
        session.query(Invoice)
        .filter(Invoice.booking_id == booking_id)
        .order_by(Invoice.id)
        .all()
    )


def get_or_create_draft_invoice(session: Session, booking_id: int) -> Invoice:
    """Return the booking's draft invoice or create a fresh one.

    Raises :class:`DuplicateFinalizedInvoiceError` when a finalized
    invoice already exists — no second finalized invoice may be created.
    """
    booking = _get_booking_or_raise(session, booking_id)
    _validate_invoiceable_status(booking)
    finalized = get_finalized_invoice_for_booking(session, booking_id)
    if finalized is not None:
        session.expunge(finalized)
        raise DuplicateFinalizedInvoiceError(
            "Invoice already exists for this booking.",
            invoice=finalized,
        )
    for invoice in get_invoices_for_booking(session, booking_id):
        if invoice.status == InvoiceStatus.DRAFT.value:
            return invoice
    return create_draft_invoice(session, booking_id)


def ensure_invoice_for_checkout(session: Session, booking_id: int) -> Invoice | None:
    """Create a draft invoice at check-out time, or return the existing one.

    No-op (returns the existing invoice) when a finalized invoice already
    exists — a second invoice is never created. This lets a freshly
    checked-out booking show up in the Invoices page right away.
    """
    try:
        return get_or_create_draft_invoice(session, booking_id)
    except DuplicateFinalizedInvoiceError as exc:
        return exc.invoice


def create_draft_invoice(session: Session, booking_id: int) -> Invoice:
    """Create a DRAFT invoice from the booking's current financial data."""
    booking = _get_booking_or_raise(session, booking_id)
    _validate_invoiceable_status(booking)
    finalized = get_finalized_invoice_for_booking(session, booking_id)
    if finalized is not None:
        session.expunge(finalized)
        raise DuplicateFinalizedInvoiceError(
            "Invoice already exists for this booking.",
            invoice=finalized,
        )

    snapshot = build_snapshot(session, booking_id)
    for _attempt in range(5):
        invoice = Invoice(
            invoice_number=generate_invoice_number(session),
            booking_id=booking.id,
            invoice_date=date.today(),
            status=InvoiceStatus.DRAFT.value,
            snapshot_json=json.dumps(snapshot, ensure_ascii=False),
        )
        _apply_snapshot_financials(invoice, snapshot)
        session.add(invoice)
        try:
            session.commit()
            session.refresh(invoice)
            logger.info(
                "Draft invoice %s created for booking %s",
                invoice.invoice_number,
                booking.booking_number,
            )
            return invoice
        except IntegrityError:
            session.rollback()
            continue
    raise InvoiceError("Could not allocate a unique invoice number.")


def refresh_draft_snapshot(session: Session, invoice_id: int) -> Invoice:
    """Re-sync a DRAFT invoice with the booking's latest financial data."""
    invoice = _get_invoice_or_raise(session, invoice_id)
    if invoice.status != InvoiceStatus.DRAFT.value:
        raise InvoiceStateError("Only a draft invoice can be refreshed.")
    snapshot = build_snapshot(session, invoice.booking_id)
    invoice.snapshot_json = json.dumps(snapshot, ensure_ascii=False)
    _apply_snapshot_financials(invoice, snapshot)
    session.commit()
    session.refresh(invoice)
    return invoice


# ---------------------------------------------------------------------------
# Finalization / cancellation
# ---------------------------------------------------------------------------

def finalize_invoice(session: Session, invoice_id: int, invoice_dir: str | Path) -> Invoice:
    """Finalize a draft invoice and generate its PDF.

    The snapshot is rebuilt at finalization so the authoritative document
    reflects the booking at the moment it is issued. Afterwards the
    snapshot is frozen.
    """
    invoice = _get_invoice_or_raise(session, invoice_id)
    if invoice.status != InvoiceStatus.DRAFT.value:
        raise InvoiceStateError("Only a draft invoice can be finalized.")

    snapshot = build_snapshot(session, invoice.booking_id)
    invoice.snapshot_json = json.dumps(snapshot, ensure_ascii=False)
    _apply_snapshot_financials(invoice, snapshot)
    invoice.status = InvoiceStatus.FINALIZED.value
    session.commit()
    session.refresh(invoice)

    pdf_path = generate_pdf(invoice, invoice_dir)
    invoice.pdf_path = str(pdf_path)
    session.commit()
    session.refresh(invoice)
    logger.info(
        "Invoice %s finalized (₹%s) — PDF at %s",
        invoice.invoice_number,
        invoice.grand_total,
        pdf_path,
    )
    return invoice


def cancel_invoice(session: Session, invoice_id: int, reason: str = "") -> Invoice:
    """Cancel a draft invoice. Finalized invoices are never cancelled."""
    invoice = _get_invoice_or_raise(session, invoice_id)
    if invoice.status == InvoiceStatus.FINALIZED.value:
        raise InvoiceStateError(
            "A finalized invoice cannot be cancelled. Corrections require a reissue."
        )
    if invoice.status == InvoiceStatus.CANCELLED.value:
        raise InvoiceStateError("This invoice is already cancelled.")
    invoice.status = InvoiceStatus.CANCELLED.value
    invoice.cancelled_at = datetime.now()
    invoice.cancellation_reason = (reason or "").strip()
    session.commit()
    session.refresh(invoice)
    logger.info("Invoice %s cancelled", invoice.invoice_number)
    return invoice


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def pdf_filename(invoice_number: str) -> str:
    return f"{invoice_number}.pdf"


def generate_pdf(invoice: Invoice, invoice_dir: str | Path) -> Path:
    """Write the invoice PDF and return its path (safe to replace)."""
    invoice_dir = Path(invoice_dir)
    invoice_dir.mkdir(parents=True, exist_ok=True)
    output = invoice_dir / pdf_filename(invoice.invoice_number)
    render = build_render_model(invoice)
    generate_invoice_pdf(render, output)
    return output


def regenerate_pdf(session: Session, invoice_id: int, invoice_dir: str | Path) -> Path:
    """Rebuild the PDF from the stored snapshot (works for any invoice)."""
    invoice = _get_invoice_or_raise(session, invoice_id)
    pdf_path = generate_pdf(invoice, invoice_dir)
    invoice.pdf_path = str(pdf_path)
    session.commit()
    session.refresh(invoice)
    logger.info("PDF regenerated for invoice %s", invoice.invoice_number)
    return pdf_path


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def get_invoice(session: Session, invoice_id: int) -> Invoice | None:
    return session.get(Invoice, invoice_id)


def get_invoice_by_number(session: Session, invoice_number: str) -> Invoice | None:
    return (
        session.query(Invoice)
        .filter(Invoice.invoice_number == (invoice_number or "").strip())
        .first()
    )


def filter_invoices(
    session: Session,
    *,
    query: str = "",
    payment_status: str | PaymentStatus | None = None,
    invoice_status: str | InvoiceStatus | None = None,
    period: str = "all",
    today: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 500,
) -> list[Invoice]:
    """Filter invoice history by search text, statuses and date window."""
    from app.database.models import Guest, Room

    query_builder = (
        session.query(Invoice)
        .options(
            joinedload(Invoice.booking).joinedload(Booking.guest),
            joinedload(Invoice.booking).joinedload(Booking.room),
        )
        .join(Booking, Invoice.booking_id == Booking.id)
        .outerjoin(Guest, Booking.guest_id == Guest.id)
        .outerjoin(Room, Booking.room_id == Room.id)
    )

    query_builder = query_builder.filter(Booking.status != BookingStatus.DELETED.value)

    if payment_status is not None:
        normalized = (
            payment_status
            if isinstance(payment_status, PaymentStatus)
            else PaymentStatus(str(payment_status).strip().lower())
        )
        query_builder = query_builder.filter(Invoice.payment_status == normalized.value)
    if invoice_status is not None:
        normalized_status = (
            invoice_status
            if isinstance(invoice_status, InvoiceStatus)
            else InvoiceStatus(str(invoice_status).strip().lower())
        )
        query_builder = query_builder.filter(Invoice.status == normalized_status.value)

    today = today or date.today()
    if period == "today":
        query_builder = query_builder.filter(Invoice.invoice_date == today)
    elif period == "week":
        week_start = today - __import__("datetime").timedelta(days=today.weekday())
        query_builder = query_builder.filter(Invoice.invoice_date >= week_start)
    elif period == "month":
        query_builder = query_builder.filter(Invoice.invoice_date >= today.replace(day=1))
    elif period == "custom":
        if date_from is not None:
            query_builder = query_builder.filter(Invoice.invoice_date >= date_from)
        if date_to is not None:
            query_builder = query_builder.filter(Invoice.invoice_date <= date_to)

    text = (query or "").strip()
    if text:
        pattern = f"%{text.lower()}%"
        query_builder = query_builder.filter(
            or_(
                func.lower(Invoice.invoice_number).like(pattern),
                func.lower(Guest.guest_name).like(pattern),
                func.lower(Guest.mobile_number).like(pattern),
                func.lower(Room.room_number).like(pattern),
            )
        )

    return (
        query_builder.order_by(Invoice.invoice_date.desc(), Invoice.id.desc())
        .limit(limit)
        .all()
    )
