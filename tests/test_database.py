"""Tests for database initialization, settings and room configuration.

All tests use temporary SQLite databases -- the real application
database is never touched.
"""

from __future__ import annotations

from sqlalchemy import inspect, text

import pytest

from app.core.config import DEFAULT_HOTEL_SETTINGS, KEY_GST_ENABLED
from app.database.database import Database
from app.database.models import HotelSetting, Room
from app.services.room_service import (
    get_room,
    get_rooms,
    initialize_default_rooms,
)
from app.services.settings_service import (
    get_bool_setting,
    get_setting,
    get_settings,
    initialize_default_settings,
    set_setting,
)
from tests._db_support import copy_db_template

AC_ROOMS = {f"{n}" for n in range(202, 208)}
NON_AC_ROOMS = {f"{n}" for n in range(208, 213)}
EXPECTED_ROOM_COUNT = 11


def _make_database(tmp_path):  # noqa: ANN001
    database = Database(copy_db_template(tmp_path / "hotel.db"))
    return database


def test_database_file_is_created(tmp_path) -> None:  # noqa: ANN001
    database = Database(tmp_path / "hotel.db")
    database.create_all()
    database.dispose()
    assert (tmp_path / "hotel.db").exists()


def test_required_tables_exist(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        tables = set(inspect(database.engine).get_table_names())
        assert {"rooms", "hotel_settings"} <= tables
    finally:
        database.dispose()


def test_session_scope_commits_and_closes(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        with database.session_scope() as session:
            session.add(HotelSetting(key="probe", value="ok"))
        with database.new_session() as session:
            row = session.query(HotelSetting).filter(HotelSetting.key == "probe").first()
            assert row is not None
            assert row.value == "ok"
    finally:
        database.dispose()


def test_session_scope_rolls_back_on_error(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        with pytest.raises(RuntimeError):
            with database.session_scope() as session:
                session.add(HotelSetting(key="bad", value="x"))
                raise RuntimeError("boom")
        with database.new_session() as session:
            row = session.query(HotelSetting).filter(HotelSetting.key == "bad").first()
            assert row is None
    finally:
        database.dispose()


def test_sqlite_connection_works(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        with database.new_session() as session:
            session.query(Room).count()
            assert session.execute(text("SELECT 1")).scalar() == 1
    finally:
        database.dispose()


def test_hotel_settings_initialized_with_defaults(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        with database.session_scope() as session:
            settings = initialize_default_settings(session)
        for key in DEFAULT_HOTEL_SETTINGS:
            assert settings[key] == DEFAULT_HOTEL_SETTINGS[key]
    finally:
        database.dispose()


def test_gst_disabled_by_default(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        with database.session_scope() as session:
            initialize_default_settings(session)
            assert get_bool_setting(session, KEY_GST_ENABLED) is False
    finally:
        database.dispose()


def test_setting_get_set_and_overwritten(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        with database.session_scope() as session:
            initialize_default_settings(session)
            set_setting(session, "probe_key", "first")
            assert get_setting(session, "probe_key") == "first"
            set_setting(session, "probe_key", "second")
            assert get_setting(session, "probe_key") == "second"
            settings = get_settings(session)
            assert settings["probe_key"] == "second"
    finally:
        database.dispose()


def test_hotel_settings_persist_after_session(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        with database.session_scope() as session:
            set_setting(session, "phone", "9999999999")
        with database.session_scope() as session:
            assert get_setting(session, "phone") == "9999999999"
    finally:
        database.dispose()


def test_rooms_initialized_with_expected_configuration(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        with database.session_scope() as session:
            rooms = initialize_default_rooms(session)
        assert len(rooms) == EXPECTED_ROOM_COUNT
        numbers = {room.room_number for room in rooms}
        assert numbers == AC_ROOMS | NON_AC_ROOMS
        by_number = {room.room_number: room for room in rooms}
        for room_number in AC_ROOMS:
            assert by_number[room_number].room_type == "AC"
        for room_number in NON_AC_ROOMS:
            assert by_number[room_number].room_type == "Non-AC"
    finally:
        database.dispose()


def test_rooms_initialization_is_idempotent(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        with database.session_scope() as session:
            initialize_default_rooms(session)
            initialize_default_rooms(session)
            assert len(get_rooms(session)) == EXPECTED_ROOM_COUNT
    finally:
        database.dispose()


def test_get_room_returns_single_room(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        with database.session_scope() as session:
            initialize_default_rooms(session)
            room = get_room(session, "205")
            assert room is not None
            assert room.room_type == "AC"
            assert get_room(session, "999") is None
    finally:
        database.dispose()


def test_room_configuration_has_no_price(tmp_path) -> None:  # noqa: ANN001
    """Pricing must not be part of room configuration."""
    from app.core.config import DEFAULT_ROOMS

    assert all("price" not in spec and "rate" not in spec for spec in DEFAULT_ROOMS)

    database = _make_database(tmp_path)
    try:
        with database.session_scope() as session:
            initialize_default_rooms(session)
            room = get_room(session, "202")
            assert not hasattr(room, "price")
            assert not hasattr(room, "rate")
    finally:
        database.dispose()


def test_migration_rebuilds_bookings_to_nullable_guest_id(tmp_path) -> None:  # noqa: ANN001
    """An existing DB with NOT NULL guest_id is rebuilt to allow NULL."""
    from sqlalchemy import create_engine, text as sa_text

    db_path = tmp_path / "hotel.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        connection.execute(
            sa_text(
                """
                CREATE TABLE bookings (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    booking_number VARCHAR(30) NOT NULL UNIQUE,
                    guest_id INTEGER NOT NULL,
                    room_id INTEGER NOT NULL,
                    booking_source_id INTEGER NOT NULL,
                    check_in_date DATE NOT NULL,
                    check_in_time TIME,
                    check_out_date DATE NOT NULL,
                    check_out_time TIME,
                    adults INTEGER NOT NULL DEFAULT 1,
                    children INTEGER NOT NULL DEFAULT 0,
                    room_rate NUMERIC(10, 2) NOT NULL DEFAULT 0,
                    extra_person_charge NUMERIC(10, 2) NOT NULL DEFAULT 0,
                    early_check_in_charge NUMERIC(10, 2) NOT NULL DEFAULT 0,
                    late_check_out_charge NUMERIC(10, 2) NOT NULL DEFAULT 0,
                    discount NUMERIC(10, 2) NOT NULL DEFAULT 0,
                    special_notes VARCHAR(1000) NOT NULL DEFAULT '',
                    status VARCHAR(30) NOT NULL,
                    actual_check_out_at DATETIME,
                    cancelled_at DATETIME,
                    cancellation_reason VARCHAR(500) NOT NULL DEFAULT '',
                    cancelled_by VARCHAR(100) NOT NULL DEFAULT '',
                    no_show_at DATETIME,
                    no_show_reason VARCHAR(500) NOT NULL DEFAULT '',
                    deleted_at DATETIME,
                    deleted_by VARCHAR(100) NOT NULL DEFAULT '',
                    deletion_reason VARCHAR(500) NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            sa_text(
                """
                INSERT INTO bookings (
                    booking_number, guest_id, room_id, booking_source_id,
                    check_in_date, check_out_date, status, created_at, updated_at
                ) VALUES ('NCS-B-2026-000099', 7, 1, 1, '2026-08-01', '2026-08-02',
                          'reserved', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )
    engine.dispose()

    database = Database(db_path)
    try:
        database.create_all()
        column = next(
            c for c in inspect(database.engine).get_columns("bookings") if c["name"] == "guest_id"
        )
        assert column["nullable"] is True
        with database.new_session() as session:
            row = session.execute(
                text("SELECT booking_number, guest_id, status FROM bookings")
            ).fetchone()
            assert row.booking_number == "NCS-B-2026-000099"
            assert row.guest_id == 7
            assert row.status == "reserved"
            indexes = {i["name"] for i in inspect(database.engine).get_indexes("bookings")}
            assert "ix_bookings_booking_number" in indexes
            assert "ix_bookings_guest_id" in indexes
            assert "ix_bookings_status" in indexes
    finally:
        database.dispose()
