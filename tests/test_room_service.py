"""Tests for the Phase 2 room service, status history and migration safety.

All tests use temporary SQLite databases — the real hotel database is
never touched.
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import inspect

from app.core.constants import RoomStatus
from app.database.database import Database
from app.database.models import RoomStatusHistory
from app.services import room_service
from tests._db_support import copy_db_template

AC_ROOMS = {f"{n}" for n in range(202, 208)}
NON_AC_ROOMS = {f"{n}" for n in range(208, 213)}
EXPECTED_ROOM_COUNT = 11


def _make_database(tmp_path):  # noqa: ANN001
    database = Database(copy_db_template(tmp_path / "hotel.db"))
    return database


def _seed(database) -> None:  # noqa: ANN001
    with database.session_scope() as session:
        room_service.initialize_default_rooms(session)


def _rooms_by_number(database) -> dict[str, Room]:  # noqa: ANN001
    with database.new_session() as session:
        rooms = room_service.get_rooms(session)
        return {room.room_number: room for room in rooms}


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def test_initialization_creates_11_rooms(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        rooms = _rooms_by_number(database)
        assert len(rooms) == EXPECTED_ROOM_COUNT
        assert set(rooms) == AC_ROOMS | NON_AC_ROOMS
        assert {rooms[n].room_type for n in AC_ROOMS} == {"AC"}
        assert {rooms[n].room_type for n in NON_AC_ROOMS} == {"Non-AC"}
    finally:
        database.dispose()


def test_initialization_sets_all_rooms_vacant(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        assert all(room.status == RoomStatus.VACANT.value for room in _rooms_by_number(database).values())
    finally:
        database.dispose()


def test_initialization_is_idempotent(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            room_service.initialize_default_rooms(session)
            room_service.initialize_default_rooms(session)
            assert len(room_service.get_rooms(session)) == EXPECTED_ROOM_COUNT
    finally:
        database.dispose()


def test_initialization_preserves_existing_rooms(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        with database.session_scope() as session:
            room_service.initialize_default_rooms(session)
            room_service.update_room_status(session, "202", RoomStatus.OCCUPIED)
        _seed(database)  # re-run initialization
        rooms = _rooms_by_number(database)
        assert len(rooms) == EXPECTED_ROOM_COUNT
        assert rooms["202"].status == RoomStatus.OCCUPIED.value  # not reset
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def test_get_all_rooms(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            assert len(room_service.get_all_rooms(session)) == EXPECTED_ROOM_COUNT
    finally:
        database.dispose()


def test_get_room_by_id(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        rooms = _rooms_by_number(database)
        room_202 = rooms["202"]
        with database.session_scope() as session:
            fetched = room_service.get_room(session, room_202.id)
            assert fetched is not None
            assert fetched.room_number == "202"
    finally:
        database.dispose()


def test_get_room_by_number(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            room = room_service.get_room_by_number(session, "205")
            assert room is not None
            assert room.room_type == "AC"
            assert room_service.get_room_by_number(session, "999") is None
    finally:
        database.dispose()


def test_get_room_accepts_room_number_string(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            assert room_service.get_room(session, "205").room_number == "205"
    finally:
        database.dispose()


def test_get_room_missing_returns_none(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            assert room_service.get_room(session, 99999) is None
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Status updates
# ---------------------------------------------------------------------------

def test_update_room_status(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            room = room_service.update_room_status(session, "202", RoomStatus.OCCUPIED)
            assert room.status == RoomStatus.OCCUPIED.value
        with database.session_scope() as session:
            assert room_service.get_room_by_number(session, "202").status == RoomStatus.OCCUPIED.value
    finally:
        database.dispose()


def test_set_status_helpers(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            room_service.set_room_occupied(session, "203")
            room_service.set_room_reserved(session, "205")
            room_service.set_room_vacant(session, "207")
        rooms = _rooms_by_number(database)
        assert rooms["203"].status == "occupied"
        assert rooms["205"].status == "reserved"
        assert rooms["207"].status == "vacant"
    finally:
        database.dispose()


def test_invalid_status_raises_value_error(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with pytest.raises(ValueError):
            with database.session_scope() as session:
                room_service.update_room_status(session, "202", "not-a-status")
    finally:
        database.dispose()


def test_is_allowed_transition(tmp_path) -> None:  # noqa: ANN001
    assert room_service.is_allowed_transition("vacant", "occupied")
    assert room_service.is_allowed_transition(RoomStatus.VACANT, RoomStatus.RESERVED)
    assert not room_service.is_allowed_transition("bogus", "occupied")


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

def test_room_notes_roundtrip(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            room_service.update_room_notes(session, "208", "AC remote needs replacement")
        with database.session_scope() as session:
            room = room_service.get_room_by_number(session, "208")
            assert room.notes == "AC remote needs replacement"
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Active / inactive
# ---------------------------------------------------------------------------

def test_deactivated_room_excluded_from_dashboard(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            room_service.set_room_active(session, "209", False)
        with database.session_scope() as session:
            active = {room.room_number for room in room_service.get_all_rooms(session)}
            all_rooms = {room.room_number for room in room_service.get_all_rooms(session, include_inactive=True)}
            assert "209" not in active
            assert "209" in all_rooms
            assert len(all_rooms) == EXPECTED_ROOM_COUNT
        with database.session_scope() as session:
            room_service.set_room_active(session, "209", True)
        with database.session_scope() as session:
            assert "209" in {room.room_number for room in room_service.get_all_rooms(session)}
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Status history
# ---------------------------------------------------------------------------

def test_status_change_records_history(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        room_id = _rooms_by_number(database)["202"].id
        with database.session_scope() as session:
            room_service.update_room_status(session, "202", RoomStatus.OCCUPIED, note="walk-in")
        with database.session_scope() as session:
            history = room_service.get_status_history(session, room_id)
            assert len(history) == 1
            entry = history[0]
            assert entry.old_status == "vacant"
            assert entry.new_status == "occupied"
            assert entry.changed_by == "Reception"
            assert entry.note == "walk-in"
            assert entry.room_id == room_id
    finally:
        database.dispose()


def test_status_history_records_multiple_changes(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        room_id = _rooms_by_number(database)["203"].id
        with database.session_scope() as session:
            room_service.set_room_occupied(session, "203")
            room_service.set_room_reserved(session, "203")
            room_service.set_room_vacant(session, "203")
        with database.session_scope() as session:
            history = room_service.get_status_history(session, room_id)
            assert len(history) == 3
            assert [h.new_status for h in history] == ["vacant", "reserved", "occupied"]
    finally:
        database.dispose()


def test_same_status_does_not_record_history(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        room_id = _rooms_by_number(database)["204"].id
        with database.session_scope() as session:
            room_service.update_room_status(session, "204", RoomStatus.VACANT)
        with database.session_scope() as session:
            assert room_service.get_status_history(session, room_id) == []
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Counts / summary (dashboard data layer)
# ---------------------------------------------------------------------------

def test_room_status_counts_reflect_changes(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            room_service.set_room_occupied(session, "202")
            room_service.set_room_occupied(session, "203")
            room_service.set_room_reserved(session, "205")
        with database.session_scope() as session:
            counts = room_service.get_room_status_counts(session)
            assert counts["total"] == EXPECTED_ROOM_COUNT
            assert counts["vacant"] == EXPECTED_ROOM_COUNT - 3
            assert counts["occupied"] == 2
            assert counts["reserved"] == 1
    finally:
        database.dispose()


def test_counts_exclude_inactive_rooms(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            room_service.set_room_active(session, "210", False)
            counts = room_service.get_room_status_counts(session)
            assert counts["total"] == EXPECTED_ROOM_COUNT - 1
    finally:
        database.dispose()


def test_get_room_summary_matches_counts(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            assert room_service.get_room_summary(session) == room_service.get_room_status_counts(session)
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Migration safety
# ---------------------------------------------------------------------------

def test_migration_upgrades_legacy_phase1_database(tmp_path) -> None:  # noqa: ANN001
    legacy_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(legacy_path)
    connection.executescript(
        """
        CREATE TABLE hotel_settings (id INTEGER PRIMARY KEY AUTOINCREMENT, key VARCHAR(100) UNIQUE, value VARCHAR(2000));
        CREATE TABLE rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_number VARCHAR(10) UNIQUE,
            room_type VARCHAR(20),
            status VARCHAR(20) DEFAULT 'vacant',
            floor VARCHAR(20) DEFAULT '',
            notes VARCHAR(500) DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1
        );
        INSERT INTO rooms (room_number, room_type, status) VALUES ('202', 'AC', 'vacant');
        INSERT INTO rooms (room_number, room_type, status) VALUES ('208', 'Non-AC', 'occupied');
        """
    )
    connection.commit()
    connection.close()

    database = Database(legacy_path)
    database.create_all()
    try:
        columns = {column["name"] for column in inspect(database.engine).get_columns("rooms")}
        assert {"created_at", "updated_at"} <= columns

        tables = set(inspect(database.engine).get_table_names())
        assert "room_status_history" in tables

        with database.session_scope() as session:
            rooms = {room.room_number: room for room in room_service.get_rooms(session)}
            assert len(rooms) == 2
            assert rooms["202"].status == "vacant"
            assert rooms["208"].status == "occupied"
            assert rooms["202"].created_at is not None
            assert rooms["202"].updated_at is not None

            # Re-running initialization must not duplicate existing rooms.
            room_service.initialize_default_rooms(session)
            assert len(room_service.get_rooms(session)) == EXPECTED_ROOM_COUNT
    finally:
        database.dispose()


def test_migration_is_idempotent(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        database.create_all()
        database.create_all()
        with database.session_scope() as session:
            assert len(room_service.get_rooms(session)) == EXPECTED_ROOM_COUNT
            assert session.query(RoomStatusHistory).count() == 0
    finally:
        database.dispose()
