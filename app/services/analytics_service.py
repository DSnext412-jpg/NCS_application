"""Admin analytics service.

Provides the numbers behind the Admin Dashboard and its reports, using a
single, clearly defined set of rules (see Phase 6 spec):

REVENUE      -> sum of *completed* payments whose *payment_date* falls in range.
OUTSTANDING  -> per-booking (grand_total - completed payments), only where > 0.
BOOKING COUNT-> unique bookings.
OCCUPANCY    -> room-night based for historical/date ranges.
CURRENT ROOM STATUS -> actual current room.status values.
BOOKING SOURCE -> booking_source attached to the booking.
PAYMENT METHOD -> the payment's own transaction method.

Money is never double-counted: completed payment amounts are summed once by
their transaction date. Unpaid invoice amounts are never treated as revenue.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.constants import BookingStatus, PaymentRecordStatus
from app.database.models import Booking, BookingSource, Payment, Room
from app.services import financial_service
from app.services.money import to_decimal

_ACTIVE_STATUSES = (
    BookingStatus.RESERVED.value,
    BookingStatus.CHECKED_IN.value,
    BookingStatus.CHECKED_OUT.value,
)

_OCCUPIED_STATUSES = (BookingStatus.CHECKED_IN.value, BookingStatus.CHECKED_OUT.value)

DELETED = BookingStatus.DELETED.value


def _normalize_range(date_from: date, date_to: date) -> tuple[date, date]:
    date_from = date_from or date.today()
    date_to = max(date_to or date.today(), date_from)
    return date_from, date_to

def _day_count(date_from: date, date_to: date) -> int:
    return (date_to - date_from).days + 1


def _overlap_nights(
    booking: Booking, date_from: date, date_to: date
) -> int:
    """Number of nights a booking's stay overlaps [date_from, date_to]."""
    start = max(booking.check_in_date, date_from)
    end = min(booking.check_out_date, date_to)
    return max(0, (end - start).days)


# ---------------------------------------------------------------------------
# Revenue
# ---------------------------------------------------------------------------

def get_revenue(session: Session, date_from: date, date_to: date) -> Any:
    """Collected revenue: completed payments whose payment_date is in range."""
    date_from, date_to = _normalize_range(date_from, date_to)
    rows = (
        session.query(func.coalesce(func.sum(Payment.amount), 0))
        .join(Booking, Payment.booking_id == Booking.id)
        .filter(
            Payment.status == PaymentRecordStatus.COMPLETED.value,
            Booking.status != DELETED,
            Payment.payment_date >= date_from,
            Payment.payment_date <= date_to,
        )
        .one()
    )
    return to_decimal(rows[0])


def get_revenue_by_day(
    session: Session, date_from: date, date_to: date
) -> list[tuple[date, Any]]:
    """Daily revenue (payment date) for every day in range, zero-filled."""
    date_from, date_to = _normalize_range(date_from, date_to)
    rows = (
        session.query(Payment.payment_date, func.sum(Payment.amount))
        .join(Booking, Payment.booking_id == Booking.id)
        .filter(
            Payment.status == PaymentRecordStatus.COMPLETED.value,
            Booking.status != DELETED,
            Payment.payment_date >= date_from,
            Payment.payment_date <= date_to,
        )
        .group_by(Payment.payment_date)
        .all()
    )
    by_day = {day: to_decimal(total) for day, total in rows}
    result: list[tuple[date, Any]] = []
    day = date_from
    while day <= date_to:
        result.append((day, by_day.get(day, to_decimal(0))))
        day += timedelta(days=1)
    return result


def get_revenue_by_method(
    session: Session, date_from: date, date_to: date
) -> dict[str, Any]:
    """Collected revenue grouped by payment method (cash/upi/qr/other)."""
    date_from, date_to = _normalize_range(date_from, date_to)
    rows = (
        session.query(Payment.payment_method, func.sum(Payment.amount))
        .join(Booking, Payment.booking_id == Booking.id)
        .filter(
            Payment.status == PaymentRecordStatus.COMPLETED.value,
            Booking.status != DELETED,
            Payment.payment_date >= date_from,
            Payment.payment_date <= date_to,
        )
        .group_by(Payment.payment_method)
        .all()
    )
    return {method or "other": to_decimal(total) for method, total in rows}


def get_payment_transactions(
    session: Session, date_from: date, date_to: date
) -> list[dict[str, Any]]:
    """Individual completed payment transactions in the range (excl. deleted).

    Returns the payment date, booking number, guest name, payment method and
    amount for every completed payment whose payment date falls in the range.
    """
    date_from, date_to = _normalize_range(date_from, date_to)
    rows = (
        session.query(Payment)
        .join(Booking, Payment.booking_id == Booking.id)
        .filter(
            Payment.status == PaymentRecordStatus.COMPLETED.value,
            Booking.status != DELETED,
            Payment.payment_date >= date_from,
            Payment.payment_date <= date_to,
        )
        .order_by(Payment.payment_date, Payment.id)
        .all()
    )
    return [
        {
            "payment_date": row.payment_date,
            "booking_number": row.booking.booking_number,
            "guest_name": row.booking.guest.guest_name if row.booking.guest else "—",
            "payment_method": row.payment_method or "other",
            "amount": to_decimal(row.amount),
        }
        for row in rows
    ]


def get_period_revenue(session: Session, today: date | None = None) -> dict[str, Any]:
    """Revenue for today / this week / this month / this year (payment date)."""
    today = today or date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)
    return {
        "today": get_revenue(session, today, today),
        "week": get_revenue(session, week_start, today),
        "month": get_revenue(session, month_start, today),
        "year": get_revenue(session, year_start, today),
    }


# ---------------------------------------------------------------------------
# Payment overview
# ---------------------------------------------------------------------------

def _bookings_overlapping(
    session: Session, date_from: date, date_to: date
) -> list[Booking]:
    return (
        session.query(Booking)
        .filter(
            Booking.status.in_(_ACTIVE_STATUSES),
            Booking.check_in_date <= date_to,
            Booking.check_out_date >= date_from,
        )
        .all()
    )


def get_payment_overview(
    session: Session, date_from: date, date_to: date
) -> dict[str, Any]:
    """Collected / outstanding / paid / partial / unpaid for the range.

    Outstanding is the sum of remaining balances (> 0) across bookings whose
    stay overlaps the range. Paid/partial/unpaid are booking counts by their
    current derived payment status.
    """
    date_from, date_to = _normalize_range(date_from, date_to)
    collected = get_revenue(session, date_from, date_to)
    bookings = _bookings_overlapping(session, date_from, date_to)
    outstanding = to_decimal(0)
    paid = partial = unpaid = 0
    for booking in bookings:
        summary = financial_service.get_financial_summary(session, booking.id)
        if summary.remaining > 0:
            outstanding += summary.remaining
        if summary.payment_status.value == "paid":
            paid += 1
        elif summary.payment_status.value == "partial":
            partial += 1
        else:
            unpaid += 1
    return {
        "collected": collected,
        "outstanding": outstanding,
        "paid": paid,
        "partial": partial,
        "unpaid": unpaid,
    }


# ---------------------------------------------------------------------------
# Booking sources
# ---------------------------------------------------------------------------

def get_booking_counts_by_source(
    session: Session, date_from: date, date_to: date
) -> dict[str, int]:
    """Unique booking counts by source (bookings whose check-in is in range)."""
    date_from, date_to = _normalize_range(date_from, date_to)
    rows = (
        session.query(BookingSource.name, func.count(Booking.id))
        .join(Booking, Booking.booking_source_id == BookingSource.id)
        .filter(
            Booking.check_in_date >= date_from,
            Booking.check_in_date <= date_to,
            Booking.status != DELETED,
        )
        .group_by(BookingSource.name)
        .all()
    )
    return {name: int(count) for name, count in rows}


def get_revenue_by_source(
    session: Session, date_from: date, date_to: date
) -> dict[str, Any]:
    """Collected revenue by booking source (payment date in range)."""
    date_from, date_to = _normalize_range(date_from, date_to)
    rows = (
        session.query(BookingSource.name, func.sum(Payment.amount))
        .join(Booking, Booking.booking_source_id == BookingSource.id)
        .join(Payment, Payment.booking_id == Booking.id)
        .filter(
            Payment.status == PaymentRecordStatus.COMPLETED.value,
            Booking.status != DELETED,
            Payment.payment_date >= date_from,
            Payment.payment_date <= date_to,
        )
        .group_by(BookingSource.name)
        .all()
    )
    return {name: to_decimal(total) for name, total in rows}


# ---------------------------------------------------------------------------
# Occupancy
# ---------------------------------------------------------------------------

def _available_rooms(session: Session) -> list[Room]:
    """Active rooms available to be occupied."""
    return list(session.query(Room).filter(Room.is_active.is_(True)))


def get_occupancy(
    session: Session, date_from: date, date_to: date
) -> dict[str, Any]:
    """Room-night based occupancy for the range.

    Available room nights = active rooms x days. Occupied room nights =
    nights actually stayed (checked-in / checked-out bookings overlapping
    the range). Inactive rooms are never counted as available.
    """
    date_from, date_to = _normalize_range(date_from, date_to)
    rooms = _available_rooms(session)
    days = _day_count(date_from, date_to)
    available_nights = len(rooms) * days
    occupied_nights = 0
    for booking in session.query(Booking).filter(Booking.status.in_(_OCCUPIED_STATUSES)):
        occupied_nights += _overlap_nights(booking, date_from, date_to)
    percent = (occupied_nights / available_nights * 100) if available_nights else 0
    return {
        "total_rooms": len(rooms),
        "days": days,
        "available_nights": available_nights,
        "occupied_nights": occupied_nights,
        "occupancy_percent": round(percent, 1),
    }


def get_room_type_report(
    session: Session, date_from: date, date_to: date
) -> list[dict[str, Any]]:
    """AC / Non-AC room-night totals, occupied nights and occupancy %."""
    date_from, date_to = _normalize_range(date_from, date_to)
    days = _day_count(date_from, date_to)
    rooms = _available_rooms(session)
    by_type: dict[str, list[Room]] = {}
    for room in rooms:
        by_type.setdefault(room.room_type or "Other", []).append(room)

    result: list[dict[str, Any]] = []
    for room_type, type_rooms in by_type.items():
        available_nights = len(type_rooms) * days
        occupied_nights = 0
        for booking in session.query(Booking).filter(
            Booking.status.in_(_OCCUPIED_STATUSES),
            Booking.room_id.in_([room.id for room in type_rooms]),
        ):
            occupied_nights += _overlap_nights(booking, date_from, date_to)
        percent = (occupied_nights / available_nights * 100) if available_nights else 0
        result.append(
            {
                "room_type": room_type,
                "rooms": len(type_rooms),
                "total_room_nights": available_nights,
                "occupied_room_nights": occupied_nights,
                "occupancy_percent": round(percent, 1),
            }
        )
    return result


def get_room_performance(
    session: Session, date_from: date, date_to: date
) -> list[dict[str, Any]]:
    """Per-room bookings, collected revenue and occupied nights for a range."""
    date_from, date_to = _normalize_range(date_from, date_to)
    rooms = _available_rooms(session)
    result: list[dict[str, Any]] = []
    for room in rooms:
        bookings = (
            session.query(Booking)
            .filter(
                Booking.room_id == room.id,
                Booking.status.in_(_OCCUPIED_STATUSES),
                Booking.check_in_date <= date_to,
                Booking.check_out_date >= date_from,
            )
            .all()
        )
        occupied_nights = sum(_overlap_nights(b, date_from, date_to) for b in bookings)
        revenue = to_decimal(0)
        if bookings:
            booking_ids = [b.id for b in bookings]
            rows = (
                session.query(func.coalesce(func.sum(Payment.amount), 0))
                .filter(
                    Payment.booking_id.in_(booking_ids),
                    Payment.status == PaymentRecordStatus.COMPLETED.value,
                    Payment.payment_date >= date_from,
                    Payment.payment_date <= date_to,
                )
                .one()
            )
            revenue = to_decimal(rows[0])
        result.append(
            {
                "room_number": room.room_number,
                "room_type": room.room_type,
                "bookings": len(bookings),
                "revenue": revenue,
                "occupied_nights": occupied_nights,
            }
        )
    return result


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------

def get_booking_trend(
    session: Session, date_from: date, date_to: date
) -> list[dict[str, Any]]:
    """Per-day bookings: reservations, check-ins and check-outs (no double count).

    Reservations are bucketed by check-in date (status reserved/new only).
    Check-ins are bucketed by check-in date (status checked-in/checked-out).
    Check-outs are bucketed by check-out date (status checked-out).
    """
    date_from, date_to = _normalize_range(date_from, date_to)
    reserved = {b.check_in_date: 0 for b in session.query(Booking).filter(
        Booking.status.in_((BookingStatus.RESERVED.value, BookingStatus.NEW.value)),
        Booking.check_in_date >= date_from,
        Booking.check_in_date <= date_to,
    )}
    checked_in = {b.check_in_date: 0 for b in session.query(Booking).filter(
        Booking.status.in_((BookingStatus.CHECKED_IN.value, BookingStatus.CHECKED_OUT.value)),
        Booking.check_in_date >= date_from,
        Booking.check_in_date <= date_to,
    )}
    checked_out = {b.check_out_date: 0 for b in session.query(Booking).filter(
        Booking.status == BookingStatus.CHECKED_OUT.value,
        Booking.check_out_date >= date_from,
        Booking.check_out_date <= date_to,
    )}

    counts_reserved: dict[date, int] = {}
    counts_checked_in: dict[date, int] = {}
    counts_checked_out: dict[date, int] = {}
    for day in reserved:
        counts_reserved[day] = counts_reserved.get(day, 0) + 1
    for day in checked_in:
        counts_checked_in[day] = counts_checked_in.get(day, 0) + 1
    for day in checked_out:
        counts_checked_out[day] = counts_checked_out.get(day, 0) + 1

    result: list[dict[str, Any]] = []
    day = date_from
    while day <= date_to:
        result.append(
            {
                "date": day,
                "reservations": counts_reserved.get(day, 0),
                "check_ins": counts_checked_in.get(day, 0),
                "check_outs": counts_checked_out.get(day, 0),
            }
        )
        day += timedelta(days=1)
    return result
