"""Booking service.

All booking business logic lives here: reservations, walk-ins, check-in,
check-out, cancellation, no-show, editing, search/filter and the critical
room-availability logic. UI widgets never touch the database directly.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, time as dtime
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.core.constants import (
    BOOKING_NUMBER_PREFIX,
    OTA_PAID_ONLINE_SOURCES,
    ROOM_BLOCKING_BOOKING_STATUSES,
    BookingStatus,
    PaymentMethod,
)
from app.database.models import Booking, BookingStatusHistory, Guest, Room
from app.services.guest_service import GuestValidationError

logger = logging.getLogger(__name__)

_UNSET = object()


class BookingError(Exception):
    """Base exception for booking domain errors."""


class BookingValidationError(BookingError):
    """Raised when booking data is invalid."""


class RoomNotAvailableError(BookingError):
    """Raised when a room is double-booked for the requested dates."""


class InvalidBookingStateError(BookingError):
    """Raised when an action is not valid for the booking's current status."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _combine(day: date, t: dtime | None) -> datetime:
    return datetime.combine(day, t or dtime(0, 0))


def _money(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _coerce_status(value: str | BookingStatus) -> BookingStatus:
    if isinstance(value, BookingStatus):
        return value
    normalized = str(value).strip().lower()
    for status in BookingStatus:
        if normalized in (status.value, status.name.lower()):
            return status
    raise BookingValidationError(f"Invalid booking status: {value!r}")


def _get_or_raise(session: Session, booking_id: int) -> Booking:
    booking = session.get(Booking, booking_id)
    if booking is None:
        raise BookingError(f"Booking {booking_id!r} not found")
    return booking


def validate_date_range(
    check_in_date: date,
    check_in_time: dtime | None,
    check_out_date: date,
    check_out_time: dtime | None,
) -> tuple[datetime, datetime]:
    """Ensure check-out happens after check-in. Returns combined datetimes."""
    check_in_dt = _combine(check_in_date, check_in_time)
    check_out_dt = _combine(check_out_date, check_out_time)
    if check_out_dt <= check_in_dt:
        raise BookingValidationError("Check-out must be after check-in.")
    return check_in_dt, check_out_dt


def _validate_required(value: Any, label: str) -> None:
    if value is None or str(value).strip() == "":
        raise BookingValidationError(f"{label} is required.")


def _set(booking: Booking, attr: str, value: Any) -> bool:
    """Apply a field only when provided; returns True if changed."""
    if value is _UNSET:
        return False
    current = getattr(booking, attr)
    if current != value:
        setattr(booking, attr, value)
        return True
    return False


def _record_status_change(session: Session, booking: Booking, new_status: str, note: str = "") -> None:
    """Record a booking status transition in the history table."""
    if booking.status == new_status:
        return
    session.add(
        BookingStatusHistory(
            booking_id=booking.id,
            old_status=booking.status,
            new_status=new_status,
            note=(note or "").strip(),
        )
    )


# ---------------------------------------------------------------------------
# Booking number generation
# ---------------------------------------------------------------------------

def generate_booking_number(session: Session, year: int | None = None) -> str:
    """Generate the next unique booking number: NCS-B-<YEAR>-000001.

    Reads the highest existing sequence from the database, so it is safe
    across application restarts and never reuses a number.
    """
    year = year or datetime.now().year
    prefix = f"{BOOKING_NUMBER_PREFIX}-{year}-"
    rows = session.query(Booking.booking_number).filter(Booking.booking_number.like(f"{prefix}%")).all()
    max_sequence = 0
    for (booking_number,) in rows:
        try:
            max_sequence = max(max_sequence, int(booking_number.rsplit("-", 1)[1]))
        except (ValueError, IndexError):
            continue
    return f"{prefix}{max_sequence + 1:06d}"


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def get_room_blocking_bookings(session: Session, room_id: int, exclude_booking_id: int | None = None) -> list[Booking]:
    """Active bookings (RESERVED/CHECKED_IN) for a room that block dates."""
    blocking_values = [status.value for status in ROOM_BLOCKING_BOOKING_STATUSES]
    query = session.query(Booking).filter(
        Booking.room_id == room_id,
        Booking.status.in_(blocking_values),
    )
    if exclude_booking_id is not None:
        query = query.filter(Booking.id != exclude_booking_id)
    return query.all()


def is_room_available(
    session: Session,
    room_id: int,
    check_in_date: date,
    check_in_time: dtime | None,
    check_out_date: date,
    check_out_time: dtime | None,
    exclude_booking_id: int | None = None,
) -> tuple[bool, Booking | None]:
    """Whether the room is free for the requested stay.

    Boundary rule: a booking ending exactly when another begins is NOT an
    overlap (check-out/check-in on the same day is allowed).
    """
    check_in_dt = _combine(check_in_date, check_in_time)
    check_out_dt = _combine(check_out_date, check_out_time)
    for booking in get_room_blocking_bookings(session, room_id, exclude_booking_id):
        booking_in = _combine(booking.check_in_date, booking.check_in_time)
        booking_out = _combine(booking.check_out_date, booking.check_out_time)
        if booking_in < check_out_dt and check_in_dt < booking_out:
            return False, booking
    return True, None


def check_rooms_availability(
    session: Session,
    room_ids: list[int],
    check_in_date: date,
    check_in_time: dtime | None,
    check_out_date: date,
    check_out_time: dtime | None,
    exclude_booking_id: int | None = None,
) -> dict[int, tuple[bool, Booking | None]]:
    """Availability for many rooms in one query (for the room map).

    Returns ``{room_id: (available, conflicting_booking_or_None)}``. Rooms
    with no active booking are always available unless the requested range
    overlaps a reserved/checked-in booking.
    """
    check_in_dt = _combine(check_in_date, check_in_time)
    check_out_dt = _combine(check_out_date, check_out_time)
    blocking_values = [status.value for status in ROOM_BLOCKING_BOOKING_STATUSES]
    query = session.query(Booking).filter(
        Booking.room_id.in_(room_ids),
        Booking.status.in_(blocking_values),
    )
    if exclude_booking_id is not None:
        query = query.filter(Booking.id != exclude_booking_id)
    blockers: dict[int, Booking] = {}
    for booking in query.all():
        booking_in = _combine(booking.check_in_date, booking.check_in_time)
        booking_out = _combine(booking.check_out_date, booking.check_out_time)
        if booking_in < check_out_dt and check_in_dt < booking_out:
            blockers.setdefault(booking.room_id, booking)
    return {
        room_id: (True, None) if room_id not in blockers else (False, blockers[room_id])
        for room_id in room_ids
    }


def _raise_if_unavailable(
    session: Session,
    room: Room,
    check_in_date: date,
    check_in_time: dtime | None,
    check_out_date: date,
    check_out_time: dtime | None,
    exclude_booking_id: int | None = None,
) -> None:
    available, conflicting = is_room_available(
        session,
        room.id,
        check_in_date,
        check_in_time,
        check_out_date,
        check_out_time,
        exclude_booking_id,
    )
    if not available:
        raise RoomNotAvailableError(
            f"Room {room.room_number} is not available for the selected dates."
        )


# ---------------------------------------------------------------------------
# Room status sync
# ---------------------------------------------------------------------------

def _set_room_reserved_if_vacant(
    session: Session,
    room_id: int,
    check_in_date: date | None = None,
) -> None:
    """Reserve the room only if it is physically vacant AND the stay starts
    today (or earlier). Future-dated reservations leave the room available so
    it can still be used before the check-in date."""
    from app.services.room_service import set_room_reserved

    if check_in_date is not None and check_in_date > date.today():
        return
    room = session.get(Room, room_id)
    if room is not None and room.status == "vacant":
        set_room_reserved(session, room.id)


def _release_room_if_free(session: Session, room_id: int) -> None:
    """Vacate a reserved room only when no other active booking needs it."""
    from app.services.room_service import set_room_vacant

    if get_room_blocking_bookings(session, room_id):
        return
    room = session.get(Room, room_id)
    if room is not None and room.status == "reserved":
        set_room_vacant(session, room.id)


def _occupy_room(session: Session, room_id: int) -> None:
    from app.services.room_service import set_room_occupied

    set_room_occupied(session, room_id)


def _release_room(session: Session, room_id: int) -> None:
    """Mark a room as needing cleaning after a guest checks out."""
    from app.services.room_service import set_room_cleaning

    set_room_cleaning(session, room_id, note="Awaiting cleaning")


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------

def _build_booking(
    session: Session,
    *,
    guest_id: int,
    room_id: int,
    booking_source_id: int,
    check_in_date: date,
    check_in_time: dtime | None,
    check_out_date: date,
    check_out_time: dtime | None,
    adults: int,
    children: int,
    room_rate: Any,
    extra_person_charge: Any,
    early_check_in_charge: Any,
    late_check_out_charge: Any,
    special_notes: str,
    status: BookingStatus,
) -> Booking:
    for value, label in ((guest_id, "Guest"), (room_id, "Room"), (booking_source_id, "Booking Source")):
        _validate_required(value, label)
    _validate_required(check_in_date, "Check-in Date")
    _validate_required(check_out_date, "Check-out Date")
    validate_date_range(check_in_date, check_in_time, check_out_date, check_out_time)
    if room_rate is None or str(room_rate).strip() == "":
        raise BookingValidationError("Room Rate is required.")

    guest = session.get(Guest, guest_id)
    if guest is None:
        raise GuestValidationError("Selected guest does not exist.")
    room = session.get(Room, room_id)
    if room is None:
        raise BookingValidationError("Selected room does not exist.")
    _raise_if_unavailable(
        session,
        room,
        check_in_date,
        check_in_time,
        check_out_date,
        check_out_time,
    )

    booking = Booking(
        booking_number=generate_booking_number(session, check_in_date.year),
        guest_id=guest_id,
        room_id=room_id,
        booking_source_id=booking_source_id,
        check_in_date=check_in_date,
        check_in_time=check_in_time,
        check_out_date=check_out_date,
        check_out_time=check_out_time,
        adults=max(0, int(adults or 0)),
        children=max(0, int(children or 0)),
        room_rate=_money(room_rate),
        extra_person_charge=_money(extra_person_charge),
        early_check_in_charge=_money(early_check_in_charge),
        late_check_out_charge=_money(late_check_out_charge),
        special_notes=(special_notes or "").strip(),
        status=status.value,
    )
    session.add(booking)
    session.flush()
    session.add(
        BookingStatusHistory(
            booking_id=booking.id,
            old_status="",
            new_status=status.value,
            note="Booking created",
        )
    )
    session.commit()
    session.refresh(booking)
    logger.info("Booking %s created (status=%s)", booking.booking_number, booking.status)
    return booking


def create_reservation(
    session: Session,
    *,
    guest_id: int,
    room_id: int,
    booking_source_id: int,
    check_in_date: date,
    check_in_time: dtime | None = None,
    check_out_date: date,
    check_out_time: dtime | None = None,
    adults: int = 1,
    children: int = 0,
    room_rate: Any = 0,
    extra_person_charge: Any = 0,
    early_check_in_charge: Any = 0,
    late_check_out_charge: Any = 0,
    special_notes: str = "",
    advance_payment: Any = 0,
    advance_payment_method: str | PaymentMethod = PaymentMethod.CASH,
    paid_online: bool = False,
) -> Booking:
    booking = _build_booking(
        session,
        guest_id=guest_id,
        room_id=room_id,
        booking_source_id=booking_source_id,
        check_in_date=check_in_date,
        check_in_time=check_in_time,
        check_out_date=check_out_date,
        check_out_time=check_out_time,
        adults=adults,
        children=children,
        room_rate=room_rate,
        extra_person_charge=extra_person_charge,
        early_check_in_charge=early_check_in_charge,
        late_check_out_charge=late_check_out_charge,
        special_notes=special_notes,
        status=BookingStatus.RESERVED,
    )
    _set_room_reserved_if_vacant(session, room_id, check_in_date)
    if paid_online:
        _record_ota_online_payment(session, booking, _source_name_for(session, booking_source_id))
    else:
        _record_advance_payment(session, booking, advance_payment, advance_payment_method)
    return booking


def create_walkin(
    session: Session,
    *,
    guest_id: int,
    room_id: int,
    booking_source_id: int,
    check_in_date: date,
    check_in_time: dtime,
    check_out_date: date,
    check_out_time: dtime | None = None,
    adults: int = 1,
    children: int = 0,
    room_rate: Any = 0,
    extra_person_charge: Any = 0,
    early_check_in_charge: Any = 0,
    late_check_out_charge: Any = 0,
    special_notes: str = "",
    advance_payment: Any = 0,
    advance_payment_method: str | PaymentMethod = PaymentMethod.CASH,
    paid_online: bool = False,
) -> Booking:
    booking = _build_booking(
        session,
        guest_id=guest_id,
        room_id=room_id,
        booking_source_id=booking_source_id,
        check_in_date=check_in_date,
        check_in_time=check_in_time,
        check_out_date=check_out_date,
        check_out_time=check_out_time,
        adults=adults,
        children=children,
        room_rate=room_rate,
        extra_person_charge=extra_person_charge,
        early_check_in_charge=early_check_in_charge,
        late_check_out_charge=late_check_out_charge,
        special_notes=special_notes,
        status=BookingStatus.CHECKED_IN,
    )
    _occupy_room(session, room_id)
    if paid_online:
        _record_ota_online_payment(session, booking, _source_name_for(session, booking_source_id))
    else:
        _record_advance_payment(session, booking, advance_payment, advance_payment_method)
    return booking


def _record_advance_payment(
    session: Session,
    booking: Booking,
    advance_payment: Any,
    advance_payment_method: str | PaymentMethod,
) -> None:
    """Record an optional advance payment taken at booking time."""
    from app.services import financial_service

    amount = _money(advance_payment)
    if amount <= 0:
        return
    financial_service.record_payment(
        session,
        booking_id=booking.id,
        amount=amount,
        payment_method=advance_payment_method,
        notes="Advance payment at booking",
    )


def _source_name_for(session: Session, booking_source_id: int) -> str:
    from app.database.models import BookingSource

    source = session.get(BookingSource, booking_source_id)
    return source.name if source is not None else ""


def _record_ota_online_payment(session: Session, booking: Booking, source_name: str) -> None:
    """Mark an OTA booking as prepaid online.

    Only valid for OTA sources that support paid-online bookings
    (``OTA_PAID_ONLINE_SOURCES`` — Booking.com is excluded). The booking is
    marked ``paid_online`` so it displays the "Paid Online" arrangement; no
    payment row is created because the hotel records nothing for the room (the
    guest already paid the OTA). Any early/late checkout charges are still
    collected at the hotel.
    """
    if source_name not in OTA_PAID_ONLINE_SOURCES:
        raise BookingValidationError(
            f"Paid-online is only available for {', '.join(OTA_PAID_ONLINE_SOURCES)} bookings."
        )
    booking.paid_online = True
    session.commit()
    session.refresh(booking)


# ---------------------------------------------------------------------------
# Lifecycle transitions
# ---------------------------------------------------------------------------

def check_in_booking(
    session: Session,
    booking_id: int,
    check_in_date: date | None = None,
    check_in_time: dtime | None = None,
) -> Booking:
    booking = _get_or_raise(session, booking_id)
    if booking.status not in (BookingStatus.RESERVED.value, BookingStatus.NEW.value):
        raise InvalidBookingStateError("Only a reserved booking can be checked in.")
    if check_in_date is not None:
        booking.check_in_date = check_in_date
    if check_in_time is not None:
        booking.check_in_time = check_in_time
    _record_status_change(session, booking, BookingStatus.CHECKED_IN.value)
    booking.status = BookingStatus.CHECKED_IN.value
    session.commit()
    session.refresh(booking)
    _occupy_room(session, booking.room_id)
    logger.info("Booking %s checked in", booking.booking_number)
    return booking


def check_out_booking(
    session: Session,
    booking_id: int,
    *,
    actual_check_out_at: datetime | None = None,
) -> Booking:
    booking = _get_or_raise(session, booking_id)
    if booking.status != BookingStatus.CHECKED_IN.value:
        raise InvalidBookingStateError("Only a checked-in booking can be checked out.")
    _record_status_change(session, booking, BookingStatus.CHECKED_OUT.value)
    booking.status = BookingStatus.CHECKED_OUT.value
    booking.actual_check_out_at = actual_check_out_at or datetime.now()
    session.commit()
    session.refresh(booking)
    _release_room(session, booking.room_id)
    logger.info("Booking %s checked out", booking.booking_number)
    return booking


def cancel_booking(session: Session, booking_id: int, reason: str) -> Booking:
    booking = _get_or_raise(session, booking_id)
    if booking.status not in (BookingStatus.RESERVED.value, BookingStatus.NEW.value):
        raise InvalidBookingStateError("Only a reservation can be cancelled.")
    reason_text = (reason or "").strip()
    if not reason_text:
        raise BookingValidationError("A cancellation reason is required.")
    _record_status_change(session, booking, BookingStatus.CANCELLED.value, reason_text)
    booking.status = BookingStatus.CANCELLED.value
    booking.cancelled_at = datetime.now()
    booking.cancellation_reason = reason_text
    booking.cancelled_by = "Reception"
    session.commit()
    session.refresh(booking)
    _release_room_if_free(session, booking.room_id)
    logger.info("Booking %s cancelled (%s)", booking.booking_number, reason_text)
    return booking


def mark_no_show(session: Session, booking_id: int, reason: str = "") -> Booking:
    booking = _get_or_raise(session, booking_id)
    if booking.status not in (BookingStatus.RESERVED.value, BookingStatus.NEW.value):
        raise InvalidBookingStateError("Only a reservation can be marked as no-show.")
    _record_status_change(session, booking, BookingStatus.NO_SHOW.value)
    booking.status = BookingStatus.NO_SHOW.value
    booking.no_show_at = datetime.now()
    booking.no_show_reason = (reason or "").strip()
    session.commit()
    session.refresh(booking)
    _release_room_if_free(session, booking.room_id)
    logger.info("Booking %s marked as no-show", booking.booking_number)
    return booking


def delete_booking(
    session: Session,
    booking_id: int,
    reason: str = "",
    changed_by: str = "Reception",
    delete_guest_if_last: bool = True,
) -> Booking:
    """Soft-delete a booking.

    The booking is flagged ``deleted`` and excluded from all counts and
    financial aggregations. Its payments/charges/history are preserved so
    the record can still be inspected in the deleted-booking history.

    When the booking was the guest's last booking, the guest record is
    removed as well so the guest disappears from the Guests page. The
    booking keeps its soft-delete history but drops its guest reference.
    """
    booking = _get_or_raise(session, booking_id)
    if booking.status == BookingStatus.DELETED.value:
        raise InvalidBookingStateError("This booking has already been deleted.")
    guest_id = booking.guest_id
    _record_status_change(session, booking, BookingStatus.DELETED.value, (reason or "").strip())
    booking.status = BookingStatus.DELETED.value
    booking.deleted_at = datetime.now()
    booking.deleted_by = changed_by
    booking.deletion_reason = (reason or "").strip()
    session.commit()
    session.refresh(booking)
    _release_room_if_free(session, booking.room_id)

    if delete_guest_if_last and guest_id is not None:
        _delete_guest_if_last(session, booking, guest_id)

    logger.info("Booking %s deleted (%s)", booking.booking_number, reason)
    return booking


def _delete_guest_if_last(session: Session, booking: Booking, guest_id: int) -> None:
    """Delete the guest when this was their only booking (any status)."""
    other = (
        session.query(Booking.id)
        .filter(Booking.guest_id == guest_id, Booking.id != booking.id)
        .count()
    )
    if other > 0:
        return
    guest = session.get(Guest, guest_id)
    if guest is None:
        return
    booking.guest_id = None
    booking.guest = None
    session.delete(guest)
    session.commit()
    session.refresh(booking)
    logger.info("Guest %s deleted (last booking %s removed)", guest_id, booking.booking_number)


def update_booking(
    session: Session,
    booking_id: int,
    *,
    guest_id: Any = _UNSET,
    room_id: Any = _UNSET,
    booking_source_id: Any = _UNSET,
    check_in_date: Any = _UNSET,
    check_in_time: Any = _UNSET,
    check_out_date: Any = _UNSET,
    check_out_time: Any = _UNSET,
    adults: Any = _UNSET,
    children: Any = _UNSET,
    room_rate: Any = _UNSET,
    extra_person_charge: Any = _UNSET,
    early_check_in_charge: Any = _UNSET,
    late_check_out_charge: Any = _UNSET,
    special_notes: Any = _UNSET,
) -> Booking:
    booking = _get_or_raise(session, booking_id)

    if booking.status == BookingStatus.CHECKED_IN.value:
        for field in (room_id, check_in_date, check_in_time, check_out_date, check_out_time):
            if field is not _UNSET:
                raise BookingValidationError("Room and dates cannot be changed after check-in.")

    changed = False
    changed |= _set(booking, "guest_id", guest_id)
    changed |= _set(booking, "booking_source_id", booking_source_id)
    changed |= _set(booking, "adults", adults)
    changed |= _set(booking, "children", children)
    changed |= _set(booking, "room_rate", _money(room_rate) if room_rate is not _UNSET else booking.room_rate)
    changed |= _set(booking, "extra_person_charge", _money(extra_person_charge) if extra_person_charge is not _UNSET else booking.extra_person_charge)
    changed |= _set(booking, "early_check_in_charge", _money(early_check_in_charge) if early_check_in_charge is not _UNSET else booking.early_check_in_charge)
    changed |= _set(booking, "late_check_out_charge", _money(late_check_out_charge) if late_check_out_charge is not _UNSET else booking.late_check_out_charge)
    changed |= _set(booking, "special_notes", (special_notes or "").strip() if special_notes is not _UNSET else booking.special_notes)

    if booking.status != BookingStatus.CHECKED_IN.value:
        if room_id is not _UNSET:
            changed |= _set(booking, "room_id", room_id)
        if check_in_date is not _UNSET:
            changed |= _set(booking, "check_in_date", check_in_date)
        if check_in_time is not _UNSET:
            changed |= _set(booking, "check_in_time", check_in_time)
        if check_out_date is not _UNSET:
            changed |= _set(booking, "check_out_date", check_out_date)
        if check_out_time is not _UNSET:
            changed |= _set(booking, "check_out_time", check_out_time)

        validate_date_range(booking.check_in_date, booking.check_in_time, booking.check_out_date, booking.check_out_time)
        room = session.get(Room, booking.room_id)
        if room is None:
            raise BookingValidationError("Selected room does not exist.")
        _raise_if_unavailable(
            session,
            room,
            booking.check_in_date,
            booking.check_in_time,
            booking.check_out_date,
            booking.check_out_time,
            exclude_booking_id=booking.id,
        )

    if not changed:
        return booking

    session.commit()
    session.refresh(booking)
    logger.info("Booking %s updated", booking.booking_number)
    return booking


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def get_booking(session: Session, booking_id: int) -> Booking | None:
    return (
        session.query(Booking)
        .options(joinedload(Booking.guest), joinedload(Booking.room), joinedload(Booking.source))
        .filter(Booking.id == booking_id)
        .first()
    )


def get_booking_by_number(session: Session, booking_number: str) -> Booking | None:
    return (
        session.query(Booking)
        .options(joinedload(Booking.guest), joinedload(Booking.room), joinedload(Booking.source))
        .filter(Booking.booking_number == (booking_number or "").strip())
        .first()
    )


def search_bookings(session: Session, query: str, limit: int = 200) -> list[Booking]:
    """Search by booking number, guest name, mobile or room number."""
    text = (query or "").strip()
    if not text:
        return []
    pattern = f"%{text.lower()}%"
    return (
        session.query(Booking)
        .options(joinedload(Booking.guest), joinedload(Booking.room), joinedload(Booking.source))
        .join(Guest, Booking.guest_id == Guest.id)
        .join(Room, Booking.room_id == Room.id)
        .filter(
            Booking.status != BookingStatus.DELETED.value,
            or_(
                func.lower(Booking.booking_number).like(pattern),
                func.lower(Guest.guest_name).like(pattern),
                func.lower(Guest.mobile_number).like(pattern),
                func.lower(Room.room_number).like(pattern),
            )
        )
        .order_by(Booking.check_in_date.desc(), Booking.id.desc())
        .limit(limit)
        .all()
    )


def filter_bookings(
    session: Session,
    *,
    query: str = "",
    status: str | BookingStatus | None = None,
    period: str | None = None,
    today: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 500,
) -> list[Booking]:
    query_builder = session.query(Booking).options(
        joinedload(Booking.guest), joinedload(Booking.room), joinedload(Booking.source)
    ).outerjoin(Guest, Booking.guest_id == Guest.id)
    if status is not None:
        if _coerce_status(status) == BookingStatus.DELETED:
            query_builder = query_builder.filter(Booking.status == BookingStatus.DELETED.value)
        else:
            query_builder = query_builder.filter(
                Booking.status == _coerce_status(status).value,
                Booking.status != BookingStatus.DELETED.value,
            )
    else:
        query_builder = query_builder.filter(Booking.status != BookingStatus.DELETED.value)

    today = today or date.today()
    if period == "today":
        query_builder = query_builder.filter(or_(Booking.check_in_date == today, Booking.check_out_date == today))
    elif period == "upcoming":
        query_builder = query_builder.filter(Booking.check_in_date > today)
    elif period == "past":
        query_builder = query_builder.filter(Booking.check_out_date < today)

    if date_from is not None:
        query_builder = query_builder.filter(Booking.check_in_date >= date_from)
    if date_to is not None:
        query_builder = query_builder.filter(Booking.check_in_date <= date_to)

    text = (query or "").strip()
    if text:
        pattern = f"%{text.lower()}%"
        query_builder = query_builder.join(Room, Booking.room_id == Room.id).filter(
            or_(
                func.lower(Booking.booking_number).like(pattern),
                func.lower(Guest.guest_name).like(pattern),
                func.lower(Guest.mobile_number).like(pattern),
                func.lower(Room.room_number).like(pattern),
            )
        )

    return query_builder.order_by(Booking.check_in_date.desc(), Booking.id.desc()).limit(limit).all()


def get_today_check_ins(session: Session, today: date | None = None) -> list[Booking]:
    """Bookings arriving today (reserved or already checked in)."""
    today = today or date.today()
    return (
        session.query(Booking)
        .options(joinedload(Booking.guest), joinedload(Booking.room))
        .filter(
            Booking.check_in_date == today,
            Booking.status.in_(
                (BookingStatus.RESERVED.value, BookingStatus.CHECKED_IN.value)
            ),
        )
        .order_by(Booking.check_in_time, Booking.id)
        .all()
    )


def get_today_check_outs(session: Session, today: date | None = None) -> list[Booking]:
    """Bookings departing today (checked in or already checked out)."""
    today = today or date.today()
    return (
        session.query(Booking)
        .options(joinedload(Booking.guest), joinedload(Booking.room))
        .filter(
            Booking.check_out_date == today,
            Booking.status.in_(
                (BookingStatus.CHECKED_IN.value, BookingStatus.CHECKED_OUT.value)
            ),
        )
        .order_by(Booking.check_out_time, Booking.id)
        .all()
    )


def get_booking_status_history(session: Session, booking_id: int) -> list[BookingStatusHistory]:
    """Booking status transitions, oldest first."""
    return (
        session.query(BookingStatusHistory)
        .filter(BookingStatusHistory.booking_id == booking_id)
        .order_by(BookingStatusHistory.changed_at, BookingStatusHistory.id)
        .all()
    )


def get_upcoming_bookings(
    session: Session,
    days: int = 7,
    today: date | None = None,
) -> list[Booking]:
    """Confirmed reservations arriving within the next ``days`` days."""
    today = today or date.today()
    horizon = today + timedelta(days=days)
    return (
        session.query(Booking)
        .options(joinedload(Booking.guest), joinedload(Booking.room))
        .filter(
            Booking.check_in_date > today,
            Booking.check_in_date <= horizon,
            Booking.status.in_(
                (BookingStatus.RESERVED.value, BookingStatus.NEW.value)
            ),
        )
        .order_by(Booking.check_in_date, Booking.check_in_time, Booking.id)
        .all()
    )


def get_active_booking_for_room(session: Session, room_id: int) -> Booking | None:
    """The booking currently occupying or reserving a room, if any."""
    return (
        session.query(Booking)
        .options(joinedload(Booking.guest), joinedload(Booking.room))
        .filter(
            Booking.room_id == room_id,
            Booking.status.in_(
                (BookingStatus.RESERVED.value, BookingStatus.CHECKED_IN.value)
            ),
        )
        .order_by(Booking.check_in_date, Booking.id)
        .first()
    )


def search_global(
    session: Session,
    query: str,
    guest_limit: int = 15,
    booking_limit: int = 15,
) -> dict[str, list]:
    """Global reception search: matching guests and bookings."""
    from app.services import guest_service

    text = (query or "").strip()
    if not text:
        return {"guests": [], "bookings": []}
    return {
        "guests": guest_service.search_guests(session, text, limit=guest_limit),
        "bookings": search_bookings(session, text, limit=booking_limit),
    }
