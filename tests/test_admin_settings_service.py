"""Tests for the Admin Settings service: hotel info validation, website
validation, logo management and booking-source management.

All tests use temporary SQLite databases and the temp ``NCS_APP_DATA``
directory for logo file operations.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.database.database import Database
from app.services import admin_settings_service, settings_service
from app.services.booking_source_service import initialize_default_sources
from tests._db_support import copy_db_template


def _make_database(tmp_path):  # noqa: ANN001
    database = Database(copy_db_template(tmp_path / "hotel.db"))
    return database


def _seed(database) -> None:  # noqa: ANN001
    with database.session_scope() as session:
        settings_service.initialize_default_settings(session)
        initialize_default_sources(session)


# ---------------------------------------------------------------------------
# Hotel info
# ---------------------------------------------------------------------------

def test_update_hotel_info_saves_values(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            admin_settings_service.update_hotel_info(
                session,
                name="My Hotel",
                description="Nice place",
                address="Somewhere",
                phone="12345",
                email="a@b.com",
                website="example.com",
            )
        with database.session_scope() as session:
            hotel = settings_service.get_hotel_settings(session)
        assert hotel["hotel_name"] == "My Hotel"
        assert hotel["hotel_description"] == "Nice place"
        assert hotel["hotel_address"] == "Somewhere"
        assert hotel["hotel_phone"] == "12345"
        assert hotel["hotel_email"] == "a@b.com"
        assert hotel["hotel_website"] == "example.com"
    finally:
        database.dispose()


def test_update_hotel_info_requires_name(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            with pytest.raises(admin_settings_service.ValidationError):
                admin_settings_service.update_hotel_info(
                    session, name="", description="", address="", phone="", email="", website=""
                )
    finally:
        database.dispose()


def test_validate_website(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        assert admin_settings_service.validate_website("") == ""
        assert admin_settings_service.validate_website("example.com") == "example.com"
        assert admin_settings_service.validate_website("https://www.example.com") == "https://www.example.com"
        with pytest.raises(admin_settings_service.ValidationError):
            admin_settings_service.validate_website("not a url")
        with pytest.raises(admin_settings_service.ValidationError):
            admin_settings_service.validate_website("ht!tp://broken")
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Logo
# ---------------------------------------------------------------------------

def _write_png(path: Path) -> None:
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)


def test_upload_logo_copies_and_sets_setting(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    import app.core.paths

    monkeypatch.setenv("NCS_APP_DATA", str(tmp_path / "appdata"))
    source = tmp_path / "logo.png"
    _write_png(source)

    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            stored = admin_settings_service.upload_logo(session, source)
        assert Path(stored).exists()
        assert stored != str(source)
        with database.session_scope() as session:
            assert settings_service.get_setting(session, "logo_path") == stored
    finally:
        database.dispose()


def test_upload_logo_rejects_non_image(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        bad = tmp_path / "notes.txt"
        bad.write_text("hello")
        with database.session_scope() as session:
            with pytest.raises(admin_settings_service.ValidationError):
                admin_settings_service.upload_logo(session, bad)
    finally:
        database.dispose()


def test_remove_logo_clears_setting(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    import app.core.paths

    monkeypatch.setenv("NCS_APP_DATA", str(tmp_path / "appdata"))
    source = tmp_path / "logo.png"
    _write_png(source)

    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            stored = admin_settings_service.upload_logo(session, source)
        assert Path(stored).exists()
        with database.session_scope() as session:
            admin_settings_service.remove_logo(session)
        with database.session_scope() as session:
            assert settings_service.get_setting(session, "logo_path") == ""
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Booking sources
# ---------------------------------------------------------------------------

def test_add_and_disable_source(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            source = admin_settings_service.add_booking_source(session, "Google Ads")
            assert source.is_active is True
            admin_settings_service.set_booking_source_active(session, source.id, active=False)
            disabled = admin_settings_service.get_booking_sources(session)
            assert any(s.id == source.id and not s.is_active for s in disabled)
            admin_settings_service.set_booking_source_active(session, source.id, active=True)
            enabled = admin_settings_service.get_booking_sources(session)
            assert any(s.id == source.id and s.is_active for s in enabled)
    finally:
        database.dispose()


def test_duplicate_source_raises(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            admin_settings_service.add_booking_source(session, "Instagram")
            with pytest.raises(ValueError):
                admin_settings_service.add_booking_source(session, "Instagram")
            with pytest.raises(ValueError):
                admin_settings_service.add_booking_source(session, "   ")
    finally:
        database.dispose()


def test_reactivating_disabled_source_reuses_row(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            first = admin_settings_service.add_booking_source(session, "Facebook")
            admin_settings_service.set_booking_source_active(session, first.id, active=False)
        with database.session_scope() as session:
            again = admin_settings_service.add_booking_source(session, "Facebook")
        assert again.id == first.id
        assert again.is_active is True
    finally:
        database.dispose()
