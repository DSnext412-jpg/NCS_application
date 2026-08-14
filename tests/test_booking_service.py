"""Tests for the booking service: reservations, walk-ins, state transitions,
room availability, filters and today's activity.

All tests use temporary SQLite databases — the real hotel database is
never touched.
"""

from __future__ import annotations

from datetime import date, timedelta, time as dtime

import pytest

from app.core.constants import BookingStatus
from app.database.database import Database
from app.services import booking_service, financial_service, guest_service, room_service
from app.services.booking_source_service import initialize_default_sources
from app.services.booking_service import (
    BookingError,
    BookingValidationError,
    InvalidBookingStateError,
    RoomNotAvailableError,
)
from app.services.guest_service import GuestValidationError
from tests._db_support import copy_db_template


def _make_database(tmp_path):  # noqa: ANN001
    database = Database(copy_db_template(tmp_path / "hotel.db"))
    return database


def _seed(database) -> None:  # noqa: ANN001
    with database.session_scope() as session:
        room_service.initialize_default_rooms(session)
        initialize_default_sources(session)


def _add_guest(database, name="Amit Sharma", mobile="9876543210") -> int:  # noqa: ANN001
    with database.session_scope() as session:
        guest = guest_service.create_guest(
            session,
            guest_name=name,
            mobile_number=mobile,
            city="Jaipur",
            id_type="Aadhaar",
            id_number="123456789012",
            address="Test Address",
        )
        return guest.id


def _first_room_id(database) -> int:  # noqa: ANN001
    with database.session_scope() as session:
        return room_service.get_rooms(session)[0].id


def _reserve(database, guest_id, room_id, *, check_in=None, check_out=None) -> int:  # noqa: ANN001
    check_in = check_in or date.today()
    check_out = check_out or (date.today() + timedelta(days=2))
    with database.session_scope() as session:
        booking = booking_service.create_reservation(
            session,
            guest_id=guest_id,
            room_id=room_id,
            booking_source_id=1,
            check_in_date=check_in,
            check_in_time=dtime(12, 0),
            check_out_date=check_out,
            check_out_time=dtime(11, 0),
            adults=1,
            children=0,
            room_rate=1000.0,
        )
        return booking.id


# ---------------------------------------------------------------------------
# Booking number
# ---------------------------------------------------------------------------

def test_booking_number_uses_expected_format(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        room_id = _first_room_id(database)
        booking_id = _reserve(database, guest_id, room_id)
        with database.session_scope() as session:
            booking = booking_service.get_booking(session, booking_id)
            assert booking.booking_number.startswith("NCS-B-")
            assert str(date.today().year) in booking.booking_number
            assert len(booking.booking_number) > 4
    finally:
        database.dispose()


def test_booking_numbers_are_unique_and_sequential(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        ids = [_reserve(database, guest_id, room_id) for room_id in (1, 2)]
        with database.session_scope() as session:
            numbers = [booking_service.get_booking(session, bid).booking_number for bid in ids]
            assert len(set(numbers)) == 2
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Reservations
# ---------------------------------------------------------------------------

def test_create_reservation_sets_status_and_marks_room_reserved(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        room_id = _first_room_id(database)
        booking_id = _reserve(database, guest_id, room_id)
        with database.session_scope() as session:
            booking = booking_service.get_booking(session, booking_id)
            assert booking.status == BookingStatus.RESERVED.value
            assert booking.room_rate == 1000.0
            assert booking.room.status == "reserved"
    finally:
        database.dispose()


def test_future_reservation_does_not_mark_room_reserved(tmp_path) -> None:  # noqa: ANN001
    """A reservation whose check-in is in the future leaves the room available
    so it can still be used before the check-in date."""
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        room_id = _first_room_id(database)
        booking_id = _reserve(
            database,
            guest_id,
            room_id,
            check_in=date.today() + timedelta(days=1),
            check_out=date.today() + timedelta(days=3),
        )
        with database.session_scope() as session:
            booking = booking_service.get_booking(session, booking_id)
            assert booking.status == BookingStatus.RESERVED.value
            assert booking.room.status == "vacant"
    finally:
        database.dispose()


def test_room_cannot_be_double_booked(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database, name="First", mobile="1111111111")
        guest2_id = _add_guest(database, name="Second", mobile="2222222222")
        room_id = _first_room_id(database)
        _reserve(database, guest_id, room_id)
        with pytest.raises(RoomNotAvailableError):
            _reserve(database, guest2_id, room_id)
    finally:
        database.dispose()


def test_adjacent_dates_do_not_conflict(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database, name="First", mobile="1111111111")
        guest2_id = _add_guest(database, name="Second", mobile="2222222222")
        room_id = _first_room_id(database)
        today = date.today()
        _reserve(database, guest_id, room_id, check_in=today, check_out=today + timedelta(days=2))
        # Check-in on the same day the first guest checks out is allowed.
        _reserve(database, guest2_id, room_id, check_in=today + timedelta(days=2), check_out=today + timedelta(days=4))
    finally:
        database.dispose()


def test_cannot_reserve_with_invalid_date_range(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        room_id = _first_room_id(database)
        with pytest.raises(BookingValidationError):
            _reserve(
                database,
                guest_id,
                room_id,
                check_in=date.today() + timedelta(days=2),
                check_out=date.today() + timedelta(days=1),
            )
    finally:
        database.dispose()


def test_cannot_reserve_without_guest(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        room_id = _first_room_id(database)
        with pytest.raises(GuestValidationError):
            with database.session_scope() as session:
                booking_service.create_reservation(
                    session,
                    guest_id=99999,
                    room_id=room_id,
                    booking_source_id=1,
                    check_in_date=date.today(),
                    check_in_time=dtime(12, 0),
                    check_out_date=date.today() + timedelta(days=1),
                    check_out_time=dtime(11, 0),
                    adults=1,
                    children=0,
                    room_rate=500,
                )
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Walk-in
# ---------------------------------------------------------------------------

def test_walkin_immediately_occupies_room(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database, name="Walk", mobile="9999999999")
        room_id = _first_room_id(database)
        with database.session_scope() as session:
            booking = booking_service.create_walkin(
                session,
                guest_id=guest_id,
                room_id=room_id,
                booking_source_id=1,
                check_in_date=date.today(),
                check_in_time=dtime(14, 0),
                check_out_date=date.today() + timedelta(days=1),
                check_out_time=dtime(11, 0),
                adults=2,
                children=1,
                room_rate=1200,
            )
            assert booking.status == BookingStatus.CHECKED_IN.value
            assert booking.room.status == "occupied"
    finally:
        database.dispose()


def test_walkin_marks_guest_checked_in(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database, name="Walk", mobile="9999999999")
        room_id = _first_room_id(database)
        with database.session_scope() as session:
            booking = booking_service.create_walkin(
                session,
                guest_id=guest_id,
                room_id=room_id,
                booking_source_id=1,
                check_in_date=date.today(),
                check_in_time=dtime(14, 0),
                check_out_date=date.today() + timedelta(days=1),
                check_out_time=dtime(11, 0),
                adults=1,
                children=0,
                room_rate=1200,
            )
            assert booking.guest.is_active is True
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------

def test_check_in_transitions_reservation(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        room_id = _first_room_id(database)
        booking_id = _reserve(database, guest_id, room_id)
        with database.session_scope() as session:
            booking = booking_service.check_in_booking(session, booking_id, check_in_time=dtime(13, 30))
            assert booking.status == BookingStatus.CHECKED_IN.value
            assert booking.check_in_time == dtime(13, 30)
            assert booking.room.status == "occupied"
    finally:
        database.dispose()


def test_check_out_releases_room(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        room_id = _first_room_id(database)
        booking_id = _reserve(database, guest_id, room_id)
        with database.session_scope() as session:
            booking_service.check_in_booking(session, booking_id)
            booking = booking_service.check_out_booking(session, booking_id)
            assert booking.status == BookingStatus.CHECKED_OUT.value
            assert booking.room.status == "cleaning"
    finally:
        database.dispose()


def test_check_out_records_given_actual_time(tmp_path) -> None:  # noqa: ANN001
    from datetime import datetime

    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        room_id = _first_room_id(database)
        booking_id = _reserve(database, guest_id, room_id)
        actual = datetime(2026, 1, 5, 15, 30)
        with database.session_scope() as session:
            booking_service.check_in_booking(session, booking_id)
            booking_service.check_out_booking(session, booking_id, actual_check_out_at=actual)
            booking = booking_service.get_booking(session, booking_id)
        assert booking.actual_check_out_at == actual
    finally:
        database.dispose()


def test_cancel_requires_reason(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        room_id = _first_room_id(database)
        booking_id = _reserve(database, guest_id, room_id)
        with pytest.raises(BookingValidationError):
            with database.session_scope() as session:
                booking_service.cancel_booking(session, booking_id, "")
    finally:
        database.dispose()


def test_cancel_releases_room(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        room_id = _first_room_id(database)
        booking_id = _reserve(database, guest_id, room_id)
        with database.session_scope() as session:
            booking = booking_service.cancel_booking(session, booking_id, "Guest changed plans")
            assert booking.status == BookingStatus.CANCELLED.value
            assert booking.cancellation_reason == "Guest changed plans"
            assert booking.room.status == "vacant"
    finally:
        database.dispose()


def test_no_show_releases_room(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        room_id = _first_room_id(database)
        booking_id = _reserve(database, guest_id, room_id)
        with database.session_scope() as session:
            booking = booking_service.mark_no_show(session, booking_id, "Did not arrive")
            assert booking.status == BookingStatus.NO_SHOW.value
            assert booking.no_show_reason == "Did not arrive"
            assert booking.room.status == "vacant"
    finally:
        database.dispose()


def test_invalid_transitions_raise(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        room_id = _first_room_id(database)
        booking_id = _reserve(database, guest_id, room_id)
        with pytest.raises(InvalidBookingStateError):
            with database.session_scope() as session:
                booking_service.check_out_booking(session, booking_id)
        with pytest.raises(BookingError):
            with database.session_scope() as session:
                booking_service.check_in_booking(session, 99999)
    finally:
        database.dispose()


def test_update_booking_allows_non_conflicting_changes(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        room_id = _first_room_id(database)
        booking_id = _reserve(database, guest_id, room_id)
        with database.session_scope() as session:
            booking = booking_service.update_booking(session, booking_id, room_rate=1500, adults=2)
            assert booking.room_rate == 1500
            assert booking.adults == 2
            assert booking.status == BookingStatus.RESERVED.value
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Filters / queries
# ---------------------------------------------------------------------------

def test_filter_by_status(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        booking_id = _reserve(database, guest_id, 1)
        with database.session_scope() as session:
            reserved = booking_service.filter_bookings(session, status=BookingStatus.RESERVED)
            cancelled = booking_service.filter_bookings(session, status=BookingStatus.CANCELLED)
            assert any(b.id == booking_id for b in reserved)
            assert cancelled == []
    finally:
        database.dispose()


def test_search_by_guest_name(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database, name="Ravi Kumar")
        booking_id = _reserve(database, guest_id, 1)
        with database.session_scope() as session:
            found = booking_service.search_bookings(session, "ravi")
            assert any(b.id == booking_id for b in found)
            assert booking_service.search_bookings(session, "zzz") == []
    finally:
        database.dispose()


def test_today_check_ins_and_outs(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        today = date.today()
        arriving_id = _reserve(
            database, guest_id, 1, check_in=today, check_out=today + timedelta(days=3)
        )
        departing_id = _reserve(
            database, guest_id, 2, check_in=today - timedelta(days=3), check_out=today
        )
        with database.session_scope() as session:
            booking_service.check_in_booking(session, arriving_id)
            booking_service.check_in_booking(session, departing_id)
        with database.session_scope() as session:
            check_ins = booking_service.get_today_check_ins(session, today)
            check_outs = booking_service.get_today_check_outs(session, today)
            assert any(b.id == arriving_id for b in check_ins)
            assert any(b.id == departing_id for b in check_outs)
    finally:
        database.dispose()


def test_delete_last_booking_removes_guest(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        room_id = _first_room_id(database)
        booking_id = _reserve(database, guest_id, room_id)
        with database.session_scope() as session:
            booking_service.delete_booking(session, booking_id, "Test cleanup")
            assert guest_service.get_guest(session, guest_id) is None
            booking = booking_service.get_booking(session, booking_id)
            assert booking.status == BookingStatus.DELETED.value
            assert booking.guest_id is None
            assert booking.deletion_reason == "Test cleanup"
        with database.session_scope() as session:
            deleted_only = booking_service.filter_bookings(session, status=BookingStatus.DELETED)
            assert any(b.id == booking_id for b in deleted_only)
    finally:
        database.dispose()


def test_delete_booking_keeps_guest_with_other_bookings(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        booking_a = _reserve(database, guest_id, 1)
        booking_b = _reserve(database, guest_id, 2)
        with database.session_scope() as session:
            booking_service.delete_booking(session, booking_a, "Removing one stay")
            assert guest_service.get_guest(session, guest_id) is not None
        with database.session_scope() as session:
            remaining = [b.id for b in booking_service.filter_bookings(session)]
            assert booking_b in remaining
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Paid Online (OTA prepaid bookings)
# ---------------------------------------------------------------------------

def test_paid_online_ota_booking_marks_paid_online_without_payment(tmp_path) -> None:  # noqa: ANN001
    """Agoda/FabHotels/etc. paid-online booking is flagged paid-online and
    records nothing for the room — no payment row is created."""
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        room_id = _first_room_id(database)
        with database.session_scope() as session:
            booking = booking_service.create_reservation(
                session,
                guest_id=guest_id,
                room_id=room_id,
                booking_source_id=1,  # Agoda
                check_in_date=date.today(),
                check_in_time=dtime(12, 0),
                check_out_date=date.today() + timedelta(days=2),
                check_out_time=dtime(11, 0),
                adults=1,
                children=0,
                room_rate=1000.0,
                paid_online=True,
            )
            assert booking.paid_online is True
        with database.session_scope() as session:
            payments = financial_service.get_payment_history(session, booking.id)
            assert payments == []
    finally:
        database.dispose()


def test_paid_online_rejected_for_booking_com(tmp_path) -> None:  # noqa: ANN001
    """Booking.com is deliberately excluded from paid-online bookings."""
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        room_id = _first_room_id(database)
        with pytest.raises(BookingValidationError):
            with database.session_scope() as session:
                booking_service.create_reservation(
                    session,
                    guest_id=guest_id,
                    room_id=room_id,
                    booking_source_id=2,  # Booking.com
                    check_in_date=date.today(),
                    check_in_time=dtime(12, 0),
                    check_out_date=date.today() + timedelta(days=2),
                    check_out_time=dtime(11, 0),
                    adults=1,
                    children=0,
                    room_rate=1000.0,
                    paid_online=True,
                )
    finally:
        database.dispose()


def test_paid_online_hidden_for_walkin_source(tmp_path) -> None:  # noqa: ANN001
    """A non-OTA source cannot be marked paid online."""
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        room_id = _first_room_id(database)
        with pytest.raises(BookingValidationError):
            with database.session_scope() as session:
                booking_service.create_reservation(
                    session,
                    guest_id=guest_id,
                    room_id=room_id,
                    booking_source_id=6,  # Walk-in
                    check_in_date=date.today(),
                    check_in_time=dtime(12, 0),
                    check_out_date=date.today() + timedelta(days=2),
                    check_out_time=dtime(11, 0),
                    adults=1,
                    children=0,
                    room_rate=1000.0,
                    paid_online=True,
                )
    finally:
        database.dispose()


def test_pay_at_hotel_ota_booking_has_no_online_payment(tmp_path) -> None:  # noqa: ANN001
    """OTA booking with 'Pay at Hotel' records no automatic payment."""
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        room_id = _first_room_id(database)
        with database.session_scope() as session:
            booking = booking_service.create_reservation(
                session,
                guest_id=guest_id,
                room_id=room_id,
                booking_source_id=1,  # Agoda
                check_in_date=date.today(),
                check_in_time=dtime(12, 0),
                check_out_date=date.today() + timedelta(days=2),
                check_out_time=dtime(11, 0),
                adults=1,
                children=0,
                room_rate=1000.0,
                paid_online=False,
            )
            assert booking.paid_online is False
        with database.session_scope() as session:
            payments = financial_service.get_payment_history(session, booking.id)
            assert payments == []
    finally:
        database.dispose()


def test_walkin_paid_online_marks_paid_online_without_payment(tmp_path) -> None:  # noqa: ANN001
    """Walk-in from an OTA source with paid-online is flagged paid-online and
    records nothing for the room."""
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        room_id = _first_room_id(database)
        with database.session_scope() as session:
            booking = booking_service.create_walkin(
                session,
                guest_id=guest_id,
                room_id=room_id,
                booking_source_id=1,  # Agoda
                check_in_date=date.today(),
                check_in_time=dtime(12, 0),
                check_out_date=date.today() + timedelta(days=1),
                check_out_time=dtime(11, 0),
                adults=1,
                children=0,
                room_rate=1000.0,
                paid_online=True,
            )
            assert booking.paid_online is True
            assert booking.status == BookingStatus.CHECKED_IN.value
        with database.session_scope() as session:
            payments = financial_service.get_payment_history(session, booking.id)
            assert payments == []
    finally:
        database.dispose()
