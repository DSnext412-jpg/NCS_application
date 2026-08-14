"""Financial service.

Computes the complete financial picture of a booking: derived base
charges (from booking columns), manual charges (from the charges
table), discount, GST (currently always 0 — GST is disabled), payments
and the remaining balance. Also handles recording/reversing payments,
adding/removing manual charges, and today's collected total.

All money values are ``Decimal``; the UI formats them with Indian
number grouping.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.core.config import KEY_GST_ENABLED
from app.core.constants import (
    BookingStatus,
    ChargeType,
    PaymentMethod,
    PaymentRecordStatus,
    PaymentStatus,
)
from app.database.models import Booking, BookingCharge, Guest, Payment
from app.services import settings_service
from app.services.money import add, to_decimal

logger = logging.getLogger(__name__)

GST_RATE = to_decimal("0.18")

# Manual charge types stored in the charges table (base charges live on
# the booking itself).
MANUAL_CHARGE_TYPES = (
    ChargeType.ROOM,
    ChargeType.EXTRA_MATTRESS,
    ChargeType.MISCELLANEOUS,
    ChargeType.OTHER,
)


class FinancialError(Exception):
    """Base exception for financial domain errors."""


class OverPaymentError(FinancialError):
    """Raised when a payment exceeds the remaining balance."""


class ChargeValidationError(FinancialError):
    """Raised when a manual charge is invalid."""


class PaymentValidationError(FinancialError):
    """Raised when a payment record is invalid."""


def _get_booking_or_raise(session: Session, booking_id: int) -> Booking:
    booking = session.get(Booking, booking_id)
    if booking is None:
        raise FinancialError(f"Booking {booking_id!r} not found")
    return booking


# ---------------------------------------------------------------------------
# Derived charges
# ---------------------------------------------------------------------------

def calculate_nights(check_in_date: date, check_out_date: date) -> int:
    """Number of billable nights.

    A same-day stay returns 0 — reception confirms the stay amount as a
    manual ROOM charge instead.
    """
    return max(0, (check_out_date - check_in_date).days)


def calculate_room_charge(booking: Booking) -> Any:
    """Derived room charge: room_rate × nights."""
    nights = calculate_nights(booking.check_in_date, booking.check_out_date)
    return (to_decimal(booking.room_rate) * nights).quantize(to_decimal("0.01"))


# ---------------------------------------------------------------------------
# Financial summary
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FinancialSummary:
    """Complete financial snapshot of a booking."""

    booking_id: int
    nights: int
    room_charges: Any          # Decimal
    extra_person_charges: Any  # Decimal
    early_check_in_charges: Any
    late_check_out_charges: Any
    mattress_charges: Any
    miscellaneous_charges: Any
    other_charges: Any
    manual_charges: Any        # total of all charges-table rows
    subtotal: Any
    discount: Any
    gst: Any
    grand_total: Any
    total_paid: Any            # sum of completed (non-reversed) payments
    remaining: Any
    payment_status: PaymentStatus


def _manual_charge_total(session: Session, booking_id: int) -> tuple[dict[ChargeType, Any], Any]:
    rows = (
        session.query(BookingCharge)
        .filter(BookingCharge.booking_id == booking_id)
        .all()
    )
    totals: dict[ChargeType, Any] = {}
    grand = to_decimal(0)
    for row in rows:
        try:
            charge_type = ChargeType(row.charge_type)
        except ValueError:
            charge_type = ChargeType.OTHER
        totals[charge_type] = add(totals.get(charge_type, 0), row.total_amount)
        grand = add(grand, row.total_amount)
    return totals, grand


def get_financial_summary(session: Session, booking_id: int) -> FinancialSummary:
    """Compute every financial figure for a booking."""
    booking = _get_booking_or_raise(session, booking_id)

    nights = calculate_nights(booking.check_in_date, booking.check_out_date)

    # Base charges derived from booking columns (authoritative).
    room_charges = calculate_room_charge(booking)
    extra_person = to_decimal(booking.extra_person_charge)
    early = to_decimal(booking.early_check_in_charge)
    late = to_decimal(booking.late_check_out_charge)

    # Manual charges from the charges table.
    manual_by_type, manual_total = _manual_charge_total(session, booking_id)
    # Manual ROOM-type charges are additional to the derived room charge.
    room_charges = add(room_charges, manual_by_type.get(ChargeType.ROOM, 0))
    mattress = manual_by_type.get(ChargeType.EXTRA_MATTRESS, to_decimal(0))
    miscellaneous = manual_by_type.get(ChargeType.MISCELLANEOUS, to_decimal(0))
    other = manual_by_type.get(ChargeType.OTHER, to_decimal(0))

    subtotal = add(room_charges, extra_person, early, late, mattress, miscellaneous, other)
    discount = to_decimal(booking.discount)

    # GST is disabled for this property; kept future-proof with a helper.
    gst_enabled = settings_service.get_bool_setting(session, KEY_GST_ENABLED, default=False)
    gst_base = max(to_decimal(0), subtotal - discount)
    gst = (gst_base * GST_RATE).quantize(to_decimal("0.01")) if gst_enabled else to_decimal(0)

    grand_total = max(to_decimal(0), subtotal - discount + gst)

    total_paid = get_total_paid(session, booking_id)
    remaining = max(to_decimal(0), grand_total - total_paid)
    payment_status = get_payment_status(grand_total, total_paid)

    return FinancialSummary(
        booking_id=booking.id,
        nights=nights,
        room_charges=room_charges,
        extra_person_charges=extra_person,
        early_check_in_charges=early,
        late_check_out_charges=late,
        mattress_charges=mattress,
        miscellaneous_charges=miscellaneous,
        other_charges=other,
        manual_charges=manual_total,
        subtotal=subtotal,
        discount=discount,
        gst=gst,
        grand_total=grand_total,
        total_paid=total_paid,
        remaining=remaining,
        payment_status=payment_status,
    )


def get_payment_status(grand_total: Any, total_paid: Any) -> PaymentStatus:
    """Booking-level payment status derived from totals."""
    grand_total = to_decimal(grand_total)
    total_paid = to_decimal(total_paid)
    if grand_total <= 0:
        return PaymentStatus.PAID
    if total_paid <= 0:
        return PaymentStatus.UNPAID
    if total_paid >= grand_total:
        return PaymentStatus.PAID
    return PaymentStatus.PARTIAL


def get_total_paid(session: Session, booking_id: int) -> Any:
    """Sum of completed payments for a booking."""
    rows = (
        session.query(Payment)
        .filter(
            Payment.booking_id == booking_id,
            Payment.status == PaymentRecordStatus.COMPLETED.value,
        )
        .all()
    )
    total = to_decimal(0)
    for row in rows:
        total = add(total, row.amount)
    return total


# ---------------------------------------------------------------------------
# Manual charges
# ---------------------------------------------------------------------------

def _normalize_charge_type(value: str | ChargeType) -> ChargeType:
    if isinstance(value, ChargeType):
        return value
    try:
        return ChargeType(str(value).strip().upper())
    except ValueError as exc:
        raise ChargeValidationError(f"Invalid charge type: {value!r}") from exc


def add_charge(
    session: Session,
    *,
    booking_id: int,
    description: str,
    charge_type: str | ChargeType,
    quantity: Any = 1,
    unit_amount: Any = 0,
) -> BookingCharge:
    """Add a manual charge to a booking (extra mattress/misc/other/room)."""
    booking = _get_booking_or_raise(session, booking_id)
    charge_type = _normalize_charge_type(charge_type)

    description_text = (description or "").strip()
    if not description_text:
        raise ChargeValidationError("A charge description is required.")

    quantity_int = int(quantity or 0)
    if quantity_int <= 0:
        raise ChargeValidationError("Quantity must be at least 1.")
    amount = to_decimal(unit_amount)
    if amount < 0:
        raise ChargeValidationError("Charge amount cannot be negative.")

    total = (amount * quantity_int).quantize(to_decimal("0.01"))
    row = BookingCharge(
        booking_id=booking.id,
        description=description_text,
        charge_type=charge_type.value,
        quantity=quantity_int,
        unit_amount=amount,
        total_amount=total,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    logger.info("Charge %s (₹%s) added to booking %s", charge_type.value, total, booking.booking_number)
    return row


def remove_charge(session: Session, charge_id: int) -> None:
    """Remove a manual charge from the charges table."""
    row = session.get(BookingCharge, charge_id)
    if row is None:
        raise ChargeValidationError(f"Charge {charge_id!r} not found")
    session.delete(row)
    session.commit()
    logger.info("Charge %s removed", charge_id)


def set_discount(session: Session, booking_id: int, discount: Any) -> Booking:
    """Set the booking discount (0 ≤ discount ≤ subtotal)."""
    booking = _get_booking_or_raise(session, booking_id)
    summary = get_financial_summary(session, booking_id)
    amount = to_decimal(discount)
    if amount < 0:
        raise ChargeValidationError("Discount cannot be negative.")
    if amount > summary.subtotal:
        raise ChargeValidationError(
            f"Discount cannot exceed the subtotal (₹{summary.subtotal:,.2f})."
        )
    booking.discount = amount
    session.commit()
    session.refresh(booking)
    logger.info("Discount ₹%s set on booking %s", amount, booking.booking_number)
    return booking


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

def _normalize_method(value: str | PaymentMethod) -> PaymentMethod:
    if isinstance(value, PaymentMethod):
        return value
    try:
        return PaymentMethod(str(value).strip().lower())
    except ValueError as exc:
        raise PaymentValidationError(f"Invalid payment method: {value!r}") from exc


def record_payment(
    session: Session,
    *,
    booking_id: int,
    amount: Any,
    payment_method: str | PaymentMethod,
    payment_date: date | None = None,
    reference_number: str = "",
    notes: str = "",
) -> Payment:
    """Record a payment against a booking.

    Rejects non-positive amounts and overpayment beyond the remaining
    balance.
    """
    booking = _get_booking_or_raise(session, booking_id)
    amount = to_decimal(amount)
    if amount <= 0:
        raise PaymentValidationError("Payment amount must be greater than zero.")

    method = _normalize_method(payment_method)

    summary = get_financial_summary(session, booking_id)
    if amount > summary.remaining:
        raise OverPaymentError(
            f"Payment of ₹{amount:,.2f} exceeds the remaining balance of ₹{summary.remaining:,.2f}."
        )

    row = Payment(
        booking_id=booking.id,
        amount=amount,
        payment_method=method.value,
        payment_date=payment_date or date.today(),
        reference_number=(reference_number or "").strip(),
        notes=(notes or "").strip(),
        status=PaymentRecordStatus.COMPLETED.value,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    logger.info(
        "Payment ₹%s (%s) recorded on booking %s",
        amount,
        method.value,
        booking.booking_number,
    )
    return row


def reverse_payment(session: Session, payment_id: int, reason: str) -> Payment:
    """Reverse a completed payment (refund foundation).

    The record is kept with ``status`` set to ``refunded`` (or
    ``reversed`` when it was reversed rather than refunded) — it is never
    deleted.
    """
    payment = session.get(Payment, payment_id)
    if payment is None:
        raise PaymentValidationError(f"Payment {payment_id!r} not found")
    if payment.status != PaymentRecordStatus.COMPLETED.value:
        raise PaymentValidationError("Only a completed payment can be reversed.")

    reason_text = (reason or "").strip()
    if not reason_text:
        raise PaymentValidationError("A reversal reason is required.")

    from datetime import datetime

    payment.status = PaymentRecordStatus.REFUNDED.value
    payment.reversed_at = datetime.now()
    payment.reversal_reason = reason_text
    session.commit()
    session.refresh(payment)
    logger.info("Payment %s reversed (%s)", payment.id, reason_text)
    return payment


def get_payment_history(session: Session, booking_id: int) -> list[Payment]:
    """All payments for a booking, oldest first."""
    return (
        session.query(Payment)
        .filter(Payment.booking_id == booking_id)
        .order_by(Payment.payment_date, Payment.id)
        .all()
    )


def get_today_payment_total(session: Session, today: date | None = None) -> Any:
    """Total amount of completed payments recorded on a given day."""
    today = today or date.today()
    rows = (
        session.query(Payment)
        .join(Booking, Payment.booking_id == Booking.id)
        .filter(
            Payment.payment_date == today,
            Payment.status == PaymentRecordStatus.COMPLETED.value,
            Booking.status != BookingStatus.DELETED.value,
        )
        .all()
    )
    total = to_decimal(0)
    for row in rows:
        total = add(total, row.amount)
    return total


def list_payments(
    session: Session,
    *,
    query: str = "",
    status: str | PaymentRecordStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 500,
) -> list[Payment]:
    """Filterable payment history for the Payments page."""
    query_builder = (
        session.query(Payment)
        .options(
            joinedload(Payment.booking).joinedload(Booking.guest),
            joinedload(Payment.booking).joinedload(Booking.room),
        )
        .join(Booking, Payment.booking_id == Booking.id)
        .join(Guest, Booking.guest_id == Guest.id)
    )
    if status is not None:
        if isinstance(status, PaymentRecordStatus):
            status = status.value
        query_builder = query_builder.filter(Payment.status == status)
    query_builder = query_builder.filter(Booking.status != BookingStatus.DELETED.value)
    if date_from is not None:
        query_builder = query_builder.filter(Payment.payment_date >= date_from)
    if date_to is not None:
        query_builder = query_builder.filter(Payment.payment_date <= date_to)
    text = (query or "").strip()
    if text:
        pattern = f"%{text.lower()}%"
        query_builder = query_builder.filter(
            or_(
                func.lower(Booking.booking_number).like(pattern),
                func.lower(Guest.guest_name).like(pattern),
                func.lower(Guest.mobile_number).like(pattern),
            )
        )
    return (
        query_builder.order_by(Payment.payment_date.desc(), Payment.id.desc())
        .limit(limit)
        .all()
    )


def get_payment_period_total(
    session: Session,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Any:
    """Total completed payments within a date range (inclusive)."""
    query = (
        session.query(Payment)
        .join(Booking, Payment.booking_id == Booking.id)
        .filter(
            Payment.status == PaymentRecordStatus.COMPLETED.value,
            Booking.status != BookingStatus.DELETED.value,
        )
    )
    if date_from is not None:
        query = query.filter(Payment.payment_date >= date_from)
    if date_to is not None:
        query = query.filter(Payment.payment_date <= date_to)
    total = to_decimal(0)
    for row in query.all():
        total = add(total, row.amount)
    return total
