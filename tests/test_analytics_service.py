"""Tests for the admin analytics service: revenue, payment overview,
booking sources, occupancy, room reports and trends.

All tests use temporary SQLite databases — the real hotel database is
never touched.
"""

from __future__ import annotations

from datetime import date, timedelta, time as dtime

from app.database.database import Database
from app.services import (
    analytics_service,
    booking_service,
    financial_service,
    guest_service,
    room_service,
)
from app.services.booking_source_service import initialize_default_sources
from tests._db_support import copy_db_template

ROOM_COUNT = 11


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


def _create_booking(
    database,
    guest_id,
    room_id,
    source_id=1,
    *,
    check_in: date,
    check_out: date,
    rate=1000.0,
) -> int:
    with database.session_scope() as session:
        booking = booking_service.create_reservation(
            session,
            guest_id=guest_id,
            room_id=room_id,
            booking_source_id=source_id,
            check_in_date=check_in,
            check_in_time=dtime(12, 0),
            check_out_date=check_out,
            check_out_time=dtime(11, 0),
            adults=1,
            children=0,
            room_rate=rate,
        )
        return booking.id


def _check_in(database, booking_id, on: date) -> None:  # noqa: ANN001
    with database.session_scope() as session:
        booking_service.check_in_booking(session, booking_id, check_in_date=on)


def _check_out(database, booking_id, on: date) -> None:  # noqa: ANN001
    with database.session_scope() as session:
        booking_service.check_in_booking(session, booking_id, check_in_date=on)
        booking_service.check_out_booking(session, booking_id)


def _pay(database, booking_id, amount, method="CASH", when: date | None = None) -> None:  # noqa: ANN001
    with database.session_scope() as session:
        financial_service.record_payment(
            session,
            booking_id=booking_id,
            amount=amount,
            payment_method=method,
            payment_date=when or date.today(),
        )


def _room_id(database, room_number: str) -> int:  # noqa: ANN001
    with database.session_scope() as session:
        return room_service.get_room(session, room_number).id


# ---------------------------------------------------------------------------
# Revenue (payment date based)
# ---------------------------------------------------------------------------

def test_revenue_counts_only_completed_payments_in_range(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest = _add_guest(database)
        room = _room_id(database, "202")
        today = date.today()

        booking_in = _create_booking(database, guest, room, check_in=today, check_out=today + timedelta(days=1), rate=1500)
        _pay(database, booking_in, 1500, when=today)

        booking_out = _create_booking(database, guest, _room_id(database, "203"), check_in=today, check_out=today + timedelta(days=1))
        _pay(database, booking_out, 900, when=today + timedelta(days=5))

        with database.session_scope() as session:
            assert analytics_service.get_revenue(session, today, today) == 1500
            assert analytics_service.get_revenue(session, today + timedelta(days=5), today + timedelta(days=5)) == 900
            assert analytics_service.get_revenue(session, today, today + timedelta(days=5)) == 2400
    finally:
        database.dispose()


def test_revenue_by_method_groups_completed_payments(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest = _add_guest(database)
        today = date.today()
        b1 = _create_booking(database, guest, _room_id(database, "202"), check_in=today, check_out=today + timedelta(days=1), rate=1000)
        b2 = _create_booking(database, guest, _room_id(database, "203"), check_in=today, check_out=today + timedelta(days=1), rate=2000)
        b3 = _create_booking(database, guest, _room_id(database, "204"), check_in=today, check_out=today + timedelta(days=1), rate=500)
        _pay(database, b1, 1000, method="CASH", when=today)
        _pay(database, b2, 2000, method="UPI", when=today)
        _pay(database, b3, 500, method="UPI", when=today)

        with database.session_scope() as session:
            methods = analytics_service.get_revenue_by_method(session, today, today)
        assert methods["cash"] == 1000
        assert methods["upi"] == 2500
    finally:
        database.dispose()


def test_revenue_by_day_zero_fills_gaps(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest = _add_guest(database)
        today = date.today()
        b = _create_booking(database, guest, _room_id(database, "202"), check_in=today, check_out=today + timedelta(days=1), rate=1200)
        _pay(database, b, 1200, when=today)

        with database.session_scope() as session:
            daily = analytics_service.get_revenue_by_day(session, today, today + timedelta(days=2))
        assert [amount for _, amount in daily] == [1200, 0, 0]
        assert len(daily) == 3
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Payment overview
# ---------------------------------------------------------------------------

def test_payment_overview_counts_and_outstanding(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest = _add_guest(database)
        today = date.today()

        paid = _create_booking(database, guest, _room_id(database, "202"), check_in=today, check_out=today + timedelta(days=1), rate=2000)
        partial = _create_booking(database, guest, _room_id(database, "203"), check_in=today, check_out=today + timedelta(days=1), rate=2000)
        _create_booking(database, guest, _room_id(database, "204"), check_in=today, check_out=today + timedelta(days=1), rate=2000)
        _pay(database, paid, 2000, when=today)
        _pay(database, partial, 1000, when=today)

        with database.session_scope() as session:
            overview = analytics_service.get_payment_overview(session, today, today)
        assert overview["collected"] == 3000
        assert overview["outstanding"] == 3000
        assert overview["paid"] == 1
        assert overview["partial"] == 1
        assert overview["unpaid"] == 1
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Booking sources
# ---------------------------------------------------------------------------

def test_booking_counts_by_source(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest = _add_guest(database)
        today = date.today()
        _create_booking(database, guest, _room_id(database, "202"), source_id=1, check_in=today, check_out=today + timedelta(days=1))
        _create_booking(database, guest, _room_id(database, "203"), source_id=1, check_in=today, check_out=today + timedelta(days=1))
        _create_booking(database, guest, _room_id(database, "204"), source_id=2, check_in=today, check_out=today + timedelta(days=1))

        with database.session_scope() as session:
            counts = analytics_service.get_booking_counts_by_source(session, today, today)
        assert counts["Agoda"] == 2
        assert counts["Booking.com"] == 1
    finally:
        database.dispose()


def test_revenue_by_source(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest = _add_guest(database)
        today = date.today()
        b1 = _create_booking(database, guest, _room_id(database, "202"), source_id=1, check_in=today, check_out=today + timedelta(days=1), rate=1000)
        b2 = _create_booking(database, guest, _room_id(database, "203"), source_id=1, check_in=today, check_out=today + timedelta(days=1), rate=1500)
        b3 = _create_booking(database, guest, _room_id(database, "204"), source_id=2, check_in=today, check_out=today + timedelta(days=1), rate=2000)
        _pay(database, b1, 1000, when=today)
        _pay(database, b2, 1500, when=today)
        _pay(database, b3, 2000, when=today)

        with database.session_scope() as session:
            revenue = analytics_service.get_revenue_by_source(session, today, today)
        assert revenue["Agoda"] == 2500
        assert revenue["Booking.com"] == 2000
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Occupancy (room-night based)
# ---------------------------------------------------------------------------

def test_occupancy_room_night_calculation(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest = _add_guest(database)
        today = date.today()
        booking_id = _create_booking(
            database,
            guest,
            _room_id(database, "202"),
            check_in=today - timedelta(days=2),
            check_out=today + timedelta(days=2),
        )
        _check_in(database, booking_id, on=today - timedelta(days=2))

        date_from = today - timedelta(days=6)
        with database.session_scope() as session:
            occupancy = analytics_service.get_occupancy(session, date_from, today)

        assert occupancy["total_rooms"] == ROOM_COUNT
        assert occupancy["days"] == 7
        assert occupancy["available_nights"] == ROOM_COUNT * 7
        assert occupancy["occupied_nights"] == 2
        assert occupancy["occupancy_percent"] == round(2 / (ROOM_COUNT * 7) * 100, 1)
    finally:
        database.dispose()


def test_occupancy_excludes_inactive_rooms(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        today = date.today()
        with database.session_scope() as session:
            room_service.set_room_active(session, _room_id(database, "203"), active=False)

        with database.session_scope() as session:
            occupancy = analytics_service.get_occupancy(session, today, today)
        # 11 rooms minus 1 inactive = 10 available rooms.
        assert occupancy["total_rooms"] == ROOM_COUNT - 1
        assert occupancy["available_nights"] == (ROOM_COUNT - 1) * 1
    finally:
        database.dispose()


def test_room_type_report(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest = _add_guest(database)
        today = date.today()
        booking_id = _create_booking(
            database,
            guest,
            _room_id(database, "202"),  # AC
            check_in=today - timedelta(days=1),
            check_out=today + timedelta(days=1),
        )
        _check_in(database, booking_id, on=today - timedelta(days=1))

        with database.session_scope() as session:
            by_type = analytics_service.get_room_type_report(session, today - timedelta(days=3), today)

        ac = next(row for row in by_type if row["room_type"] == "AC")
        non_ac = next(row for row in by_type if row["room_type"] == "Non-AC")
        assert ac["rooms"] == 6
        assert ac["occupied_room_nights"] == 1
        assert non_ac["occupied_room_nights"] == 0
    finally:
        database.dispose()


def test_room_performance(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest = _add_guest(database)
        today = date.today()
        booking_id = _create_booking(
            database,
            guest,
            _room_id(database, "202"),
            check_in=today - timedelta(days=1),
            check_out=today + timedelta(days=1),
            rate=1500,
        )
        _check_in(database, booking_id, on=today - timedelta(days=1))
        _pay(database, booking_id, 1500, when=today)

        with database.session_scope() as session:
            rows = analytics_service.get_room_performance(session, today - timedelta(days=3), today)
        room_202 = next(row for row in rows if row["room_number"] == "202")
        assert room_202["bookings"] == 1
        assert room_202["revenue"] == 1500
        assert room_202["occupied_nights"] == 1
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------

def test_booking_trend_counts(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest = _add_guest(database)
        today = date.today()
        reserved = _create_booking(database, guest, _room_id(database, "202"), check_in=today, check_out=today + timedelta(days=1))
        _create_booking(database, guest, _room_id(database, "203"), check_in=today, check_out=today + timedelta(days=1))
        _check_in(database, reserved, on=today)

        with database.session_scope() as session:
            trend = analytics_service.get_booking_trend(session, today, today)
        assert len(trend) == 1
        row = trend[0]
        assert row["reservations"] == 1
        assert row["check_ins"] == 1
        assert row["check_outs"] == 0
    finally:
        database.dispose()


def test_range_is_normalized_when_reversed(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest = _add_guest(database)
        today = date.today()
        booking = _create_booking(database, guest, _room_id(database, "202"), check_in=today, check_out=today + timedelta(days=1))
        _pay(database, booking, 500, when=today)

        with database.session_scope() as session:
            # Reversed range should behave as a single-day range.
            assert analytics_service.get_revenue(session, today + timedelta(days=2), today) == 0
            assert analytics_service.get_revenue(session, today, today + timedelta(days=2)) == 500
    finally:
        database.dispose()
