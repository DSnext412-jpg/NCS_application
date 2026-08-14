"""Tests for Phase 7 features.

Covers: booking status history, advance payments at booking time, actual
check-out timestamps, upcoming-bookings queries, active booking for a
room, the payments page queries, ID masking and global search.
"""

from __future__ import annotations

from datetime import date, timedelta, time as dtime

import pytest

from app.core.constants import BookingStatus, PaymentMethod, PaymentRecordStatus
from app.database.database import Database
from app.database.models import Payment
from app.services import (
    booking_service,
    financial_service,
    guest_service,
    room_service,
)
from app.ui.formatters import mask_id_number
from tests._db_support import copy_db_template


def _make_database(tmp_path):  # noqa: ANN001
    database = Database(copy_db_template(tmp_path / "hotel.db"))
    return database


def _add_guest(database, name="Ravi Kumar", mobile="9998887776") -> int:  # noqa: ANN001
    with database.session_scope() as session:
        guest = guest_service.create_guest(
            session,
            guest_name=name,
            mobile_number=mobile,
            id_type="Aadhaar",
            id_number="123456789012",
        )
        return guest.id


def _first_room_id(database) -> int:  # noqa: ANN001
    with database.session_scope() as session:
        return room_service.get_all_rooms(session)[0].id


def _second_room_id(database) -> int:  # noqa: ANN001
    with database.session_scope() as session:
        return room_service.get_all_rooms(session)[1].id


# ---------------------------------------------------------------------------
# Status history
# ---------------------------------------------------------------------------

def test_booking_creation_records_initial_status(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    guest_id = _add_guest(database)
    room_id = _first_room_id(database)
    with database.session_scope() as session:
        booking = booking_service.create_reservation(
            session,
            guest_id=guest_id,
            room_id=room_id,
            booking_source_id=1,
            check_in_date=date.today(),
            check_in_time=dtime(12, 0),
            check_out_date=date.today() + timedelta(days=1),
            check_out_time=dtime(11, 0),
            room_rate=1000,
        )
        history = booking_service.get_booking_status_history(session, booking.id)
    assert len(history) == 1
    assert history[0].new_status == BookingStatus.RESERVED.value
    assert history[0].old_status == ""


def test_check_in_and_out_are_recorded(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    guest_id = _add_guest(database)
    room_id = _first_room_id(database)
    with database.session_scope() as session:
        booking = booking_service.create_reservation(
            session,
            guest_id=guest_id,
            room_id=room_id,
            booking_source_id=1,
            check_in_date=date.today(),
            check_in_time=dtime(12, 0),
            check_out_date=date.today() + timedelta(days=1),
            check_out_time=dtime(11, 0),
            room_rate=1000,
        )
        booking_service.check_in_booking(session, booking.id, check_in_time=dtime(14, 30))
        booking_service.check_out_booking(session, booking.id)
        history = booking_service.get_booking_status_history(session, booking.id)
    statuses = [entry.new_status for entry in history]
    assert statuses == [
        BookingStatus.RESERVED.value,
        BookingStatus.CHECKED_IN.value,
        BookingStatus.CHECKED_OUT.value,
    ]


def test_cancellation_is_recorded(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    guest_id = _add_guest(database)
    room_id = _first_room_id(database)
    with database.session_scope() as session:
        booking = booking_service.create_reservation(
            session,
            guest_id=guest_id,
            room_id=room_id,
            booking_source_id=1,
            check_in_date=date.today() + timedelta(days=3),
            check_in_time=dtime(12, 0),
            check_out_date=date.today() + timedelta(days=4),
            check_out_time=dtime(11, 0),
            room_rate=1000,
        )
        booking_service.cancel_booking(session, booking.id, "Guest request")
        history = booking_service.get_booking_status_history(session, booking.id)
    assert history[-1].new_status == BookingStatus.CANCELLED.value
    assert history[-1].note == "Guest request"


# ---------------------------------------------------------------------------
# Advance payments
# ---------------------------------------------------------------------------

def test_reservation_advance_payment_recorded(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    guest_id = _add_guest(database)
    room_id = _first_room_id(database)
    with database.session_scope() as session:
        booking = booking_service.create_reservation(
            session,
            guest_id=guest_id,
            room_id=room_id,
            booking_source_id=1,
            check_in_date=date.today() + timedelta(days=2),
            check_in_time=dtime(12, 0),
            check_out_date=date.today() + timedelta(days=4),
            check_out_time=dtime(11, 0),
            room_rate=1000,
            advance_payment=500,
            advance_payment_method=PaymentMethod.UPI,
        )
        summary = financial_service.get_financial_summary(session, booking.id)
        payments = financial_service.get_payment_history(session, booking.id)
    assert summary.total_paid == 500
    assert summary.payment_status.value == "partial"
    assert len(payments) == 1
    assert payments[0].payment_method == PaymentMethod.UPI.value


def test_walkin_advance_payment_recorded(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    guest_id = _add_guest(database)
    room_id = _first_room_id(database)
    with database.session_scope() as session:
        booking = booking_service.create_walkin(
            session,
            guest_id=guest_id,
            room_id=room_id,
            booking_source_id=2,
            check_in_date=date.today(),
            check_in_time=dtime(12, 0),
            check_out_date=date.today() + timedelta(days=1),
            check_out_time=dtime(11, 0),
            room_rate=1000,
            advance_payment=1000,
        )
        summary = financial_service.get_financial_summary(session, booking.id)
    assert summary.total_paid == 1000
    assert summary.payment_status.value == "paid"


def test_zero_advance_payment_records_nothing(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    guest_id = _add_guest(database)
    room_id = _first_room_id(database)
    with database.session_scope() as session:
        booking = booking_service.create_reservation(
            session,
            guest_id=guest_id,
            room_id=room_id,
            booking_source_id=1,
            check_in_date=date.today() + timedelta(days=1),
            check_in_time=dtime(12, 0),
            check_out_date=date.today() + timedelta(days=2),
            check_out_time=dtime(11, 0),
            room_rate=1000,
            advance_payment=0,
        )
        payments = financial_service.get_payment_history(session, booking.id)
    assert payments == []


# ---------------------------------------------------------------------------
# Actual check-out timestamp
# ---------------------------------------------------------------------------

def test_check_out_records_actual_time(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    guest_id = _add_guest(database)
    room_id = _first_room_id(database)
    with database.session_scope() as session:
        booking = booking_service.create_walkin(
            session,
            guest_id=guest_id,
            room_id=room_id,
            booking_source_id=2,
            check_in_date=date.today(),
            check_in_time=dtime(12, 0),
            check_out_date=date.today() + timedelta(days=1),
            check_out_time=dtime(11, 0),
            room_rate=1000,
        )
        assert booking.actual_check_out_at is None
        booking_service.check_out_booking(session, booking.id)
        refreshed = booking_service.get_booking(session, booking.id)
    assert refreshed.actual_check_out_at is not None
    assert refreshed.status == BookingStatus.CHECKED_OUT.value


# ---------------------------------------------------------------------------
# Upcoming bookings & room occupants
# ---------------------------------------------------------------------------

def test_upcoming_bookings_within_seven_days(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    guest_id = _add_guest(database)
    today = date.today()
    with database.session_scope() as session:
        booking_service.create_reservation(
            session,
            guest_id=guest_id,
            room_id=_first_room_id(database),
            booking_source_id=1,
            check_in_date=today + timedelta(days=3),
            check_in_time=dtime(12, 0),
            check_out_date=today + timedelta(days=4),
            check_out_time=dtime(11, 0),
            room_rate=1000,
        )
        booking_service.create_reservation(
            session,
            guest_id=guest_id,
            room_id=_second_room_id(database),
            booking_source_id=1,
            check_in_date=today + timedelta(days=30),
            check_in_time=dtime(12, 0),
            check_out_date=today + timedelta(days=31),
            check_out_time=dtime(11, 0),
            room_rate=1000,
        )
        upcoming = booking_service.get_upcoming_bookings(session, days=7, today=today)
    assert len(upcoming) == 1
    assert (upcoming[0].check_in_date - today).days == 3


def test_active_booking_for_room(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    guest_id = _add_guest(database)
    room_id = _first_room_id(database)
    with database.session_scope() as session:
        booking = booking_service.create_walkin(
            session,
            guest_id=guest_id,
            room_id=room_id,
            booking_source_id=2,
            check_in_date=date.today(),
            check_in_time=dtime(12, 0),
            check_out_date=date.today() + timedelta(days=1),
            check_out_time=dtime(11, 0),
            room_rate=1000,
        )
        active = booking_service.get_active_booking_for_room(session, room_id)
        assert active.id == booking.id
        booking_service.check_out_booking(session, booking.id)
        active_after = booking_service.get_active_booking_for_room(session, room_id)
    assert active_after is None


# ---------------------------------------------------------------------------
# Payments page queries
# ---------------------------------------------------------------------------

def test_list_payments_filters_by_status_and_query(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    guest_id = _add_guest(database, name="Payal Gupta", mobile="9000000001")
    with database.session_scope() as session:
        booking = booking_service.create_reservation(
            session,
            guest_id=guest_id,
            room_id=_first_room_id(database),
            booking_source_id=1,
            check_in_date=date.today() + timedelta(days=5),
            check_in_time=dtime(12, 0),
            check_out_date=date.today() + timedelta(days=6),
            check_out_time=dtime(11, 0),
            room_rate=1000,
            advance_payment=200,
        )
        financial_service.record_payment(
            session, booking_id=booking.id, amount=100, payment_method=PaymentMethod.CASH
        )
        payments = financial_service.list_payments(session, query="Payal", status="completed")
        reversed_payments = financial_service.list_payments(session, query="Payal", status="refunded")
        total = financial_service.get_payment_period_total(session)
    assert len(payments) == 2
    assert reversed_payments == []
    assert total == 300


def test_list_payments_date_range(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    guest_id = _add_guest(database)
    yesterday = date.today() - timedelta(days=1)
    with database.session_scope() as session:
        booking = booking_service.create_reservation(
            session,
            guest_id=guest_id,
            room_id=_first_room_id(database),
            booking_source_id=1,
            check_in_date=date.today() + timedelta(days=5),
            check_in_time=dtime(12, 0),
            check_out_date=date.today() + timedelta(days=6),
            check_out_time=dtime(11, 0),
            room_rate=1000,
        )
        financial_service.record_payment(
            session, booking_id=booking.id, amount=100, payment_method=PaymentMethod.CASH,
            payment_date=date.today(),
        )
        financial_service.record_payment(
            session, booking_id=booking.id, amount=100, payment_method=PaymentMethod.UPI,
            payment_date=yesterday,
        )
        recent = financial_service.list_payments(session, date_from=date.today())
        today_total = financial_service.get_payment_period_total(session, date_from=date.today())
    assert len(recent) == 1
    assert today_total == 100


# ---------------------------------------------------------------------------
# ID masking
# ---------------------------------------------------------------------------

def test_mask_id_number() -> None:
    assert mask_id_number("1234 5678 9012") == "XXXXXXXX 9012"
    assert mask_id_number("AB123456") == "XXXX 3456"
    assert mask_id_number("") == "—"
    assert mask_id_number(None) == "—"
    assert mask_id_number("A1B2") == "XXX2"


# ---------------------------------------------------------------------------
# Global search
# ---------------------------------------------------------------------------

def test_global_search_returns_guests_and_bookings(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    guest_id = _add_guest(database, name="Sneha Patil", mobile="9870000001")
    with database.session_scope() as session:
        booking = booking_service.create_reservation(
            session,
            guest_id=guest_id,
            room_id=_first_room_id(database),
            booking_source_id=1,
            check_in_date=date.today() + timedelta(days=5),
            check_in_time=dtime(12, 0),
            check_out_date=date.today() + timedelta(days=6),
            check_out_time=dtime(11, 0),
            room_rate=1000,
        )
        by_name = booking_service.search_global(session, "Sneha")
        by_number = booking_service.search_global(session, booking.booking_number)
        empty = booking_service.search_global(session, " ")
    assert len(by_name["guests"]) == 1
    assert len(by_name["bookings"]) == 1
    assert len(by_number["bookings"]) == 1
    assert empty == {"guests": [], "bookings": []}
