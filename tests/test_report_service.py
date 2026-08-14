"""Tests for the report building service.

Verifies that each Phase 6 report type is built from the same analytics
data and carries a consistent title, summary and tables. All tests use
temporary SQLite databases.
"""

from __future__ import annotations

from datetime import date, timedelta, time as dtime

import pytest

from app.database.database import Database
from app.services import (
    booking_service,
    financial_service,
    guest_service,
    report_service,
    room_service,
)
from app.services.booking_source_service import initialize_default_sources
from tests._db_support import copy_db_template


def _make_database(tmp_path):  # noqa: ANN001
    database = Database(copy_db_template(tmp_path / "hotel.db"))
    return database


def _seed(database) -> None:  # noqa: ANN001
    with database.session_scope() as session:
        room_service.initialize_default_rooms(session)
        initialize_default_sources(session)


def _guest(database) -> int:  # noqa: ANN001
    with database.session_scope() as session:
        return guest_service.create_guest(
            session,
            guest_name="Test Guest",
            mobile_number="9000000000",
            city="Nashik",
            id_type="Aadhaar",
            id_number="111111111111",
            address="Address",
        ).id


def _booking(database, guest_id, room_id, *, rate=1000.0, check_in=None, check_out=None) -> int:  # noqa: ANN001
    check_in = check_in or date.today()
    check_out = check_out or (check_in + timedelta(days=1))
    with database.session_scope() as session:
        return booking_service.create_reservation(
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
            room_rate=rate,
        ).id


def _pay(database, booking_id, amount, when=None) -> None:  # noqa: ANN001
    with database.session_scope() as session:
        financial_service.record_payment(
            session,
            booking_id=booking_id,
            amount=amount,
            payment_method="CASH",
            payment_date=when or date.today(),
        )


def test_financial_report_contents(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest = _guest(database)
        today = date.today()
        booking = _booking(database, guest, 1, rate=1500)
        _pay(database, booking, 1500, when=today)

        with database.session_scope() as session:
            report = report_service.build_report(session, "financial", today, today)
        assert report.report_type == "financial"
        assert report.title == "Financial Summary"
        summary = dict(report.summary)
        assert summary["Collected (Completed Payments)"] == "\u20b91,500.00"
        assert summary["Outstanding"] == "\u20b90.00"
        assert any(table.name == "Payment Methods" for table in report.tables)
        assert any(table.name == "Daily Revenue" for table in report.tables)
    finally:
        database.dispose()


def test_source_report_contents(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest = _guest(database)
        today = date.today()
        _booking(database, guest, 1)
        _booking(database, guest, 2, check_in=today, check_out=today + timedelta(days=1))

        with database.session_scope() as session:
            report = report_service.build_report(session, "sources", today, today)
        assert report.title == "Booking Sources Report"
        table = report.tables[0]
        agoda = next(row for row in table.rows if row[0] == "Agoda")
        assert agoda[1] == "2"
    finally:
        database.dispose()


def test_occupancy_report_contents(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest = _guest(database)
        today = date.today()
        _booking(database, guest, 1)

        with database.session_scope() as session:
            report = report_service.build_report(session, "occupancy", today, today)
        assert report.title == "Occupancy Report"
        summary = dict(report.summary)
        assert summary["Active Rooms"] == "11"
        assert summary["Occupied Room Nights"] == "0"
        names = [table.name for table in report.tables]
        assert names == ["By Room Type", "Room Performance"]
    finally:
        database.dispose()


def test_booking_trend_report_contents(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest = _guest(database)
        today = date.today()
        _booking(database, guest, 1)

        with database.session_scope() as session:
            report = report_service.build_report(session, "booking_trend", today, today)
        assert report.title == "Booking Trend Report"
        table = report.tables[0]
        assert len(table.rows) == 1
        assert table.rows[0][1] == "1"
    finally:
        database.dispose()


def test_build_report_rejects_unknown_type(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session, pytest.raises(ValueError):
            report_service.build_report(session, "nope", date.today(), date.today())
    finally:
        database.dispose()


def test_build_all_reports_returns_all_four(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            reports = report_service.build_all_reports(session, date.today(), date.today())
        assert sorted(r.report_type for r in reports) == sorted(
            ["financial", "sources", "occupancy", "booking_trend"]
        )
    finally:
        database.dispose()


def test_report_filename_is_deterministic(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        name = report_service.report_filename("financial", date(2026, 8, 1), date(2026, 8, 5), "csv")
        assert name == "financial_2026-08-01_2026-08-05.csv"
    finally:
        database.dispose()
